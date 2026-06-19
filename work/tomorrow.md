# Tomorrow's tasks

<!--
ФОРМАТ — едно заглавие = един PR. Една активна задача наведнъж.
Контекст / Scope / DoD. Следващите се добавят след одобрение на предишната.
-->

## ✅ DONE — POC: запали дисплея (hardware handshake)

Светна на branch `poc/display-handshake` (commit 6cec590). Блокерът се оказа vendor app `TURMO.exe`, която граби COM5 (protected процес — иска elevated taskkill). Подробности в README "COM5 е зает".

---

## ccusage data layer (АКТИВНА)

Контекст: POC-ът светна със статичен "42". Сега правим слоя, който вади реални Claude usage данни от `ccusage`. САМО data слой — layout на дисплея и refresh loop са отделни PR-и след това.

Scope:
- `ccusage_client.py`: subprocess към `ccusage blocks --json` + `daily --json`, парс в dataclass-ове.
- Метрики: активен 5h блок (costUSD, totalTokens, % изтекло от прозореца по време, projection.totalCost, remainingMinutes, burnRate), днес (totalCost/totalTokens от `daily`), седмица (sum последни 7 дни).
- CustomDataSource-съвместими класове (`as_numeric`/`as_string`/`last_values`) за headline метриките — да се консумират от layout задачата.
- Graceful handling: ccusage липсва (FileNotFoundError), няма активен блок (между сесии), празен/невалиден JSON.
- `__main__`: принтва четлив snapshot за верификация без дисплей.

DoD: `python ccusage_client.py` принтва реални парснати метрики; не гърми при no-active-block; commit на branch `feat/ccusage-source`. НЕ се закача за дисплея още.

<!--
ОПАШКА:
- Layout/theme — 5h %, weekly %, session tokens/cost на 480×320 (консумира ccusage_client)
- Refresh loop 30–60s + автостарт (Task Scheduler / startup); + handle TURMO.exe (autostart kill / exclusion)
-->
