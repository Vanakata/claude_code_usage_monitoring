# Tomorrow's tasks

<!--
ФОРМАТ — едно заглавие = един PR. Една активна задача наведнъж.
Контекст / Scope / DoD. Следващите се добавят след одобрение на предишната.
-->

## POC — запали дисплея (hardware handshake)

Контекст: преди каквато и да е логика трябва да докажем, че комуникацията с дисплея работи. Хардуерът е разузнат (виж README): Turing Smart Screen **Revision A**, 3.5" (480×320), на **COM5**, CH340 serial (`VID_1A86/PID_5722`). Грешна ревизия/порт = черен екран без грешка, затова това е стъпка нула — еквивалент на scaffold/verification.

Scope:
- Setup Python 3.9+ venv в repo-то; `pip install` зависимостите на `mathoudebine/turing-smart-screen-python` (clone-ни го локално — вече е в `.gitignore`).
- Конфигурирай за **Revision A** + **COM5** (в библиотеката: `REVISION: A`, `COM_PORT: COM5`, или директно през `LcdCommRevA`).
- Минимален скрипт `poc.py`: инициализирай дисплея, изчисти екрана, покажи **статичен текст + едно число** (напр. "CLAUDE USAGE" + някаква стойност) на 480×320.
- НЕ свързвай ccusage още — целта е само да светне правилно.

DoD: при `python poc.py` дисплеят на COM5 показва четим статичен текст/число (потвърждава Rev A протокол + порт); кратко README обновяване как се пуска; commit на branch `poc/display-handshake`.

<!--
ОПАШКА (добави след като POC светне):
- ccusage integration — parse `ccusage blocks --json` + `daily --json`, мапни в CustomDataSource
- Layout/theme — 5h limit %, weekly %, session tokens/cost на 480×320
- Refresh loop 30–60s + автостарт (Task Scheduler / startup)
-->
