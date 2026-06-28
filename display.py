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
from datetime import date

import serial

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
import render as render_mod  # noqa: E402  — dashboard renderer (споделен; alias, че да не се сблъска с функцията render())


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

# Рендерът (dashboard тема, цветове, шрифтове) живее в render.py (споделен с SmallTV).

# Динамични региони (480x320 dashboard), които render() обновява всеки цикъл
# (фонът/header/календарът са в пълния кадър, рисуван при connect / смяна на ден).
_DYN_REGIONS = [
    (40, 54, 124, 168),    # 5H пръстен + label + reset
    (156, 54, 240, 168),   # WK пръстен + label + reset
    (300, 4, 468, 42),     # активен модел (header дясно)
    (304, 84, 470, 230),   # SESSION стойности (cost/tokens/today/week)
]


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
    lcd._dash_base = False  # render() ще нарисува пълния кадър при първото извикване
    lcd._dash_day = None
    return lcd


def render(lcd: LcdCommRevA, usage, snap) -> None:
    """Dashboard рендер (480x320), инкрементален -> без насичане.

    Пълен кадър (вкл. календар) се рисува при connect и при смяна на ден; иначе
    се обновяват само динамичните региони (пръстени/модел/SESSION стойности).
    """
    frame = render_mod.render_dashboard(usage, snap, 480, 320)
    today = date.today()
    wk = usage.seven_day if usage else None
    # ключ за календарната лента — сменя ли се reset датата (вкл. None->дата при идване
    # на данните след 429), трябва пълен redraw, иначе лентата няма да се появи
    reset_key = wk.resets_at.astimezone().date() if (wk and wk.resets_at) else None
    theme = render_mod.theme_for_now()  # смяна на тема (ден/нощ) -> пълен redraw
    need_full = (not getattr(lcd, "_dash_base", False)
                 or getattr(lcd, "_dash_day", None) != today
                 or getattr(lcd, "_dash_reset", "init") != reset_key
                 or getattr(lcd, "_dash_theme", "init") != theme)
    if need_full:
        lcd.DisplayPILImage(frame, 0, 0)   # пълен кадър при connect/нов ден/нов reset/смяна на тема
        lcd._dash_base = True
        lcd._dash_day = today
        lcd._dash_reset = reset_key
        lcd._dash_theme = theme
    else:
        for (x, y, x2, y2) in _DYN_REGIONS:
            lcd.DisplayPILImage(frame.crop((x, y, x2, y2)), x, y)


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
