# SmallTV „ЛЕНТИ" (2c) — спецификация за render.py

Заменя `render_smalltv_ambient`. 240×240, Pillow, Roboto Mono (FONT_BOLD/FONT_REG).

Референтни картинки (1:1 pixel мокове, в тази папка):
- `smalltv_lenti_safe.png` — safe
- `smalltv_lenti_warn.png` — warn
- `smalltv_lenti_critical.png` — critical (RESTART strip)
- `smalltv_lenti_alarm.png` — alarm (рамка + banner)

## Палитра (RGB)

| Token | Hex | RGB |
|---|---|---|
| BG | `#0B0E14` | (11, 14, 20) |
| BORDER (divider/track) | `#232A38` | (35, 42, 56) |
| TXT | `#E2E7F0` | (226, 231, 240) |
| MUTED | `#8E98AC` | (142, 152, 172) |
| DIM | `#5C6678` | (92, 102, 120) |
| TEAL | `#26B2AA` | (38, 178, 170) |
| AMBER | `#F5AF37` | (245, 175, 55) |
| RED | `#E45252` | (228, 82, 82) |
| RED_BG (crit track/strip fill) | `#2A1218` | (42, 18, 24) |
| RED_BORDER (crit track) | `#3A2430` | (58, 36, 48) |

## Геометрия (padding 10 отвсякъде)

**Header** — project ляво: `">_ " + slug[:18]`, fb(11), TXT, anchor `lm` @ (10, 16); модел дясно: fb(9), AMBER, anchor `rm` @ (230, 16). Divider линия BORDER y=26, x 10→230.

**3 gauge реда** (5H, WK, CTX) — центрове y = 58, 105, 152:
- Label: fr(9), MUTED, `lm` @ (10, y)
- Bar: x=38, w=140, h=12 — 1px BORDER рамка, вътре 1px padding, fill със `draw_segmented` (сегмент 4px, gap 2px). Track фон `#0E1219`; при red state рамка RED_BORDER, фон RED_BG.
- Value: fb(16), `rm` @ (230, y). 5H/WK: `{pct}%`; CTX: `{tok//1000}K`.

**Footer** — divider BORDER y=192; 3 равни колони (центрове x = 46, 120, 194), вертикални разделители BORDER на x=83 и x=157 (y 196→222):
- Label: fr(8), DIM, `mm` @ (cx, 200) — `TODAY` / `BURN` / `RESET`
- Value: fb(13), `mm` @ (cx, 214) — `$33.77` (AMBER) / `$12.9/h` (TXT) / `5h33m` (TXT)

## Цветова логика

- **5H / WK** — съществуващия `_ring_color`: <70 TEAL, 70–90 AMBER, ≥90 RED.
- **CTX** — по session status: <60K TEAL, 60–100K AMBER, ≥100K RED (cap bar на 100%).
- Value текстът е TXT при teal, иначе цвета на бара.
- Без сесия: CTX стойност `--`, празен bar.

## Състояния

**WARN (3a)** — само per-metric оцветяване, никакъв друг chrome.

**CRITICAL (3b)** — при CTX ≥ 100K: strip между гейджовете и footer-а (x 10→230, h=18, y≈166–184): fill RED_BG, 1px RED рамка, radius 3; ляво `RESTART SESSION` fb(10) RED, дясно `ctx over 100K` fr(9) RED. Гейдж зоната се свива (редове y = 52, 96, 140).

**ALARM (3c)** — при 5H или WK ≥ ALARM_PCT (95): 
- 5px RED рамка по цялото платно
- Banner най-отгоре (вътре в рамката, x 15→225, h=18): fill RED, ляво `■ LIMIT ALARM` fb(11) цвят BG, дясно breach-а (`5H ≥ 95%`) fb(9) BG
- Header пада под banner-а, редове y = 66, 108, 150; RESET стойността RED.
- Alarm печели пред Critical strip (не се показват едновременно).

## Текстура (по избор)

CRT scanlines: хоризонтална 1px линия rgba(0,0,0,~30) на всеки 3px върху целия кадър (composite с alpha). Пропусни, ако JPEG артефактите я зацапват на реалния дисплей.
