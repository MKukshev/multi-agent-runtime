# Документ 4 — Migration Map: перенос `sgr-agent-core (sgr-memory-agent)` → новый проект (Вариант B)

> Назначение: максимально практичное сопоставление “старый файл/класс → новый модуль/компонент”, плюс список необходимых изменений в логике.

---

## 1) Что переносим “copy-as-is” (минимальные изменения)

### Tools
- `sgr_deep_research/core/base_tool.py` → `platform/core/tools/base_tool.py`
- `sgr_deep_research/core/tools/*.py` → `platform/core/tools/*`
- `sgr_deep_research/core/tools/mem_tools/*` → `platform/core/tools/mem_tools/*`
- `sgr_deep_research/core/services/mcp_service.py` → `platform/core/mcp/mcp_tools.py` (или `platform/core/services/...`)

### SGR schema builder
- `sgr_deep_research/core/next_step_tool.py` → `platform/core/sgr/next_step_tool.py`

### Streaming protocol
- `sgr_deep_research/core/stream.py` → `platform/core/streaming/openai_sse.py`

---

## 2) Что переносим с рефакторингом (must-refactor)

### BaseAgent
Файл: `sgr_deep_research/core/base_agent.py`

**Причина:** содержит блокирующий clarification wait и хранит session-state внутри self.

**Что делаем:**
- вводим `SessionRuntime` (task/context/messages/stream/log)
- `BaseAgent` превращаем в “алгоритм”, который работает поверх `SessionRuntime`
- ClarificationTool → persist WAITING + return (не блокировать)

### PromptLoader
Файл: `sgr_deep_research/core/services/prompt_loader.py`

**Причина:** системный промпт перечисляет весь toolset.

**Что делаем:**
- либо печатаем только subset tools (retrieval result)
- либо переносим tool descriptions в tool metadata (function schema) и оставляем system prompt общим

### AgentFactory
Файл: `sgr_deep_research/core/agent_factory.py`

**Причина:** создаёт agent per request.

**Что делаем:**
- `TemplateLoader` (DB templates → runtime config)
- `InstanceBuilder` (создание worker instance pinned to template/version)
- `ToolLoader` (DB tools → python class/remote executor)

### API endpoints
Файл: `sgr_deep_research/api/endpoints.py`

**Причина:** in-memory `agents_storage`, нет DB.

**Что делаем:**
- gateway читает/пишет sessions в DB
- runtime исполняет sessions на worker pool
- clarification/resume через DB state machine

---

## 3) Что переписываем “с нуля” (new subsystems)

- Persistence слой:
  - SQLAlchemy models
  - repositories
  - migrations
- Tool Search Service (pgvector retrieval)
- Agent Directory Service (template retrieval)
- Instance Pool (leases, health, reset)
- Admin API (tools/templates CRUD)

---

## 4) Семантические изменения поведения (важно сохранить корректность)

### 4.1. Clarification flow
**Сейчас:**
- агент ждёт event и продолжает в той же coroutine.

**Будет:**
- ClarificationTool → session.state=WAITING, run заканчивается
- при новом сообщении → resume session на любом worker

### 4.2. Agent ID vs Session ID
**Сейчас:**
- `agent.id` используется как OpenAI `model` в SSE.

**Будет:**
- `session_id` — внешний идентификатор для клиента (model=session_id)
- `instance_id` — внутренний идентификатор worker-а (не обязателен клиенту)

### 4.3. Toolset в LLM
**Сейчас:**
- system prompt перечисляет все tools.

**Будет:**
- top-k tools per step через retrieval (плюс обязательные system tools)

---

## 5) Контрольные точки паритета (parity checklist)

- [ ] SGRToolCallingAgent workflow сохраняется:
  - reasoning tool call → tool selection → tool execution → запись tool messages
- [ ] Сообщения в OpenAI формате сохраняются
- [ ] SSE chunks совместимы с openai-python
- [ ] max_iterations/max_searches/max_clarifications влияют на доступность tools
- [ ] CreateReportTool сохраняет отчёт как артефакт
- [ ] Memory tools работают в изолированном storage (как минимум per instance)

---

Конец документа.
