# LLMPolicy: применение и примеры

Политика LLM хранится в версиях шаблонов и теперь применяется прямо в агентах: на её основе создаётся клиент `AsyncOpenAI`, а параметры запроса (модель, температурa, лимит токенов и режим стриминга) автоматически пробрасываются в вызовы чат-комплишенов.

## Конфигурация политики в шаблоне
```python
from platform.runtime import ExecutionPolicy, LLMPolicy, PromptConfig, TemplateService, ToolPolicy

llm_policy = LLMPolicy(
    model="gpt-4o-mini",
    base_url="https://example.ai/v1",
    api_key_ref="CUSTOM_OPENAI_KEY",  # имя переменной окружения
    temperature=0.3,
    max_tokens=256,
    streaming=True,
)

version = await TemplateService(session_factory).create_version(
    template_id,
    llm_policy=llm_policy,
    prompts=PromptConfig(system="You are helpful"),
    execution_policy=ExecutionPolicy(max_iterations=4),
    tool_policy=ToolPolicy(max_tools_in_prompt=3),
    tools=["search"],
    prompt="You are helpful",
    activate=True,
)
```

## Построение OpenAI-клиента в агенте
`BaseAgent` использует `LLMClientFactory` для создания клиента. API-ключ берётся из `api_key_ref` или из `OPENAI_API_KEY`, а `base_url` и остальные поля политики применяются к каждому запросу.

```python
from platform.core.agents.base_agent import BaseAgent
from platform.core.llm import LLMClientFactory
from platform.runtime import ChatMessage, TemplateRuntimeConfig

class MyLLMAgent(BaseAgent):
    async def run(self):
        # Генерация ответа LLM и конвертация в SSE-события для gateway
        user = ChatMessage.text("user", "Hello!").to_openai()
        return await self._generate_llm_response([user], stream=True)

config: TemplateRuntimeConfig = ...  # получен из TemplateService
agent = MyLLMAgent(
    task="hello",
    template_config=config,
    template_version_id=config.version_id,
    llm_client_factory=LLMClientFactory(),
)

# events — готовые SSE-сообщения; содержимое можно собрать так:
answer = "".join(
    event.data["choices"][0]["delta"].get("content", "")
    for event in await agent.run()
    if event.event == "message"
)
```

### Что происходит внутри
- `LLMClientFactory.for_policy()` создаёт (и кеширует) `AsyncOpenAI` с `base_url` и `api_key`, извлечённым из переменной окружения.
- `_generate_llm_response()` формирует payload для `chat.completions.create`, включая `temperature`, `max_tokens` и `stream` (по умолчанию из `LLMPolicy.streaming`).
- Ответы, включая стриминговые чанки, собираются в текст и транслируются в формат SSE, совместимый с OpenAI.

Такой подход гарантирует, что настройки LLM из шаблонов действительно влияют на то, как агент инициализирует клиента и вызывает модель.
