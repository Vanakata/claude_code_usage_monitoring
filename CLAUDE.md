# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Показва Claude `/usage` (5h + weekly %) на Turing Smart Screen Rev A (USB serial, 480×320) и/или GeekMagic SmallTV Ultra (240×240, WiFi). README.md покрива hardware + setup — не дублирай тук.

## Команди

```powershell
# Setup (clone driver lib + venv + deps), idempotent
powershell -ExecutionPolicy Bypass -File setup.ps1

# Refresh loop — target идва от $env:CLAUDE_USAGE_TARGET (turing|smalltv|both)
.\.venv\Scripts\python.exe run.py

# Един кадър за debug (без loop)
.\.venv\Scripts\python.exe display.py          # Turing
.\.venv\Scripts\python.exe display_smalltv.py  # SmallTV

# Data layer-и самостоятелно (stdout, без display)
.\.venv\Scripts\python.exe usage_client.py     # /api/oauth/usage
.\.venv\Scripts\python.exe ccusage_client.py
.\.venv\Scripts\python.exe profile_client.py   # email/org

# Layout preview без хардуер
.\.venv\Scripts\python.exe tools\preview_layout.py
```

Няма test suite/linter. Промени се верифицират през `display*.py` или `preview_layout.py`.

## Env vars

| Var | Default | За какво |
|---|---|---|
| `CLAUDE_USAGE_TARGET` | `turing` | `turing` / `smalltv` / `both` |
| `CLAUDE_USAGE_INTERVAL` | `60` | сек. между refresh-ите |
| `CLAUDE_USAGE_COM_PORT` | `AUTO` | override; AUTO търси VID/PID `1A86:5722` |
| `CLAUDE_USAGE_BRIGHTNESS` | `15` | 0–255 (Turing) |
| `CLAUDE_USAGE_SMALLTV_IP` | `192.168.100.15` | IP в текущата мрежа |
| `CLAUDE_USAGE_SMALLTV_BRIGHTNESS` | `10` | −10..100 (SmallTV `/set?brt=`) |
| `CLAUDE_USAGE_THEME` | `auto` | `light` / `dark` / `auto` (по час) |
| `CLAUDE_USAGE_DAY_START` / `_DAY_END` | `7` / `19` | граници за auto theme |
| `CLAUDE_USAGE_ALARM_PCT` | `95` | праг за червена аларма + рамка |
| `CLAUDE_USAGE_SETTLE` | `4` | сек. чакане след replug (MCU boot) |

## Архитектура

```
data layer            render layer         transport layer
─────────────         ────────────         ─────────────────
usage_client    ─┐                         display.py (Turing serial, COM)
ccusage_client  ─┼─► render.py     ─►      display_smalltv.py (HTTP push)
profile_client  ─┘                                ▲
                                                  │
                       run.py — един loop, едно /usage викане,
                       подава snapshot-а на всеки driver (both = 2-та)
```

Ключови инварианти:

- **`run.py` диспечер.** Построява списък от driver-и (`TuringDriver` / `SmallTvDriver`) според `CLAUDE_USAGE_TARGET`. Дърпа `fetch_usage()` + `fetch_snapshot()` **веднъж** и подава на всеки. `both` НЕ удвоява rate-limit-а към `/api/oauth/usage`. Всеки driver е изолиран — единият падне (мрежа/serial), другият продължава.
- **`render.py` е чист рендер** — без I/O. Един `render_dashboard(usage, snap, w, h)` обслужва и 480×320 (Turing), и 240×240 (SmallTV); branchва се вътре по `big = w >= 400`. Промени в layout/цветове/threshold-и → тук. SmallTV получава САМО пръстени (без cost/tokens) по дизайн.
- **`display.py` patch-ва драйвер либ-а на runtime:**
  1. `LcdCommRevA.openSerial` — оригиналът прави `os._exit(0)` при липсващ/зает порт (нехванаем kill с код 0 → Task Scheduler не рестартира). Patch-нат → `raise SerialException` → `run.py` reconnect.
  2. `WriteLine` (`_resilient_write_line`) — при serial срив насред bitmap вдига `_needs_reinit`; `run.py` го вижда и прави чист HELLO-resync + Clear + orientation на следващия тик, иначе кадърът е разместен в portrait.
  Рендира **инкрементално** — пълен кадър само при connect / смяна на ден / reset / тема / аларма (виж `_DYN_REGIONS`).
- **`display_smalltv.py`** — JPEG (не PNG!) → multipart POST на `/doUpload?dir=/image/` с фиксирано име `dashboard.jpg` (презапис, не трупане на flash) → `GET /set?img=...`. При `connect()`: cleanup на наши файлове (НЕ user pics) + `theme=3` (Photo Album) + `i_i=3600&autoplay=0` (без авто-ротация) + `brt=<N>` (яркост, default 10). Brightness endpoint-ът е `/set?brt=N`, N: −10..100.
- **`turing-smart-screen-python/`** е external dep — clone-ва се при setup, **не** е committed (`.gitignore`). Patch-вай на runtime от `display.py`, не вътре в clone-а.

## Reverse-engineered endpoints (крехки)

Извлечени от Claude Code `extension.js` v2.1.183. Може да се счупят при ъпдейт — третирай fail-soft.

| Endpoint | За какво |
|---|---|
| `GET /api/oauth/usage` (api.anthropic.com) | реалните 5h + weekly % + reset |
| `GET /api/oauth/profile` (api.anthropic.com) | email + org name (header overlay) |
| `POST /v1/oauth/token` (platform.claude.com) | refresh при 401 (`client_id` в `usage_client.py`) |

Headers и за двата GET-а: `Authorization: Bearer <oauth>`, `anthropic-beta: oauth-2025-04-20`. Token се чете от `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`. **На 401 автоматичен refresh → retry**; credentials се пишат атомарно (`.tmp` + `os.replace`), за да не corrupt-нат при паралелен Claude Code refresh.

**Кой акаунт се показва** = този, в който Claude Code на ТАЗИ машина е логнат (interactive `claude login`, не API key).

## Hardware уловки

- **TURMO.exe** (Turing vendor app) auto-start-ва и държи COM5 ексклузивно като **protected процес**. Иска elevated `taskkill /F /IM TURMO.exe` — `Stop-Process` няма ефект. Затова autostart task-ът ходи с **Highest privileges**.
- Stream Dock AJAZZ vendor app също claim-ва CH340 порта (същия проблем).
- След replug CH340 bridge е готов преди MCU-то → `connect()` retry-ва `InitializeComm` (HELLO) до 10 пъти със 2 сек. пауза. Без resync байтовете се разместват → кадърът излиза размазан в portrait.
- **SmallTV е last-write-wins** — ако друг PC също push-ва към същия IP, картините се сменят. И двата хоста на една локална мрежа = задължително. Refresh ≥ 60s (flash износване).

## Стил

Глобалните инструкции в `~/.claude/CLAUDE.md` важат (БГ език, термини на EN, бро-стил). Коментарите в кода и git history-то са на български — продължавай в същия стил при редакция.
