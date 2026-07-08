#!/usr/bin/env python
"""Offline preview на layout-а (без дисплей) -> work/bg-previews/layout_preview.png.

Ползва истинските display.draw_static + display.render през fake LCD, който рисува
върху PIL canvas. Само за визуална проверка.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import display as d  # noqa: E402
import usage_client as uc  # noqa: E402
import ccusage_client as cc  # noqa: E402
import session_client as sc  # noqa: E402


class FakeLcd:
    def __init__(self):
        self.canvas = Image.new("RGB", (480, 320), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.canvas)

    def get_width(self):
        return 480

    def get_height(self):
        return 320

    def DisplayBitmap(self, path):
        self.canvas.paste(Image.open(path).convert("RGB").resize((480, 320)), (0, 0))
        self.draw = ImageDraw.Draw(self.canvas)

    def DisplayPILImage(self, img, x=0, y=0):
        self.canvas.paste(img, (x, y))

    def DisplayText(self, text, x, y, font=None, font_size=20, font_color=(255, 255, 255),
                    background_image=None, **kw):
        f = ImageFont.truetype(font, font_size)
        self.draw.text((x, y), text, font=f, fill=font_color)


now = datetime.now(timezone.utc)
usage = uc.Usage(
    five_hour=uc.UsageWindow(39.0, now + timedelta(hours=4, minutes=44)),
    seven_day=uc.UsageWindow(9.0, now + timedelta(days=6, hours=2)),
    generated_at=now,
)
block = cc.ActiveBlock(cost_usd=12.34, total_tokens=3_700_000, elapsed_pct=40.0,
                       remaining_min=284, projected_cost=64.0, projected_tokens=9_000_000,
                       burn_cost_per_hour=12.9, models=["claude-opus-4-8"])
snap = cc.Snapshot(has_active_block=True, block=block,
                   daily=cc.DailySnapshot(today_cost=33.77, today_tokens=41_000_000,
                                          week_cost=80.6, week_tokens=94_000_000),
                   generated_at=now)

session = sc.SessionCtx(
    tokens=52_500,
    project_slug="D--Projects-personal-projects-claude-code-usage-monitoring",
    session_id="preview-fake-uuid",
    updated_at=now,
    model="claude-opus-4-7",
)

fake = FakeLcd()
d.render(fake, usage, snap, session)  # render() рисува пълния dashboard кадър при първо извикване
out = os.path.join(ROOT, "work", "bg-previews", "layout_preview.png")
fake.canvas.save(out)
print("wrote", out)
