#!/usr/bin/env python
"""SmallTV Ultra — HTTP/WiFi transport (втори дисплей).

GeekMagic SmallTV Ultra е самостоятелно WiFi устройство: рендираме 240x240 кадър
на PC-то и го push-ваме по HTTP. API (reverse-engineer-нат от web UI-то):
  - upload : POST /doUpload?dir=/image/   (multipart, поле `file`, JPEG)
  - album  : GET  /set?theme=3            (Photo Album режим)
  - no-auto: GET  /set?i_i=<s>&autoplay=0 (изключва image auto-display)
  - show   : GET  /set?img=/image/<file>
  - delete : GET  /delete?file=<urlencoded>
  - list   : GET  /filelist?dir=/image/

Фиксирано име `dashboard.jpg` -> презаписва (flash е малък, не трупаме файлове).
Транспортът е потвърден end-to-end. Виж work/tomorrow.md.
"""
from __future__ import annotations

import concurrent.futures
import io
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

import ccusage_client as cc
import profile_client as pc
import render as render_mod
import session_client as sc
import usage_client as uc

# IP resolution: env override > текущ/кеширан (ако отговаря) > мрежов scan > default.
# Обикновен потребител не знае какъв IP е дало DHCP-то — затова auto-discovery.
DEFAULT_IP = "192.168.100.3"
_IP_OVERRIDE = os.environ.get("CLAUDE_USAGE_SMALLTV_IP")  # изрично зададен → без scan
IP = _IP_OVERRIDE or DEFAULT_IP   # provisional; resolve_ip() може да го смени
BASE = f"http://{IP}"
IMG_DIR = "/image/"
IMG_NAME = "dashboard.jpg"
IMG_PATH = IMG_DIR + IMG_NAME
JPEG_QUALITY = 90
# Яркост (-10..100, reverse-engineer-нат от web UI: `name="brt"`). 10 е default-а на Ванака.
BRIGHTNESS = int(os.environ.get("CLAUDE_USAGE_SMALLTV_BRIGHTNESS", "10"))
# Изглед: 'lenti' (segmented ленти + footer; default) или 'rings' (дублирани 5H/WK).
MODE = os.environ.get("CLAUDE_USAGE_SMALLTV_MODE", "lenti").lower()

HERE = os.path.dirname(os.path.abspath(__file__))
BG_240 = os.path.join(HERE, "assets", "background_240.png")
IP_CACHE_PATH = os.path.join(HERE, "work", "smalltv_ip.txt")  # запомнено discovery IP

# Наши файлове за чистене при старт (НЕ user pics като ezgif-*/spaceman.gif!)
_OUR_FILES = ["claude_test.jpg"]


class SmallTvError(RuntimeError):
    """Мрежова/HTTP грешка към SmallTV."""


_bg = None


def _bg_img() -> Image.Image:
    global _bg
    if _bg is None:
        _bg = Image.open(BG_240).convert("RGB")
    return _bg


def _get(path: str, timeout: int = 8) -> str:
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise SmallTvError(f"GET {path}: {exc}") from exc


def _upload_jpeg(jpeg: bytes, timeout: int = 20) -> None:
    """Multipart POST на JPEG като поле `file` с фиксирано име (презаписва)."""
    boundary = "----claudeusageSmallTV7913"
    pre = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{IMG_NAME}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode()
    body = pre + jpeg + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/doUpload?dir={IMG_DIR}", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
    except urllib.error.URLError as exc:
        raise SmallTvError(f"upload: {exc}") from exc


def cleanup() -> None:
    """Трие само НАШИ файлове (тестови/стари кадри); user pics остават."""
    for name in _OUR_FILES:
        q = urllib.parse.quote(IMG_DIR + name, safe="")
        try:
            _get(f"/delete?file={q}")
        except SmallTvError:
            pass  # липсва -> ок


# --------------------------------------------------------------------------- #
# IP auto-discovery — намира SmallTV-то по мрежата без ръчно въвеждане на IP
# --------------------------------------------------------------------------- #
def _set_ip(ip: str) -> None:
    global IP, BASE
    IP, BASE = ip, f"http://{ip}"


def _is_smalltv(ip: str, timeout: float = 1.5) -> bool:
    """Недеструктивен probe: GET /set без параметри връща точно 'FAIL' на SmallTV."""
    try:
        with urllib.request.urlopen(f"http://{ip}/set", timeout=timeout) as r:
            return r.read(16).strip() == b"FAIL"
    except (urllib.error.URLError, OSError):
        return False


