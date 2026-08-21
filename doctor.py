#!/usr/bin/env python
r"""Preflight health-check — казва на човешки език какво липсва за старт.

Пусни:  .\.venv\Scripts\python.exe doctor.py
Преизползва data/transport слоевете, тъй че проверява РЕАЛНО същите неща,
които run.py ще ползва. Нула mutation — само чете и probe-ва.

Изход:  0 = всичко наред за текущия target; 1 = има блокер.
"""
from __future__ import annotations

import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

OK = "  [ OK ] "
WARN = "  [WARN] "
FAIL = "  [FAIL] "


def _check_token() -> bool:
    """OAuth access token в credentials (интерактивен claude login, не API key)."""
    import usage_client as uc
    try:
        uc._read_token()
        print(OK + "Claude login: намерен OAuth token в ~/.claude/.credentials.json")
        return True
    except uc.UsageError as exc:
        print(FAIL + f"Claude login липсва: {exc}")
        print("         → Пусни `claude login` (интерактивно, НЕ API key). "
              "Без това гейджовете стоят на '--'.")
        return False


def _check_ccusage() -> bool:
    """ccusage в PATH — за SESSION/CTX/BURN. SmallTV не го ползва (само пръстени)."""
    if shutil.which("ccusage"):
        print(OK + "ccusage: намерен в PATH (SESSION/CTX/BURN данни налични)")
        return True
    print(WARN + "ccusage липсва — SESSION/CTX/BURN ще са празни.")
    print("         → Инсталирай Node.js (nodejs.org), после: npm i -g ccusage")
    print("         → SmallTV НЕ го ползва — ако си само на SmallTV, спокойно го пропусни.")
    return True  # не е блокер


def _check_smalltv() -> bool:
    """SmallTV достъпен по мрежата (env override или auto-discovery)."""
    import display_smalltv as st
    if st._IP_OVERRIDE:
        if st._is_smalltv(st._IP_OVERRIDE):
            print(OK + f"SmallTV: отговаря на {st._IP_OVERRIDE} (от env)")
            return True
        print(FAIL + f"SmallTV: {st._IP_OVERRIDE} (от env) не отговаря.")
        print("         → Провери IP-то или махни CLAUDE_USAGE_SMALLTV_IP за auto-discovery.")
        return False
    print("  ...    SmallTV: търся по мрежата (може да отнеме няколко сек.)…")
    ip = st.discover_smalltv()
    if ip:
        st._save_cached_ip(ip)
        print(OK + f"SmallTV: намерен на {ip}")
        return True
    print(FAIL + "SmallTV: не намирам устройството по мрежата.")
    print("         → PC-то и дисплеят на една WiFi мрежа ли са? Включен ли е дисплеят?")
    return False


def _check_turing() -> bool:
    """Turing serial порт по VID/PID (или CLAUDE_USAGE_COM_PORT override)."""
    import run
    port = run._resolve_port()
    if port:
        print(OK + f"Turing: намерен на {port}")
        return True
    print(FAIL + "Turing: не намирам serial дисплея (CH340 1A86:5722).")
    print("         → Включен ли е USB кабелът? Държи ли го TURMO.exe/vendor app?")
    return False


def main() -> int:
    target = os.environ.get("CLAUDE_USAGE_TARGET", "smalltv").lower()
    print(f"=== doctor — preflight за target='{target}' ===\n")

    blockers = 0
    if not _check_token():
        blockers += 1
    _check_ccusage()

    if target in ("smalltv", "both"):
        if not _check_smalltv():
            blockers += 1
    if target in ("turing", "both"):
        if not _check_turing():
            blockers += 1

    print()
    if blockers:
        print(f"[doctor] {blockers} блокер(а) — оправи горното, после пусни пак.")
        return 1
    print("[doctor] Всичко наред. Стартирай: .\\.venv\\Scripts\\python.exe run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
