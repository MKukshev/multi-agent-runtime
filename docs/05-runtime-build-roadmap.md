# Multi-agent runtime build roadmap (Variant B)

> Цель: консолидированный пошаговый план запуска нового мульти-агентного рантайма на базе `sgr-agent-core` (ветка `sgr-memory-agent`) с учётом целевой архитектуры Variant B. План упрощает проверку готовности, связывает переносимые части кода и новые подсистемы.

## Этап 0 — инвентаризация и подготовка базовой кодовой базы
- Зафиксировать список модулей для прямого переноса (tools, SGR/FC агенты, `next_step_tool`, поток SSE) и для обязательного рефакторинга (`base_agent`, `prompt_loader`, `agent_factory`, API слой).
- Выпустить артефакт `docs/migration_inventory.md` с пометкой `copy / refactor / rewrite` для каждого исходного файла.
- Результат: подтверждённый перечень переносимых компонентов и известных разрывов.

## Этап 1 — скелет проекта и перенос core без БД
- Создать новую структуру пакета (`platform/gateway`, `platform/runtime`, `platform/core`, `platform/persistence`, `platform/retrieval`, `platform/admin`).
- Перенести core-реализации (tools, агенты, `next_step_tool`, `prompt_loader`, `stream`) и обновить импорты под новую структуру.
- Собрать минимальный in-memory демо-раннер (один запрос, стриминг SSE) для проверки совместимости переносимого кода.
- Результат: код компилируется, демо-запрос выполняется и стримится.

## Этап 2 — слой хранения: модели БД, миграции, репозитории
- Спроектировать таблицы: `tools`, `agent_templates` (+ версии), `sessions`, `session_messages`, `tool_executions`, `agent_instances`, при необходимости `sources` и `artifacts`.
- Настроить alembic и реализовать репозитории для CRUD/активации tools/templates, работы с сессиями и пулами инстансов.
- Результат: миграции применяются на чистую БД; интеграционный тест создаёт и читает tool/template/session.

## Этап 3 — Tool Catalog и загрузка исполнителей
- Определить `ToolDescriptor` (Pydantic) как контракт каталога и LLM-facing модели.
- Реализовать `ToolLoader` (python entrypoint/registry), `ToolSchemaBuilder` (FC schema + SGR schema union) и `ToolExecutor` с записью `tool_executions` в БД.
- Результат: инструмент, добавленный в БД, подхватывается рантаймом и исполняется в сессии.

## Этап 4 — Templates Service
- Ввести `TemplateService` для CRUD, версионирования и активации шаблонов поведения.
- Отразить поля шаблона в runtime-конфигурацию: LLM policy, execution limits, prompts, tool policy (allow/deny, required system tools, `max_tools_in_prompt`).
- Результат: активный шаблон из БД используется агентом при запуске сессии.

## Этап 5 — Session Service и сериализация контекста
- Описать `SessionContext` (сериализуемый аналог `ResearchContext`) и `MessageStore` для истории в формате OpenAI.
- Переподключить агентский цикл к SessionService так, чтобы после каждого шага сохранять контекст и сообщения.
- Результат: рестарт процесса не ломает сессию; её можно продолжить после WAITING.

## Этап 6 — Persistent runtime и неблокирующий clarification
- Реализовать `AgentInstance` (долгоживущий worker, закреплённый за шаблоном) и `InstancePool` (claim/release, auto-create).
- Переписать `BaseAgent.execute` под re-entrant семантику: ClarificationTool → `session.state=WAITING` → завершить run без блокировки; `resume(session_id)` стартует на любом idle-инстансе.
- Результат: один worker обрабатывает серию сессий без пересоздания и не блокируется на уточнениях.

## Этап 7 — Tool Search Service (retrieval top-k)
- Добавить `embedding` для tools/templates и `EmbeddingProvider` с пересчётом при обновлении.
- Реализовать `ToolSearchService` (pgvector retrieval + policy/rules фильтры + обязательные system tools + лимит `max_tools_in_prompt`).
- Интегрировать в `_prepare_tools` и обновлённый `PromptLoader`, чтобы в промпт попадал subset актуальных tools.
- Результат: количество tools в промпте ограничено top-k, выбор логируется.

## Этап 8 — Rules/Discriminators
- Формализовать правила доступности tools (итерации, счётчики, стадии) в policy-шаблоне.
- Реализовать `RulesEngine.evaluate(session, template)` с pre/post-фильтрацией выдачи ToolSearchService.
- Результат: прежние условные блоки (например, только FinalAnswer после `max_iterations`) воспроизводятся через правила.

## Этап 9 — Gateway и Admin API
- Gateway: OpenAI совместимость (`/v1/chat/completions` streaming, `GET /v1/models`), поддержка `model=session_id` для resume, SSE протокол из core.
- Admin: CRUD для tools/templates, список инстансов/сессий, активация версий.
- Результат: клиент openai-python работает “из коробки”; админ-операции управляют каталогом и шаблонами.

## Этап 10 — Multi-agent и делегирование
- AgentDirectoryService: embeddings поиска по шаблонам, router для выбора подходящего агента.
- Agent-as-Tool: wrapper-инструмент для вызова другого шаблона/агента; демонстрация делегирования.
- Результат: роутер-агент способен подобрать и дернуть нужный шаблон или делегировать задачу.

## Этап 11 — Наблюдаемость и контроль паритета
- Добавить метрики (LLM/tool durations, iterations/tools_used counters), корреляцию логов по `session_id`, трассировку выбора tools.
- Проверить parity-чеклист: совместимость SSE, сохранение формата сообщений, влияние лимитов итераций/поиска/уточнений, работа отчётов/памяти.
- Результат: прозрачная диагностика выполнения и подтверждённый паритет с исходной логикой SGR.
