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


# --- Dashboard тема (DARK, радиални пръстени) ---
DB_BG = (16, 20, 30)          # тъмен фон
CARD = (28, 34, 50)           # тъмна карта
NAVY = (22, 28, 46)           # header лента (тъмно navy)
TXT = (226, 231, 240)         # основен светъл текст
HEADER_TXT = (236, 240, 248)
DB_AMBER = (245, 175, 55)     # accent (модел)
TEAL = (38, 178, 170)         # ring нисък %
MUTED = (142, 152, 172)       # вторичен текст
RING_TRACK = (45, 53, 72)     # празна част на пръстена
DB_RED = (228, 82, 82)
CAL_GREEN = (60, 185, 105)    # календар: начало на reset седмицата


def _apply_theme(mode: str) -> None:
    """Сетва цветовете на палитрата (light / dark)."""
    global DB_BG, CARD, NAVY, TXT, HEADER_TXT, DB_AMBER, TEAL, MUTED, RING_TRACK, DB_RED, CAL_GREEN
    if mode == "light":
        DB_BG, CARD, NAVY, TXT = (236, 239, 243), (255, 255, 255), (28, 42, 74), (28, 42, 74)
        HEADER_TXT, DB_AMBER, TEAL = (244, 247, 250), (245, 166, 35), (26, 150, 150)
        MUTED, RING_TRACK, DB_RED, CAL_GREEN = (122, 134, 152), (220, 225, 232), (220, 70, 70), (46, 170, 90)
    else:  # dark
        DB_BG, CARD, NAVY, TXT = (16, 20, 30), (28, 34, 50), (22, 28, 46), (226, 231, 240)
        HEADER_TXT, DB_AMBER, TEAL = (236, 240, 248), (245, 175, 55), (38, 178, 170)
        MUTED, RING_TRACK, DB_RED, CAL_GREEN = (142, 152, 172), (45, 53, 72), (228, 82, 82), (60, 185, 105)


def theme_for_now() -> str:
    """Активна тема: env CLAUDE_USAGE_THEME=light|dark|auto (default auto по час).

    Auto: светло между DAY_START и DAY_END (default 07–19), иначе тъмно.
    """
    mode = os.environ.get("CLAUDE_USAGE_THEME", "auto").lower()
    if mode in ("light", "dark"):
        return mode
    start = int(os.environ.get("CLAUDE_USAGE_DAY_START", "7"))
    end = int(os.environ.get("CLAUDE_USAGE_DAY_END", "19"))
    return "light" if start <= datetime.now().hour < end else "dark"


ALARM_PCT = int(os.environ.get("CLAUDE_USAGE_ALARM_PCT", "95"))  # праг за аларма


def alarm_breaches(usage):
    """Списък с пробитите прозорци, напр. ['5H 98%', 'WK 96%']. Празен -> няма аларма."""
    out = []
    if usage:
        if usage.five_hour and usage.five_hour.utilization >= ALARM_PCT:
            out.append(f"5H {usage.five_hour.utilization:.0f}%")
        if usage.seven_day and usage.seven_day.utilization >= ALARM_PCT:
            out.append(f"WK {usage.seven_day.utilization:.0f}%")
    return out


def _warn_tri(d, cx, cy, s, col=(255, 255, 255)):
    """Малък триъгълник-предупреждение с удивителна."""
    d.polygon([(cx, cy - s), (cx - s, cy + s), (cx + s, cy + s)], outline=col, width=2)
    d.line([(cx, cy - s + 4), (cx, cy + s - 5)], fill=col, width=2)
    d.ellipse([cx - 1, cy + s - 4, cx + 1, cy + s - 2], fill=col)


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
    d.text((cx, cy), s, font=_font(FONT_BOLD, pct_size), fill=TXT, anchor="mm")


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
           fill=TXT, anchor="ma")
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

    # неделята на reset седмицата (за да покажем целите 7 дни, дори от съседен месец)
    week_sunday = reset_d - timedelta(days=(reset_d.weekday() + 1) % 7) if reset_d else None

    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            cx = x0 + (c + 0.5) * cw
            cy = gy + (r + 0.5) * rh
            if r == reset_row and week_sunday is not None:
                # цялата reset седмица — реални дати, вкл. дни от другия месец
                dnum = (week_sunday + timedelta(days=c)).day
                d.text((cx, cy), str(dnum), font=_font(FONT_BOLD, 11),
                       fill=(255, 255, 255), anchor="mm")
            elif day != 0:
                d.text((cx, cy), str(day), font=_font(FONT_REG, 11), fill=TXT, anchor="mm")


