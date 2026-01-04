# Документ 3 (v2) — Подробный поэтапный план реализации (Вариант B) в формате ТЗ для Codex

> Документ ориентирован на генерацию/реализацию кода. Содержит последовательные этапы, задачи, артефакты, критерии приёмки и прямые ссылки на то, что переносим из текущей кодовой базы (`sgr-memory-agent`).

---

## 0) Definition of Done (DoD)

Система готова, если выполнено:

1) **Postgres schema + миграции** (alembic):
   - tools (+ embeddings)
   - agent_templates (+ versions, embeddings)
   - sessions (+ messages, context snapshot)
   - tool_executions, sources, artifacts
   - agent_instances (pool status)

2) **OpenAI-compatible Gateway API**:
   - `POST /v1/chat/completions` (stream=true)
   - `GET /v1/models` (templates)
   - поддержка “resume”: `model=session_id`
   - корректный clarification-flow без блокировки runtime

3) **Admin API**:
   - CRUD Tools
   - CRUD Templates (versioning + activation)
   - (минимально) list instances/sessions

4) **Agent Runtime (Persistent Workers)**:
   - pool instances pinned to template version
   - после завершения/паузы session worker возвращается в IDLE
   - session-state хранится в DB, worker держит в памяти только во время исполнения

5) **Tool Search Service**:
   - vector retrieval top-k
   - фильтрация по policy + discriminators (iteration/searches/clarifications)
   - обязательные system tools всегда добавляются

6) **Multi-agent слой**:
   - Agent Directory search (template embeddings)
   - Agent-as-Tool (делегирование)

7) **Parity с текущим SGR-Agent (минимум)**:
   - сохранён SGRToolCalling workflow (ReasoningTool → tool call → tool exec)
   - сохранён формат messages и SSE потока (совместимость с openai-python)

---

## 1) Новый репозиторий: структура и технологический стек

### 1.1. Рекомендуемый стек
- Python 3.11+
- FastAPI + uvicorn
- SQLAlchemy 2.x (async) + alembic
- Postgres + pgvector
- Pydantic v2
- openai-python (AsyncOpenAI)
- (опционально) Redis для кэша/очередей (не обязательно в MVP)

### 1.2. Предлагаемая структура проекта
```
agent-platform/
  README.md
  pyproject.toml
  src/
    platform/
      gateway/                # OpenAI compatible API
      admin/                  # templates/tools CRUD
      runtime/                # pool, sessions, runners
      core/                   # перенесённые агенты/tools/prompt loader/stream
      persistence/            # db models, repos, migrations
      retrieval/              # tool search, agent directory
      security/               # policies
      observability/          # logs/metrics
  tests/
  docker/
    docker-compose.yml
```

---

## 2) Этап 0 — Import/Inventory текущей кодовой базы (обязательный “портинг чеклист”)

### 2.1. Зафиксировать, что переносим 1:1
Из текущего репо (`sgr-memory-agent`) переносим как baseline:

- `sgr_deep_research/core/tools/*`
- `sgr_deep_research/core/next_step_tool.py`
- `sgr_deep_research/core/agents/sgr_agent.py`
- `sgr_deep_research/core/agents/tool_calling_agent.py`
- `sgr_deep_research/core/agents/sgr_tool_calling_agent.py`
- `sgr_deep_research/core/base_tool.py` (+ MCPBaseTool)
- `sgr_deep_research/core/services/prompt_loader.py` (после модификаций)
- `sgr_deep_research/core/stream.py` (протокол SSE)

### 2.2. Зафиксировать, что переписываем
- `sgr_deep_research/api/endpoints.py` → заменить на DB + runtime router
- `core/base_agent.py` → убрать blocking wait() и разделить instance vs session state
- `core/agent_factory.py` → Template/Tool loaders из DB + instance pool

Артефакт:
- `docs/migration_inventory.md` (список файлов и статус: copy/refactor/rewrite)

Acceptance:
- список файлов согласован и приложен в репозиторий.

---

## 3) Этап 1 — Скелет проекта + перенос “core” без БД (компилируемость)

### Задачи
- [ ] Создать новый пакет `platform/core/` и перенести туда:
  - tools
  - agents
  - next_step_tool
  - stream
  - prompt_loader
