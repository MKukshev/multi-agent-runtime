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

### Admin UI (веб-интерфейс)
Веб-интерфейс для управления платформой — Next.js приложение в директории `admin-ui/`.

**Установка и запуск:**
```bash
cd admin-ui
npm install
npm run dev
```

Приложение запустится на `http://localhost:3000`.

**Функциональность:**
- **Templates** — управление шаблонами агентов и их версиями
- **Instances** — просмотр и управление агентными инстансами (Named Slots)
- **Sessions** — мониторинг сессий и истории сообщений
- **Tools** — каталог инструментов
- **Prompts** — редактирование системных промптов
- **Chat** — тестовый интерфейс для взаимодействия с агентами

**Требования:**
- Node.js 18+
- Запущенный Admin API на порту 8001

## Миграции и база данных

### Быстрый старт (новый сервер)
Для развёртывания на чистом сервере используйте скрипты из `scripts/db/`:

```bash
# Полная установка: создание БД + схема + начальные данные
./scripts/db/deploy.sh full

# Или по шагам:
./scripts/db/deploy.sh init    # Только схема
./scripts/db/deploy.sh seed    # Только данные
```

Параметры подключения через переменные окружения:
```bash
export DB_HOST=your-server.com
export DB_PORT=5432
export DB_USER=maruntime_user
export DB_PASSWORD=secret
export DB_NAME=maruntime

./scripts/db/deploy.sh full
```

### Экспорт данных с локальной БД
```bash
./scripts/db/export_data.sh exported_data.sql
```

### Alembic миграции
- Инициализация и миграции также управляются из `scripts/db.py`:
  ```bash
  export DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/maruntime
  python -m scripts.db init --url "${DATABASE_URL}"
  python -m scripts.db upgrade --url "${DATABASE_URL}"         # downgrade аналогично
  ```
- Для SQLite используйте `DATABASE_URL=sqlite+aiosqlite:///./dev.db`. Команда `init` создаёт схему через SQLAlchemy и проставляет ревизию Alembic (`head`).
- Активные миграции находятся в корневом каталоге `alembic/versions`.

### Структура скриптов БД
```
scripts/db/
├── init_schema.sql   # Полная DDL-схема (10 таблиц)
├── seed_data.sql     # Начальные данные (промпты, шаблоны, инстансы)
├── deploy.sh         # Скрипт развёртывания
└── export_data.sh    # Экспорт данных
```

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

### На внешний сервер (VPS/VM)

1. **Подготовка PostgreSQL:**
   ```bash
   # На сервере с PostgreSQL
   sudo -u postgres createuser maruntime_user -P
   sudo -u postgres createdb maruntime -O maruntime_user
   ```

2. **Инициализация схемы:**
   ```bash
   # С локальной машины или на сервере
   export DB_HOST=your-server.com
   export DB_USER=maruntime_user
   export DB_PASSWORD=your_password
   export DB_NAME=maruntime
   
   ./scripts/db/deploy.sh full
   ```

3. **Запуск сервисов:**
   ```bash
   export DATABASE_URL=postgresql+asyncpg://maruntime_user:password@localhost:5432/maruntime
   
   # Gateway (порт 8000)
   uvicorn maruntime.gateway.main:app --host 0.0.0.0 --port 8000
   
   # Admin API (порт 8001)
   python -m scripts.run_admin
   ```

### Docker Compose (рекомендуемый способ)

**Требования:** Docker 20+, Docker Compose v2

**1. Настройка переменных окружения:**
```bash
# Создайте .env файл
cat > .env << EOF
DB_PASSWORD=your_secure_password
OPENAI_API_KEY=sk-your-openai-key
EOF
```

**2. Запуск всех сервисов:**
```bash
# Сборка и запуск
docker-compose up -d --build

# Применение миграций БД
docker-compose --profile migrate up migrate

# Загрузка начальных данных (опционально)
docker-compose --profile seed up seed
```

**3. Сервисы:**
| Сервис | URL | Описание |
|--------|-----|----------|
| Admin UI | http://localhost:3000 | Веб-интерфейс |
| Gateway API | http://localhost:8000 | OpenAI-совместимый API |
| Admin API | http://localhost:8001 | CRUD для шаблонов/инструментов |
| PostgreSQL | localhost:5432 | База данных |

**4. С nginx (всё через порт 80):**
```bash
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d --build
```

**5. Полезные команды:**
```bash
# Логи
docker-compose logs -f gateway

# Остановка
docker-compose down

# Полная очистка (включая volumes)
docker-compose down -v
```

**6. Volumes:**
- `maruntime-postgres-data` — данные PostgreSQL
- `maruntime-memory-data` — файлы памяти агентов
- `maruntime-logs-data` — логи агентов

### Kubernetes
Рекомендуется разделить deployment'ы на gateway, admin-api и admin-ui, используя общий ConfigMap для переменных окружения и отдельные Secret для ключей. Helm chart будет добавлен в будущих версиях.

## Полезные ссылки
- Архитектура и компоненты: `docs/02-target-architecture-variant-b-v2.md`
- План реализации: `docs/03-implementation-plan-variant-b-v2.md`
- План миграции: `docs/04-migration-map-sgr-to-variant-b.md`
