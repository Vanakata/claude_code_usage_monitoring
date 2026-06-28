#!/usr/bin/env python
"""Layout — рендерира Claude usage на Turing Rev A (480x320), /usage-style.

Източници:
  - usage_client.fetch_usage()  -> РЕАЛНИ 5h/weekly utilization % + reset (като /usage)
  - ccusage_client.fetch_snapshot() -> session cost/tokens на активния блок

Рисува върху dark matrix background (assets/background.png) — текстът/баровете са с
прозрачен фон, за да се вижда картинката. Виж work/tomorrow.md.
"""
from __future__ import annotations

import os
import sys
import time
import types

import serial
from PIL import Image, ImageDraw

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(HERE, "turing-smart-screen-python")
sys.path.insert(0, LIB_DIR)

from library.lcd.lcd_comm_rev_a import LcdCommRevA, Orientation, SubRevision  # noqa: E402

import ccusage_client as cc  # noqa: E402
import usage_client as uc  # noqa: E402
from render import (  # noqa: E402  — споделени helpers/цветове (без дублиране)
    WHITE, DIM, GREEN, AMBER, RED, MODEL,
    bar_color as _bar_color, model_label as _model_label, draw_segmented,
)


def _safe_open_serial(self):
    """Замества библиотечния openSerial: RAISE вместо os._exit(0).

    Оригиналът прави os._exit(0) при липсващ/зает порт — НЕхванаемо, убива целия
    процес, и то с код 0 (успех) -> Task Scheduler не рестартира. Това е причината
    за "вечния бял екран" след дръпване. Тук хвърляме SerialException, за да я хване
    run.py и да reconnect-не (процесът остава жив завинаги).
    """
    port = self.com_port
    if port == "AUTO":
        port = self.auto_detect_com_port()
        if not port:
            raise serial.SerialException("AUTO: дисплеят не е намерен")
        self.com_port = port
    self.lcd_serial = serial.Serial(self.com_port, 115200, timeout=1, rtscts=True)


# Patch-ваме на ниво клас -> покрива и __init__, и Reset(), и всеки retry.
LcdCommRevA.openSerial = _safe_open_serial

# --- Hardware (виж README) ---
# AUTO -> библиотеката намира устройството по VID/PID (USB35INCHIPSV2 / 1A86:5722),
# та преживява смяна на COM номера при ново включване. Override с env при нужда.
COM_PORT = os.environ.get("CLAUDE_USAGE_COM_PORT", "AUTO")
BRIGHTNESS = int(os.environ.get("CLAUDE_USAGE_BRIGHTNESS", "15"))
WIDTH, HEIGHT = 320, 480  # portrait dims; landscape -> 480x320 след SetOrientation

# --- Asset-и ---
BG_IMAGE = os.path.join(HERE, "assets", "background.png")  # 480x320 matrix фон

# --- Шрифтове (абсолютни пътища -> cwd-независими) ---
_F = os.path.join(LIB_DIR, "res", "fonts", "roboto-mono")
FONT_REG = os.path.join(_F, "RobotoMono-Regular.ttf")
FONT_BOLD = os.path.join(_F, "RobotoMono-Bold.ttf")

# Цветове, _bar_color, _model_label, draw_segmented идват от render.py (споделени).

_BG_PIL = None


def _bg_pil() -> Image.Image:
    """Кешира matrix фона (за crop под segmented бара)."""
    global _BG_PIL
    if _BG_PIL is None:
        _BG_PIL = Image.open(BG_IMAGE).convert("RGB")
    return _BG_PIL


def _segmented_bar(lcd, x: int, y: int, w: int, h: int, pct, color, cells: int = 14) -> None:
    """Turing: crop на matrix фона + segmented клетки (render.draw_segmented) + push."""
    img = _bg_pil().crop((x, y, x + w, y + h)).copy()
    draw_segmented(ImageDraw.Draw(img), 0, 0, w, h, pct, color, cells=cells)
    lcd.DisplayPILImage(img, x, y)


def _resilient_write_line(self, line: bytes) -> None:
    """WriteLine с reopen+resend (като оригинала) НО маркира за пълен re-init.

    Защо: при serial срив оригиналът reopen-ва насред bitmap и продължава ->
    кадърът се ДОВЪРШВА (иначе остава бял/недорисуван), но е разместен. Затова
    вдигаме `_needs_reinit` -> run.py прави чист пълен reconnect веднага след кадъра
    (HELLO-resync + Clear + orientation) -> следващият кадър е чист.
    Ако устройството наистина го няма, openSerial/resend ще гръмнат -> грешката
    изхвърча -> run.py пак прави reconnect.
    """
    try:
        self.serial_write(line)
    except serial.SerialTimeoutException:
        pass  # твърде бързо — толерираме
    except serial.SerialException:
        self._needs_reinit = True
        self.closeSerial()
        time.sleep(1)
        self.openSerial()       # ако портът го няма -> raise -> run.py reconnect
        self.serial_write(line)  # ако и това гръмне -> raise -> run.py reconnect


