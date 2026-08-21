# Design tokens — Claude Usage dashboard (v2 draft)

Source of truth: `render.py` (`_apply_theme`, palette globals). Тази таблица е
човекочетимото огледало — при разминаване кодът печели.

## Палитра

| Role | Token | Dark | Light |
|---|---|---|---|
| Background | `DB_BG` | `#10141E` | `#ECEFF3` |
| Card fill | `CARD` | `#1C2232` | `#FFFFFF` |
| Card border | `CARD_BORDER` | `#242C3E` | `#DCE1E9` |
| Header band | `NAVY` | `#161C2E` | `#1C2A4A` |
| Text primary | `TXT` | `#E2E7F0` | `#1C2A4A` |
| Text on header | `HEADER_TXT` | `#ECF0F8` | `#F4F7FA` |
| Text secondary | `MUTED` | `#8E98AC` | `#687488` |
| Track (ring/bar empty) | `RING_TRACK` | `#2D3548` | `#DEE3EA` |
| Accent / model | `DB_AMBER` | `#F5AF37` | `#C6840C` |
| Ring low / safe | `TEAL` | `#26B2AA` | `#108C86` |
| Warn | `DB_AMBER` | `#F5AF37` | `#C6840C` |
| Critical / alarm | `DB_RED` | `#E45252` | `#D04040` |

**Защо light accent-ите са потъмнени:** `#26B2AA` teal и `#F5AF37` amber избеляват
до нечитаемост върху бяла карта. Light темата ползва потъмнени варианти (`#108C86`,
`#C6840C`) за да държат WCAG-приемлив контраст на `#FFFFFF`.

## Threshold-и (state color mapping)

| Метрика | safe (teal) | warn (amber) | critical (red) |
|---|---|---|---|
| Rate limit ринг (`_ring_color`) | < 70% | 70–90% | ≥ 90% |
| CTX (`session_client`) | < 60K | 60K–100K | ≥ 100K |
| Alarm (`ALARM_PCT`) | — | — | 5H или WK ≥ 95% |

CTX статус-думи: safe → `HEADROOM`, warn → `WRAP UP SOON`, critical →
`RESTART NOW` / `RESTART SESSION` badge.

## Typography (Roboto Mono — bundled)

| Role | Font | Size | Къде |
|---|---|---|---|
| CTX hero | Bold | 40 | дясна карта, context tokens |
| Metric primary | Bold | 30 | TODAY $, ambient CTX 46 |
| Ring % | Bold | 19 (Turing) / 28 (SmallTV) | център на ринг |
| Header title | Bold | 20 | "CLAUDE USAGE" |
| Model badge | Bold | 16 | header center/right |
| Section label | Regular | 12 | "TODAY", "CTX" |
| Metric secondary | Bold | 14 | burn/proj/week стойности |
| Row label | Regular | 13 | burn/proj/week етикети |
| Status word / badge | Bold | 12 | CTX статус лента |
| Timestamp / meta | Regular | 11 | "Opus 4.8 · live", remaining |

> Втори шрифт (Inter за числата) — **не** въведен в тоя draft. Roboto Mono държи
> моноширинните цифри стабилни между refresh-ите (важно за incremental paint —
> числото не мърда). Ако искаш по-плътен hero, кажи и пробвам Inter само за CTX/TODAY.

## Spacing / geometry

| Token | Стойност |
|---|---|
| Card padding (inner) | 16px |
| Card radius | 12px |
| Badge / pill radius | 6px |
| Row step (SPEND) | 20px |
| Header height | 44px (Turing) / 26–30px (SmallTV) |
| Ring stroke | 10px (Turing) / 13–15px (SmallTV ambient) |
| Ring radius | 37px (Turing) / 50–74px (SmallTV) |
| Progress bar height | 12px |
| Divider / card border | 1px |
| Alarm frame | 6px (Turing) / 5px (SmallTV) |

## Layout карта (Turing 480×320)

```
┌───────────────────────────────────────────────┐ 44  header
│ CLAUDE USAGE      Opus 4.8      email           │
├──────────────────────────┬──────────────────────┤
│  (5H ring)  (WK ring)    │  CTX            ●     │
│   39%         9%         │  30K      / 100K      │  дясна
│   5H          WK         │  ▓▓▓░░░░░░░░░          │  колона:
│   5h33m       6d 2h      │  usage-monitoring     │  CTX
│ ┌── SPEND card ────────┐ │  Opus 4.8 · live      │  ХЕРОЙ
│ │ TODAY                │ │                       │
│ │ $33.77 ▲             │ │                       │
│ │ ───────────────────  │ │  ┌─ HEADROOM ──────┐  │
│ │ burn        $12.9/h  │ │  └─────────────────┘  │
│ │ proj    $64 · 05:14  │ │                       │
│ │ week          $81    │ │                       │
│ └──────────────────────┘ │                       │
└──────────────────────────┴──────────────────────┘
```
