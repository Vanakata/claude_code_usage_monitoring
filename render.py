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
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

import ccusage_client as cc
import session_client as sc
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


def _apply_theme(mode: str) -> None:
    """Сетва цветовете на палитрата (light / dark)."""
    global DB_BG, CARD, NAVY, TXT, HEADER_TXT, DB_AMBER, TEAL, MUTED, RING_TRACK, DB_RED
    if mode == "light":
        DB_BG, CARD, NAVY, TXT = (236, 239, 243), (255, 255, 255), (28, 42, 74), (28, 42, 74)
        HEADER_TXT, DB_AMBER, TEAL = (244, 247, 250), (245, 166, 35), (26, 150, 150)
        MUTED, RING_TRACK, DB_RED = (122, 134, 152), (220, 225, 232), (220, 70, 70)
    else:  # dark
        DB_BG, CARD, NAVY, TXT = (16, 20, 30), (28, 34, 50), (22, 28, 46), (226, 231, 240)
        HEADER_TXT, DB_AMBER, TEAL = (236, 240, 248), (245, 175, 55), (38, 178, 170)
        MUTED, RING_TRACK, DB_RED = (142, 152, 172), (45, 53, 72), (228, 82, 82)


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
    """Месечен календар (Sunday-first). Червен pill върху деня на weekly reset."""
    cols = 7
    cw = w / cols
    reset_d = reset_date.astimezone().date() if reset_date else None
    # календарът показва МЕСЕЦА НА RESET-а (иначе при reset в следващ месец не се вижда)
    anchor = reset_d if reset_d else now.date()

    d.text((x0 + w / 2, y0), anchor.strftime("%B %Y").upper(), font=_font(FONT_BOLD, 13),
           fill=TXT, anchor="ma")
    hy = y0 + 22
    for i, ww in enumerate(["S", "M", "T", "W", "T", "F", "S"]):
        d.text((x0 + (i + 0.5) * cw, hy), ww, font=_font(FONT_REG, 11), fill=MUTED, anchor="ma")

    weeks = _calmod.Calendar(firstweekday=6).monthdayscalendar(anchor.year, anchor.month)
    gy = y0 + 40
    rh = min(18.0, (h - 40) / max(len(weeks), 1))

    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            if day == 0:
                continue
            cx = x0 + (c + 0.5) * cw
            cy = gy + (r + 0.5) * rh
            if reset_d is not None and day == reset_d.day:
                # solid червен pill: маркира конкретния weekly-reset ден. anchor.month
                # e reset_d.month, а `day != 0` иска ден от anchor месеца -> уникално
                pr = min(rh, cw) * 0.42
                d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=DB_RED)
                d.text((cx, cy), str(day), font=_font(FONT_BOLD, 11),
                       fill=(255, 255, 255), anchor="mm")
            else:
                d.text((cx, cy), str(day), font=_font(FONT_REG, 11), fill=TXT, anchor="mm")


def _ctx_status_color(status) -> tuple:
    """'safe'→TEAL, 'warn'→AMBER, 'critical'→RED. None (без данни) → MUTED."""
    if status == "critical":
        return DB_RED
    if status == "warn":
        return DB_AMBER
    if status == "safe":
        return TEAL
    return MUTED


