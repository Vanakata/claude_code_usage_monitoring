#!/usr/bin/env python
"""Споделена render логика за двата transport-а (Turing serial / SmallTV HTTP).

Тук живеят НЕзависимите от transport-а неща: цветове, threshold-и, форматиране,
segmented bar рисуване (PIL), label на модела, и пълен 240x240 кадър за SmallTV.

Turing (display.py) ползва helper-ите тук + инкрементален serial draw (за да не
насича). SmallTV (display_smalltv.py) рендира пълен PIL кадър и го праща като JPEG.
Данните идват от ccusage_client / usage_client (споделени и за двата).
"""
from __future__ import annotations

import os
import re

from PIL import Image, ImageDraw, ImageFont

import ccusage_client as cc
import usage_client as uc

# --- Цветове (общи) ---
WHITE = (235, 235, 235)
DIM = (150, 150, 150)
GREEN = (0, 220, 90)
AMBER = (240, 180, 0)
RED = (235, 60, 60)
MODEL = (120, 235, 160)
EMPTY_CELL = (35, 80, 50)  # контур на празна клетка в segmented bar

# --- Шрифтове (от драйвер либ-а; cwd-независими) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_F = os.path.join(_HERE, "turing-smart-screen-python", "res", "fonts", "roboto-mono")
FONT_BOLD = os.path.join(_F, "RobotoMono-Bold.ttf")
FONT_REG = os.path.join(_F, "RobotoMono-Regular.ttf")


def bar_color(pct) -> tuple:
    """Зелено < 70%, кехлибар < 90%, червено иначе."""
    if pct is None:
        return DIM
    if pct >= 90:
        return RED
    if pct >= 70:
        return AMBER
    return GREEN


def model_label(models) -> str:
    """['claude-opus-4-8'] -> 'Opus 4.8'. При няколко — най-силния (opus>sonnet>haiku)."""
    if not models:
        return "--"
    rank = {"opus": 0, "sonnet": 1, "haiku": 2}
    top = min(models, key=lambda m: next((v for k, v in rank.items() if k in m), 9))
    fam = next((k for k in rank if k in top), None)
    nums = re.findall(r"\d+", top)
    if fam and len(nums) >= 2:
        return f"{fam.capitalize()} {nums[0]}.{nums[1]}"
    return top


def draw_segmented(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                   pct, color, cells: int = 14, gap: int = 4, radius: int = 3) -> None:
    """Рисува segmented bar (дискретни клетки) върху ImageDraw на абсолютни (x,y).

    Пълните клетки са плътен цвят, празните — тънък контур (фонът прозира).
    Споделя се от Turing (върху bg crop) и SmallTV (върху пълния кадър).
    """
    p = max(0.0, min(100.0, pct)) if pct is not None else 0.0
    filled = int(round(p / 100.0 * cells))
    cw = (w - gap * (cells - 1)) / cells
    for i in range(cells):
        cx0 = x + int(round(i * (cw + gap)))
        cx1 = cx0 + int(round(cw))
        box = [cx0, y, cx1, y + h - 1]
        if i < filled:
            draw.rounded_rectangle(box, radius=radius, fill=color)
        else:
            draw.rounded_rectangle(box, radius=radius, outline=EMPTY_CELL, width=1)


# --- SmallTV 240x240 пълен кадър ---
_F240 = {}


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _F240:
        _F240[key] = ImageFont.truetype(path, size)
    return _F240[key]


def render_smalltv(usage, snap, bg: Image.Image) -> Image.Image:
    """Пълен 240x240 кадър за SmallTV (компактен layout, преподреден за тясно)."""
    img = bg.copy()
    d = ImageDraw.Draw(img)

    def txt(s, x, y, size, color, bold=True):
        d.text((x, y), s, font=_font(FONT_BOLD if bold else FONT_REG, size), fill=color)

    fh = usage.five_hour if usage else None
    wk = usage.seven_day if usage else None
    models = snap.block.models if snap and snap.block else []

    # модел (горе)
    txt(model_label(models), 8, 6, 18, MODEL)

    # 5H
    fh_pct = fh.utilization if fh else None
    txt("5H", 8, 36, 18, DIM)
    txt(f"{fh_pct:>3.0f}%" if fh_pct is not None else " --", 48, 30, 30, bar_color(fh_pct))
    txt(uc._fmt_delta(fh.remaining()) if fh else "--", 150, 40, 16, DIM, bold=False)
    draw_segmented(d, 8, 70, 224, 16, fh_pct, bar_color(fh_pct), cells=12)

    # WK
    wk_pct = wk.utilization if wk else None
    txt("WK", 8, 104, 18, DIM)
    txt(f"{wk_pct:>3.0f}%" if wk_pct is not None else " --", 48, 98, 30, bar_color(wk_pct))
    txt(uc._fmt_delta(wk.remaining()) if wk else "--", 150, 108, 16, DIM, bold=False)
    draw_segmented(d, 8, 138, 224, 16, wk_pct, bar_color(wk_pct), cells=12)

    # SESSION
    cost = snap.block.cost_usd if snap and snap.block else 0.0
    tokens = snap.block.total_tokens if snap and snap.block else 0
    txt("SESSION", 8, 170, 14, DIM)
    txt(f"${cost:>6.2f}", 8, 190, 30, WHITE)
    txt(f"{cc.format_tokens(tokens)} tok", 8, 222, 15, DIM, bold=False)
    return img
