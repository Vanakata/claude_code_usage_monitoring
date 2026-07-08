# Claude Design brief — Claude Usage physical dashboard

> Copy-paste-ни в Claude Design като първо съобщение. Прикачи и текущите previews:
> `work/bg-previews/ctx_safe_30k.png`, `ctx_warn_75k.png`, `ctx_critical_120k.png`,
> `smalltv_with_email.png`. Те са текущият baseline (v1).

---

## Какво проектираш

Physical glance-only dashboard за Claude Code / Anthropic API power user. Показва
се на **две различни устройства** едновременно, захранени от един Python процес
който rendera PIL bitmap-и и ги пуска към хардуера.

**Целта**: за 1 секунда поглед да разбереш (a) колко rate-limit budget ти остава,
(b) в какво състояние е активната Claude Code сесия (context tokens близо ли са
до kill-and-restart прага), и (c) колко харчиш днес/седмично. Никакви interactions
— само display.

**Не е**: browser dashboard, mobile app, admin UI. Няма scroll, няма hover, няма
tooltip-и. Всичко което не се вижда веднага не съществува.

## Двете устройства (viewports)

| Устройство | Размер | Транспорт | Refresh | Роля днес |
|---|---|---|---|---|
| **Turing Smart Screen Rev A** | 480×320 landscape | USB serial | ≥60s, incremental frame regions | Пълен dashboard (рингове + календар + CTX карта) |
| **GeekMagic SmallTV Ultra** | 240×240 square | WiFi HTTP (full JPEG upload) | ≥60s (flash износване) | Само двата ринга (5H + WK) + email + модел |

**Ролята на SmallTV е отворена за пре-разпределение.** Ако смяташ че duplicating
рингове върху и двете е ниска стойност, предложи алтернатива — например SmallTV
да стане ambient индикатор (един голям метрик + status color-code), а Turing да
поеме цялата детайлна информация. Обоснови избора.

## Rendering pipeline (constraints)

- **PIL/Pillow** е single rendering primitive. Възможни примитиви:
  `rectangle`, `rounded_rectangle`, `arc`, `line`, `polygon`, `ellipse`, `text`.
  Няма native gradients, blur, shadows — може да се симулират, но всеки такъв
  трик изяжда CPU и мозъчен bandwidth. Плоски цветове са normal.
- **Шрифт**: Roboto Mono (bundled, cwd-independent). Отворен съм за **1 един
  допълнителен шрифт** ако си струва (напр. Inter за numbers). Не повече.
- **Няма анимации** — refresh е дискретен, всеки 60s. Не рисувай нищо което
  зависи от motion.
- **Turing = incremental paint**: пълен frame само при първи draw / смяна на
  ден / reset / theme swap / alarm entry. Дневни ъпдейти прекадряват отделни
  regions (номер, ринг). Layout трябва да е стабилен ⇒ elements не мърдат
  между refresh-ите. **SmallTV = full JPEG upload** всеки път, така че за него
  layout флуктуации нямат значение.
- **Bitmap output** — device-ите не разбират HTML/SVG. Каквото нарисуваш в PIL,
  това виждаш. Няма fallback fonts, няма emoji rendering (default).

## Теми и state

Три visual state-а трябва да съжителстват в един design system:

1. **Dark** — активна между 19:00 и 07:00 local. Текущи цветове (виж preview):
   BG `#10141E`, Card `#1C2232`, TXT `#E2E7F0`, MUTED `#8E98AC`, TEAL `#26B2AA`,
   AMBER `#F5AF37`, RED `#E45252`, TRACK `#2D3548`.
2. **Light** — активна между 07:00 и 19:00 local. Днес: BG `#ECEFF3`,
   Card `#FFFFFF`, TXT `#1C2A4A`, tuning е груб — има място за подобрение.
3. **Alarm** — когато 5H или WK ≥ 95%. Днес: hdr става red, red border около
   целия екран, warning triangle icon в header. Отделен overlay върху и dark, и
   light.

**Ново status измерение**: CTX (context tokens) има собствена thresholds система:
- 0–60k = safe (teal)
- 60k–100k = warn (amber) — активно време е да мислиш за end на сесията
- ≥100k = critical (red) — RESTART SESSION badge, kill-and-restart сигнал

Дизайнът трябва да третира CTX state-а като **първокласен**, не като страничен
badge. Това е информацията която най-често сменя стойност между refresh-ите и
най-често е причината юзърът да погледне.

## Данни които имаме (пълен инвентар)

Всичко идва от три data slot-а — свободно решавай кое да purchase-неш display-real
estate.

### /api/oauth/usage (реалните Anthropic rate limits)
- `five_hour.utilization` — 0-100%, 5-часовият rolling прозорец
- `five_hour.resets_at` — timestamp, computed remaining "4h44m"
- `seven_day.utilization` — 0-100%, седмичен прозорец
- `seven_day.resets_at` — timestamp, remaining "5d 23h"

### ccusage (локален CLI върху logs)
- `block.cost_usd` — $ похарчени в активния 5h billing блок
- `block.total_tokens` — общо токени в активния 5h блок
- `block.elapsed_pct` — % от 5h billing блока изтекъл (ВРЕМЕВО, не rate)
- `block.remaining_min` — минути до края на 5h billing блока
- `block.projected_cost` — ccusage прогноза за $ на края на блока
- `block.projected_tokens` — прогноза за tokens на края на блока
- `block.burn_cost_per_hour` — burn rate ($/час) в момента
- `block.models` — **list** от моделите ползвани в блока (opus/sonnet/haiku)
- `daily.today_cost` / `today_tokens` — днешен сбор
- `daily.week_cost` / `week_tokens` — последни 7 дни

