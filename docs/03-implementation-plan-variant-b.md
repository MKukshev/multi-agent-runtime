# Документ 3 — Поэтапный план реализации (Вариант B) как ТЗ/план для Codex

> Назначение: подробный, линейный план реализации нового проекта на базе логики SGR-Agent Core, но с Persistent Agent Runtime, Tool Catalog, Tool Search, Templates и Multi-Agent.

---

## 0. Результат проекта (Definition of Done)

Система считается реализованной, если:

1) Есть Postgres схема и миграции для Tool Catalog, Agent Templates, Agent Instances, Sessions, Messages, Tool Executions, Sources, Artifacts.
2) Есть API (OpenAI-compatible) `/v1/chat/completions`, который:
   - принимает `model` как template name или session_id,
   - стримит ответы (SSE) в стиле OpenAI,
   - поддерживает Clarification-flow (WAITING → provide_clarification → continue).
3) Есть Admin API:
   - CRUD Tools (минимум: create/list/get/update/activate),
   - CRUD Templates (create/version/list/get/activate),
   - мониторинг активных sessions/instances.
4) Есть Agent Runtime:
   - worker-инстансы создаются по template,
   - worker обслуживает много сессий последовательно,
   - после завершения сессии worker очищает session-state и возвращается в IDLE,
   - есть пул/менеджер инстансов.
5) Есть Tool Search Service:
   - retrieval top-k инструментов по запросу (task + reasoning),
   - фильтры и правила (лимиты, allow/deny, risk),
   - обязательное добавление system tools.
6) Есть Multi-Agent интерфейс:
   - поиск подходящего template под запрос (Agent Directory),
   - возможность делегировать задачу другому агенту как tool.

---

## 1. Стартовые вводные (перенос логики SGR-Agent)

### 1.1. Что переносим из текущего SGR-Agent (см. Документ 1)
- BaseAgent цикл и контракты `_prepare_context/_prepare_tools/_reasoning_phase/_select_action_phase/_action_phase`.
- Формат conversation history в стиле OpenAI messages.
- BaseTool контракт (Pydantic + async __call__) и ToolRegistry.
- AgentConfig/GlobalConfig/AgentDefinition/AgentFactory концепт (но меняем storage).
- Системные tools и лимиты доступности (max_iterations/max_searches/max_clarifications).
- Streaming generator (OpenAI-like SSE chunks).

### 1.2. Что добавляем принципиально нового
- БД (Postgres) как source-of-truth для templates/tools/sessions.
- Persistent runtime: AgentInstance pool + reset lifecycle.
- Tool Search Service (retrieval) для динамического подсета tools.
- Multi-agent слой: Agent Directory + Agent-as-Tool.

---

## 2. Рекомендуемая структура репозитория (новый проект)

```
new-agent-platform/
  README.md
  pyproject.toml
  src/
    app/
      main.py                 # FastAPI entrypoint
      api/
        openai_compat.py       # /v1/chat/completions
        admin_templates.py
        admin_tools.py
        agents_monitoring.py   # /agents, /agents/{id}/state
      deps.py
    core/
      config/
        models.py              # AgentConfig, policies
        prompts.py             # prompt pack
      tools/
        base.py                # BaseTool, registry mixin
        registry.py            # ToolRegistry
        catalog_models.py      # ToolDescriptor, ToolPolicy
      agents/
        base.py                # BaseAgent, execution loop contracts
        sgr.py                 # SGRAgent
        tool_calling.py        # ToolCallingAgent
        sgr_tool_calling.py    # SGRToolCallingAgent
        research_variants.py   # Research* agents
      runtime/
        instance.py            # AgentInstance (worker)
        pool.py                # AgentPool
        session.py             # Session runtime
        state_machine.py       # FSM for instance/session
        router.py              # request routing + multi-agent selection
      retrieval/
        tool_search.py         # Tool Search Service (pgvector)
        agent_search.py        # Agent Directory (pgvector)
      persistence/
        db.py                  # async engine, sessionmaker
        migrations/            # alembic
        repositories/          # templates/tools/sessions
        models/                # SQLAlchemy models
      streaming/
        generator.py           # streaming generator, chunk models
      security/
        policies.py            # tool risk policy, allowlists
      observability/
        logging.py
        metrics.py
  tests/
    unit/
    integration/
```

---

## 3. План работ по фазам

### Фаза 0 — Техническая подготовка и фиксация требований
**Цель:** создать каркас проекта и зафиксировать интерфейсы.

Задачи:
- [ ] Создать новый репозиторий/пакет, настроить линтеры, тесты, CI.
- [ ] Зафиксировать версии библиотек: FastAPI, SQLAlchemy async, Pydantic v2, alembic, pgvector.
- [ ] Описать минимальные SLA/ограничения: max concurrent sessions, timeouts, top_k tools, payload limits.

Артефакты:
- `README.md` (цели, запуск, ENV)
- `docs/requirements.md` (необязательно, но полезно)

Acceptance:
- Проект запускается, имеет базовый health endpoint и тестовый pipeline.

---

### Фаза 1 — Перенос Core: Agent loop + Tools contract + Streaming (без БД)
**Цель:** получить работающий core без persistent runtime.

