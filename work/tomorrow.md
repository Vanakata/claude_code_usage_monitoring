# Tomorrow's tasks

<!--
ФОРМАТ — едно заглавие = един PR. Една активна задача наведнъж.
Контекст / Scope / DoD. Следващите се добавят след одобрение на предишната.
-->

## 🔖 HANDOFF (къде сме — 2026-06-20, късно)

Проектът е **функционален end-to-end** и качен на GitHub (`master`, последен `ef64cab`).
Върви като Scheduled Task `ClaudeUsageDisplay` (на тая машина, elevated, AtLogOn).

**Текущо състояние:** `/api/oauth/usage` връща **HTTP 429** (rate-limit от многото тестови
рестарти, НЕ е бъг). Затова дисплеят показва `5H --% / WK --%`. Кодът кешира и **сам**
попълва реалните числа при първото успешно дърпане — само трябва да падне 429-цата.

**Да се потвърди утре:**
1. 429 паднала ли е → реалните % върнаха ли се сами? (виж `work/run.log` или монитора)
2. Дръпни/върни кабела → очаквано: най-много 1 разместен кадър, после чист; **никога бял екран**.

**Фиксове от тая сесия (reconnect устойчивост):** AUTO порт по VID/PID, preflight преди
connect, HELLO-resync, `_resilient_write_line` (reopen+resend + `_needs_reinit`),
always-render с кеш (екранът винаги рисува, дори без данни). Виж git log.

**Капани (важни за setup на лаптопа):**
- `TURMO.exe` (Turing vendor app) граби COM5 — protected, иска **elevated** taskkill.
- библиотечният `openSerial` прави `os._exit(0)` при липсващ/зает порт → затова preflight-ваме.
- Pro лимитът тежи **по модел** (Opus яде бързо) → ccusage approximation е невъзможна;
  затова четем реалния `/usage` от `/api/oauth/usage` (виж README).

**Продължаване от лаптопа:** `git clone` + setup от README. NB: ще показва usage-а на
акаунта в Claude Code на ОНАЗИ машина.

---

## SmallTV Ultra — втори transport (HTTP/WiFi) — ✅ DONE

Реализирано на branch `feat/smalltv-http-transport`: споделен `render.py` (helpers + 240 renderer), `display_smalltv.py` (HTTP transport), `run.py` backend switch (`CLAUDE_USAGE_TARGET`), 240×240 matrix фон, cleanup (хирургически — само наши файлове). Delete endpoint-ът е `GET /delete?file=` (reverse-engineer-нат), auto-switch off е `/set?i_i=3600&autoplay=0`. Транспортът е тестван на живо (dashboard.jpg на устройството). Turing backend-ът непокътнат (re-verified). Виж README "SmallTV Ultra".

<!-- оригинален scope (за референция):

Контекст: добавяме GeekMagic SmallTV Ultra като **втори дисплей** за същите Claude usage данни. За разлика от Turing (serial), SmallTV е самостоятелно WiFi устройство — рендираме кадър на PC-то и го **push-ваме по HTTP**. Транспортът е **тестван на живо и потвърден** (виж "Закован API" долу). Целта: един проект, два transport-а, споделен data/render код — НЕ нов repo.

**Закован API (потвърден end-to-end на 192.168.100.15):**
- Upload: `POST http://<ip>/doUpload?dir=/image/` — multipart, поле `file`, **JPEG** (тествано с quality 90).
- Photo Album режим (веднъж при старт): `GET http://<ip>/set?theme=3`.
- Покажи кадъра: `GET http://<ip>/set?img=/image/<filename>`.
- Device: **240×240**, IP `192.168.100.15` (env-конфигурируем). И PC-то, и дисплеят трябва да са на една мрежа.

Scope:
- **Рефактор:** извади render логиката от `display.py` в споделен модул (напр. `render.py`), параметризиран по размер (480×320 Turing / 240×240 SmallTV). Споделят се `ccusage_client.py`, `usage_client.py`, gauge-ове, цветове, `_model_label`, threshold-ите — без дублиране.
- **Нов `display_smalltv.py`** (тънък HTTP transport): render 240×240 → save JPEG → `POST /doUpload` → `theme=3` (веднъж) → `/set?img`. Фиксирано име `dashboard.jpg`, за да **презаписва**, а не да трупа файлове.
- **`run.py`** да избира backend по env (`CLAUDE_USAGE_TARGET=turing|smalltv`), със същия refresh loop + error handling.
- **240×240 layout** — по-тясно от 480×320: компактни 5H/WK gauge-ове + session числа. Преподреди, не само scale.
- **Cleanup механизъм:** намери точната delete команда (inspect-ни `deletef()`/`setgif()` в browser DevTools на web UI-то — `/set?del` НЕ работи) и изтрий стари кадри при старт; изтрий и тестовия `claude_test.jpg`.

Уловки (вече установени):
- **JPEG, не PNG** (тествано).
- `theme=3` веднъж при connect; изключи **auto-switch** на Photo Album, иначе ще ротира с другите картинки.
- **Refresh 60s** — SmallTV пише на вътрешен flash при upload; чести uploads износват flash-а.

DoD: `CLAUDE_USAGE_TARGET=smalltv python run.py` рендира реалните Claude usage данни (5H/WK + session) на SmallTV-то на 240×240, обновява на 60s, без да трупа файлове; Turing backend-ът продължава да работи непокътнат; commit на branch `feat/smalltv-http-transport`, PR срещу `master`.

-->

## Опашка (опционални)

- Verify replug self-heal след като 429 падне (виж по-горе).
- Лек backoff при 429, за да не хамерим (сега просто кешира — ок).
- `.exe` пакет (PyInstaller) за лесно местене без clone/Python.
- Втори изглед (седмичен график от ccusage daily), аларма при висок %.