- [ ] Обновить импорты на новую структуру.
- [ ] Поднять минимальный “in-memory demo runner”, который:
  - создаёт agent (как сейчас AgentFactory),
  - выполняет один запрос, стримит SSE.

Acceptance:
- `pytest -q` базовые тесты (smoke) проходят или хотя бы сервис стартует.
- один demo запрос возвращает SSE.

---

## 4) Этап 2 — DB слой: модели, миграции, репозитории

### 4.1. Модели БД (SQLAlchemy)
Создать таблицы:

- `tools`
- `agent_templates`
- `agent_template_versions` (если делаем версионирование отдельной таблицей)
- `sessions`
- `session_messages`
- `tool_executions`
- `agent_instances`
- (опционально) `sources`, `artifacts`

### 4.2. Репозитории
- ToolRepository (CRUD, activate, list versions)
- TemplateRepository (CRUD, create_version, activate)
- SessionRepository (create, load, append_messages, update_context, update_state)
- InstanceRepository (claim/release, heartbeat)

Acceptance:
- alembic миграции применяются на чистую БД.
- интеграционный тест: создать tool/template/session, получить обратно.

---

## 5) Этап 3 — Tool Catalog Service (DB → runtime)

### Цель
Tools перестают быть “просто python классами”, становятся сущностями каталога.

### Задачи
- [ ] Ввести `ToolDescriptor` (Pydantic) как LLM-facing модель.
- [ ] Реализовать `ToolLoader`:
  - загрузка по `python_entrypoint` (import string)
  - fallback: ToolRegistry (если класс уже импортирован)
- [ ] Реализовать `ToolSchemaBuilder`:
  - для FC агентов: build `ChatCompletionFunctionToolParam` с **description != ""**
  - для SGR structured output: вернуть список tool классов для NextStepToolsBuilder
- [ ] Реализовать `ToolExecutor`:
  - исполнить tool на `SessionContext`
  - записать `tool_executions` в БД
  - вернуть result

Acceptance:
- можно добавить tool в БД, указать entrypoint, и runtime сможет его вызвать.

---

## 6) Этап 4 — Templates Service (DB templates → runtime config)

### Задачи
- [ ] Реализовать `TemplateService`:
  - create template
  - create new version
  - activate version
  - get active version
- [ ] Сопоставить template → runtime config:
  - LLMPolicy → openai client settings
  - Prompts → prompt loader
  - ExecutionPolicy → лимиты (итерации/поиск/уточнения)
  - ToolPolicy → allowlist/required/max_tools_in_prompt

Acceptance:
- template создаётся в БД и используется для исполнения.

---

## 7) Этап 5 — Session Service: persisted conversation + context snapshots

### Цель
Session полностью восстанавливаемая после рестарта.

### Задачи
- [ ] Реализовать `SessionContext` (Pydantic), аналог `ResearchContext`, но сериализуемый:
  - state, iteration, counters, sources, searches, execution_result
- [ ] Реализовать `MessageStore`:
  - хранить messages в формате OpenAI (role/content/tool_call_id/tool_calls)
- [ ] Обновить core agent code так, чтобы:
  - `conversation` читалась/писалась через SessionService
  - `_context` сохранялся после каждого шага

Acceptance:
- рестарт runtime не ломает WAITING и можно продолжить session.

---

## 8) Этап 6 — Persistent Runtime: AgentInstance pool + non-blocking clarification

### 8.1. AgentInstance и Pool
- [ ] Реализовать `AgentInstance` (worker):
  - pinned template version
  - shared openai client
  - `run(session_id)` / `resume(session_id)`
  - `reset()` → очистка session state
- [ ] Реализовать `InstancePool`:
  - get_idle(template_id)
  - create_if_needed
  - release(instance_id)

### 8.2. Неблокирующий WAITING (переписываем BaseAgent.execute semantics)
В core:
- [ ] Изменить поведение на:
  - если выполнен ClarificationTool → сохранить session.state=WAITING → завершить run (return)
  - **не** ждать Event внутри агента

В API:
- [ ] `POST /v1/chat/completions` при `model=session_id`:
  - если session.state == WAITING → append clarification message → resume

