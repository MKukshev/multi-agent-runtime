# План: Авторизация + Chat Memory Agent

## Цель
Добавить систему авторизации с привязкой сессий к пользователям и создать chat-memory-agent для сохранения и поиска по истории чатов.

---

## Фаза 1: Авторизация и пользователи

### 1.1 Модель данных (PostgreSQL)

```sql
-- Таблица пользователей
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    login VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,  -- как обращаться
    about TEXT,                           -- описание в свободной форме
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Таблица авторизационных сессий (cookies)
CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,     -- хеш session token
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_auth_sessions_token ON auth_sessions(token_hash);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);

-- Модификация существующей таблицы sessions (чаты)
ALTER TABLE sessions ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE sessions ADD COLUMN title VARCHAR(255) DEFAULT 'New Chat';
CREATE INDEX idx_sessions_user ON sessions(user_id);
```

### 1.2 Backend: Auth Service

**Файл:** `src/maruntime/auth/service.py`

```python
class AuthService:
    async def register(login, password, display_name, about) -> User
    async def login(login, password) -> AuthSession
    async def logout(session_token) -> None
    async def validate_session(session_token) -> User | None
    async def change_password(user_id, new_password) -> None
    async def get_user(user_id) -> User | None
```

**Хеширование:** bcrypt (passlib)

### 1.3 Backend: Auth Endpoints

**Файл:** `src/maruntime/auth/routes.py`

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход (set cookie) |
| POST | `/auth/logout` | Выход (clear cookie) |
| GET | `/auth/me` | Текущий пользователь |
| PUT | `/auth/password` | Смена пароля |

**Cookie:** `session_token` (httponly, secure in prod)

### 1.4 Backend: Auth Middleware

**Файл:** `src/maruntime/auth/middleware.py`

- Middleware для FastAPI
- Извлекает `session_token` из cookie
- Валидирует сессию
- Добавляет `request.state.user` для authenticated routes

### 1.5 Frontend: Auth Pages

| Страница | Путь | Описание |
|----------|------|----------|
| Login | `/login` | Форма входа |
| Register | `/register` | Форма регистрации |
| Profile | `/profile` | Просмотр/редактирование профиля |

### 1.6 Frontend: Auth Context

```typescript
// contexts/AuthContext.tsx
interface User {
  id: string;
  login: string;
  displayName: string;
  about: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login(login: string, password: string): Promise<void>;
  register(data: RegisterData): Promise<void>;
  logout(): Promise<void>;
}
```

---

## Фаза 2: Привязка сессий к пользователям

### 2.1 Модификация Session Service

**Изменения в:** `src/maruntime/runtime/session_service.py`

```python
async def start_session(template_version_id, user_id=None, title=None) -> SessionContext
async def list_user_sessions(user_id) -> list[SessionContext]
async def get_session_with_user(session_id) -> SessionContext  # includes user_id
```

### 2.2 Модификация Gateway Routes

**Изменения в:** `src/maruntime/gateway/routes.py`

- Требовать авторизацию для `/v1/chat/completions`
- Извлекать `user_id` из `request.state.user`
- Передавать `user_id` при создании/возобновлении сессии

### 2.3 Frontend: Chat Management

**Изменения в:** `admin-ui/src/app/chat/page.tsx`

- Sidebar с списком чатов пользователя
- Кнопка "New Chat"
- Переключение между чатами
- Удаление чата

**Новый компонент:** `admin-ui/src/components/ChatSidebar.tsx`

---

## Фаза 3: Chat Memory Agent

### 3.1 Формат хранения истории

**Путь:** `memory_dir/chats/{user_id}/{session_id}.md`

```markdown
# Chat Session
ID: {session_id}
User: {display_name} ({user_id})
Agent: {agent_name}
Created: {timestamp}
Updated: {timestamp}

---

## Conversation

[2026-01-08 14:30:15] **{display_name}**: Какая погода сегодня в Москве?

[2026-01-08 14:30:45] **{agent_name}**: Сегодня в Москве температура -6°C, облачно с небольшим снегом.

[2026-01-08 14:32:10] **{display_name}**: А завтра?

[2026-01-08 14:32:35] **{agent_name}**: Завтра ожидается -8°C, преимущественно облачно.
```

### 3.2 Chat Memory Service

**Файл:** `src/maruntime/memory/chat_memory_service.py`

```python
class ChatMemoryService:
    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir

    async def append_message(
        user_id: str,
        session_id: str,
        role: str,  # user | agent
        actor_name: str,
        content: str,
        agent_name: str | None = None
    ) -> None
    
    async def get_chat_history(user_id: str, session_id: str) -> str
    
    async def search_chats(
        user_id: str,
        query: str,
        scope: str = "all"  # "current" | "all"
    ) -> list[SearchResult]
    
    async def create_chat_document(
        user_id: str,
        session_id: str,
        display_name: str,
        agent_name: str
    ) -> None
```

### 3.3 Интеграция с Agent Loop

**Изменения в:** `src/maruntime/core/agents/tool_calling_agent.py`

