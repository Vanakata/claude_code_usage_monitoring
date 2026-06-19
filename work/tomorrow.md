# Tomorrow's tasks

<!--
ФОРМАТ — едно заглавие = един PR. Една активна задача наведнъж.
Контекст / Scope / DoD. Следващите се добавят след одобрение на предишната.
-->

## ✅ DONE

- **POC: display handshake** — `poc/display-handshake` (6cec590). Свети. Блокер: `TURMO.exe` граби COM5 (виж README).
- **ccusage data layer** — `feat/ccusage-source` (6627fc6). `ccusage_client.py`.
- **Layout + реални /usage данни + matrix фон** — `feat/display-layout` (3ab32c1). `display.py` + `usage_client.py` (reverse-engineer-нат `/api/oauth/usage`).
- **Refresh loop + автостарт** — `feat/refresh-loop`. `run.py` (loop с TURMO kill + reconnect + token refresh на 401), `tools/start.cmd` + `tools/install_autostart.ps1` (Scheduled Task, elevated). README документирано.

---

## Опашка (празна — проектът е функционален end-to-end)

Възможни бъдещи подобрения (не приоритетни):
- Регистрация на autostart task-а (изисква elevated; инсталаторът е готов).
- Втори екран/изгледи (седмичен график от ccusage daily history).
- Алармен цвят/мигане при висок % (вече има цветови прагове в gauge-а).
- По-стабилен fallback ако `/api/oauth/usage` се счупи на Claude Code ъпдейт.
