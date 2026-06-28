# turing-claude-usage

Показва Claude Code usage статистики в реално време на малък USB дисплей (Turing Smart Screen).

## Hardware (разузнато 2026-06-19)

| Параметър | Стойност |
|---|---|
| Модел | Turing Smart Screen **Revision A**, 3.5" |
| Резолюция | 480 × 320 |
| Порт | **COM5** |
| USB ID | `VID_1A86 & PID_5722` (`USB35INCHIPSV2`) |
| Serial чип | CH340 (QinHeng) |

Rev A е най-добре поддържаната ревизия в библиотеката по-долу — стабилен serial протокол.

## Зависимости

- **Дисплей драйвер:** [`mathoudebine/turing-smart-screen-python`](https://github.com/mathoudebine/turing-smart-screen-python) — custom data през `library/sensors/sensors_custom.py` (`CustomDataSource`, методи `as_numeric()` / `as_string()`).
- **Данни:** [`ccusage`](https://github.com/ryoppippi/ccusage) v20.0.14 — вече инсталиран глобално. Полезни команди:
  - `ccusage blocks --json` → 5-часов прозорец (за limit %)
  - `ccusage daily --json` → дневен/сесиен breakdown (token/cost)

## Архитектура

```
ccusage --json  →  Python parser  →  CustomDataSource  →  Turing Rev A (COM5)
                                          ↑ refresh loop 30–60s
```

Python 3.9+. Виж `work/tomorrow.md` за активната задача.

## Quick setup (Windows)

Еднократно, от root на проекта (clone на драйвер либ-а + venv + зависимости + проверки):

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

После: вкарай монитора и `./.venv/Scripts/python.exe run.py` (виж "Refresh loop + автостарт" по-долу). Изисква Node (за `ccusage`) и да си логнат в Claude Code (за `/usage` token-а). NB: показва usage-а на акаунта на тази машина.

### Старт на нова машина (служебен лаптоп)

```powershell
# 1. clone + (ако не е merge-нат в master) feature branch-а
git clone https://github.com/Vanakata/claude_code_usage_monitoring.git
cd claude_code_usage_monitoring
git checkout feat/smalltv-http-transport   # или master, ако PR-ът е merge-нат

# 2. setup (clone на драйвер либ-а + venv + зависимости)
powershell -ExecutionPolicy Bypass -File setup.ps1

# 3. пусни според дисплея(ите) — env в PowerShell:
$env:CLAUDE_USAGE_TARGET = "both"                  # turing | smalltv | both
$env:CLAUDE_USAGE_SMALLTV_IP = "192.168.x.x"       # IP на SmallTV в ТАЗИ мрежа (само за smalltv/both)
.\.venv\Scripts\python.exe run.py
```

Помни: трябва Node (`ccusage`) + логнат Claude Code на лаптопа; SmallTV и лаптопът на **една WiFi мрежа**; показва усиджа на акаунта **там** (на API key гейджовете са `--`); autostart task-ът иска admin (за TURMO kill) — без admin пускаш `run.py` ръчно.

## POC — пускане (display handshake)

Доказва, че serial протоколът (Rev A) + портът (COM5) работят: светва дисплея със статичен текст + число. Никаква ccusage логика.

```bash
# 1. Clone-ни драйвер библиотеката (gitignore-ната, не се commit-ва)
git clone https://github.com/mathoudebine/turing-smart-screen-python.git

# 2. venv + минимални зависимости (само за POC: pyserial/Pillow/numpy)
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install pyserial Pillow numpy

# 3. Пусни
./.venv/Scripts/python.exe poc.py
```

Очакван резултат: на COM5, landscape 480×320, черен фон с `CLAUDE USAGE` (бяло) + `42` (зелено).

### ⚠️ COM5 е зает / `PermissionError(13) Access is denied`

Turing-ската vendor app **`TURMO.exe`** (TURING MOnitor) auto-start-ва и граби COM5 ексклузивно — два USBSER handle-а. Тя е **protected процес**, та:
- не се вижда с non-elevated `handle.exe`;
- не се убива с обикновен `Stop-Process` — трябва elevated `taskkill /F /IM TURMO.exe`.

Преди да пуснеш POC-а, убий я (или я махни от autostart). Същото важи и за **Stream Dock AJAZZ** app-а, ако е инсталиран — той също claim-ва CH340 порта. Kaspersky-то НЕ е виновникът (проверено).

Бележки по hardware-а: устройството се enumerate-ва като `USB Serial Device` (генеричен `usbser.sys`, не CH340 драйвер) и докладва sub-revision `USBMONITOR_3_5` на `HELLO`. Това не пречи на Rev A протокола.

## Live layout

```bash
./.venv/Scripts/python.exe display.py    # рисува един кадър (виж refresh loop по-долу)
```

Рисува на 480×320 (matrix фон `assets/background.png`):
- **5H / WK gauge** — реалните Claude rate-limit % + reset, същите като `/usage`
- **SESSION** — cost/tokens на активния 5h блок (от ccusage)

### Данни

| Метрика | Източник |
|---|---|
| 5h / weekly % + reset (`usage_client.py`) | `GET https://api.anthropic.com/api/oauth/usage` с OAuth token от `~/.claude/.credentials.json` (header `anthropic-beta: oauth-2025-04-20`) |
| session cost/tokens (`ccusage_client.py`) | `ccusage blocks/daily --json` |

⚠️ `/api/oauth/usage` е **недокументиран** endpoint (reverse-engineer-нат от Claude Code `extension.js`). Дава точните `/usage` % — за разлика от ccusage approximation, защото лимитът тежи по модел вътрешно. Може да се счупи на Claude Code ъпдейт. Token-ът изтича; Claude Code го refresh-ва, иначе ще трябва собствен refresh през `/v1/oauth/token`.

Фонът се генерира с `tools/gen_background.py` (matrix / code / circuit варианти).

## Refresh loop + автостарт

```bash
./.venv/Scripts/python.exe run.py    # върти: fetch -> render -> sleep
```

Loop-ът обновява дисплея на всеки `CLAUDE_USAGE_INTERVAL` секунди (default 60). Преживява временни грешки (network/ccusage/usage — лог + пази стария кадър), reconnect-ва при serial проблем, и **убива TURMO.exe** ако се върне и грабне COM5. Token-ът се refresh-ва автоматично на 401 (виж `usage_client.refresh_token`).

**Автостарт (Windows, на logon, elevated):** от **elevated** PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
Start-ScheduledTask -TaskName ClaudeUsageDisplay   # стартирай веднага
```

Task-ът трябва да е **elevated** (Highest), иначе не може да убие protected `TURMO.exe`. Логове: `work\run.log`. Махане: `Unregister-ScheduledTask -TaskName ClaudeUsageDisplay -Confirm:$false`.

## SmallTV Ultra — втори дисплей (HTTP/WiFi)

GeekMagic SmallTV Ultra (240×240) е самостоятелно WiFi устройство — рендираме кадър на PC-то и го push-ваме по HTTP. Споделя `render.py` / `ccusage_client.py` / `usage_client.py` с Turing backend-а.

```bash
CLAUDE_USAGE_TARGET=smalltv CLAUDE_USAGE_SMALLTV_IP=192.168.100.15 ./.venv/Scripts/python.exe run.py
```

`CLAUDE_USAGE_TARGET`: `turing` (default) кара serial дисплея; `smalltv` — SmallTV по HTTP; **`both`** — двата едновременно от ЕДИН процес (едно `/usage` викане, не удвоява rate-limit-а; всеки backend с независим error handling). И PC-то, и дисплеят трябва да са на една мрежа.

Autostart task-ът (`tools/start.cmd`) е настроен на **`both`** — кара двата дисплея. Edit-ни `start.cmd` ако искаш само единия.

### API (reverse-engineer-нат от web UI-то)

| Действие | Endpoint |
|---|---|
| Upload | `POST /doUpload?dir=/image/` — multipart, поле `file`, **JPEG** |
| Photo Album | `GET /set?theme=3` |
| Изключи авто-ротация | `GET /set?i_i=3600&autoplay=0` |
| Покажи кадър | `GET /set?img=/image/dashboard.jpg` |
| Изтрий файл | `GET /delete?file=<urlencoded>` |
| Списък | `GET /filelist?dir=/image/` |

Фиксирано име `dashboard.jpg` → **презаписва** (flash е малък, не трупа файлове). Cleanup при старт трие само наши файлове (НЕ user pics). Flash износване → refresh 60s.