После каждого user message и agent response:
```python
await chat_memory_service.append_message(
    user_id=self.session_context.user_id,
    session_id=self.session_context.session_id,
    role="user" | "assistant",
    actor_name=display_name | agent_name,
    content=message_content
)
```

### 3.4 Search Tool

**Файл:** `src/maruntime/core/tools/chat_history_search.py`

```python
class ChatHistorySearchTool(PydanticTool):
    """Search through chat history with the user."""
    
    query: str = Field(description="Search query")
    scope: str = Field(default="all", description="'current' for current chat, 'all' for all user chats")
    
    async def __call__(self, context, config):
        results = await chat_memory_service.search_chats(
            user_id=context.user_id,
            query=self.query,
            scope=self.scope
        )
        return format_search_results(results)
```

---

## Фаза 4: User Profile Memory

### 4.1 Формат user.md

**Путь:** `memory_dir/users/{user_id}/user.md`

```markdown
# User Profile

## Identity
- **ID:** {user_id}
- **Login:** {login}
- **Display Name:** {display_name}
- **Registered:** {timestamp}

## About
{about_text_from_registration}

## Preferences
(Reserved for future use - agent can learn preferences from conversations)
```

### 4.2 User Memory Service

**Файл:** `src/maruntime/memory/user_memory_service.py`

```python
class UserMemoryService:
    async def create_user_profile(user: User) -> None
    async def get_user_profile(user_id: str) -> str
    async def update_user_profile(user_id: str, section: str, content: str) -> None
```

### 4.3 Интеграция с Memory Agent

**Изменения в:** system prompt для memory-agent

- Читать `user.md` для контекста о пользователе
- Использовать `display_name` при обращении к пользователю

---

## Фаза 5: UI Improvements

### 5.1 Layout с Sidebar

```
+------------------+--------------------------------+
|  Logo            |  Header (User Menu)            |
+------------------+--------------------------------+
|  Chat List       |                                |
|  - Chat 1        |                                |
|  - Chat 2        |       Chat Messages            |
|  - Chat 3        |                                |
|  [+ New Chat]    |                                |
|                  +--------------------------------+
|                  |  Input Field     [Send]        |
+------------------+--------------------------------+
```

### 5.2 Компоненты

| Компонент | Файл | Описание |
|-----------|------|----------|
| ChatSidebar | `components/ChatSidebar.tsx` | Список чатов + New Chat |
| UserMenu | `components/UserMenu.tsx` | Dropdown: Profile, Logout |
| ChatLayout | `app/chat/layout.tsx` | Layout с sidebar |

---

## Порядок реализации

### Этап 1: База (Фаза 1.1-1.4)
1. [ ] Alembic миграция для users, auth_sessions, sessions changes
2. [ ] SQLAlchemy модели User, AuthSession
3. [ ] AuthService с bcrypt
4. [ ] Auth routes (register, login, logout, me)
5. [ ] Auth middleware

### Этап 2: Frontend Auth (Фаза 1.5-1.6)
6. [ ] AuthContext provider
7. [ ] Login page
8. [ ] Register page
9. [ ] Profile page
10. [ ] Protected routes

### Этап 3: Sessions + Users (Фаза 2)
11. [ ] Session service modifications
12. [ ] Gateway routes auth integration
13. [ ] ChatSidebar component
14. [ ] Chat list API

### Этап 4: Chat Memory (Фаза 3)
15. [ ] ChatMemoryService
16. [ ] Integration with agent loop
17. [ ] ChatHistorySearchTool

### Этап 5: User Memory (Фаза 4)
18. [ ] UserMemoryService
19. [ ] Create user.md on registration
20. [ ] Memory agent integration

### Этап 6: Polish (Фаза 5)
21. [ ] Chat layout with sidebar
22. [ ] User menu
23. [ ] UI polish

---

## Файловая структура (новые файлы)

```
src/maruntime/
├── auth/
│   ├── __init__.py
│   ├── models.py          # User, AuthSession SQLAlchemy models
│   ├── service.py         # AuthService
│   ├── routes.py          # FastAPI routes
│   └── middleware.py      # Auth middleware
├── memory/
│   ├── __init__.py
│   ├── chat_memory_service.py
│   └── user_memory_service.py
└── core/tools/
    └── chat_history_search.py

admin-ui/src/
├── contexts/
│   └── AuthContext.tsx
├── components/
│   ├── ChatSidebar.tsx
│   └── UserMenu.tsx
└── app/
    ├── login/page.tsx
    ├── register/page.tsx
    ├── profile/page.tsx
    └── chat/
        └── layout.tsx

alembic/versions/
└── xxx_add_auth_tables.py
```

---

## Зависимости

**Backend:**
```
passlib[bcrypt]  # password hashing
python-multipart  # form data for auth
```

**Frontend:**
```
js-cookie  # cookie handling (optional, можно через fetch credentials)
```

---

## Примечания

1. **Простота для MVP:** Минимум валидаций, без email verification
2. **Session cookie:** httponly для безопасности
3. **Миграция:** Существующие сессии без user_id остаются как legacy
4. **Поиск:** Начинаем с простого текстового поиска (grep по файлам)