Задачи:
- [ ] Перенести/реализовать `BaseTool` (Pydantic + async __call__) и `ToolRegistry`.
- [ ] Реализовать `BaseAgent` каркас и контракты методов.
- [ ] Реализовать (минимально) 2 агента:
  - `ToolCallingAgent` (чистый FC)
  - `SGRToolCallingAgent` (Hybrid reasoning via ReasoningTool)
- [ ] Реализовать `streaming_generator` (async iterator) для публикации chunk’ов.
- [ ] Реализовать базовые system tools:
  - ReasoningTool
  - FinalAnswerTool
  - ClarificationTool
- [ ] Поднять OpenAI-совместимый endpoint `/v1/chat/completions` в упрощённом режиме (in-memory session).

Артефакты:
- runnable MVP без БД, поддерживающий простой запрос и возврат финального ответа.

Acceptance:
- Тест: запрос -> стрим -> финальный ответ.
- Тест: ClarificationTool переводит сессию в WAITING.

---

### Фаза 2 — Введение Postgres и миграций (основные таблицы)
**Цель:** сделать БД источником истины.

Задачи:
- [ ] Подключить Postgres (async engine).
- [ ] Подключить alembic миграции.
- [ ] Создать SQLAlchemy модели + миграции для таблиц:
  - tools
  - agent_templates
  - agent_template_tools
  - agent_instances
  - sessions
  - session_messages
  - tool_executions
  - (опционально) sources, artifacts
- [ ] Реализовать репозитории (DAO) для CRUD tools/templates/sessions.

Acceptance:
- Интеграционный тест: поднять Postgres, применить миграции, выполнить CRUD.

---

### Фаза 3 — Tool Catalog Service (CRUD + загрузка в runtime)
**Цель:** инструмент становится сущностью в БД, а не «просто классом в коде».

Задачи:
- [ ] Реализовать `ToolCatalogService`:
  - create/update/activate/deactivate tools
  - получать tool schema (json_schema)
  - хранить python entrypoint или remote endpoint
- [ ] Реализовать механизм загрузки tool-класса по entrypoint (import string).
- [ ] Реализовать «tool descriptor → OpenAI tool schema» конвертер.
- [ ] Добавить Admin API для Tools:
  - `GET /admin/tools`
  - `POST /admin/tools`
  - `PATCH /admin/tools/{id}`
  - `POST /admin/tools/{id}/activate`

Acceptance:
- Можно добавить новый tool через API/DB, и он доступен в runtime после reload (или hot-load).

---

### Фаза 4 — Agent Templates Service (CRUD + версионирование)
**Цель:** шаблоны задают поведение и состав инструментов.

Задачи:
- [ ] Реализовать `TemplateService`:
  - create template v1
  - create new version (v2) от v1 (copy-on-write)
  - activate version
  - list/get
- [ ] Структурировать Template:
  - prompt_pack
  - llm_config
  - execution_policy
  - tool_policy (required tools, allowlist, max_tools_in_prompt, strategy)
  - discriminators/rules
  - multiagent metadata (description/tags/embedding placeholder)
- [ ] Admin API:
  - `GET /admin/templates`
  - `POST /admin/templates`
  - `POST /admin/templates/{id}/versions`
  - `POST /admin/templates/{id}/activate`

Acceptance:
- Шаблон создаётся и может быть использован для запуска сессии.

---

### Фаза 5 — Session Service (персистентная сессия + messages)
**Цель:** заменить in-memory сессию на persisted.

Задачи:
- [ ] Реализовать `SessionManager`:
  - create session (task/messages)
  - append messages (assistant/tool/user)
  - persist context snapshot
  - update counters/state
- [ ] Протокол «agent_id == session_id» для OpenAI-совместимости:
  - при стриме возвращаем `model=session_id` (или agent_id) как сейчас.
- [ ] Реализовать endpoints мониторинга:
  - `GET /agents` (active sessions)
  - `GET /agents/{session_id}/state`
  - `POST /agents/{session_id}/provide_clarification`

Acceptance:
- Можно перезапустить сервис и продолжить WAITING_FOR_CLARIFICATION сессии (state хранится в DB).

---

### Фаза 6 — Persistent Agent Runtime: AgentInstance + Pool + Reset lifecycle
**Цель:** агенты не создаются заново на каждый запрос — создаются worker-инстансы, которые переиспользуются.

Задачи:
- [ ] Реализовать `AgentInstance` (worker):
  - pinned template_id+version
  - shared clients
  - очередь jobs (sessions) или mutex для последовательного исполнения
  - методы: `run_session(session_id)`, `reset()`, `health()`
- [ ] Реализовать `AgentPool`:
  - получить idle instance под template
  - создать новый instance при нехватке
  - лимиты pool size
- [ ] Реализовать `cleanup/reset`:
  - очистить conversation/context в памяти
  - закрыть/обнулить session-level кеши
  - обновить instance status -> IDLE

Acceptance:
- Нагрузочный тест (минимальный): 10 запросов последовательно проходят через один instance без роста памяти.
- После завершения 1-й сессии instance возвращается в IDLE, 2-я сессия стартует на том же instance.