### session_client (активната Claude Code сесия)
- `session.tokens` — точно каквото `/context` показва (input+cache_creation+cache_read)
- `session.project_slug` — от кое репо е сесията (парснат за читаемост, макс 20ch)
- `session.session_id` — UUID на jsonl-а
- `session.model` — модел на последния assistant reply
- `session.updated_at` — mtime, показва "жива" сесия vs "стара"
- Ако няма активност > 5 мин → `None` (показваме "no active session")

### profile
- `profile.email` — Anthropic account email
- `profile.full_name`, `profile.org_name` — засега не се ползват

## Кое е underutilized (data → design opportunities)

Тук ти давам списък с неща които днес НЕ се показват, но са налични и биха
носили стойност. Не е задължително да включиш всички — избери и обоснови:

1. **Burn rate** ($/час) — веднага показва "разхарчваш се бързо ли". Малко
   sparkline или единично число до session card-а.
2. **Projected end-of-block cost** — "at this rate you'll spend $64 by 21:03" —
   психологически много по-силно от "текущо $12".
3. **Elapsed % на 5h billing блока** vs. **5H rate-limit utilization %** — това
   са ДВЕ различни неща и днес показваме само второто. Първото показва къде си
   времево в 5h прозореца (полезно за pace).
4. **Множество модели** — днес показваме "най-силния" (opus). Ако си използвал
   opus+sonnet в блока, може да е polezno да видиш split (напр. миниатюрен bar:
   80% opus, 20% sonnet, оцветени различно).
5. **Trend / delta** — refresh-нахме преди 60s. Отиде ли CTX с +5K за минута?
   Малка стрелка ▲/▼ до числото щеше да казва повече от само абсолютно число.
6. **Reset countdown визуализация** — днес: "4h43m" текст. Мини pie/arc който
   се пълни към reset би бил по-glance-friendly.
7. **Session identity** — `project_slug` е там, но е малко и без weight. За
   power user който сменя проекти често, това е важен ориентир.
8. **Weekly progress спрямо typical usage** — ccusage знае последните 7 дни; ако
   днес си на $33 а средният ден е $20, това е сигнал.

## Какво искам от теб (deliverable)

### 1. Design tokens (JSON или таблица)
- **Палитра** dark / light / alarm state — hex codes с role labels (bg, card,
  accent, warn, critical, muted, track, text primary, text secondary)
- **Typography scale** — размери, weights, къде се ползват (metric primary,
  metric secondary, label, timestamp, badge). Ако предлагаш втори font, посочи
  role split.
- **Spacing scale** — 4/8/12/16... каквото ползваш
- **Corner radii** — cards, badges, pills
- **Stroke widths** — рингове, borders, dividers

### 2. Mockup PNG-и (native resolution!)

**Turing 480×320** — минимум тези state-ове:
- Normal, dark theme, session active, CTX safe (30k), 5H 39%, WK 9%
- Normal, light theme, session active, CTX safe
- CTX warn (75k, ~75% пълен) — dark
- CTX critical (120k, RESTART badge) — dark
- 5H alarm state (≥95%, red border + header) — dark
- Няма активна сесия ("no active session") — dark

**SmallTV 240×240** — минимум:
- Normal, dark, active
- Alarm state
- (Ако предложиш alternative role) — новата версия в 2-3 state-а

### 3. Layout rationale (кратко)
- Защо си сложил X на позиция Y (grid, visual hierarchy, F-pattern скан)
- Кои от underutilized данните включи и защо тези, а не други
- Ако си пре-разпределил SmallTV — какво прави тя сега и защо

### 4. (Optional) Micro-illustrations
Ако предложиш нови icon primitives (напр. по-хубав warning от текущия triangle,
model badges, session status dot), направи ги като плоски shapes които могат да
се преведат в PIL primitives. Никакви raster illustrations.

## Anti-goals

- **Skeuomorphism** — glass, drop shadows, gradients които се преструват на
  material. PIL не ги прави гладко и не пасват на 480×320.
- **Dashboard decoration** — всеки пиксел трябва да носи информация. Няма
  "decorative dots" или "abstract accent lines" без функция.
- **Movement suggestion** — motion blur, "arrow going forward" метафори. Refresh-
  ът е дискретен, не приличаме на streaming визуализация.
- **Emojis / pictorial icons от Unicode** — default PIL не ги render-ва цветно,
  а fallback fonts липсват. Собствени плоски shape icons — да; Unicode emoji — не.
- **Информация която прикрива алармата** — при alarm state червената рамка +
  header трябва да доминират; не я карай да се "състезава" с CTX badge примерно.
- **Duplicated information** — ако едно и също число се появи два пъти в различна
  форма, махни едното.

## Референции (какво харесвам стилово)

- **Apple Watch complications** — density на glance-only, no chrome, огромни
  цифри за primary metric.
- **Grafana single-stat panels** — плоски, честни, thresholds ясно оцветени.
- **Linear-style dark UI** — тъмни palettes които не са черни; teal/amber
  accents без пренасищане.

## Референции (какво НЕ харесвам)

- Стандартните smart-screen "cyber gauge" themes с glow effects.
- Windows Vista Sidebar gadgets.
- Всичко което изглежда като "PC monitoring" (CPU/RAM/temp) — това е data
  dashboard, не sysmon.

---

**Готов съм да итерирам. Върни първи draft (mockups + tokens), после ще посочим
кое остава и кое пипаме.**
