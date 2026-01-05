# Multi-agent Runtime (Variant B)

Persistent рантайм для SGR-агентов с OpenAI-совместимым gateway, пулом долговечных агентных инстансов, каталогом инструментов и сервисом поиска. Текущая кодовая база представляет собой каркас, который развивается по плану из `docs/`.

## Структура репозитория
- `docs/` — архитектура Variant B, план внедрения и миграции с текущего SGR-Agent.
- `src/maruntime/` — реализация платформы.
  - `core/` — переносимые агенты, инструменты, SGR builder и SSE-поток.
  - `gateway/` — OpenAI-совместимые endpoint'ы (chat/completions, tools).
  - `admin/` — CRUD API для инструментов, шаблонов и пайплайнов.
  - `runtime/` — пул агентных инстансов, менеджмент сессий и оркестрация задач.
  - `persistence/` — модели БД, репозитории, миграции (Alembic).
  - `retrieval/` — поиск инструментов и агентных директориях.
  - `security/` — политики авторизации/аутентификации и фильтры доступа.
  - `observability/` — логи, метрики, трассировка.
- `tests/` — автотесты (будут добавляться по мере реализации).

## Требования
- Python 3.11+
- Poetry или `pip` для установки зависимостей
- PostgreSQL (для production) или SQLite (для локальных прототипов)

## Установка
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Локальный запуск компонентов
Ниже — сценарии запуска для локальной разработки.

### Gateway (OpenAI-совместимый API)
- Экспортируйте переменные окружения для подключения к БД и секретам:
  ```bash
  export DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/maruntime
  export OPENAI_API_KEY=<key>  # при использовании проксирующих запросов
  ```
- Запустите приложение (модуль `src/maruntime/gateway/main.py` поднимает FastAPI-приложение и подключает зависимости):
  ```bash
  uvicorn maruntime.gateway.main:app --reload --host 0.0.0.0 --port 8000
  ```
- Примеры запросов (с OpenAI-совместимым форматом):
  ```bash
  curl -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"sgr-agent","messages":[{"role":"user","content":"ping"}]}'
  ```

### Runtime pool
- Для локальной отладки планируется отдельный процесс менеджера инстансов:
  ```bash
  python -m maruntime.runtime.worker --session-store redis://localhost:6379/0
  ```
- Сервис держит живые агентные сессии, запускает/останавливает их по сигналам от gateway.

### Admin API
- CRUD для инструментов и шаблонов развёрнут как FastAPI-приложение:
  ```bash
  export DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/maruntime
  export ADMIN_API_KEY=<optional-api-key>
  python -m scripts.run_admin
  ```
- Через Admin API можно публиковать инструменты и выдавать их в каталог. По умолчанию слушает `0.0.0.0:8001` и принимает заголовок `X-API-Key`, если задан `ADMIN_API_KEY`.

## Миграции и база данных
- Инициализация и миграции управляются из `scripts/db.py`:
  ```bash
  export DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/maruntime
  python -m scripts.db init --url "${DATABASE_URL}"
  python -m scripts.db upgrade --url "${DATABASE_URL}"         # downgrade аналогично
  ```
- Для SQLite используйте `DATABASE_URL=sqlite+aiosqlite:///./dev.db`. Команда `init` создаёт схему через SQLAlchemy и проставляет ревизию Alembic (`head`).
- Активные миграции находятся в корневом каталоге `alembic/versions`.

### Наполнение каталога инструментов и шаблонов
- Сценарий `scripts/seed_catalog.py` подтянет определения инструментов и агентов из `sgr-agent-core`:
  ```bash
  export DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/maruntime
  python -m scripts.seed_catalog --url "${DATABASE_URL}" \
    --repo-url https://github.com/sourcegraph/sgr-agent-core.git \
    --branch main --branch sgr-memory-agent
  ```
- Можно передать `--repo-path` с локальной копией репозитория; по умолчанию версии помечаются активными (если они новые).

## Тестирование и статические проверки
- Сборка пакета в editable-режиме: уже выполнена при установке.
- Базовая проверка синтаксиса (актуальна уже сейчас):
  ```bash
  python -m compileall src
  ```
- После добавления кода добавьте команды `pytest` и `ruff`/`mypy` при необходимости.

## Развёртывание
- **Container-based**: После появления `Dockerfile` соберите образ и задайте переменные окружения (`DATABASE_URL`, `SECRET_KEY`, `LOG_LEVEL`). Пример:
  ```bash
  docker build -t multi-agent-runtime .
  docker run -p 8000:8000 -e DATABASE_URL=... multi-agent-runtime
  ```
- **Kubernetes**: рекомендуется разделить deployment'ы на gateway, runtime pool и admin API, используя общий ConfigMap для переменных окружения и отдельные Secret для ключей.

## Полезные ссылки
- Архитектура и компоненты: `docs/02-target-architecture-variant-b-v2.md`
- План реализации: `docs/03-implementation-plan-variant-b-v2.md`
- План миграции: `docs/04-migration-map-sgr-to-variant-b.md`
