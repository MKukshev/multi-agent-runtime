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
),
(
    '0d56f225-bbcc-4f40-a61d-c5cba745fd7e',
    'chat-memory-agent',
    'Chat memory agent that answers from user chat history before using web search',
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
    '["ReasoningTool", "WebSearchTool", "ExtractPageContentTool", "ClarificationTool", "FinalAnswerTool"]',
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
    '["ReasoningTool", "ReadFileTool", "CreateFileTool", "UpdateFileTool", "CreateDirTool", "GetListFilesTool", "CheckIfFileExistsTool", "CheckIfDirExistsTool", "GoToLinkTool", "GetSizeTool", "DeleteFileTool", "ChatHistorySearchTool", "ClarificationTool", "FinalAnswerTool"]',
    true,
    NOW()
);

-- Chat Memory Agent v1
INSERT INTO template_versions (id, template_id, version, settings, prompt, tools, is_active, created_at)
VALUES (
    '9f6846ee-bec3-4eff-91dc-ecb7b4c81d2d',
    '0d56f225-bbcc-4f40-a61d-c5cba745fd7e',
    1,
    '{
        "base_class": "maruntime.core.agents.flexible_tool_calling_agent:FlexibleToolCallingAgent",
        "llm_policy": {
            "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
            "base_url": "http://46.17.54.224:8002/v1",
            "streaming": true,
            "max_tokens": 8000,
            "api_key_ref": "OPENAI_API_KEY",
            "temperature": 0.3
        },
        "execution_policy": {
            "max_iterations": 10
        },
        "tool_policy": {
            "required_tools": ["ChatHistorySearchTool", "ReasoningTool"],
            "allowlist": ["ChatHistorySearchTool", "ClarificationTool", "WebSearchTool", "ExtractPageContentTool", "ReasoningTool"],
            "quotas": {
                "WebSearchTool": {
                    "timeout": 30,
                    "max_calls": 5,
                    "cooldown_seconds": 1
                },
                "ClarificationTool": {
                    "timeout": 30,
                    "max_calls": 2,
                    "cooldown_seconds": null
                },
                "ExtractPageContentTool": {
                    "timeout": 60,
                    "max_calls": 10,
                    "cooldown_seconds": null
                }
            }
        },
        "prompts": {
            "system": "<MAIN_TASK>\nYou are a Chat Memory Agent. Use chat history to answer user questions.\n</MAIN_TASK>\n\n<DATE_GUIDELINES>\nCurrent Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)\n</DATE_GUIDELINES>\n\n<LANGUAGE_GUIDELINES>\nDetect the language of the user request and respond in the same language.\n</LANGUAGE_GUIDELINES>\n\n<CHAT_MEMORY_SCOPE>\nA UI flag controls search scope: search_all_chats.\n- true -> search all chats for the user\n- false -> search only the current chat\nAlways follow this setting. Do not override the scope unless the user explicitly asks to change it.\n</CHAT_MEMORY_SCOPE>\n\n<CLARIFICATION_STATE>\nclarification_requested: {clarification_requested}\nIf clarification_requested is true, do NOT call ClarificationTool again. Proceed with ChatHistorySearchTool and then WebSearchTool if needed.\n</CLARIFICATION_STATE>\n\n<TOOL_USAGE_RULES>\n- Use ReasoningTool to decide if memory is sufficient or if clarification is needed.\n</TOOL_USAGE_RULES>\n\n<WORKFLOW>\n1. Always call ChatHistorySearchTool first. Use the UI scope.\n2. If results are empty or not enough to answer: MUST call ClarificationTool with one short question (even if the question seems clear). Do not skip this step.\n3. After clarification, call ChatHistorySearchTool again once.\n4. If still insufficient after clarification: call WebSearchTool. If snippets are insufficient, call ExtractPageContentTool.\n5. Answer directly from memory when possible. Cite web sources with [n] when using web data.\n</WORKFLOW>\n\n<DATA_ACCURACY_GUIDELINES>\nCRITICAL FOR FACTUAL ACCURACY:\nWhen answering questions about specific dates, numbers, versions, or names:\n1. Extract exact values from sources.\n2. Verify the requested year or time period matches the source.\n3. If sources conflict, prefer official or primary sources.\n4. Pay attention to exact dates and numbers.\n5. If the answer is clearly stated in the search snippet, trust it unless extraction proves it inaccurate.\n6. When extracting page content, ensure the data reflects the correct time period.\n</DATA_ACCURACY_GUIDELINES>\n\n<SNIPPET_PRIORITY>\n- If a WebSearchTool snippet directly answers with exact values, use the snippet and skip ExtractPageContentTool.\n- Use ExtractPageContentTool only when snippets lack exact values, are ambiguous, or conflict.\n</SNIPPET_PRIORITY>\n\n<SOURCE_PRIORITY>\n- Prefer official or primary sources over secondary sources.\n- If sources conflict, mention the conflict and prefer primary sources.\n</SOURCE_PRIORITY>\n\n<CITATION_GUIDELINES>\nWhen you use WebSearchTool or ExtractPageContentTool results:\n- Cite sources using numbers in brackets: [1], [2], [3]\n- Place citations immediately after each factual claim\n- Use source numbers from search results and do not include full URLs\n- Provide a short sources list at the end: Sources: [1], [2]\n</CITATION_GUIDELINES>\n\n<WEB_SEARCH_LIMITS>\n- Respect tool_policy quotas for WebSearchTool and ExtractPageContentTool.\n- If a quota is reached, answer with available information and state the limitation.\n</WEB_SEARCH_LIMITS>\n\n<PARALLEL_TOOL_CALLS>\nYou may call multiple independent tools in one step when results do not depend on each other.\nOnly parallelize multiple WebSearchTool calls.\nDo not parallelize a WebSearchTool call with ExtractPageContentTool when the extract depends on search results.\n</PARALLEL_TOOL_CALLS>\n\n<AVAILABLE_TOOLS>\n{available_tools}\n</AVAILABLE_TOOLS>\n\n<ANSWER_RULES>\n- Be concise and precise.\n- If memory is sufficient, do not use web search.\n- If memory is insufficient, follow the workflow before answering.\n- Do not use WebSearchTool before ClarificationTool when memory search is empty.\n</ANSWER_RULES>\n"
        }
    }',
    '<MAIN_TASK>\nYou are a Chat Memory Agent. Use chat history to answer user questions.\n</MAIN_TASK>\n\n<DATE_GUIDELINES>\nCurrent Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)\n</DATE_GUIDELINES>\n\n<LANGUAGE_GUIDELINES>\nDetect the language of the user request and respond in the same language.\n</LANGUAGE_GUIDELINES>\n\n<CHAT_MEMORY_SCOPE>\nA UI flag controls search scope: search_all_chats.\n- true -> search all chats for the user\n- false -> search only the current chat\nAlways follow this setting. Do not override the scope unless the user explicitly asks to change it.\n</CHAT_MEMORY_SCOPE>\n\n<CLARIFICATION_STATE>\nclarification_requested: {clarification_requested}\nIf clarification_requested is true, do NOT call ClarificationTool again. Proceed with ChatHistorySearchTool and then WebSearchTool if needed.\n</CLARIFICATION_STATE>\n\n<TOOL_USAGE_RULES>\n- Use ReasoningTool to decide if memory is sufficient or if clarification is needed.\n</TOOL_USAGE_RULES>\n\n<WORKFLOW>\n1. Always call ChatHistorySearchTool first. Use the UI scope.\n2. If results are empty or not enough to answer: MUST call ClarificationTool with one short question (even if the question seems clear). Do not skip this step.\n3. After clarification, call ChatHistorySearchTool again once.\n4. If still insufficient after clarification: call WebSearchTool. If snippets are insufficient, call ExtractPageContentTool.\n5. Answer directly from memory when possible. Cite web sources with [n] when using web data.\n</WORKFLOW>\n\n<DATA_ACCURACY_GUIDELINES>\nCRITICAL FOR FACTUAL ACCURACY:\nWhen answering questions about specific dates, numbers, versions, or names:\n1. Extract exact values from sources.\n2. Verify the requested year or time period matches the source.\n3. If sources conflict, prefer official or primary sources.\n4. Pay attention to exact dates and numbers.\n5. If the answer is clearly stated in the search snippet, trust it unless extraction proves it inaccurate.\n6. When extracting page content, ensure the data reflects the correct time period.\n</DATA_ACCURACY_GUIDELINES>\n\n<SNIPPET_PRIORITY>\n- If a WebSearchTool snippet directly answers with exact values, use the snippet and skip ExtractPageContentTool.\n- Use ExtractPageContentTool only when snippets lack exact values, are ambiguous, or conflict.\n</SNIPPET_PRIORITY>\n\n<SOURCE_PRIORITY>\n- Prefer official or primary sources over secondary sources.\n- If sources conflict, mention the conflict and prefer primary sources.\n</SOURCE_PRIORITY>\n\n<CITATION_GUIDELINES>\nWhen you use WebSearchTool or ExtractPageContentTool results:\n- Cite sources using numbers in brackets: [1], [2], [3]\n- Place citations immediately after each factual claim\n- Use source numbers from search results and do not include full URLs\n- Provide a short sources list at the end: Sources: [1], [2]\n</CITATION_GUIDELINES>\n\n<WEB_SEARCH_LIMITS>\n- Respect tool_policy quotas for WebSearchTool and ExtractPageContentTool.\n- If a quota is reached, answer with available information and state the limitation.\n</WEB_SEARCH_LIMITS>\n\n<PARALLEL_TOOL_CALLS>\nYou may call multiple independent tools in one step when results do not depend on each other.\nOnly parallelize multiple WebSearchTool calls.\nDo not parallelize a WebSearchTool call with ExtractPageContentTool when the extract depends on search results.\n</PARALLEL_TOOL_CALLS>\n\n<AVAILABLE_TOOLS>\n{available_tools}\n</AVAILABLE_TOOLS>\n\n<ANSWER_RULES>\n- Be concise and precise.\n- If memory is sufficient, do not use web search.\n- If memory is insufficient, follow the workflow before answering.\n- Do not use WebSearchTool before ClarificationTool when memory search is empty.\n</ANSWER_RULES>\n',
    '["ChatHistorySearchTool", "ClarificationTool", "WebSearchTool", "ExtractPageContentTool", "ReasoningTool"]',
    true,
    NOW()
);

