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