Acceptance:
- worker не блокируется ожиданием уточнения.
- один worker может обслужить 100 последовательных sessions без пересоздания.

---

## 9) Этап 7 — Tool Search Service (retrieval top-k) и интеграция в agents

### 9.1. Embeddings pipeline
- [ ] Добавить `embedding` поле в tools/templates
- [ ] Реализовать `EmbeddingProvider` интерфейс:
  - `embed_text(text) -> vector`
- [ ] Реализовать job:
  - при create/update tool → пересчитать embedding
  - при create/update template capabilities → пересчитать embedding

### 9.2. ToolSearchService
- [ ] Реализовать retrieval по pgvector:
  - filters policy (type/tags/allowlist/denylist)
  - required tools всегда добавлять
  - max_tools_in_prompt hard limit
  - caching на время session (optional)

### 9.3. Интеграция
- [ ] Внести в `BaseAgent._prepare_tools()` / `_prepare_context()` поддержку “tools subset per step”.
- [ ] В `PromptLoader.get_system_prompt()` перестать всегда печатать все tools; варианты:
  1) system prompt без tools, descriptions в tool metadata
  2) печатать только subset tools (top-k)

Acceptance:
- количество tools в prompt ограничено (логируем top_k).
- агент всё ещё умеет делать поиск/репорт/финал.

---

## 10) Этап 8 — Rules/Discriminators engine (формализация текущих if-ов)

### Цель
Убрать “захардкоженные” правила из `_prepare_tools()` в policy слой.

### Задачи
- [ ] Определить формат rules в template (JSON):
  - conditions: iteration>=N, searches_used>=M, clarifications_used>=K, state==...
  - actions: exclude_tool, keep_only_tools, set_stage
- [ ] Реализовать `RulesEngine.evaluate(session, template) -> ToolPolicyDecision`
- [ ] Применять rules:
  - до retrieval (filter)
  - после retrieval (post-filter)

Acceptance:
- поведение “после max_iterations оставить только FinalAnswer/CreateReport” воспроизводится rules’ами.

---

## 11) Этап 9 — Multi-agent: Agent Directory + Agent-as-Tool + Router

### Задачи
- [ ] AgentDirectoryService:
  - template embeddings
  - `search(query, top_k)` → templates
- [ ] Router:
  - выбрать template по retrieval
  - создать session на выбранном template
  - запустить session на worker
- [ ] Agent-as-Tool:
  - wrapper tool, который вызывает другой template

Acceptance:
- Демонстрация: один “router agent” выбирает из нескольких templates.

---

## 12) Этап 10 — Gateway API: OpenAI compatibility + observability + hardening

### Задачи
- [ ] Полная совместимость SSE с openai-python клиентом.
- [ ] Метрики:
  - durations (llm/tool/retrieval)
  - counters (iterations/tools used)
- [ ] Логи:
  - correlation_id=session_id
  - tool selection trace (почему tool включён/исключён)
- [ ] Security:
  - risk policy для domain tools
  - allowlist per environment

Acceptance:
- e2e тесты: basic, waiting/resume, retrieval, delegation.

---

## 13) Приложение: конкретные “рефакторинг шаги” по core коду

### 13.1. BaseAgent: что меняем
Текущее (`core/base_agent.py`):
- хранит session state в self
- блокируется на clarification

Нужно:
- отделить instance state от session state
- сделать execute re-entrant и non-blocking

Практический путь:
1) Ввести `SessionRuntime` объект:
   - `session_id`, `task`, `context`, `messages`, `stream`
2) На уровне `AgentInstance.run(session_id)`:
   - загрузить session из DB → создать SessionRuntime
   - “подключить” его к агенту (`agent.attach_session(runtime)`)
3) В `execute()`:
   - после каждого шага persist session
   - на ClarificationTool: persist WAITING + return
4) На завершении: persist COMPLETED/FAILED + cleanup + release worker

### 13.2. PromptLoader
Убрать необходимость вставлять **все** tools в system prompt:
- либо печатать только subset tools (top-k)
- либо использовать description в tool metadata (FC) и schema (SGR)

---

Конец документа.
