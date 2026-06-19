#!/usr/bin/env python
"""POC — hardware handshake за Turing Smart Screen Revision A на COM5.

Цел: да докажем, че serial протоколът (Rev A) + портът (COM5) работят, като
светнем дисплея и покажем статичен текст + едно число на 480x320 (landscape).
Никаква ccusage логика тук — това е стъпка нула.
"""
import os
import sys

# Windows конзолата е cp1252 по подразбиране -> кирилицата в print чупи скрипта.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Cloned library (виж README / .gitignore) — добавяме го към path-а.
LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turing-smart-screen-python")
sys.path.insert(0, LIB_DIR)

from PIL import Image  # noqa: E402
from library.lcd.lcd_comm_rev_a import LcdCommRevA, Orientation  # noqa: E402

# Hardware (разузнато 2026-06-19, виж README)
COM_PORT = "COM5"
# Размери за PORTRAIT ориентация; landscape се прави през SetOrientation по-долу.
WIDTH, HEIGHT = 320, 480

# Абсолютен font path -> POC-ът работи независимо от cwd.
FONT = os.path.join(LIB_DIR, "res", "fonts", "roboto-mono", "RobotoMono-Bold.ttf")


def main() -> int:
    print(f"[POC] Свързвам Rev A дисплей на {COM_PORT} ({WIDTH}x{HEIGHT})...")
    lcd = LcdCommRevA(com_port=COM_PORT, display_width=WIDTH, display_height=HEIGHT)

    lcd.Reset()            # reset от евентуално нестабилно състояние (чисти и екрана)
    lcd.InitializeComm()   # init команди
    lcd.SetBrightness(level=15)  # Rev A се топли — дръж <=50%

    # ВАЖНО: Clear() вътрешно връща ориентацията на PORTRAIT (виж lcd_comm_rev_a.py),
    # затова landscape се слага СЛЕД него, иначе текстът излиза завъртян на 90°.
    lcd.Clear()
    lcd.SetOrientation(orientation=Orientation.LANDSCAPE)  # 480x320

    # Clear не трие надеждно стария vendor background на този sub-revision ->
    # рисуваме плътен черен кадър върху целия екран.
    black = Image.new("RGB", (lcd.get_width(), lcd.get_height()), (0, 0, 0))
    lcd.DisplayPILImage(black)

    lcd.DisplayText("CLAUDE USAGE", 40, 100,
                    font=FONT, font_size=40,
                    font_color=(255, 255, 255), background_color=(0, 0, 0))
    lcd.DisplayText("42", 180, 180,
                    font=FONT, font_size=90,
                    font_color=(0, 255, 0), background_color=(0, 0, 0))

    lcd.closeSerial()
    print("[POC] Готово — провери дисплея за 'CLAUDE USAGE' + '42'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