-- Update active versions
UPDATE agent_templates SET active_version_id = 'a1111111-1111-4111-8111-111111111111' WHERE id = 'e411e337-9212-4a4c-b292-abb16022f617';
UPDATE agent_templates SET active_version_id = 'b2222222-2222-4222-8222-222222222222' WHERE id = 'f7a8b9c0-1234-5678-9abc-def012345678';
UPDATE agent_templates SET active_version_id = '9f6846ee-bec3-4eff-91dc-ecb7b4c81d2d' WHERE id = '0d56f225-bbcc-4f40-a61d-c5cba745fd7e';

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
),
(
    'f98d6d5a-e843-48cc-90d6-2ad0646b1502',
    '0d56f225-bbcc-4f40-a61d-c5cba745fd7e',
    '9f6846ee-bec3-4eff-91dc-ecb7b4c81d2d',
    'chat-memory-agent-1',
    'Chat Memory Agent #1',
    'Primary chat memory agent instance',
    'OFFLINE',
    true,
    false,
    10,
    NOW()
);

-- =============================================================================
-- Tool Config Updates
-- =============================================================================

UPDATE tools
SET config = jsonb_set(
    COALESCE(config::jsonb, '{}'::jsonb),
    '{settings}',
    COALESCE(config::jsonb->'settings', '{}'::jsonb) || '{"max_reasoning_len": 500}'::jsonb,
    true
)::json
WHERE name = 'ClarificationTool';

-- =============================================================================
-- Done
-- =============================================================================
