# CampusMeet-Server

## Project Name

**CampusMeet / EventHub — контракты API, HTTP mock и MCP MVP.** Лабораторная работа №4: «Стили интеграции программных систем и проектирование API», ПЧМИ, БГУ ФПМИ, 2026–2027.

## Description

Репозиторий содержит OpenAPI 3.0.3 на 33 операции, физические модели PostgreSQL и SQLite на 17 таблиц, исполняемый HTTP mock и MCP-сервер. Регистрация, очередь, отмена, чекин и редактирование событий работают с транзакционной SQLite mock-базой. Остальные операции показывают примеры контракта и обозначены `X-Mock-Mode: example`; фоновые рассылки, Wallet и криптографический QR еще не реализованы. Полная реализация на FastAPI относится к следующим работам; учебный mock работает на стандартной библиотеке Python без установки зависимостей.

## Installation

Python 3.12+, для контейнеров — Docker Compose v2. CampusMeet-Web должен находиться рядом с Server.

```bash
git clone git@github.com:fpmi-hci-2026/CampusMeet-Server.git
cd CampusMeet-Server
python3 scripts/export_contracts.py
python3 scripts/build_sqlite_schema.py
python3 -m campusmeet.mock_api
```

Mock создает `data/mock.sqlite3` при отсутствии схемы, сохраняет данные при перезапуске. Для отдельной демонстрации: `python3 -m campusmeet.mock_api --db /tmp/campusmeet-demo.sqlite3`. Не запускайте две инициализации одной новой базы одновременно. Схема ЛР1 сохранена в `database/schema.sql`; она содержит DROP TABLE и предназначена только для воспроизведения старого учебного примера, не для обновления базы.

```bash
# API + Web:
docker compose up --build -d
# PostgreSQL для проверки физической модели:
docker compose --profile database up -d postgres
# На свежей mock-базе:
python3 scripts/smoke_http.py --output evidence/http-session.json
# Остановить, сохранив данные:
docker compose down
```

Полная независимая Docker-проверка из обычного терминала: `bash scripts/verify-docker.sh`. Скрипт создает отдельный Compose-проект, проверяет HTTP и 17 таблиц PostgreSQL, сохраняет протокол в evidence и удаляет только созданные им демонстрационные контейнеры/volumes. Требует свободных портов 8000 и 3000.

API: `http://127.0.0.1:8000/api/v1`; Web: `http://127.0.0.1:3000`; OpenAPI: `http://127.0.0.1:8000/openapi.json`. PostgreSQL-профиль проверяет целевую схему и **не подключает SQLite mock к PostgreSQL**. Промышленный PostgreSQL-адаптер относится к следующему этапу.

## Sub modules

- [CampusMeet — отчеты, Wiki, портал](https://github.com/fpmi-hci-2026/CampusMeet).
- [CampusMeet-Web — Next.js каркас и Lab4 demo-афиша](https://github.com/fpmi-hci-2026/CampusMeet-Web).
- [CampusMeet-Mobile — Expo каркас, минимальная афиша и API-клиент](https://github.com/fpmi-hci-2026/CampusMeet-Mobile).

## Usage

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/events
python3 -m campusmeet.mcp_server --token demo-artem
python3 scripts/mcp_client.py --output evidence/mcp-session.json
python3 -m unittest discover -s tests -v
```

Полная валидация и линтер для CI:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check campusmeet scripts tests
python3 -m unittest discover -s tests -v
```

| Материал | Файл |
|:--|:--|
| Контракт, примеры, Bruno и Postman | [api/README.md](api/README.md) |
| Маршруты → User Stories → Use Cases | [api/route-matrix.md](api/route-matrix.md) |
| PostgreSQL 16, новая физическая модель | [database/schema.postgresql.sql](database/schema.postgresql.sql) |
| SQLite 3, исполняемая mock-модель | [database/schema.sqlite.sql](database/schema.sqlite.sql) |
| MCP: Tools, Resources, Prompts, Inspector | [mcp/README.md](mcp/README.md) |
| Локальные тесты | [evidence/local-tests.txt](evidence/local-tests.txt) |
| Протокол MCP-процесса | [evidence/mcp-session.json](evidence/mcp-session.json) |
| Контейнеры API, Web, PostgreSQL, SonarQube | [compose.yaml](compose.yaml) |

Учебные токены: `demo-artem`, `demo-vlad`, `demo-kirill`, `demo-daria`, `demo-maxim`, `demo-viktor`, `demo-sergey`. Они соответствуют персонажам ЛР1. `POST /auth/token` — имитация входа по fixture user без проверки пароля, не настоящая аутентификация. Событие имеет два места для демонстрации исчерпания квоты и очереди.

## Инфраструктура и публикация

`.github/workflows/ci.yml` экспортирует контракты, проверяет актуальность генерируемых файлов, выполняет тесты, применяет DDL в PostgreSQL 16 и только затем собирает контейнер с HTTP smoke-проверкой. Workflow запустится после отправки коммитов, которой на этапе подготовки ЛР4 еще не было.

Локальный SonarQube: `docker compose --profile quality up -d sonarqube`, затем запустите SonarScanner со своим токеном и `sonar-project.properties`. Поднятый контейнер без анализа не считается пройденной проверкой качества.

Для SonarCloud и Render подготовлен ручной workflow `quality-deploy.yml`: нужны `SONAR_TOKEN`, переменная `SONAR_ORGANIZATION`, секрет `RENDER_DEPLOY_HOOK`, проект Sonar и окружение `production`. При отсутствии конфигурации он завершается ошибкой, не пропускает quality gate. `render.yaml` описывает учебный mock с временным SQLite-хранилищем; автодеплой отключен. Деплой и облачный анализ пока не выполнялись.

Существующий `main` соответствует production, будущий `develop` — development. Отдельные ветки production/development команда может согласовать позже. Ветки, коммиты, Issues и GitHub Projects при подготовке файлов не создавались. План и распределение на ревью находятся в Wiki основного репозитория.

## Contributing

Команда: Минчук Станислав, Иванова Виктория, Шварцман Дидар. Комплект ЛР4 подготовлен для просмотра командой до коммита. В отчете предложенные ответственные за ревью отделены от подтвержденного вклада; несуществующие коммиты и запуски CI не перечисляются.