def _load_cached_ip() -> str | None:
    try:
        with open(IP_CACHE_PATH, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _save_cached_ip(ip: str) -> None:
    try:
        os.makedirs(os.path.dirname(IP_CACHE_PATH), exist_ok=True)
        with open(IP_CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(ip)
    except OSError:
        pass


def _local_prefixes() -> list[str]:
    """/24 префиксът на активния интерфейс (напр. '192.168.100')."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # не праща трафик, само избира интерфейс
        ip = s.getsockname()[0]
        s.close()
        return [ip.rsplit(".", 1)[0]]
    except OSError:
        return []


def _port80_open(ip: str, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((ip, 80), timeout=timeout):
            return True
    except OSError:
        return False


def discover_smalltv() -> str | None:
    """Scan-ва локалния /24: бърз TCP port-80 филтър → /set=='FAIL' identify."""
    for prefix in _local_prefixes():
        hosts = [f"{prefix}.{i}" for i in range(1, 255)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            open_hosts = [ip for ip, ok in zip(hosts, ex.map(_port80_open, hosts)) if ok]
        for ip in open_hosts:
            if _is_smalltv(ip):
                return ip
    return None


def resolve_ip(rediscover: bool = False) -> str:
    """Установява работещ IP. Env override печели винаги (без scan)."""
    if _IP_OVERRIDE:
        _set_ip(_IP_OVERRIDE)
        return IP
    if not rediscover and _is_smalltv(IP):   # текущият still живее → бърз път
        return IP
    cached = _load_cached_ip()
    if cached and cached != IP and _is_smalltv(cached):
        _set_ip(cached)
        return IP
    print("[smalltv] търся дисплея по мрежата…")
    found = discover_smalltv()
    if found:
        _set_ip(found)
        _save_cached_ip(found)
        print(f"[smalltv] намерен на {found}")
        return IP
    print(f"[smalltv] не намирам дисплея — на една WiFi мрежа ли сте? "
          f"пробвам default {DEFAULT_IP}", file=sys.stderr)
    _set_ip(DEFAULT_IP)
    return IP


def connect(_port: str = "") -> str:
    """Setup (веднъж): resolve IP + cleanup + Photo Album + изключи image auto-display."""
    resolve_ip()
    print(f"[smalltv] {BASE} — setup (theme=3, autoplay off, brt={BRIGHTNESS})")
    cleanup()
    _get("/set?theme=3")              # Photo Album режим
    _get("/set?i_i=3600&autoplay=0")  # без авто-ротация на картинките
    _get(f"/set?brt={BRIGHTNESS}")    # яркост (default 10 → приятно за вечер)
    return BASE


def render(_handle, usage, snap, session=None) -> None:
    """Рендира 240x240 кадър и го push-ва: upload -> show.

    Profile (email/org) се чете на всеки tick през pc.get_profile() — реагира
    на `claude login` без рестарт. Mtime-кешът прави това евтино (без HTTP при
    непроменени credentials).
    Изгледът е по `CLAUDE_USAGE_SMALLTV_MODE`: 'lenti' (default) е terminal изгледът
    от Claude Design handoff-а — 3 segmented ленти (5H/WK/CTX) + footer TODAY/BURN/
    RESET, critical strip + alarm рамка. 'rings' връща стария дублиран 5H/WK изглед.
    """
    profile = pc.get_profile()
    if MODE == "rings":
        frame = render_mod.render_smalltv(usage, snap, _bg_img(), profile=profile)
    else:
        frame = render_mod.render_smalltv_lenti(usage, snap, session=session, profile=profile)
    buf = io.BytesIO()
    frame.save(buf, format="JPEG", quality=JPEG_QUALITY)
    _upload_jpeg(buf.getvalue())
    _get("/set?img=" + urllib.parse.quote(IMG_PATH, safe=""))


def render_once() -> int:
    try:
        usage = uc.fetch_usage()
    except uc.UsageError as exc:
        print(f"[smalltv] usage ГРЕШКА: {exc}", file=sys.stderr)
        return 1
    snap = None
    try:
        snap = cc.fetch_snapshot()
    except cc.CcusageError as exc:
        print(f"[smalltv] ccusage недостъпен ({exc})", file=sys.stderr)
    try:
        session = sc.fetch()
    except Exception as exc:  # fail-soft — ambient показва 'no session'
        print(f"[smalltv] session недостъпен ({exc})", file=sys.stderr)
        session = None
    h = connect()
    render(h, usage, snap, session)
    print("[smalltv] Кадър изпратен — провери дисплея.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(render_once())
