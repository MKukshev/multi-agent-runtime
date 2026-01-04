# Документ 1 (v2) — Текущая внутренняя логика **SGR-Agent Core** (ветка `sgr-memory-agent`) на уровне кода

> Назначение: зафиксировать **реальную** архитектуру и алгоритмику работы репозитория `sgr-agent-core` в ветке `sgr-memory-agent`, чтобы перенести её в новый проект (Вариант B: persistent runtime + templates + tool catalog + tool search + multi-agent).

Документ основан на анализе исходников из архива ветки `sgr-memory-agent` (структура пакета `sgr_deep_research/*`).

---

## 1) Структура пакета и “точки входа”

### 1.1. Пакеты/модули
Ключевые модули:

- `sgr_deep_research/__main__.py` — запуск FastAPI сервера, загрузка конфигов и дефиниций агентов
- `sgr_deep_research/api/endpoints.py` — OpenAI-like API (`/v1/chat/completions`) + endpoints для состояния агента и clarification
- `sgr_deep_research/core/base_agent.py` — **каркас агента**, главный execution-loop
- `sgr_deep_research/core/agents/*` — реализации стратегий: SGR (structured output), tool calling, hybrid
- `sgr_deep_research/core/base_tool.py` — контракт инструмента (Pydantic + `async __call__`) + MCP tool base
- `sgr_deep_research/core/tools/*` — инструменты (web search, extract, report, memory tools и т. д.)
- `sgr_deep_research/core/agent_definition.py` — модели конфигов + AgentDefinition
- `sgr_deep_research/core/agent_config.py` — `GlobalConfig` singleton: ENV + YAML + merging agents
- `sgr_deep_research/core/agent_factory.py` — создание агента по AgentDefinition (agent class + openai client + tools)
- `sgr_deep_research/core/services/*` — prompt loader, MCP tools converter, tavily service, registry
- `sgr_deep_research/core/stream.py` — генератор SSE в OpenAI-compatible формате
- `sgr_deep_research/core/models.py` — `ResearchContext`, `AgentStatesEnum`, модели поиска/источников
- `sgr_deep_research/core/next_step_tool.py` — SGR “NextStepToolsBuilder”: dynamic union schema для structured output

---

## 2) Загрузка конфигурации и дефиниций агентов (boot sequence)

### 2.1. Запуск приложения (`sgr_deep_research/__main__.py`)
Алгоритм `main()`:

1) `setup_logging()` (из `sgr_deep_research/settings.py`) — читает `logging_config.yaml`.
2) Загружает CLI параметры `ServerConfig()` (файл конфига, файл дефиниций агентов, host/port).
3) `GlobalConfig.from_yaml(args.config_file)` — загружает `config.yaml` (или другой путь), формирует singleton.
4) `config.agents.update(get_default_agents_definitions())` — добавляет дефолтные агенты (из `default_definitions.py`).
5) `config.definitions_from_yaml(args.agents_file)` — загружает/мерджит `agents.yaml`.
6) Создаёт FastAPI app, подключает роутер `sgr_deep_research/api/endpoints.py`.

**Важно для переноса:** дефиниции агентов (templates) реально создаются **в runtime на старте** путём merge:
- global config (LLM/Search/Prompts/Execution/MCP),
- default agent definitions,
- overrides из `agents.yaml`.

В новом проекте (Вариант B) это станет: **seed** в БД + версия шаблонов + activation.

---

## 3) Registry: как регистрируются агенты и tools

### 3.1. Общий механизм (`core/services/registry.py`)
`Registry` — static-class с:
- `register(cls)` / `register(name="...")`
- `get(name)`
- `list_items()`
- `resolve(names)`

Есть два наследника:
- `AgentRegistry`
- `ToolRegistry`

### 3.2. Авто-регистрация агентов (`core/base_agent.py`)
`AgentRegistryMixin.__init_subclass__` автоматически регистрирует любой класс-наследник `BaseAgent` (кроме самого BaseAgent), используя `cls.name`.

### 3.3. Авто-регистрация инструментов (`core/base_tool.py`)
`ToolRegistryMixin.__init_subclass__` автоматически регистрирует любой класс-наследник `BaseTool` (кроме BaseTool/MCPBaseTool), используя `cls.tool_name`.

`BaseTool.__init_subclass__` задаёт:
- `tool_name = cls.tool_name or cls.__name__.lower()`
- `description = cls.description or cls.__doc__ or ""`

---

## 4) Конфигурационные модели: что сейчас можно настраивать

### 4.1. AgentConfig (`core/agent_definition.py`)
Секции:

- **LLMConfig**
  - `api_key`
  - `base_url`
  - `model` (default: `gpt-4o-mini`)
  - `max_tokens` (default: 8000)
  - `temperature` (default: 0.4)
  - `proxy`

