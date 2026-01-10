-- =============================================================================
-- Multi-Agent Runtime - Seed Data
-- Version: 20260109
-- =============================================================================

-- =============================================================================
-- System Prompts (Global Templates)
-- =============================================================================

INSERT INTO system_prompts (id, name, description, content, placeholders, is_active, created_at, updated_at)
VALUES
(
    'system',
    'System Prompt',
    'Main system prompt with agent instructions, capabilities, and guidelines',
    '<MAIN_TASK_GUIDELINES>
You are an expert assistant with adaptive planning and schema-guided-reasoning capabilities.
You receive tasks from users and need to understand the requirements, determine the appropriate approach, and deliver accurate results.
</MAIN_TASK_GUIDELINES>

<DATE_GUIDELINES>
Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)
PAY ATTENTION TO THE DATE when answering questions about current events or time-sensitive information.
</DATE_GUIDELINES>

<LANGUAGE_GUIDELINES>
Detect the language from user request and use this LANGUAGE for all responses and outputs.
Always respond in the SAME LANGUAGE as the user''s request.
</LANGUAGE_GUIDELINES>

<CORE_PRINCIPLES>
1. Assess task complexity: For simple questions, provide direct answers. For complex tasks, create a plan and follow it.
2. Adapt your plan when new data contradicts initial assumptions.
3. Use available tools to gather information and complete tasks.
</CORE_PRINCIPLES>

<AVAILABLE_TOOLS>
{available_tools}
</AVAILABLE_TOOLS>

<TOOL_USAGE_GUIDELINES>
- Use ReasoningTool before other tools to plan your approach
- Use WebSearchTool for current information and facts
- Use ExtractPageContentTool to get full content from URLs found in search
- Use ClarificationTool when the request is ambiguous
- Use FinalAnswerTool to complete the task with your findings
</TOOL_USAGE_GUIDELINES>
',
    '["current_date", "available_tools"]',
    true,
    NOW(),
    NOW()
),
(
    'initial_user',
    'Initial User Request',
    'Template for wrapping user''s first message with context',
    'Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)

USER REQUEST:

{task}
',
    '["current_date", "task"]',
    true,
    NOW(),
    NOW()
),
(
    'clarification',
    'Clarification Response',
    'Template for formatting user''s clarification responses',
    'Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)

USER CLARIFICATION:

{clarifications}

Please continue with your task using this additional information.
',
    '["current_date", "clarifications"]',
    true,
    NOW(),
    NOW()
);

-- =============================================================================
-- Agent Templates
-- =============================================================================

INSERT INTO agent_templates (id, name, description, active_version_id, created_at, updated_at)
VALUES
(
    'e411e337-9212-4a4c-b292-abb16022f617',
    'sgr-research-agent',
    'Schema-Guided Reasoning research agent with web search capabilities',
    NULL,
    NOW(),
    NOW()
),
(
    'f7a8b9c0-1234-5678-9abc-def012345678',
    'memory-agent',
    'Memory agent with persistent knowledge base and entity tracking',
    NULL,
    NOW(),
    NOW()
);

-- =============================================================================
-- Template Versions
-- =============================================================================

-- SGR Research Agent v1
INSERT INTO template_versions (id, template_id, version, settings, prompt, tools, is_active, created_at)
VALUES (
    'a1111111-1111-4111-8111-111111111111',
    'e411e337-9212-4a4c-b292-abb16022f617',
    1,
    '{
        "model": "anthropic/claude-sonnet-4-20250514",
        "temperature": 0.7,
        "max_tokens": 8192,
        "max_iterations": 15
    }',
    NULL,
    '["reasoningtool", "websearchtool", "extractpagecontenttool", "clarificationtool", "finalanswertool"]',
    true,
    NOW()
);

-- Memory Agent v1
INSERT INTO template_versions (id, template_id, version, settings, prompt, tools, is_active, created_at)
VALUES (
    'b2222222-2222-4222-8222-222222222222',
    'f7a8b9c0-1234-5678-9abc-def012345678',
    1,
    '{
        "model": "anthropic/claude-sonnet-4-20250514",
        "temperature": 0.3,
        "max_tokens": 8192,
        "max_iterations": 10
    }',
    NULL,
    '["reasoningtool", "readfiletool", "createfiletool", "updatefiletool", "createdirtool", "getlistfilestool", "checkiffileexiststool", "checkifdirexiststool", "gotolinktool", "getsizetool", "deletefiletool", "chathistorysearchtool", "clarificationtool", "finalanswertool"]',
    true,
    NOW()
);

-- Update active versions
UPDATE agent_templates SET active_version_id = 'a1111111-1111-4111-8111-111111111111' WHERE id = 'e411e337-9212-4a4c-b292-abb16022f617';
UPDATE agent_templates SET active_version_id = 'b2222222-2222-4222-8222-222222222222' WHERE id = 'f7a8b9c0-1234-5678-9abc-def012345678';

-- =============================================================================
-- Agent Instances (Named Slots)
-- =============================================================================

INSERT INTO agent_instances (
    id, template_id, template_version_id, name, display_name, description,
    status, is_enabled, auto_start, priority, created_at
)
VALUES
(
    '8531cecd-3e43-4823-a240-3b1f9c7749aa',
    'e411e337-9212-4a4c-b292-abb16022f617',
    'a1111111-1111-4111-8111-111111111111',
    'research-agent-1',
    'Research Agent #1',
    'Primary research agent instance',
    'OFFLINE',
    true,
    false,
    10,
    NOW()
),
(
    '7bbd7ca0-c0a9-4d0e-8474-9ab627d2e52b',
    'e411e337-9212-4a4c-b292-abb16022f617',
    'a1111111-1111-4111-8111-111111111111',
    'research-agent-2',
    'Research Agent #2',
    'Secondary research agent instance',
    'OFFLINE',
    true,
    false,
    5,
    NOW()
),
(
    'a1b2c3d4-5678-9abc-def0-123456789abc',
    'f7a8b9c0-1234-5678-9abc-def012345678',
    'b2222222-2222-4222-8222-222222222222',
    'memory-agent-1',
    'Memory Agent #1',
    'Primary memory agent instance',
    'OFFLINE',
    true,
    false,
    10,
    NOW()
);

-- =============================================================================
-- Done
-- =============================================================================
