-- =============================================================================
-- Multi-Agent Runtime - Database Schema
-- Version: 20260105_000002
-- Compatible with: PostgreSQL 14+
-- =============================================================================

-- Drop existing tables (in reverse dependency order)
DROP TABLE IF EXISTS tool_executions CASCADE;
DROP TABLE IF EXISTS artifacts CASCADE;
DROP TABLE IF EXISTS sources CASCADE;
DROP TABLE IF EXISTS session_messages CASCADE;
DROP TABLE IF EXISTS agent_instances CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS template_versions CASCADE;
DROP TABLE IF EXISTS agent_templates CASCADE;
DROP TABLE IF EXISTS tools CASCADE;
DROP TABLE IF EXISTS system_prompts CASCADE;
DROP TABLE IF EXISTS alembic_version CASCADE;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Agent Templates (blueprints for agents)
CREATE TABLE agent_templates (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    active_version_id VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Template Versions (versioned configurations)
CREATE TABLE template_versions (
    id VARCHAR(36) PRIMARY KEY,
    template_id VARCHAR(36) NOT NULL REFERENCES agent_templates(id),
    version INTEGER NOT NULL,
    settings JSON NOT NULL DEFAULT '{}',
    embedding JSON,
    prompt TEXT,
    tools JSON NOT NULL DEFAULT '[]',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (template_id, version)
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
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System Prompts (global prompt templates)
CREATE TABLE system_prompts (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    content TEXT NOT NULL,
    placeholders JSON,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- Session & Instance Tables
-- =============================================================================

-- Sessions (conversation contexts)
CREATE TABLE sessions (
    id VARCHAR(36) PRIMARY KEY,
    template_version_id VARCHAR(36) NOT NULL REFERENCES template_versions(id),
    instance_id VARCHAR(36),
    state VARCHAR(50) NOT NULL DEFAULT 'active',
    context JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Agent Instances (Named Slots model - runtime agents)
CREATE TABLE agent_instances (
    id VARCHAR(36) PRIMARY KEY,
    template_id VARCHAR(36) NOT NULL REFERENCES agent_templates(id),
    template_version_id VARCHAR(36) NOT NULL REFERENCES template_versions(id),
    current_session_id VARCHAR(36) REFERENCES sessions(id),
    
    -- Identity
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    description TEXT,
    
    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'OFFLINE',
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
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sources (data sources for sessions)
CREATE TABLE sources (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES sessions(id),
    uri VARCHAR(512) NOT NULL,
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Artifacts (generated outputs)
CREATE TABLE artifacts (
    id VARCHAR(36) PRIMARY KEY,
    source_id VARCHAR(36) REFERENCES sources(id),
    session_id VARCHAR(36) REFERENCES sessions(id),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    payload JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- Alembic Version Tracking
-- =============================================================================

CREATE TABLE alembic_version (
    version_num VARCHAR(32) PRIMARY KEY
);

INSERT INTO alembic_version (version_num) VALUES ('20260105_000002');

-- =============================================================================
-- Indexes for Performance
-- =============================================================================

CREATE INDEX idx_template_versions_template ON template_versions(template_id);
CREATE INDEX idx_sessions_template_version ON sessions(template_version_id);
CREATE INDEX idx_sessions_instance ON sessions(instance_id);
CREATE INDEX idx_agent_instances_template ON agent_instances(template_id);
CREATE INDEX idx_agent_instances_status ON agent_instances(status);
CREATE INDEX idx_session_messages_session ON session_messages(session_id);
CREATE INDEX idx_tool_executions_session ON tool_executions(session_id);

-- =============================================================================
-- Done
-- =============================================================================