---

### Фаза 7 — Tool Search Service (pgvector retrieval) и интеграция в _prepare_tools
**Цель:** экономия контекста: LLM видит ограниченный top-k набор tools.

Задачи:
- [ ] Добавить pgvector extension и поле embeddings в tools.
- [ ] Реализовать генерацию embeddings для tools:
  - offline job при create/update tool
  - хранить embedding в tools.embedding
- [ ] Реализовать `ToolSearchService`:
  - search(query, template_id, session_state, top_k, filters)
  - обязательное добавление system tools
  - фильтрация по rules/discriminators
  - fallback на template allowlist при пустой выдаче
- [ ] Интегрировать в agent workflow:
  - на каждом iteration формировать query (task + reasoning.next_step)
  - получать subset tools
  - передавать только subset в LLM

Acceptance:
- Измерение: количество tools в prompt уменьшается (логируем).
- Функциональный тест: агент всё ещё решает задачу (не «сломался» из-за отсутствия tool).
- Тест: после достижения max_searches WebSearchTool не выдаётся retrieval’ом.

---

### Фаза 8 — Discriminators / Rules Engine (явный механизм)
**Цель:** формализовать логику доступности tools и этапов.

Задачи:
- [ ] Описать DSL/JSON-формат rules в template:
  - conditions: iteration >= max_iterations, searches_used >= max_searches, state == ...
  - actions: remove_tool, keep_only_tools, set_stage, etc.
- [ ] Реализовать rules evaluator, который применяется:
  - до tool retrieval (как фильтр),
  - после retrieval (как post-filter),
  - при переходах state machine.
- [ ] Добавить тесты на правила.

Acceptance:
- Правила полностью заменяют «жёстко прошитую» логику отключения tools.

---

### Фаза 9 — Multi-Agent слой: Agent Directory + Agent-as-Tool + Router
**Цель:** запускать специализированных агентов по запросу и позволить делегирование.

Задачи:
- [ ] Реализовать embeddings для agent_templates (capability description).
- [ ] Реализовать `AgentDirectoryService.search(query, top_k)`.
- [ ] Реализовать Router:
  - выбрать template по retrieval (или default)
  - получить instance из pool
  - запустить session
- [ ] Реализовать Agent-as-Tool wrapper:
  - tool schema для «вызова агента»
  - выполнение создаёт session на целевом template и возвращает результат

Acceptance:
- Демо: «default router agent» выбирает подходящий template из 3+ доступных.
- Демо: агент A вызывает агент B как tool и получает результат.

---

### Фаза 10 — Совместимость и полировка: OpenAI protocol + Observability + Hardening
Задачи:
- [ ] Полная совместимость структуры SSE chunk’ов с OpenAI clients (минимум: openai-python).
- [ ] Логи и трассировка:
  - correlation_id = session_id
  - логирование tool selection и причин фильтрации
- [ ] Метрики:
  - длительность шагов
  - количество LLM вызовов
  - tool usage statistics
- [ ] Security policies:
  - allowlist инструментов по окружению
  - rate limiting на domain tools
- [ ] Документация:
  - как добавлять tool
  - как создавать template
  - как подключать новый агент
- [ ] Интеграционные тесты end-to-end.

Acceptance:
- Есть набор e2e тестов: basic, clarification, tool retrieval, multi-agent delegation.
- Продукт можно развернуть docker-compose (api + postgres).

---

## 4. Прикладные сценарии тестирования (Acceptance Scenarios)

### Сценарий A: Обычный запрос без уточнений
1) POST /v1/chat/completions model=<template>
2) stream chunks
3) final answer
4) session state = COMPLETED
5) agent instance state = IDLE

### Сценарий B: Clarification-flow
1) POST /v1/chat/completions model=<template>
2) агент вызывает ClarificationTool → state WAITING
3) клиент продолжает model=session_id (или provide_clarification endpoint)
4) агент завершает исследование → COMPLETED
5) instance reset → IDLE

### Сценарий C: Лимиты и дискриминаторы
- max_searches=1 → после 1 поиска WebSearchTool исчезает из retrieval.

### Сценарий D: Multi-agent routing
- Router выбирает template «research_agent» для запроса «сделай ресёрч».
- Router выбирает template «writer_agent» для «напиши эссе».

### Сценарий E: Agent-as-tool delegation
- Агент A (orchestrator) вызывает агент B как tool и включает результат в финальный ответ.

---

## 5. Примечания по миграции из sgr-agent-core (важные тонкости)

1) **GlobalConfig singleton**: в новом проекте лучше ограничить его роль runtime-дефолтами. Templates — в DB.
2) **ToolRegistry auto-registration**: при подходе «tools из DB» всё равно нужен слой «loader/importer» и реестр runtime классов.
3) **Conversation format**: сохранять строго OpenAI формат, иначе сломается совместимость клиента.
4) **Streaming**: сначала сохраняем OpenAI-like стрим, потом можно оптимизировать формат.
5) **Вычисление embeddings**: на старте можно использовать простую модель/провайдер; важно обеспечить возможность reindex.

---

Конец документа.
