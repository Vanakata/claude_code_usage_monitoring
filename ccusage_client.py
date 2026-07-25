#!/usr/bin/env python
"""ccusage data layer — вади реални Claude usage метрики през `ccusage --json`.

Това е САМО data слоят: subprocess към ccusage, парс в dataclass-ове.
Никакъв дисплей тук — render.py чете Snapshot-а директно.

Архитектура:
    ccusage blocks/daily --json  ->  parse  ->  Snapshot
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# 5-часовият прозорец на Claude billing блоковете.
BLOCK_WINDOW = timedelta(hours=5)


class CcusageError(RuntimeError):
    """ccusage липсва, гръмна или върна боклук."""


# --------------------------------------------------------------------------- #
# subprocess + raw JSON
# --------------------------------------------------------------------------- #
def _run_ccusage(*args: str) -> dict:
    """Пуска `ccusage <args> --json` и връща парснатия JSON."""
    exe = shutil.which("ccusage")
    if exe is None:
        raise CcusageError(
            "ccusage не е намерен в PATH. Инсталирай го: npm i -g ccusage"
        )

    cmd = [exe, *args, "--json"]
    try:
        # На Windows ccusage е .cmd shim -> нужен е shell за изпълнение.
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=(os.name == "nt"),
            timeout=30,
        )
    except FileNotFoundError as exc:  # pragma: no cover - покрито от which() горе
        raise CcusageError(f"ccusage не може да се изпълни: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CcusageError("ccusage не отговори за 30s") from exc

    if proc.returncode != 0:
        raise CcusageError(
            f"ccusage {' '.join(args)} върна код {proc.returncode}: "
            f"{proc.stderr.strip()[:200]}"
        )

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CcusageError(f"невалиден JSON от ccusage: {exc}") from exc


# --------------------------------------------------------------------------- #
# dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class ActiveBlock:
    """Активният 5-часов billing блок."""
    cost_usd: float
    total_tokens: int
    elapsed_pct: float          # % изтекло от 5h прозореца (по време)
    remaining_min: int          # минути до края на прозореца
    projected_cost: Optional[float]      # ccusage прогноза за края на блока
    projected_tokens: Optional[int]
    burn_cost_per_hour: Optional[float]
    models: List[str] = field(default_factory=list)


@dataclass
class DailySnapshot:
    today_cost: float
    today_tokens: int
    week_cost: float            # сума последни 7 дни (вкл. днес)
    week_tokens: int


@dataclass
class Snapshot:
    has_active_block: bool
    block: Optional[ActiveBlock]
    daily: DailySnapshot
    generated_at: datetime


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def _parse_iso(ts: str) -> datetime:
    """ISO timestamp с 'Z' -> timezone-aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _parse_active_block(blocks_json: dict, now: datetime) -> Optional[ActiveBlock]:
    blocks = blocks_json.get("blocks", [])
    active = next(
        (b for b in blocks if b.get("isActive") and not b.get("isGap")), None
    )
    if active is None:
        return None

    start = _parse_iso(active["startTime"])
    end = _parse_iso(active["endTime"])
    window = (end - start) or BLOCK_WINDOW
    elapsed_pct = max(0.0, min(100.0, (now - start) / window * 100.0))
    remaining_min = max(0, int((end - now).total_seconds() // 60))

    projection = active.get("projection") or {}
    burn = active.get("burnRate") or {}

    return ActiveBlock(
        cost_usd=float(active.get("costUSD", 0.0)),
        total_tokens=int(active.get("totalTokens", 0)),
        elapsed_pct=elapsed_pct,
        remaining_min=remaining_min,
        projected_cost=projection.get("totalCost"),
        projected_tokens=projection.get("totalTokens"),
        burn_cost_per_hour=burn.get("costPerHour"),
        models=list(active.get("models", [])),
    )


def _parse_daily(daily_json: dict, now: datetime) -> DailySnapshot:
    days = daily_json.get("daily", [])
    today_str = now.astimezone().strftime("%Y-%m-%d")

    today = next((d for d in days if d.get("period") == today_str), None)
    today_cost = float(today.get("totalCost", 0.0)) if today else 0.0
    today_tokens = int(today.get("totalTokens", 0)) if today else 0

    # Седмица = последните 7 календарни дни (период >= днес - 6).
    week_start = (now.astimezone().date() - timedelta(days=6)).strftime("%Y-%m-%d")
    week = [d for d in days if d.get("period", "") >= week_start]
    week_cost = sum(float(d.get("totalCost", 0.0)) for d in week)
    week_tokens = sum(int(d.get("totalTokens", 0)) for d in week)

    return DailySnapshot(
        today_cost=today_cost,
        today_tokens=today_tokens,
        week_cost=week_cost,
        week_tokens=week_tokens,
    )


def fetch_snapshot() -> Snapshot:
    """Дърпа пресни данни от ccusage и ги парсва (без кеш)."""
    now = datetime.now(timezone.utc)
    blocks_json = _run_ccusage("blocks")
    daily_json = _run_ccusage("daily")

    block = _parse_active_block(blocks_json, now)
    daily = _parse_daily(daily_json, now)
    return Snapshot(
        has_active_block=block is not None,
        block=block,
        daily=daily,
        generated_at=now,
    )


# --------------------------------------------------------------------------- #
# helpers за форматиране
# --------------------------------------------------------------------------- #
def format_tokens(n: int) -> str:
    """1_234_567 -> '1.2M', 12_345 -> '12.3K'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# --------------------------------------------------------------------------- #
# верификация без дисплей
# --------------------------------------------------------------------------- #
def _print_snapshot() -> int:
    try:
        snap = fetch_snapshot()
    except CcusageError as exc:
        print(f"[ccusage] ГРЕШКА: {exc}", file=sys.stderr)
        return 1

    print("=== Claude usage snapshot ===")
    print(f"генериран: {snap.generated_at.astimezone():%Y-%m-%d %H:%M:%S}")
    if snap.block:
        b = snap.block
        print("\n5h блок (активен):")
        print(f"  cost          : ${b.cost_usd:.2f}")
        print(f"  tokens        : {format_tokens(b.total_tokens)} ({b.total_tokens})")
        print(f"  прозорец      : {b.elapsed_pct:.0f}% изтекъл, {b.remaining_min} мин остават")
        if b.projected_cost is not None:
            print(f"  прогноза cost : ${b.projected_cost:.2f}")
        if b.burn_cost_per_hour is not None:
            print(f"  burn rate     : ${b.burn_cost_per_hour:.2f}/час")
        print(f"  модели        : {', '.join(b.models) or '-'}")
    else:
        print("\n5h блок: НЯМА активен (между сесии)")

    d = snap.daily
    print("\nДнес:")
    print(f"  cost   : ${d.today_cost:.2f}")
    print(f"  tokens : {format_tokens(d.today_tokens)}")
    print("\nСедмица (7 дни):")
    print(f"  cost   : ${d.week_cost:.2f}")
    print(f"  tokens : {format_tokens(d.week_tokens)}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(_print_snapshot())
