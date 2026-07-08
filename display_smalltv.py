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

import io
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

import ccusage_client as cc
import profile_client as pc
import render as render_mod
import usage_client as uc

IP = os.environ.get("CLAUDE_USAGE_SMALLTV_IP", "192.168.100.15")
BASE = f"http://{IP}"
IMG_DIR = "/image/"
IMG_NAME = "dashboard.jpg"
IMG_PATH = IMG_DIR + IMG_NAME
JPEG_QUALITY = 90
# Яркост (-10..100, reverse-engineer-нат от web UI: `name="brt"`). 10 е default-а на Ванака.
BRIGHTNESS = int(os.environ.get("CLAUDE_USAGE_SMALLTV_BRIGHTNESS", "10"))

HERE = os.path.dirname(os.path.abspath(__file__))
BG_240 = os.path.join(HERE, "assets", "background_240.png")

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


def connect(_port: str = "") -> str:
    """Setup (веднъж): cleanup + Photo Album + изключи image auto-display."""
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
    `session` се приема за signature parity с TuringDriver, но SmallTV по design
    показва само пръстени (без CTX панел) — параметърът се игнорира тук.
    """
    del session  # unused by design
    frame = render_mod.render_smalltv(usage, snap, _bg_img(), profile=pc.get_profile())
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
    h = connect()
    render(h, usage, snap)
    print("[smalltv] Кадър изпратен — провери дисплея.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(render_once())
