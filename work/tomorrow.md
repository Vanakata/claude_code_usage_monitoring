# Tomorrow's tasks

<!--
ФОРМАТ — едно заглавие = един PR. Една активна задача наведнъж.
Контекст / Scope / DoD. Следващите се добавят след одобрение на предишната.
-->

## ✅ DONE

- **POC: display handshake** — `poc/display-handshake` (6cec590). Свети. Блокер: `TURMO.exe` граби COM5 (виж README).
- **ccusage data layer** — `feat/ccusage-source` (6627fc6). `ccusage_client.py`.
- **Layout + реални /usage данни + matrix фон** — `feat/display-layout`. `display.py` рисува 5H/WK gauge с РЕАЛНИТЕ `/usage` % (reverse-engineer-нат `/api/oauth/usage`, виж `usage_client.py`) + SESSION cost/tokens, върху matrix background. Approximation подходът беше изоставен (лимитът тежи по модел; виж README).

---

## Refresh loop + автостарт (АКТИВНА)

Контекст: `display.py` сега прави само `render_once()` (един кадър). Трябва да върти и да тръгва сам на boot.

Scope:
- Loop: `fetch usage + ccusage → render → sleep 30–60s → пак`. Конфигуруем интервал (env). Не гърми при временна грешка (network/ccusage) — лог + продължава.
- **TURMO.exe** при старт: убива го (elevated) преди да хване COM5, иначе портът е зает.
- **Token refresh** за `/api/oauth/usage`: access token-ът изтича. Ако 401 → refresh през `POST /v1/oauth/token` с refresh_token от credentials (grant `refresh_token`, header `anthropic-beta: oauth-2025-04-20,...`), презаписва credentials. (Виж extension.js: `qw="/v1/oauth/token"`.)
- Автостарт: Task Scheduler или startup (elevated, заради TURMO kill). Документация в README.

DoD: пуснат веднъж, дисплеят се обновява на всеки 30–60s с пресни данни; преживява прекъсване на мрежата; тръгва сам след reboot; commit на нов branch.

<!--
ОПАШКА: (нищо засега)
-->
