# Migration Inventory: `sgr-memory-agent` → Variant B runtime

Список исходных модулей и предполагаемый статус переноса. Используется как чеклист для этапа 0 из плана реализации (см. `docs/03-implementation-plan-variant-b-v2.md`).

## Copy (минимальные изменения)
- `sgr_deep_research/core/base_tool.py` → `platform/core/tools/base_tool.py`
- `sgr_deep_research/core/tools/*.py` → `platform/core/tools/*`
- `sgr_deep_research/core/tools/mem_tools/*` → `platform/core/tools/mem_tools/*`
- `sgr_deep_research/core/services/mcp_service.py` → `platform/core/mcp/mcp_tools.py`
- `sgr_deep_research/core/next_step_tool.py` → `platform/core/sgr/next_step_tool.py`
- `sgr_deep_research/core/stream.py` → `platform/core/streaming/openai_sse.py`

## Refactor (обязательные изменения при переносе)
- `sgr_deep_research/core/base_agent.py` → `platform/core/agents/base_agent.py`
  - Разделить состояние session/runtime, убрать блокирующий WAITING.
- `sgr_deep_research/core/services/prompt_loader.py` → `platform/core/services/prompt_loader.py`
  - Исключить перечисление всех tools в system prompt; поддержать subset/top-k.
- `sgr_deep_research/core/agent_factory.py` → `platform/runtime/instance_builder.py`
  - Поддержать загрузку шаблонов/инструментов из БД, создание инстансов.
- `sgr_deep_research/api/endpoints.py` → `platform/gateway/routes.py`
  - Перевести на хранение сессий в БД и неблокирующий resume-flow.

## Rewrite (новые подсистемы)
- Persistence слой (модели БД, alembic миграции, репозитории).
- Tool Search Service (pgvector retrieval, фильтры по policy/rules).
- Agent Directory + Router (embeddings шаблонов, agent-as-tool wrapper).
- Instance Pool (lease/heartbeat/reset, pinned template version).
- Admin API (CRUD tools/templates/версионирование, список инстансов/сессий).
- Observability (метрики, трассировка выбора инструментов).

## Паритетные требования (контрольная проверка)
- Сохранить workflow SGRToolCallingAgent: reasoning tool → tool call → tool exec → tool messages.
- Поддерживать OpenAI-совместимый формат сообщений и SSE поток.
- Соблюдать лимиты max_iterations/searches/clarifications через policy/rules.
- Обеспечить сохранение артефактов (например, отчётов) и корректную работу memory tools.