- **SearchConfig**
  - `tavily_api_key`, `tavily_api_base_url`
  - `max_searches`
  - `max_results`
  - `content_limit`

- **ExecutionConfig**
  - `max_clarifications`
  - `max_iterations`
  - `mcp_context_limit`
  - `logs_dir`
  - `reports_dir`
  - `extra="allow"` (разрешает дополнительные поля)

- **PromptsConfig**
  - *file paths*: `system_prompt_file`, `initial_user_request_file`, `clarification_response_file`
  - *inline*: `system_prompt_str`, `initial_user_request_str`, `clarification_response_str`
  - computed fields: `system_prompt`, `initial_user_request`, `clarification_response`
  - приоритет: строка > файл

- **MCPConfig** (fastmcp)

### 4.2. AgentDefinition (шаблон агента в текущей системе)
`AgentDefinition` наследуется от `AgentConfig` и добавляет:
- `name`
- `base_class` (class / import string / str)
- `tools` (list[str] или list[type])

Ключевой механизм: `default_config_override_validator` автоматически мерджит поля агентского определения поверх `GlobalConfig()`:
- llm/search/prompts/execution/mcp берутся из GlobalConfig и обновляются overrides агента.

---

## 5) PromptLoader: как формируется контекст LLM

### 5.1. System prompt (`core/services/prompt_loader.py`)
`PromptLoader.get_system_prompt(available_tools, prompts_config)`:
- читает `prompts_config.system_prompt`
- формирует список:
  - `"{i}. {tool.tool_name}: {tool.description}"` для каждого tool
- вставляет в `{available_tools}` placeholder шаблона system prompt

**Следствие:** при большом числе tools — системный промпт раздувается. Это прямо связано с требованием Tool Search Service в новом проекте.

### 5.2. Initial user request
`PromptLoader.get_initial_user_request(task, prompts_config)` вставляет `task` и `current_date`.

### 5.3. Clarification response
`PromptLoader.get_clarification_template(clarifications, prompts_config)` — формирует сообщение пользователя с уточнением.

---

## 6) AgentFactory: как сейчас создаётся agent instance под запрос

Модуль: `core/agent_factory.py`.

Алгоритм `AgentFactory.create(agent_def, task)`:

1) Resolve base class:
   - если `agent_def.base_class` str → `AgentRegistry.get()`
   - иначе использует класс напрямую
2) Build MCP tools: `MCP2ToolConverter.build_tools_from_mcp(agent_def.mcp)`
3) Resolve tools list:
   - tool name str → `ToolRegistry.get(tool)`
4) Create OpenAI client: `_create_client(agent_def.llm)` (AsyncOpenAI + proxy support)
5) Instantiate agent:
   - `BaseClass(task=task, def_name=agent_def.name, toolkit=tools, openai_client=client, agent_config=agent_def)`

**Ключевое ограничение:** агент создаётся под запрос (per request) и “умирает логически” после выполнения.

---

## 7) BaseAgent: основной execution loop, состояние и clarification

Файл: `core/base_agent.py`.

### 7.1. Поля BaseAgent (важно для переноса)
- `id`: `f"{def_name or self.name}_{uuid.uuid4()}"` (используется как `model` в SSE)
- `openai_client`: `AsyncOpenAI`
- `config`: `AgentConfig` (по сути AgentDefinition)
- `task`: исходная задача (user request)
- `toolkit`: list[Type[BaseTool]] — **классы** инструментов
- `_context`: `ResearchContext()` — runtime состояние
- `conversation`: list[dict] — история сообщений (без system/initial, они добавляются при подготовке контекста)
- `streaming_generator`: `OpenAIStreamingGenerator(model=self.id)`
- `log`: list[dict] — детальный debug log по шагам

### 7.2. ResearchContext (`core/models.py`)
- `state`: INITED / RESEARCHING / WAITING_FOR_CLARIFICATION / COMPLETED / FAILED / ERROR
- `iteration`: int
- `searches_used`: int
- `clarifications_used`: int
- `searches`: list[SearchResult]
- `sources`: dict[url -> SourceData]
- `clarification_received`: `asyncio.Event` (для синхронизации в текущей реализации)
- `execution_result`: str | None
- `current_step_reasoning`: Any

### 7.3. execute(): фактический loop
Упрощённо:

```python
while context.state not in FINISH_STATES:
    context.iteration += 1

    reasoning = await _reasoning_phase()
    context.current_step_reasoning = reasoning

    action_tool = await _select_action_phase(reasoning)
    await _action_phase(action_tool)

    if isinstance(action_tool, ClarificationTool):
        context.state = WAITING_FOR_CLARIFICATION
        streaming_generator.finish()
        context.clarification_received.clear()
        await context.clarification_received.wait()
        continue
```

**Важно:** в текущей реализации агент **блокируется** и ждёт `clarification_received` event.

