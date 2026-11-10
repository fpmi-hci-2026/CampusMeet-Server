# CampusMeet MCP — MVP лабораторной работы №4

MCP-сервер дает ассистенту доступ к каталогу и собственным билетам пользователя. REST и MCP используют один транзакционный слой `campusmeet/store.py` и одну SQLite mock-базу. Отмена чужого или использованного билета блокируется в слое данных независимо от текста промпта.

## Installation

Требуется Python 3.12+. Для исполняемого MVP внешние библиотеки не нужны.

```bash
cd CampusMeet-Server
python3 -m campusmeet.mcp_server --db data/mock.sqlite3 --token demo-artem
```

Транспорт — stdio, JSON-RPC 2.0, одна UTF-8 JSON-строка на сообщение. Зафиксирована версия MCP **2025-11-25** с `initialize` → `notifications/initialized`. Версия 2026-07-28 и Streamable HTTP этим MVP не поддерживаются. Выбран прямой небольшой адаптер стандартной библиотеки, чтобы учебный mock запускался без установки SDK; это не полная реализация MCP. Не заявляются subscriptions, sampling, pagination, OAuth или tasks. SDK-вариант можно добавить при разработке промышленного сервера.

Идентичность задается при запуске процесса. Инструменты не принимают `user_id`, `role`, URL сервера, SQL или путь к файлу. Параметры проверяются по JSON Schema; [tools.json](tools.json) — экспорт реальных схем `tools/list`. stdout содержит только протокол; диагностика выводится в stderr. Все корректно типизированные вызовы Tools и успешные чтения Resources записываются в `agent_audit_log`: actor, action, target, outcome, timestamp; токены и QR-payload не сохраняются. Ошибки JSON-RPC/схемы возвращаются до выполнения действия и не включаются в предметный журнал.

## Tools

| Tool | Параметры | Назначение |
|:--|:--|:--|
| `list_events` | `query?` | Поиск опубликованных мероприятий |
| `check_event_capacity` | `event_id` | Свободные места и доступность очереди |
| `get_ticket` | `ticket_id` | Собственный билет по точному ID |
| `register_for_event` | `event_id`, `join_waitlist`, `idempotency_key` | Атомарная регистрация / очередь |
| `cancel_ticket` | `ticket_id` | Отмена до прохода с передачей места первому в очереди |

Annotations — подсказки клиенту; доступ обеспечивается программными проверками. Ошибка аргументов — JSON-RPC `-32602`, неизвестный метод — `-32601`. Предметный отказ возвращается через `isError: true`. Изменения транзакционны. Повтор с одним ключом идемпотентности не создает новый билет; изменение тела при том же ключе отклоняется.

## Resources и Prompts

| Вид | Имя / URI | Содержание |
|:--|:--|:--|
| Resource | `events://upcoming` | Публичный каталог текущей демонстрационной базы |
| Resource | `tickets://mine` | Только билеты текущего пользователя |
| Resource | `policy://ticket-cancellation` | Правила отмены и перевода очереди |
| Resource template | `events://{event_id}` | Публичная карточка; черновик только владельцу |
| Prompt | `plan_visit(interest)` | Каталог → проверка мест → выбор события |
| Prompt | `cancel_registration(ticket_id)` | Правила → собственный билет → отмена |

Примеры фраз пользователя: «Найди митап про AI и проверь свободные места», «Запиши меня на выбранный митап, если мест нет — предложи очередь», «Покажи мои билеты», «Отмени мой билет, если я еще не проходил».

## Проверка клиентом и Inspector

```bash
python3 scripts/mcp_client.py --output evidence/mcp-session.json
python3 -m unittest discover -s tests -v
```

Первый скрипт запускает **отдельный процесс сервера**, выполняет handshake, discovery всех трех примитивов, читает ресурсы, получает оба промпта, регистрирует пользователя, повторяет запрос с тем же ключом и отменяет билет. Клиент не использует LLM API и не выдает эту проверку за запуск Inspector. Полный протокол находится в [evidence/mcp-session.json](../evidence/mcp-session.json).

Для ручной проверки официальным Inspector при доступе к npm:

```bash
npx @modelcontextprotocol/inspector python3 -m campusmeet.mcp_server --token demo-artem
```

В клиенте выберите совместимую версию протокола 2025-11-25. Ручной запуск Inspector в текущей среде не выполнен.

Пример конфигурации stdio-клиента (замените абсолютные пути своими):

```json
{
  "mcpServers": {
    "campusmeet": {
      "command": "/absolute/path/to/python3",
      "args": ["-m", "campusmeet.mcp_server", "--db", "/absolute/path/to/CampusMeet-Server/data/mock.sqlite3", "--token", "demo-artem"],
      "cwd": "/absolute/path/to/CampusMeet-Server"
    }
  }
}
```

Не все клиенты поддерживают `cwd`; для них используйте абсолютный launcher-скрипт, выполняющий `cd` в Server перед `python3 -m campusmeet.mcp_server`. Все записи — синтетические учебные данные. Токены `demo-*` не предназначены для публикации настоящего API.