def connect(port: str = COM_PORT) -> LcdCommRevA:
    print(f"[display] Свързвам Rev A на {port}...")
    lcd = LcdCommRevA(com_port=port, display_width=WIDTH, display_height=HEIGHT)
    lcd._needs_reinit = False
    # reopen+resend, но с маркер за чист re-init след кадъра (виж _resilient_write_line)
    lcd.WriteLine = types.MethodType(_resilient_write_line, lcd)
    lcd.Reset()
    # След replug дисплеят cold-boot-ва: CH340 мостът е готов преди screen MCU-то.
    # Retry-ваме HELLO докато не върне ВАЛИДЕН отговор — това едновременно изчаква
    # boot-а И гарантира byte-alignment на протокола (иначе HELLO се чете разместен
    # -> всички следващи команди са офсетнати -> размазан кадър в portrait).
    for attempt in range(10):
        try:
            lcd.lcd_serial.reset_input_buffer()
            lcd.lcd_serial.reset_output_buffer()
        except Exception:
            pass
        try:
            lcd.InitializeComm()  # _hello -> сетва lcd.sub_revision
        except serial.SerialException:
            pass  # още буутва -> retry
        if getattr(lcd, "sub_revision", None) == SubRevision.USBMONITOR_3_5:
            break
        print(f"[display] HELLO не е синхронизиран (опит {attempt + 1}/10) — изчаквам boot...")
        time.sleep(2)
    lcd.SetBrightness(level=BRIGHTNESS)
    lcd.Clear()  # вътрешно връща PORTRAIT
    lcd.SetOrientation(orientation=Orientation.REVERSE_LANDSCAPE)  # 480x320, обърнато 180°
    draw_static(lcd)  # фон + статични етикети ВЕДНЪЖ (виж draw_static)
    return lcd


def _txt(lcd, text, x, y, size, color, bold=True):
    lcd.DisplayText(text, x, y, font=FONT_BOLD if bold else FONT_REG, font_size=size,
                    font_color=color, background_image=BG_IMAGE)


def draw_static(lcd: LcdCommRevA) -> None:
    """Рисува фона + НЕпроменящите се елементи ВЕДНЪЖ (при connect/reconnect).

    Така render() не преначертава целия екран всеки цикъл (което насича по serial) —
    обновява само малките динамични полета.
    """
    lcd.DisplayBitmap(BG_IMAGE)
    _txt(lcd, "CLAUDE USAGE", 12, 8, 26, WHITE)
    _txt(lcd, "5H", 12, 58, 24, DIM)
    _txt(lcd, "WK", 12, 140, 24, DIM)
    _txt(lcd, "SESSION", 12, 224, 20, DIM)


def _gauge(lcd: LcdCommRevA, y: int, pct, reset_txt: str) -> None:
    """Динамичната част на gauge: %, reset, бар. Фиксирана ширина -> без ghosting."""
    has = pct is not None
    color = _bar_color(pct) if has else DIM
    _txt(lcd, f"{pct:>3.0f}%" if has else "  --", 64, y, 34, color)
    _txt(lcd, f"resets {reset_txt:<6}", 250, y + 10, 18, DIM, bold=False)
    _segmented_bar(lcd, 12, y + 46, 456, 22, pct, color)


def render(lcd: LcdCommRevA, usage, snap) -> None:
    """Обновява само ДИНАМИЧНИТЕ полета (фонът/етикетите са от draw_static).

    usage може да е None (-> '--'). Всички полета са с фиксирана ширина, за да
    презапишат старата стойност изцяло (иначе остатъци ghost-ват без пълен redraw).
    """
    fh = usage.five_hour if usage else None
    wk = usage.seven_day if usage else None
    _gauge(lcd, 52, fh.utilization if fh else None,
           uc._fmt_delta(fh.remaining()) if fh else "--")
    _gauge(lcd, 134, wk.utilization if wk else None,
           uc._fmt_delta(wk.remaining()) if wk else "--")

    # --- активен модел (горе вдясно, от ccusage block) ---
    models = snap.block.models if snap and snap.block else []
    _txt(lcd, f"{_model_label(models):>11}", 270, 16, 20, MODEL)

    # --- SESSION (активен блок, от ccusage) ---
    block_cost = snap.block.cost_usd if snap and snap.block else 0.0
    block_tokens = snap.block.total_tokens if snap and snap.block else 0
    _txt(lcd, f"${block_cost:>6.2f}", 12, 252, 40, WHITE)
    _txt(lcd, f"{cc.format_tokens(block_tokens):>6} tok", 250, 264, 28, WHITE)

    today = snap.daily.today_cost if snap else 0.0
    _txt(lcd, f"today ${today:>6.2f}", 12, 300, 16, DIM, bold=False)


def render_once() -> int:
    try:
        usage = uc.fetch_usage()
    except uc.UsageError as exc:
        print(f"[display] usage ГРЕШКА: {exc}", file=sys.stderr)
        return 1

    # ccusage е best-effort — gauge-овете и без него работят
    snap = None
    try:
        snap = cc.fetch_snapshot()
    except cc.CcusageError as exc:
        print(f"[display] ccusage недостъпен ({exc}) — session ще е празен", file=sys.stderr)

    lcd = connect()
    render(lcd, usage, snap)
    lcd.closeSerial()
    print("[display] Кадър изрисуван — провери дисплея.")
    return 0


if __name__ == "__main__":
    sys.exit(render_once())