def render_dashboard(usage, snap, w: int, h: int, profile=None, session=None) -> Image.Image:
    """Dashboard кадър (радиални %-пръстени). Тема по часа (light денем / dark вечер).

    `session` (session_client.SessionCtx | None) заменя дясната карта с CTX панел
    (Turing big layout). При None → показва '--' + празен bar. SmallTV branch-ът го
    игнорира (по design показва само пръстени).
    """
    _apply_theme(theme_for_now())
    img = Image.new("RGB", (w, h), DB_BG)
    d = ImageDraw.Draw(img)
    big = w >= 400

    fh = usage.five_hour if usage else None
    wk = usage.seven_day if usage else None
    fhp = fh.utilization if fh else None
    wkp = wk.utilization if wk else None
    models = snap.block.models if snap and snap.block else []
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

        # CTX карта (вдясно, цяла височина) — context tokens на активната Claude Code сесия
        cx0 = 302
        cx1 = w - 10
        d.rounded_rectangle([cx0, 52, cx1, h - 8], radius=12, fill=CARD)
        d.text((cx0 + 16, 70), "CTX", font=fb(14), fill=MUTED, anchor="lm")

        if session is not None:
            ctx_tokens = session.tokens
            status = sc.status_for(ctx_tokens)
            slug = sc.display_slug(session.project_slug)
        else:
            ctx_tokens = None
            status = None
            slug = "no active session"
        ctx_color = _ctx_status_color(status)

        num_s = f"{ctx_tokens / 1000:.1f}K" if ctx_tokens is not None else "--"
        lim_s = f"/ {sc.CTX_LIMIT // 1000}K"
        d.text((cx0 + 16, 108), num_s, font=fb(28), fill=ctx_color, anchor="lm")
        d.text((cx1 - 14, 116), lim_s, font=fr(13), fill=MUTED, anchor="rm")

        # progress bar 0 → CTX_LIMIT (клипваме >100% визуално, но цветът е червен)
        bx0, bx1_ = cx0 + 16, cx1 - 14
        by, bh = 142, 12
        d.rounded_rectangle([bx0, by, bx1_, by + bh], radius=6, fill=RING_TRACK)
        if ctx_tokens is not None:
            frac = min(1.0, ctx_tokens / max(sc.CTX_LIMIT, 1))
            fill_x = bx0 + int(round((bx1_ - bx0) * frac))
            if fill_x > bx0 + 2:
                d.rounded_rectangle([bx0, by, fill_x, by + bh], radius=6, fill=ctx_color)

        # source slug (кой проект / кое репо) — clip до 20 chars
        d.text(((cx0 + cx1) / 2, 174), slug[:20], font=fr(12), fill=MUTED, anchor="ma")

        # divider
        d.line([cx0 + 16, 196, cx1 - 14, 196], fill=RING_TRACK, width=1)

        # today / week $ (запазени от старата SESSION карта — полезен daily контекст)
        d.text((cx0 + 16, 218), "today", font=fr(13), fill=MUTED, anchor="lm")
        d.text((cx1 - 14, 218), f"${today:.2f}", font=fb(14), fill=TXT, anchor="rm")
        week_s = f"${snap.daily.week_cost:.0f}" if snap else "--"
        d.text((cx0 + 16, 244), "week", font=fr(13), fill=MUTED, anchor="lm")
        d.text((cx1 - 14, 244), week_s, font=fb(14), fill=TXT, anchor="rm")

        # RESTART badge — само при critical (сигнал за kill-and-restart)
        if status == "critical":
            by0, by1 = h - 42, h - 20
            d.rounded_rectangle([cx0 + 16, by0, cx1 - 14, by1], radius=6, fill=DB_RED)
            d.text(((cx0 + cx1) / 2, (by0 + by1) / 2), "RESTART SESSION",
                   font=fb(12), fill=(255, 255, 255), anchor="mm")
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


# --- SmallTV "ЛЕНТИ" палитра (ФИКСИРАНА terminal dark — независима от темата) ---
# Виж Claude Usage Physical Dashboard/handoff/smalltv-lenti-spec.md
L_BG = (11, 14, 20)
L_BORDER = (35, 42, 56)       # divider / track рамка
L_TXT = (226, 231, 240)
L_MUTED = (142, 152, 172)
L_DIM = (92, 102, 120)        # footer label-и
L_TEAL = (38, 178, 170)
L_AMBER = (245, 175, 55)
L_RED = (228, 82, 82)
L_TRACK = (14, 18, 25)        # фон на bar-а
L_REDBG = (42, 18, 24)        # crit track / strip fill
L_REDBORDER = (58, 36, 48)    # crit track рамка


def _l_rate_color(pct) -> tuple:
    """5H / WK: <70 teal, 70-90 amber, ≥90 red. None → muted."""
    if pct is None:
        return L_MUTED
    if pct >= 90:
        return L_RED
    if pct >= 70:
        return L_AMBER
    return L_TEAL


def _l_ctx_color(status) -> tuple:
    return {"critical": L_RED, "warn": L_AMBER, "safe": L_TEAL}.get(status, L_MUTED)


def _lenti_bar(d, x, y, w, h, frac, color, red=False, cells=15, seg=4, gap=2) -> None:
    """Segmented "лента": рамка + track фон + плътни сегменти до frac.

    Празната част е само тъмен track (без outline-нати клетки, за разлика от
    draw_segmented). Клетките се събират в (w-4)px съдържание: за w=92, cells=15
    (15·4 + 14·2 = 88 = 92-4). При смяна на ширината подай подходящ cells.
    """
    border = L_REDBORDER if red else L_BORDER
    track = L_REDBG if red else L_TRACK
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=2, outline=border, fill=track, width=1)
    ix, iy, ih = x + 2, y + 2, h - 4  # 1px рамка + 1px padding
    filled = int(round(max(0.0, min(1.0, frac)) * cells))
    for i in range(filled):
        cx0 = ix + i * (seg + gap)
        d.rectangle([cx0, iy, cx0 + seg - 1, iy + ih - 1], fill=color)


