#!/usr/bin/env python
"""Реалните Claude /usage rate-limit данни (5h + weekly utilization + reset).

Чете OAuth token-а от ~/.claude/.credentials.json и вика същия endpoint, който
Claude Code `/usage` дърпа:
    GET https://api.anthropic.com/api/oauth/usage
    headers: Authorization: Bearer <token>, anthropic-beta: oauth-2025-04-20

Това е недокументиран endpoint (reverse-engineer-нат от Claude Code extension.js,
v2.1.183). Може да се счупи на Claude Code ъпдейт. Дава точните % като /usage —
за разлика от ccusage approximation, защото лимитът тежи по модел вътрешно.

Response shape (релевантното):
    {"five_hour": {"utilization": 21.0, "resets_at": "...Z"},
     "seven_day": {"utilization": 19.0, "resets_at": "...Z"}, ...}
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"


class UsageError(RuntimeError):
    """Липсва token, 401/мрежа, или невалиден отговор."""


@dataclass
class UsageWindow:
    utilization: float          # 0-100 %
    resets_at: Optional[datetime]

    def remaining(self, now: Optional[datetime] = None):
        """timedelta до reset (None ако няма resets_at)."""
        if self.resets_at is None:
            return None
        return self.resets_at - (now or datetime.now(timezone.utc))


@dataclass
class Usage:
    five_hour: UsageWindow
    seven_day: UsageWindow
    generated_at: datetime


def _read_token() -> str:
    try:
        cred = json.load(open(CREDENTIALS_PATH, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"не мога да чета {CREDENTIALS_PATH}: {exc}") from exc
    tok = (cred.get("claudeAiOauth") or {}).get("accessToken")
    if not tok:
        raise UsageError("няма claudeAiOauth.accessToken в credentials (логнат ли си в Claude?)")
    return tok


def _parse_window(obj: Optional[dict]) -> UsageWindow:
    obj = obj or {}
    util = obj.get("utilization")
    resets = obj.get("resets_at")
    dt = None
    if resets:
        try:
            dt = datetime.fromisoformat(resets.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    return UsageWindow(utilization=float(util) if util is not None else 0.0, resets_at=dt)


def fetch_usage() -> Usage:
    """Дърпа реалните rate-limit данни (без кеш)."""
    token = _read_token()
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise UsageError("401 — token изтекъл (Claude Code refresh-ва го; пусни Claude)") from exc
        raise UsageError(f"HTTP {exc.code} от /api/oauth/usage") from exc
    except urllib.error.URLError as exc:
        raise UsageError(f"мрежова грешка: {exc.reason}") from exc

    return Usage(
        five_hour=_parse_window(data.get("five_hour")),
        seven_day=_parse_window(data.get("seven_day")),
        generated_at=datetime.now(timezone.utc),
    )


def _fmt_delta(td) -> str:
    """timedelta -> '4h44m' или '5d 12h' за по-дълги."""
    if td is None:
        return "--"
    secs = max(0, int(td.total_seconds()))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h"
    return f"{h}h{m:02d}m"


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        u = fetch_usage()
    except UsageError as exc:
        print(f"[usage] ГРЕШКА: {exc}", file=sys.stderr)
        sys.exit(1)
    print("=== Claude /usage (реално) ===")
    print(f"5h:   {u.five_hour.utilization:>3.0f}%   resets in {_fmt_delta(u.five_hour.remaining())}")
    print(f"week: {u.seven_day.utilization:>3.0f}%   resets in {_fmt_delta(u.seven_day.remaining())}")