### 7.4. provide_clarification()
Метод:
- добавляет сообщение `"role":"user"` в `conversation`, используя `PromptLoader.get_clarification_template`
- инкрементирует `clarifications_used`
- `clarification_received.set()`
- переводит state в `RESEARCHING`

### 7.5. Логирование и сохранение агент-лога
`_save_agent_log()`:
- берёт `logs_dir` из `GlobalConfig().execution.logs_dir`
- пишет JSON лог с:
  - `id`, `model_config` (без api_key/proxy), `task`, `toolkit`, `log[]`

---

## 8) Реализации агентов (core/agents/*)

### 8.1. SGRAgent (structured output)
Файл: `core/agents/sgr_agent.py`.

Особенности:
- `_prepare_tools()` возвращает **Pydantic модель** (не tools list) через `NextStepToolsBuilder.build_NextStepTools(...)`.
- `_reasoning_phase()` вызывает:
  - `openai_client.chat.completions.stream(..., response_format=<NextStepTools>)`
  - `reasoning = completion.choices[0].message.parsed`
- `_select_action_phase()` извлекает `tool = reasoning.function` (инстанс BaseTool)
- `_action_phase()` выполняет `await tool(context, config)` и пишет tool message.

**SGR-ключ:** модель возвращает структурированный объект, в котором сразу есть `function` (выбранный инструмент) и reasoning-поля (унаследованы от `ReasoningTool`).

### 8.2. NextStepToolsBuilder (динамический union инструментов)
Файл: `core/next_step_tool.py`.

Механизм:
- для каждого инструмента создаётся “дискриминирующая” модель `D_<Tool>` с полем `tool_name_discriminator: Literal[tool_name]`
- затем строится discriminated union всех таких моделей (OR-тип) и назначается в `NextStepToolStub.function`
- итог: LLM получает schema, где поле `function` должно соответствовать одному из инструментов

### 8.3. ToolCallingAgent (native function calling)
Файл: `core/agents/tool_calling_agent.py`.

Особенности:
- `_reasoning_phase()` отсутствует
- `_prepare_tools()` возвращает `list[ChatCompletionFunctionToolParam]`, строится `pydantic_function_tool(tool_class, name=tool_name, description="")`
- `_select_action_phase()`:
  - запускает streaming completion с `tool_choice="required"` и `parallel_tool_calls=True`
  - после завершения читает `completion.choices[0].message.tool_calls`
  - поддерживает **несколько tool calls** (list)
  - добавляет assistant message с tool_calls и создаёт tool_call_id вида `"{iteration}-action-{idx}"`
- `_action_phase()`:
  - выполняет tool(ы) по очереди
  - добавляет tool message для каждого tool_call_id
  - стримит результат как `add_chunk_from_str`

> Нюанс: `BaseAgent.execute()` проверяет `isinstance(action_tool, ClarificationTool)`. Если ToolCallingAgent вернёт список tools, этот чек не сработает. В текущем дизайне предполагается, что ClarificationTool вызывается не параллельно с другими.

### 8.4. SGRToolCallingAgent (hybrid: reasoning tool + FC selection)
Файл: `core/agents/sgr_tool_calling_agent.py`.

Особенности:
- наследуется от `SGRAgent`, но переопределяет `_prepare_tools/_reasoning_phase/_select_action_phase`
- добавляет `ReasoningTool` в `toolkit`
- `_reasoning_phase()`:
  - вызывает completion с `tool_choice` принудительно на `ReasoningTool`
  - получает parsed_arguments ReasoningTool
  - добавляет assistant tool_call + tool message (результат `await reasoning(context)` = JSON reasoning)
- `_select_action_phase()`:
  - вызывает completion с `tool_choice="required"`
  - пытается получить tool_call; если LLM вернул текст — fallback на `FinalAnswerTool(status=COMPLETED)`
  - добавляет assistant message + tool_call
- `_action_phase()` — наследуется от `SGRAgent` (один tool_call)

### 8.5. Deprecated варианты
- `SGRAutoToolCallingAgent`, `SGRSOToolCallingAgent` — помечены как deprecated (benchmark).

---

## 9) Инструменты (Tools) — состав, поля, side effects

### 9.1. System / Core tools (ядро)
- `ReasoningTool` (`core/tools/reasoning_tool.py`)
  - поля: reasoning_steps, current_situation, plan_status, enough_data, remaining_steps, task_completed
  - __call__ возвращает JSON модели
- `ClarificationTool` (`core/tools/clarification_tool.py`)
  - __call__ возвращает список вопросов (строкой)
  - **не меняет context.state** (это делает BaseAgent.execute)
- `FinalAnswerTool` (`core/tools/final_answer_tool.py`)
  - side effects: `context.state = COMPLETED/FAILED`, `context.execution_result = answer`

