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

import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from usage_client import (CREDENTIALS_PATH, OAUTH_BETA, USER_AGENT, UsageError,
                           _read_token, refresh_or_adopt)

PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
# Акаунтът, който Claude Code ПОКАЗВА като активен (oauthAccount). Не е източник
# на auth — token-ът в credentials може да е от друг акаунт (видяно: oauthAccount
# = личен gmail, token = A1 team) и тогава екранът тихо показва чужди проценти.
CLAUDE_JSON_PATH = os.path.expanduser("~/.claude.json")


class ProfileError(RuntimeError):
    """Липсва token, 401/мрежа, или ендпойнтът е счупен."""


@dataclass
class Profile:
    email: str
    full_name: str
    org_name: str
    account_uuid: str = ""
    # email-ът от ~/.claude.json, ако е РАЗЛИЧЕН акаунт от token-а; "" = съвпадат/няма данни
    mismatch_email: str = ""


def _get_profile(token: str) -> dict:
    req = urllib.request.Request(
        PROFILE_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA,
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_profile() -> Profile:
    """Дърпа email + org name. На 401 → refresh → retry."""
    stale = _read_token()
    try:
        data = _get_profile(stale)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            # refresh_or_adopt() може да хвърли UsageError (напр. HTTP 403 при invalid
            # refresh) — превеждаме към ProfileError, за да не bubble-не суров
            # UsageError към caller-а, който очаква fail-soft върху ProfileError.
            try:
                token = refresh_or_adopt(stale)
            except UsageError as exc_r:
                raise ProfileError(str(exc_r)) from exc_r
            try:
                data = _get_profile(token)
            except urllib.error.HTTPError as exc2:
                raise ProfileError(f"HTTP {exc2.code} от /api/oauth/profile (след refresh)") from exc2
            except urllib.error.URLError as exc2:
                raise ProfileError(f"мрежова грешка (след refresh): {exc2.reason}") from exc2
            except (http.client.HTTPException, OSError) as exc2:
                raise ProfileError(f"мрежова грешка (след refresh): {type(exc2).__name__}: {exc2}") from exc2
        else:
            raise ProfileError(f"HTTP {exc.code} от /api/oauth/profile") from exc
    except urllib.error.URLError as exc:
        raise ProfileError(f"мрежова грешка: {exc.reason}") from exc
    except (http.client.HTTPException, OSError) as exc:
        # RemoteDisconnected и подобни: unwrapped от urllib -> хванато за fail-soft.
        raise ProfileError(f"мрежова грешка: {type(exc).__name__}: {exc}") from exc
    except UsageError as exc:
        raise ProfileError(str(exc)) from exc

    acc = data.get("account") or {}
    org = data.get("organization") or {}
    return Profile(
        email=acc.get("email") or "",
        full_name=acc.get("full_name") or "",
        org_name=org.get("name") or "",
        account_uuid=acc.get("uuid") or "",
    )


def active_account() -> tuple[str, str]:
    """(accountUuid, email) от ~/.claude.json → oauthAccount; ("", "") при липса."""
    try:
        with open(CLAUDE_JSON_PATH, encoding="utf-8") as f:
            acc = json.load(f).get("oauthAccount") or {}
    except (OSError, ValueError):
        return "", ""
    return acc.get("accountUuid") or "", acc.get("emailAddress") or ""


# --- mtime-based cache (за да реагираме на `claude login` без рестарт) ---
# Викаме fetch_profile() само когато credentials.json mtime се е променил —
# така един и същ профил не се дърпа по мрежата на всеки tick, но смяна на
# акаунт (с `claude login` -> пренаписва credentials) се хваща веднага.
_cache: Optional[Profile] = None
_cache_mtime: float = 0.0
_cj_mtime: float = 0.0  # ~/.claude.json mtime при последната mismatch проверка
_warned: str = ""       # последното логнато mismatch състояние (лог само при промяна)


def _check_mismatch(p: Profile) -> None:
    """Сверява token акаунта с oauthAccount; логва само при смяна на състоянието."""
    global _warned
    uuid, email = active_account()
    bad = bool(uuid and p.account_uuid and uuid != p.account_uuid)
    p.mismatch_email = email if bad else ""
    state = f"{p.account_uuid}|{uuid}" if bad else ""
    if state != _warned:
        if bad:
            print(f"[profile] ВНИМАНИЕ: token-ът е на {p.email}, а Claude Code показва "
                  f"{email} като активен — екранът е за {p.email}. Оправя се с /login.",
                  file=sys.stderr)
        elif _warned:
            print(f"[profile] акаунтите пак съвпадат ({p.email})", file=sys.stderr)
        _warned = state


def get_profile() -> Optional[Profile]:
    """Връща profile; refresh-ва САМО ако credentials.json е променен.

    Fail-soft: при ProfileError връща предишния кеширан profile (или None ако
    още няма успешно дърпан). mtime не се update-ва при грешка → следващият
    tick ще опита пак.
    """
    global _cache, _cache_mtime, _cj_mtime
    try:
        mt = os.path.getmtime(CREDENTIALS_PATH)
    except OSError:
        return _cache  # няма файл -> върни каквото имаме (или None)
    try:
        cj = os.path.getmtime(CLAUDE_JSON_PATH)
    except OSError:
        cj = 0.0
    if mt == _cache_mtime and cj == _cj_mtime and _cache is not None:
        return _cache
    if mt != _cache_mtime or _cache is None:
        try:
            _cache = fetch_profile()
            _cache_mtime = mt
        except ProfileError:
            pass  # запазваме стария кеш; следващият tick ще опита пак
    if _cache is not None:
        # ~/.claude.json се пише постоянно (history, кешове) -> само локално четене,
        # без HTTP; profile-ът се пре-дърпва единствено при смяна на credentials
        _check_mismatch(_cache)
        _cj_mtime = cj
    return _cache


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
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
    _check_mismatch(p)
    if p.mismatch_email:
        print(f"active (~/.claude.json): {p.mismatch_email}  <-- РАЗЛИЧЕН акаунт")
