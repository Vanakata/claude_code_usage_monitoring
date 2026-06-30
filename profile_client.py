#!/usr/bin/env python
"""Claude OAuth profile — email + organization name.

Чете OAuth token-а от ~/.claude/.credentials.json и вика недокументирания
профил endpoint:
    GET https://api.anthropic.com/api/oauth/profile
    headers: Authorization: Bearer <token>, anthropic-beta: oauth-2025-04-20

Reverse-engineer-нат (същия pattern като /api/oauth/usage). Може да се счупи
на Claude Code ъпдейт; ползвателят го третира fail-soft.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from usage_client import CREDENTIALS_PATH, OAUTH_BETA, UsageError, _read_token, refresh_token

PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"


class ProfileError(RuntimeError):
    """Липсва token, 401/мрежа, или ендпойнтът е счупен."""


@dataclass
class Profile:
    email: str
    full_name: str
    org_name: str


def _get_profile(token: str) -> dict:
    req = urllib.request.Request(
        PROFILE_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_profile() -> Profile:
    """Дърпа email + org name. На 401 → refresh → retry."""
    try:
        data = _get_profile(_read_token())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            token = refresh_token()
            try:
                data = _get_profile(token)
            except urllib.error.HTTPError as exc2:
                raise ProfileError(f"HTTP {exc2.code} от /api/oauth/profile (след refresh)") from exc2
            except urllib.error.URLError as exc2:
                raise ProfileError(f"мрежова грешка (след refresh): {exc2.reason}") from exc2
        else:
            raise ProfileError(f"HTTP {exc.code} от /api/oauth/profile") from exc
    except urllib.error.URLError as exc:
        raise ProfileError(f"мрежова грешка: {exc.reason}") from exc
    except UsageError as exc:
        raise ProfileError(str(exc)) from exc

    acc = data.get("account") or {}
    org = data.get("organization") or {}
    return Profile(
        email=acc.get("email") or "",
        full_name=acc.get("full_name") or "",
        org_name=org.get("name") or "",
    )


# --- mtime-based cache (за да реагираме на `claude login` без рестарт) ---
# Викаме fetch_profile() само когато credentials.json mtime се е променил —
# така един и същ профил не се дърпа по мрежата на всеки tick, но смяна на
# акаунт (с `claude login` -> пренаписва credentials) се хваща веднага.
_cache: Optional[Profile] = None
_cache_mtime: float = 0.0


def get_profile() -> Optional[Profile]:
    """Връща profile; refresh-ва САМО ако credentials.json е променен.

    Fail-soft: при ProfileError връща предишния кеширан profile (или None ако
    още няма успешно дърпан). mtime не се update-ва при грешка → следващият
    tick ще опита пак.
    """
    global _cache, _cache_mtime
    try:
        mt = os.path.getmtime(CREDENTIALS_PATH)
    except OSError:
        return _cache  # няма файл -> върни каквото имаме (или None)
    if mt == _cache_mtime and _cache is not None:
        return _cache
    try:
        _cache = fetch_profile()
        _cache_mtime = mt
    except ProfileError:
        pass  # запазваме стария кеш; следващият tick ще опита пак
    return _cache


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        p = fetch_profile()
    except ProfileError as exc:
        print(f"[profile] ГРЕШКА: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"email: {p.email}")
    print(f"name:  {p.full_name}")
    print(f"org:   {p.org_name}")
