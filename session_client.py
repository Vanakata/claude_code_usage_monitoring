#!/usr/bin/env python
"""Data layer за context tokens на активната Claude Code сесия.

Намира най-recently modified jsonl в ~/.claude/projects/**, парсва последния
assistant reply и извлича usage → context input tokens
(input_tokens + cache_creation_input_tokens + cache_read_input_tokens).
Това е точно каквото `/context` показва (context прозорецът за следващия prompt).

Ако mtime > STALE_AFTER_SEC → връща None (не е активна сесия → на дисплея "--").
Threshold-ите (WARN / LIMIT) са в input tokens и параметризирани през env.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

HOME = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
PROJECTS_DIR = HOME / ".claude" / "projects"

# По-стара от това = "мълчи" (не активна сесия за kill-restart сигнала).
STALE_AFTER_SEC = int(os.environ.get("CLAUDE_USAGE_SESSION_STALE", "300"))  # 5 min
# 100k = праг за kill-and-restart (NDC "How I Tamed Claude"). Виж CLAUDE.md.
CTX_LIMIT = int(os.environ.get("CLAUDE_USAGE_CTX_LIMIT", "100000"))
# 60k = warn: активно време е да мислиш за приключване на сесията.
CTX_WARN = int(os.environ.get("CLAUDE_USAGE_CTX_WARN", "60000"))

# Последният assistant reply обикновено е <5KB; 64KB tail е с голям запас.
_TAIL_BYTES = 64 * 1024


@dataclass
class SessionCtx:
    tokens: int              # input tokens за следващия prompt = /context
    project_slug: str        # jsonl parent dir (Claude Code slug на репото)
    session_id: str          # jsonl uuid
    updated_at: datetime     # mtime на jsonl-а (последна активност)
    model: Optional[str]     # модел на последния reply, ако имаме


def _find_latest_jsonl() -> Optional[Path]:
    """Най-новия jsonl файл в ~/.claude/projects/**/*.jsonl (по mtime)."""
    if not PROJECTS_DIR.is_dir():
        return None
    latest: Optional[Path] = None
    latest_mtime = 0.0
    for f in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            m = f.stat().st_mtime
        except OSError:
            continue
        if m > latest_mtime:
            latest_mtime = m
            latest = f
    return latest


def _tail_lines(path: Path, max_bytes: int = _TAIL_BYTES) -> List[str]:
    """Последните ~max_bytes байта → комплетни редове (без съсечен префикс)."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    start = max(0, size - max_bytes)
    with path.open("rb") as fh:
        fh.seek(start)
        data = fh.read()
    # ако сме зачукнали среден ред — изхвърляме първия непълен
    if start > 0:
        i = data.find(b"\n")
        if i >= 0:
            data = data[i + 1:]
    return [ln.decode("utf-8", errors="replace") for ln in data.splitlines() if ln.strip()]


def _extract_usage(line: str) -> Optional[Tuple[int, Optional[str]]]:
    """От JSONL ред → (context_input_tokens, model), ако е assistant reply с usage."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if obj.get("type") != "assistant":
        return None
    msg = obj.get("message") or {}
    usage = msg.get("usage") or {}
    if not usage:
        return None
    total = (int(usage.get("input_tokens", 0))
             + int(usage.get("cache_creation_input_tokens", 0))
             + int(usage.get("cache_read_input_tokens", 0)))
    return total, msg.get("model")


def _is_compact_boundary(line: str) -> bool:
    """True ако редът е /compact граница (summary) → контекстът е ресетнат.

    Всичко ПРЕДИ такъв ред е от старата сесия. Claude Code маркира summary-то
    с `isCompactSummary: true` (валидно и за ръчен `/compact`, и за auto-compact).
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False
    return obj.get("isCompactSummary") is True


def fetch() -> Optional[SessionCtx]:
    """Контекст на най-recently активния Claude Code session. None ако stale.

    Обхожда опашката назад и връща usage-а на **най-новия assistant reply**.
    Ако удари `/compact` граница ПРЕДИ такъв reply → контекстът е току-що ресетнат,
    а единственият по-стар assistant reply е пред-compact пикът (напр. 250K). В тоя
    прозорец (между /compact и първия нов reply) рапортуваме 0, иначе дисплеят виси
    на стария връх и "не се занулява" след compact.
    """
    latest = _find_latest_jsonl()
    if latest is None:
        return None
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        return None
    updated_at = datetime.fromtimestamp(mtime, timezone.utc)
    if (datetime.now(timezone.utc) - updated_at).total_seconds() > STALE_AFTER_SEC:
        return None
    compacted = False
    for line in reversed(_tail_lines(latest)):
        if not compacted and _is_compact_boundary(line):
            # Прекрачихме compact граница без да сме намерили нов reply → reset.
            # Продължаваме само за да вземем модела (за хедъра) от стария reply.
            compacted = True
            continue
        parsed = _extract_usage(line)
        if parsed is None:
            continue
        tokens, model = parsed
        return SessionCtx(
            tokens=0 if compacted else tokens,
            project_slug=latest.parent.name,
            session_id=latest.stem,
            updated_at=updated_at,
            model=model,
        )
    if compacted:
        # compact граница, но нямаме дори стар reply в опашката за модела → пак reset
        return SessionCtx(0, latest.parent.name, latest.stem, updated_at, None)
    return None


def status_for(tokens: int) -> str:
    """'safe' | 'warn' | 'critical' bucket за цвят / badge."""
    if tokens >= CTX_LIMIT:
        return "critical"
    if tokens >= CTX_WARN:
        return "warn"
    return "safe"


def display_slug(slug: str) -> str:
    """Grubby Claude-Code slug → четимо име. Пример:

    'D--Projects-personal-projects-claude-code-usage-monitoring'
       → 'code-usage-monitoring'
    """
    # ~/.claude/projects конвенция: '--' раздели path сегментите (drive : path).
    # Взимаме последния фрагмент (същинското име на репото), после ако е дълго —
    # клипваме последните няколко '-' сегмента.
    parts = slug.split("--")
    last = parts[-1] if parts else slug
    segs = last.split("-")
    if len(segs) > 2:
        return "-".join(segs[-2:])
    return last


def _cli() -> int:
    ctx = fetch()
    if ctx is None:
        print("(no active session in last 5 min)")
        return 1
    kb = ctx.tokens / 1000
    print(f"CTX: {kb:.1f}K tokens  ({status_for(ctx.tokens)})")
    print(f"session: {ctx.session_id}")
    print(f"project: {ctx.project_slug} → {display_slug(ctx.project_slug)}")
    print(f"model:   {ctx.model or '--'}")
    print(f"updated: {ctx.updated_at.astimezone():%Y-%m-%d %H:%M:%S}")
    return 0


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(_cli())