def render_dashboard(usage, snap, w: int, h: int, profile=None) -> Image.Image:
    """Dashboard кадър (радиални %-пръстени). Тема по часа (light денем / dark вечер)."""
    _apply_theme(theme_for_now())
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

    breaches = alarm_breaches(usage)   # аларма при >= ALARM_PCT
    alarm = bool(breaches)
    hdr_fill = DB_RED if alarm else NAVY

    def fb(size):
        return _font(FONT_BOLD, size)

    def fr(size):
        return _font(FONT_REG, size)

    if big:  # 480x320 (Turing)
        hh = 44
        d.rectangle([0, 0, w, hh], fill=hdr_fill)
        if alarm:
            _warn_tri(d, 24, hh // 2, 10)
            d.text((44, hh // 2), "LIMIT  " + "  ".join(breaches), font=fb(18),
                   fill=(255, 255, 255), anchor="lm")
            d.text((w - 14, hh // 2), model_label(models), font=fb(15),
                   fill=(255, 235, 235), anchor="rm")
        else:
            d.text((16, hh // 2), "CLAUDE USAGE", font=fb(20), fill=HEADER_TXT, anchor="lm")
            if profile and profile.email:
                d.text((w // 2, hh // 2), model_label(models), font=fb(16), fill=DB_AMBER, anchor="mm")
                d.text((w - 14, hh // 2), profile.email, font=fr(13), fill=HEADER_TXT, anchor="rm")
            else:
                d.text((w - 14, hh // 2), model_label(models), font=fb(16), fill=DB_AMBER, anchor="rm")

        # пръстени (горе-ляво)
        for cx, label, p, win in ((80, "5H", fhp, fh), (196, "WK", wkp, wk)):
            draw_ring(d, cx, 96, 37, 10, p, 19)
            d.text((cx, 138), label, font=fb(15), fill=TXT, anchor="ma")
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
        d.text((cx0 + 16, 102), f"${cost:.2f}", font=fb(28), fill=TXT, anchor="lm")
        d.text((cx0 + 16, 136), f"{cc.format_tokens(tokens)} tok", font=fr(14), fill=MUTED, anchor="lm")
        d.line([cx0 + 16, 160, w - 24, 160], fill=RING_TRACK, width=1)
        d.text((cx0 + 16, 184), "today", font=fr(13), fill=MUTED, anchor="lm")
        d.text((w - 24, 184), f"${today:.2f}", font=fb(14), fill=TXT, anchor="rm")
        week_s = f"${snap.daily.week_cost:.0f}" if snap else "--"
        d.text((cx0 + 16, 212), "week", font=fr(13), fill=MUTED, anchor="lm")
        d.text((w - 24, 212), week_s, font=fb(14), fill=TXT, anchor="rm")
    else:  # 240x240 (SmallTV)
        hh = 30
        d.rectangle([0, 0, w, hh], fill=hdr_fill)
        if alarm:
            _warn_tri(d, 13, hh // 2, 7)
            d.text((26, hh // 2), "LIMIT " + " ".join(breaches), font=fb(12),
                   fill=(255, 255, 255), anchor="lm")
        else:
            if profile and profile.email:
                d.text((8, hh // 2), profile.email, font=fr(11), fill=HEADER_TXT, anchor="lm")
            else:
                d.text((8, hh // 2), "CLAUDE", font=fb(14), fill=HEADER_TXT, anchor="lm")
            d.text((w - 7, hh // 2), model_label(models), font=fb(12), fill=DB_AMBER, anchor="rm")

        # САМО пръстени (по-големи, за по-добра четимост) + reset време; без cost/tokens
        for cx, label, p, win in ((62, "5H", fhp, fh), (178, "WK", wkp, wk)):
            draw_ring(d, cx, 110, 50, 13, p, 28)
            d.text((cx, 176), label, font=fb(16), fill=TXT, anchor="ma")
            d.text((cx, 198), uc._fmt_delta(win.remaining()) if win else "--",
                   font=fr(13), fill=MUTED, anchor="ma")

    if alarm:  # червена рамка около целия екран
        bw = 6 if big else 5
        off = bw // 2
        d.rounded_rectangle([off, off, w - 1 - off, h - 1 - off], radius=10,
                            outline=DB_RED, width=bw)
    return img


def render_smalltv(usage, snap, bg=None, profile=None) -> Image.Image:
    """SmallTV 240x240 кадър (dashboard тема). `bg` се игнорира (light тема)."""
    return render_dashboard(usage, snap, 240, 240, profile=profile)
