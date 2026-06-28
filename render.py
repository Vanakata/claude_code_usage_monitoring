#!/usr/bin/env python
"""Споделена render логика за двата transport-а (Turing serial / SmallTV HTTP).

Тук живеят НЕзависимите от transport-а неща: цветове, threshold-и, форматиране,
segmented bar рисуване (PIL), label на модела, и пълен 240x240 кадър за SmallTV.

Turing (display.py) ползва helper-ите тук + инкрементален serial draw (за да не
насича). SmallTV (display_smalltv.py) рендира пълен PIL кадър и го праща като JPEG.
Данните идват от ccusage_client / usage_client (споделени и за двата).
"""
from __future__ import annotations

import calendar as _calmod
import os
import re
from datetime import date, datetime, timedelta

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


_FONTS = {}


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]


# --- Dashboard тема (clean, light, радиални пръстени) ---
DB_BG = (236, 239, 243)       # светъл фон
CARD = (255, 255, 255)        # бяла карта
NAVY = (28, 42, 74)           # header / основен текст
HEADER_TXT = (244, 247, 250)
DB_AMBER = (245, 166, 35)     # accent (модел)
TEAL = (26, 150, 150)         # ring нисък %
MUTED = (122, 134, 152)       # вторичен текст
RING_TRACK = (220, 225, 232)  # празна част на пръстена
DB_RED = (220, 70, 70)
CAL_GREEN = (46, 170, 90)      # календар: начало на reset седмицата


def _ring_color(pct) -> tuple:
    """Тийл < 70%, кехлибар < 90%, червено иначе (dashboard палитра)."""
    if pct is None:
        return RING_TRACK
    if pct >= 90:
        return DB_RED
    if pct >= 70:
        return DB_AMBER
    return TEAL


def draw_ring(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, th: int, pct, pct_size: int) -> None:
    """Радиален gauge: сив track + цветна дъга (от 12 часа, по часовниковата) + център %."""
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 0, 360, fill=RING_TRACK, width=th)
    if pct is not None and pct > 0:
        d.arc(box, -90, -90 + min(100.0, pct) / 100.0 * 360.0, fill=_ring_color(pct), width=th)
    s = f"{pct:.0f}%" if pct is not None else "--"
    d.text((cx, cy), s, font=_font(FONT_BOLD, pct_size), fill=NAVY, anchor="mm")


def draw_calendar(d: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, now: datetime,
                  reset_date=None) -> None:
    """Месечен календар (Sunday-first). Цветни кръгчета:
    тийл=днес, червено=ден на weekly reset, зелено=началото (неделя) на reset седмицата.
    """
    cols = 7
    cw = w / cols
    reset_d = reset_date.astimezone().date() if reset_date else None
    # календарът показва МЕСЕЦА НА RESET-а (иначе при reset в следващ месец лентата не се вижда)
    anchor = reset_d if reset_d else now.date()

    d.text((x0 + w / 2, y0), anchor.strftime("%B %Y").upper(), font=_font(FONT_BOLD, 13),
           fill=NAVY, anchor="ma")
    hy = y0 + 22
    for i, ww in enumerate(["S", "M", "T", "W", "T", "F", "S"]):
        d.text((x0 + (i + 0.5) * cw, hy), ww, font=_font(FONT_REG, 11), fill=MUTED, anchor="ma")

    weeks = _calmod.Calendar(firstweekday=6).monthdayscalendar(anchor.year, anchor.month)
    gy = y0 + 40
    rh = min(18.0, (h - 40) / max(len(weeks), 1))

    # ред на reset седмицата (reset денят винаги е в показания месец)
    reset_row = None
    if reset_d:
        for r, week in enumerate(weeks):
            if reset_d.day in week:
                reset_row = r
                break

    # фон-лента за целия 7-дневен период: green (начало) -> red (reset)
    if reset_row is not None:
        by0 = gy + reset_row * rh
        by1 = by0 + rh
        span = max(1.0, w)
        for xi in range(int(x0), int(x0 + w)):
            t = (xi - x0) / span
            col = tuple(int(CAL_GREEN[k] + (DB_RED[k] - CAL_GREEN[k]) * t) for k in range(3))
            d.line([(xi, by0), (xi, by1)], fill=col)

    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            if day == 0:
                continue
            cx = x0 + (c + 0.5) * cw
            cy = gy + (r + 0.5) * rh
            in_band = r == reset_row
            d.text((cx, cy), str(day),
                   font=_font(FONT_BOLD if in_band else FONT_REG, 11),
                   fill=(255, 255, 255) if in_band else NAVY, anchor="mm")