def render_smalltv_lenti(usage, snap, session=None, profile=None) -> Image.Image:
    """SmallTV 240×240 "ЛЕНТИ" изглед (Claude Design handoff).

    Terminal естетика: header `>_ slug` + модел, 3 segmented ленти (5H/WK/CTX),
    footer TODAY/BURN/RESET. Critical strip при CTX≥100K, alarm рамка+banner при
    rate-limit ≥95%. Фиксирана dark палитра (не се влияе от theme_for_now).
    Спец: Claude Usage Physical Dashboard/handoff/smalltv-lenti-spec.md
    """
    W = H = 240
    img = Image.new("RGB", (W, H), L_BG)
    d = ImageDraw.Draw(img)

    def fb(size):
        return _font(FONT_BOLD, size)

    def fr(size):
        return _font(FONT_REG, size)

    fh = usage.five_hour if usage else None
    wk = usage.seven_day if usage else None
    fhp = fh.utilization if fh else None
    wkp = wk.utilization if wk else None
    tok = session.tokens if session else None
    ctx_status = sc.status_for(tok) if tok is not None else None
    models = snap.block.models if snap and snap.block else []
    slug = sc.display_slug(session.project_slug) if session else "no session"

    breaches = alarm_breaches(usage)      # 5H/WK ≥ ALARM_PCT
    alarm = bool(breaches)
    critical = (tok is not None and tok >= sc.CTX_LIMIT) and not alarm  # alarm печели

    # --- header (пада под banner-а при alarm) ---
    if alarm:
        d.rectangle([15, 8, 225, 30], fill=L_RED)
        d.text((21, 19), "■ LIMIT ALARM", font=fb(13), fill=L_BG, anchor="lm")
        names = [n for n, p in (("5H", fhp), ("WK", wkp))
                 if p is not None and p >= ALARM_PCT]
        d.text((219, 19), f"{'·'.join(names)} ≥ {ALARM_PCT}%",
               font=fb(10), fill=L_BG, anchor="rm")
        hy, dy, rows_y = 46, 56, (82, 142, 202)
    else:  # critical вече няма strip → същото разстояние като normal
        hy, dy, rows_y = 17, 28, (66, 134, 202)

    d.text((10, hy), (">_ " + slug)[:20], font=fb(12), fill=L_TXT, anchor="lm")
    d.text((230, hy), model_label(models).upper(), font=fb(10), fill=L_AMBER, anchor="rm")
    d.line([10, dy, 230, dy], fill=L_BORDER, width=1)

    # --- 3 gauge ленти: label + лента + голямо число + под него countdown/лимит ---
    # 5H/WK subtext = колко остава до reset на брояча; CTX = лимит (или RESTART при crit).
    ctx_col = _l_ctx_color(ctx_status)
    ctx_frac = min(1.0, tok / max(sc.CTX_LIMIT, 1)) if tok is not None else 0.0
    ctx_val = f"{tok // 1000}K" if tok is not None else "--"
    if critical:
        ctx_sub = "RESTART"
    elif tok is not None:
        ctx_sub = f"/{sc.CTX_LIMIT // 1000}K"
    else:
        ctx_sub = ""
    c5, cwk = _l_rate_color(fhp), _l_rate_color(wkp)
    specs = [
        ("5H", (fhp or 0) / 100.0, c5, f"{fhp:.0f}%" if fhp is not None else "--",
         uc._fmt_delta(fh.remaining()) if fh else "--", c5 == L_RED),
        ("WK", (wkp or 0) / 100.0, cwk, f"{wkp:.0f}%" if wkp is not None else "--",
         uc._fmt_delta(wk.remaining()) if wk else "--", cwk == L_RED),
        ("CTX", ctx_frac, ctx_col, ctx_val, ctx_sub, critical),
    ]
    for (label, frac, color, val, sub, sub_red), y in zip(specs, rows_y):
        d.text((10, y - 6), label, font=fb(16), fill=L_MUTED, anchor="lm")
        _lenti_bar(d, 44, y - 16, 92, 16, frac, color, red=(color == L_RED))
        vcol = L_TXT if color == L_TEAL else color
        d.text((232, y - 4), val, font=fb(30), fill=vcol, anchor="rm")
        if sub:
            d.text((232, y + 22), sub, font=fb(13),
                   fill=L_RED if sub_red else L_MUTED, anchor="rm")

    # --- alarm рамка (5px, накрая — над всичко) ---
    if alarm:
        d.rectangle([0, 0, W - 1, H - 1], outline=L_RED, width=5)
    return img