### 9.2. Research tools
- `WebSearchTool`
  - вызывает Tavily API через `TavilySearchService`
  - side effects: пополняет `context.sources`, `context.searches`, `context.searches_used += 1`
- `ExtractPageContentTool`
  - вызывает Tavily extract по urls
  - обновляет `context.sources[url].full_content`
- `CreateReportTool`
  - сохраняет `.md` в `config.execution.reports_dir`
  - возвращает JSON со статистикой, путь к файлу

### 9.3. Plan tools
- `GeneratePlanTool`
- `AdaptPlanTool`
Оба возвращают JSON (без поля reasoning).

### 9.4. Memory tools (ветка `sgr-memory-agent`)
Пакет: `core/tools/mem_tools/*`. Все инструменты работают с файловой памятью в директории:

- `MEMORY_PATH = "memory_dir"` (см. `mem_tools/settings.py`)

Инструменты:
- File ops: `CreateFileTool`, `ReadFileTool`, `UpdateFileTool`, `DeleteFileTool`, `CheckIfFileExistsTool`
- Dir ops: `CreateDirTool`, `CheckIfDirExistsTool`
- Utilities: `GetSizeTool` (рекурсивный размер), `GetListFilesTool`, `GoToLinkTool` (obsidian-style `[[path]]`)

Нюансы:
- часть инструментов возвращает `"True"` / `"Error: ..."` строками, часть кидает exception
- `mem_tools/utils.py` содержит size limit checks, но использует `os.path.getsize()` на директорию/текущую папку (это **не** суммарный размер). При переносе лучше заменить на реализацию как в `GetSizeTool`.

---

## 10) Streaming: OpenAI-совместимый SSE

Файл: `core/stream.py`.

`OpenAIStreamingGenerator`:
- кладёт в очередь SSE-строки вида `data: {json}\n\n`
- может:
  - `add_chunk(ChatCompletionChunk)`
  - `add_chunk_from_str(text)` — искусственный chunk
  - `add_tool_call(tool_call_id, function_name, arguments)` — искусственный tool_call chunk
  - `finish(content=None)` → финальный chunk + `[DONE]` + termination signal

В API это используется через `StreamingResponse(generator.stream(), media_type="text/event-stream")`.

---

## 11) API слой: как сейчас устроен “lifecycle”

Файл: `api/endpoints.py`.

### 11.1. in-memory storage
`agents_storage: dict[str, BaseAgent] = {}` — хранит активные агенты.

### 11.2. /v1/chat/completions (только stream=true)
Логика:

1) Если `request.model` похож на agent_id (`_is_agent_id`) и:
   - agent есть в storage
   - agent.state == WAITING_FOR_CLARIFICATION  
   → роутим в `provide_clarification(...)`

2) Иначе:
   - извлекаем последнюю user message как task
   - находим agent_def по `request.model` среди `AgentFactory.get_definitions_list()`
   - `agent = await AgentFactory.create(agent_def, task)`
   - `agents_storage[agent.id] = agent`
   - `asyncio.create_task(agent.execute())`
   - возвращаем SSE stream

### 11.3. /agents/{agent_id}/provide_clarification
- вызывает `agent.provide_clarification(...)`
- возвращает SSE stream **того же** `agent.streaming_generator`

---

## 12) Почему текущая архитектура не соответствует требованию “persistent lifecycle”

Текущий дизайн **частично** поддерживает “живой агент” (wait/clarify), но:

1) Инстанс создаётся на каждый первый запрос (`AgentFactory.create`).
2) Storage — in-memory dict; при рестарте сервиса все активные агенты теряются.
3) WAITING реализован как блокировка coroutine (`await Event.wait()`), из-за чего worker занят и не может обслуживать другие сессии без дополнительных инстансов.
4) System prompt каждый шаг включает перечисление **всех** tools (контекст растёт).
5) Нет каталога tools/templates в БД, нет версий, нет policy/retrieval слоя.

---

## 13) Что переносим в новый проект “как есть”, а что меняем

### 13.1. Переносим (core invariants)
- формат conversation сообщений (system/user/assistant/tool)
- контракты инструментов: Pydantic + `async __call__`
- SGR NextStepToolsBuilder (если остаёмся на structured output варианте)
- алгоритмику SGRToolCallingAgent (reasoning tool → tool calling → tool exec)
- logging semantics (step logs), но переносим в БД

### 13.2. Меняем (для Варианта B)
- вводим **AgentInstance (worker)** и **Session** как отдельные сущности
- WAITING перестаёт блокировать worker: “Clarification → сохранить session → завершить run → вернуть worker в IDLE”
- добавляем Tool Catalog + Tool Search (pgvector)
- добавляем Agent Templates (DB) + создание runtime instances
- добавляем Multi-agent Router / Agent Directory
