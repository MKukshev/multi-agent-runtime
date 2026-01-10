-- =============================================================================
-- Multi-Agent Runtime - Database Schema
-- Version: 20260109_000001
-- Compatible with: PostgreSQL 14+
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Drop existing tables (in reverse dependency order)
DROP TABLE IF EXISTS tool_executions CASCADE;
DROP TABLE IF EXISTS artifacts CASCADE;
DROP TABLE IF EXISTS sources CASCADE;
DROP TABLE IF EXISTS chat_turns CASCADE;
DROP TABLE IF EXISTS session_messages CASCADE;
DROP TABLE IF EXISTS auth_sessions CASCADE;
DROP TABLE IF EXISTS agent_instances CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS template_versions CASCADE;
DROP TABLE IF EXISTS agent_templates CASCADE;
DROP TABLE IF EXISTS tools CASCADE;
DROP TABLE IF EXISTS system_prompts CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS alembic_version CASCADE;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Users
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    login VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    about TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Auth sessions
CREATE TABLE auth_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent Templates (blueprints for agents)
CREATE TABLE agent_templates (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    active_version_id VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Template Versions (versioned configurations)
CREATE TABLE template_versions (
    id VARCHAR(36) PRIMARY KEY,
    template_id VARCHAR(36) NOT NULL REFERENCES agent_templates(id),
    version INTEGER NOT NULL,
    settings JSON,
    embedding JSON,
    prompt TEXT,
    tools JSON,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_template_version UNIQUE (template_id, version)
);

-- Add FK from agent_templates to template_versions (deferred)
ALTER TABLE agent_templates
    ADD CONSTRAINT fk_agent_templates_active_version
    FOREIGN KEY (active_version_id) REFERENCES template_versions(id);

-- Tools catalog
CREATE TABLE tools (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    python_entrypoint VARCHAR(255),
    config JSON,
    embedding JSON,
    category VARCHAR(50) NOT NULL DEFAULT 'utility',
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- System Prompts (global prompt templates)
CREATE TABLE system_prompts (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    content TEXT NOT NULL,
    placeholders JSON,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- =============================================================================
-- Session & Instance Tables
-- =============================================================================

-- Sessions (conversation contexts)
CREATE TABLE sessions (
    id VARCHAR(36) PRIMARY KEY,
    template_version_id VARCHAR(36) NOT NULL,
    instance_id VARCHAR(36),
    user_id VARCHAR(36),
    title VARCHAR(255) DEFAULT 'New Chat',
    state VARCHAR(50),
    context JSON,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_sessions_template_versions FOREIGN KEY (template_version_id) REFERENCES template_versions(id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Agent Instances (Named Slots model - runtime agents)
CREATE TABLE agent_instances (
    id VARCHAR(36) PRIMARY KEY,
    template_id VARCHAR(36) NOT NULL REFERENCES agent_templates(id),
    template_version_id VARCHAR(36) NOT NULL REFERENCES template_versions(id),
    current_session_id VARCHAR(36) REFERENCES sessions(id),

    -- Identity
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,

    -- Status
    status VARCHAR(50),
    last_heartbeat TIMESTAMP WITH TIME ZONE,

    -- Configuration
    is_enabled BOOLEAN DEFAULT true,
    auto_start BOOLEAN DEFAULT false,
    priority INTEGER DEFAULT 0,
    config_overrides JSON,

    -- Statistics
    total_sessions INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    total_tool_calls INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP WITH TIME ZONE,

    -- Lifecycle
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_agent_instances_name UNIQUE (name)
);

-- Add FK from sessions to agent_instances
ALTER TABLE sessions
    ADD CONSTRAINT fk_session_instance
    FOREIGN KEY (instance_id) REFERENCES agent_instances(id);

-- =============================================================================
-- Message & Execution Tables
-- =============================================================================

-- Session Messages (conversation history)
CREATE TABLE session_messages (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES sessions(id),
    role VARCHAR(20) NOT NULL,
    content JSON,
    tool_call_id VARCHAR(255),
    message_type VARCHAR(50) NOT NULL DEFAULT 'message',
    step_number INTEGER,
    step_data JSON,
    created_at TIMESTAMP WITH TIME ZONE
);

-- Chat Turns (indexed Q/A pairs for search)
CREATE TABLE chat_turns (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id VARCHAR(36) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    user_text TEXT NOT NULL DEFAULT '',
    assistant_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    search_text TEXT GENERATED ALWAYS AS (
        coalesce(user_text, '') || E'\n\n' || coalesce(assistant_text, '')
    ) STORED,
    search_text_norm TEXT GENERATED ALWAYS AS (
        lower(regexp_replace(
            coalesce(user_text, '') || E'\n\n' || coalesce(assistant_text, ''),
            '[^[:alnum:][:space:]]+', ' ', 'g'
        ))
    ) STORED,
    search_tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('russian', coalesce(user_text, '') || E'\n\n' || coalesce(assistant_text, ''))
    ) STORED,

    CONSTRAINT uq_chat_turns_order UNIQUE (user_id, chat_id, turn_index)
);

-- Sources (data sources for sessions)
CREATE TABLE sources (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES sessions(id),
    uri VARCHAR(512) NOT NULL,
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE
);

-- Artifacts (generated outputs)
CREATE TABLE artifacts (
    id VARCHAR(36) PRIMARY KEY,
    source_id VARCHAR(36) REFERENCES sources(id),
    session_id VARCHAR(36) REFERENCES sessions(id),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    payload JSON,
    created_at TIMESTAMP WITH TIME ZONE
);

-- Tool Executions (tool call history)
CREATE TABLE tool_executions (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES sessions(id),
    tool_id VARCHAR(36) REFERENCES tools(id),
    tool_name VARCHAR(255) NOT NULL,
    arguments JSON,
    result JSON,
    status VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE
);

-- =============================================================================
-- Alembic Version Tracking
-- =============================================================================

CREATE TABLE alembic_version (
    version_num VARCHAR(32) PRIMARY KEY
);

INSERT INTO alembic_version (version_num) VALUES ('007_add_tool_category');

-- =============================================================================
-- Indexes for Performance
-- =============================================================================

CREATE INDEX ix_auth_sessions_token_hash ON auth_sessions(token_hash);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX ix_session_messages_message_type ON session_messages(message_type);

CREATE INDEX ix_chat_turns_user_id
  ON chat_turns (user_id);

CREATE INDEX ix_chat_turns_chat_id
  ON chat_turns (chat_id);

CREATE INDEX ix_chat_turns_owner_chat_pos
  ON chat_turns (user_id, chat_id, turn_index);

CREATE INDEX gin_chat_turns_search_tsv
  ON chat_turns USING GIN (search_tsv);

CREATE INDEX gin_chat_turns_search_trgm
  ON chat_turns USING GIN (search_text_norm gin_trgm_ops);

-- =============================================================================
-- Done
-- =============================================================================