def render_dashboard(usage, snap, w: int, h: int) -> Image.Image:
    """Clean dashboard кадър (light тема, радиални %-пръстени). За двата размера."""
    img = Image.new("RGB", (w, h), DB_BG)
    d = ImageDraw.Draw(img)
    big = w >= 400

    fh = usage.five_hour if usage else None
    wk = usage.seven_day if usage else None
    fhp = fh.utilization if fh else None
    wkp = wk.utilization if wk else None
    models = snap.block.models if snap and snap.block else []
    cost = snap.block.cost_usd if snap and snap.block else 0.0
    tokens = snap.block.total_tokens if snap and snap.block else 0
    today = snap.daily.today_cost if snap else 0.0

    def fb(size):
        return _font(FONT_BOLD, size)

    def fr(size):
        return _font(FONT_REG, size)

    if big:  # 480x320 (Turing)
        hh = 44
        d.rectangle([0, 0, w, hh], fill=NAVY)
        d.text((16, hh // 2), "CLAUDE USAGE", font=fb(20), fill=HEADER_TXT, anchor="lm")
        d.text((w - 14, hh // 2), model_label(models), font=fb(16), fill=DB_AMBER, anchor="rm")

        # пръстени (горе-ляво)
        for cx, label, p, win in ((80, "5H", fhp, fh), (196, "WK", wkp, wk)):
            draw_ring(d, cx, 96, 37, 10, p, 19)
            d.text((cx, 138), label, font=fb(15), fill=NAVY, anchor="ma")
            d.text((cx, 156), uc._fmt_delta(win.remaining()) if win else "--",
                   font=fr(11), fill=MUTED, anchor="ma")

        # календар (долу-ляво, бяла карта)
        d.rounded_rectangle([10, 176, 292, h - 8], radius=10, fill=CARD)
        draw_calendar(d, 22, 188, 258, 118, datetime.now(),
                      reset_date=wk.resets_at if wk else None)

        # SESSION карта (вдясно, цяла височина)
        cx0 = 302
        d.rounded_rectangle([cx0, 52, w - 10, h - 8], radius=12, fill=CARD)
        d.text((cx0 + 16, 70), "SESSION", font=fb(14), fill=MUTED, anchor="lm")
        d.text((cx0 + 16, 102), f"${cost:.2f}", font=fb(28), fill=NAVY, anchor="lm")
        d.text((cx0 + 16, 136), f"{cc.format_tokens(tokens)} tok", font=fr(14), fill=MUTED, anchor="lm")
        d.line([cx0 + 16, 160, w - 24, 160], fill=RING_TRACK, width=1)
        d.text((cx0 + 16, 184), "today", font=fr(13), fill=MUTED, anchor="lm")
        d.text((w - 24, 184), f"${today:.2f}", font=fb(14), fill=NAVY, anchor="rm")
        week_s = f"${snap.daily.week_cost:.0f}" if snap else "--"
        d.text((cx0 + 16, 212), "week", font=fr(13), fill=MUTED, anchor="lm")
        d.text((w - 24, 212), week_s, font=fb(14), fill=NAVY, anchor="rm")
    else:  # 240x240 (SmallTV)
        hh = 30
        d.rectangle([0, 0, w, hh], fill=NAVY)
        d.text((8, hh // 2), "CLAUDE", font=fb(14), fill=HEADER_TXT, anchor="lm")
        d.text((w - 7, hh // 2), model_label(models), font=fb(12), fill=DB_AMBER, anchor="rm")

        # пръстени по-нагоре + reset време под всеки (за да се вижда на малкия екран)
        for cx, label, p, win in ((64, "5H", fhp, fh), (176, "WK", wkp, wk)):
            draw_ring(d, cx, 74, 36, 11, p, 18)
            d.text((cx, 114), label, font=fb(13), fill=NAVY, anchor="ma")
            d.text((cx, 131), uc._fmt_delta(win.remaining()) if win else "--",
                   font=fr(11), fill=MUTED, anchor="ma")

        d.rounded_rectangle([8, 152, w - 8, 226], radius=8, fill=CARD)
        d.text((18, 170), f"${cost:.2f}", font=fb(24), fill=NAVY, anchor="lm")
        d.text((w - 16, 172), f"{cc.format_tokens(tokens)} tok", font=fr(12), fill=MUTED, anchor="rm")
        d.text((18, 202), f"today ${today:.2f}", font=fr(12), fill=MUTED, anchor="lm")
    return img


def render_smalltv(usage, snap, bg=None) -> Image.Image:
    """SmallTV 240x240 кадър (dashboard тема). `bg` се игнорира (light тема)."""
    return render_dashboard(usage, snap, 240, 240)
