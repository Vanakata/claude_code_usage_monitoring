#!/usr/bin/env python
"""Design харнес — рендира render.render_dashboard() през всички изисквани state-ове
на native resolution, без хардуер. Fake data. Изход → work/design/out/<name>.png.

Ползване:
    .\.venv\Scripts\python.exe work\design\gen_states.py [theme_override]

theme_override (optional): 'dark' | 'light' — форсира CLAUDE_USAGE_THEME за всички
кадри (иначе всеки state сам сетва env-а).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import render as R          # noqa: E402
import usage_client as uc   # noqa: E402
import ccusage_client as cc # noqa: E402
import session_client as sc # noqa: E402

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

NOW = datetime.now(timezone.utc)  # реален now → remaining() (RESET footer) е положителен


def usage(fh_pct, wk_pct, fh_left=timedelta(hours=4, minutes=44),
          wk_left=timedelta(days=6, hours=2)):
    return uc.Usage(
        five_hour=uc.UsageWindow(fh_pct, NOW + fh_left),
        seven_day=uc.UsageWindow(wk_pct, NOW + wk_left),
        generated_at=NOW,
    )


def snap(today=33.77, week=80.6, models=("claude-opus-4-8",), burn=12.9,
         proj_cost=64.0):
    block = cc.ActiveBlock(cost_usd=12.34, total_tokens=3_700_000, elapsed_pct=40.0,
                           remaining_min=284, projected_cost=proj_cost,
                           projected_tokens=9_000_000, burn_cost_per_hour=burn,
                           models=list(models))
    return cc.Snapshot(has_active_block=True, block=block,
                       daily=cc.DailySnapshot(today_cost=today, today_tokens=41_000_000,
                                              week_cost=week, week_tokens=94_000_000),
                       generated_at=NOW)


def session(tokens):
    return sc.SessionCtx(
        tokens=tokens,
        project_slug="D--Projects-personal-projects-claude-code-usage-monitoring",
        session_id="preview-fake-uuid", updated_at=NOW, model="claude-opus-4-8")


PROFILE = SimpleNamespace(email="ivan.talmazov@a1.bg", full_name="", org_name="")


def save(name, img):
    p = os.path.join(OUT, name + ".png")
    img.save(p)
    print("wrote", p)


def render(name, w, h, theme, u, s, sess, profile=PROFILE):
    os.environ["CLAUDE_USAGE_THEME"] = theme
    save(name, R.render_dashboard(u, s, w, h, profile=profile, session=sess))


# ---- Turing 480x320 state-ове ----
render("turing_dark_safe",   480, 320, "dark",  usage(39, 9),  snap(), session(30_000))
render("turing_light_safe",  480, 320, "light", usage(39, 9),  snap(), session(30_000))
render("turing_dark_warn",   480, 320, "dark",  usage(55, 40), snap(), session(75_000))
render("turing_dark_crit",   480, 320, "dark",  usage(60, 44), snap(), session(120_000))
render("turing_dark_alarm",  480, 320, "dark",  usage(98, 75, fh_left=timedelta(minutes=10)), snap(), session(48_000))
render("turing_dark_nosess", 480, 320, "dark",  usage(39, 9),  snap(), None)

# ---- SmallTV 240x240 — вариант A: текущи дублирани рингове ----
render("smalltv_rings_dark",  240, 240, "dark",  usage(50, 75), snap(), None)
render("smalltv_rings_alarm", 240, 240, "dark",  usage(98, 75, fh_left=timedelta(minutes=10)), snap(), None)


# ---- SmallTV 240x240 — "ЛЕНТИ" (Claude Design handoff) ----
def render_lenti(name, u, s, sess):
    save(name, R.render_smalltv_lenti(u, s, session=sess, profile=PROFILE))


# match-нати спрямо handoff мокове: safe/warn/critical/alarm
render_lenti("lenti_safe",   usage(39, 9,  fh_left=timedelta(hours=5, minutes=33)), snap(today=33.77, burn=12.9), session(30_000))
render_lenti("lenti_warn",   usage(78, 31, fh_left=timedelta(hours=2, minutes=5)),  snap(today=41.20, burn=14.2), session(72_000))
render_lenti("lenti_crit",   usage(91, 42, fh_left=timedelta(minutes=48)),          snap(today=58.40, burn=16.8), session(104_000))
render_lenti("lenti_alarm",  usage(97, 44, fh_left=timedelta(minutes=22)),          snap(today=62.10, burn=17.4), session(55_000))
render_lenti("lenti_nosess", usage(39, 9,  fh_left=timedelta(hours=5, minutes=33)), snap(), None)

print("done ->", OUT)
