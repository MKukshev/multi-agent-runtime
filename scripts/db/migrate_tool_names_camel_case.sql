-- =============================================================================
-- Migration: Normalize tool names to CamelCase in template_versions
-- - Updates template_versions.tools array
-- - Updates template_versions.settings.tool_policy (required_tools/allowlist/denylist/quotas)
-- - Updates template_versions.settings.rules actions (exclude/keep_only)
-- Safe to run multiple times.
-- =============================================================================

BEGIN;

CREATE TEMP TABLE tool_name_map (
    from_name TEXT PRIMARY KEY,
    to_name TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO tool_name_map (from_name, to_name) VALUES
    ('adapt_plan_tool', 'AdaptPlanTool'),
    ('adaptplantool', 'AdaptPlanTool'),
    ('chat_history_search_tool', 'ChatHistorySearchTool'),
    ('chathistorysearchtool', 'ChatHistorySearchTool'),
    ('check_if_dir_exists_tool', 'CheckIfDirExistsTool'),
    ('checkifdirexiststool', 'CheckIfDirExistsTool'),
    ('check_if_file_exists_tool', 'CheckIfFileExistsTool'),
    ('checkiffileexiststool', 'CheckIfFileExistsTool'),
    ('clarification_tool', 'ClarificationTool'),
    ('clarificationtool', 'ClarificationTool'),
    ('create_dir_tool', 'CreateDirTool'),
    ('createdirtool', 'CreateDirTool'),
    ('create_file_tool', 'CreateFileTool'),
    ('createfiletool', 'CreateFileTool'),
    ('create_report_tool', 'CreateReportTool'),
    ('createreporttool', 'CreateReportTool'),
    ('delete_file_tool', 'DeleteFileTool'),
    ('deletefiletool', 'DeleteFileTool'),
    ('delegate_template_tool', 'DelegateTemplateTool'),
    ('delegatetemplatetool', 'DelegateTemplateTool'),
    ('agent.delegate_template', 'DelegateTemplateTool'),
    ('echo_tool', 'EchoTool'),
    ('echotool', 'EchoTool'),
    ('extract_page_content_tool', 'ExtractPageContentTool'),
    ('extractpagecontenttool', 'ExtractPageContentTool'),
    ('final_answer_tool', 'FinalAnswerTool'),
    ('finalanswertool', 'FinalAnswerTool'),
    ('final_answer', 'FinalAnswerTool'),
    ('finalanswer', 'FinalAnswerTool'),
    ('generate_plan_tool', 'GeneratePlanTool'),
    ('generateplantool', 'GeneratePlanTool'),
    ('get_list_files_tool', 'GetListFilesTool'),
    ('getlistfilestool', 'GetListFilesTool'),
    ('get_size_tool', 'GetSizeTool'),
    ('getsizetool', 'GetSizeTool'),
    ('go_to_link_tool', 'GoToLinkTool'),
    ('gotolinktool', 'GoToLinkTool'),
    ('read_file_tool', 'ReadFileTool'),
    ('readfiletool', 'ReadFileTool'),
    ('reasoning_tool', 'ReasoningTool'),
    ('reasoningtool', 'ReasoningTool'),
    ('reasoning', 'ReasoningTool'),
    ('update_file_tool', 'UpdateFileTool'),
    ('updatefiletool', 'UpdateFileTool'),
    ('web_search_tool', 'WebSearchTool'),
    ('websearchtool', 'WebSearchTool'),
    ('test_tool', 'TestTool'),
    ('testtool', 'TestTool');

-- -----------------------------------------------------------------------------
-- Update template_versions.tools (array of tool names)
-- -----------------------------------------------------------------------------

UPDATE template_versions AS tv
SET tools = (
    SELECT jsonb_agg(
        to_jsonb(COALESCE(m.to_name, e.value))
        ORDER BY e.ord
    )::json
    FROM jsonb_array_elements_text(
        COALESCE(tv.tools::jsonb, '[]'::jsonb)
    ) WITH ORDINALITY AS e(value, ord)
    LEFT JOIN tool_name_map AS m ON m.from_name = e.value
)
WHERE tv.tools IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Update template_versions.settings (tool_policy + rules)
-- -----------------------------------------------------------------------------

WITH base AS (
    SELECT id, settings::jsonb AS settings
    FROM template_versions
    WHERE settings IS NOT NULL
),
required_updated AS (
    SELECT id,
        CASE
            WHEN settings ? 'tool_policy'
             AND jsonb_typeof(settings->'tool_policy'->'required_tools') = 'array' THEN
                jsonb_set(
                    settings,
                    '{tool_policy,required_tools}',
                    COALESCE((
                        SELECT jsonb_agg(
                            to_jsonb(COALESCE(m.to_name, e.value))
                            ORDER BY e.ord
                        )
                        FROM jsonb_array_elements_text(
                            COALESCE(settings->'tool_policy'->'required_tools', '[]'::jsonb)
                        ) WITH ORDINALITY AS e(value, ord)
                        LEFT JOIN tool_name_map AS m ON m.from_name = e.value
                    ), '[]'::jsonb),
                    true
                )
            ELSE settings
        END AS settings
    FROM base
),
allow_updated AS (
    SELECT id,
        CASE
            WHEN settings ? 'tool_policy'
             AND jsonb_typeof(settings->'tool_policy'->'allowlist') = 'array' THEN
                jsonb_set(
                    settings,
                    '{tool_policy,allowlist}',
                    COALESCE((
                        SELECT jsonb_agg(
                            to_jsonb(COALESCE(m.to_name, e.value))
                            ORDER BY e.ord
                        )
                        FROM jsonb_array_elements_text(
                            COALESCE(settings->'tool_policy'->'allowlist', '[]'::jsonb)
                        ) WITH ORDINALITY AS e(value, ord)
                        LEFT JOIN tool_name_map AS m ON m.from_name = e.value
                    ), '[]'::jsonb),
                    true
                )
            ELSE settings
        END AS settings
    FROM required_updated
),
deny_updated AS (
    SELECT id,
        CASE
            WHEN settings ? 'tool_policy'
             AND jsonb_typeof(settings->'tool_policy'->'denylist') = 'array' THEN
                jsonb_set(
                    settings,
                    '{tool_policy,denylist}',
                    COALESCE((
                        SELECT jsonb_agg(
                            to_jsonb(COALESCE(m.to_name, e.value))
                            ORDER BY e.ord
                        )
                        FROM jsonb_array_elements_text(
                            COALESCE(settings->'tool_policy'->'denylist', '[]'::jsonb)
                        ) WITH ORDINALITY AS e(value, ord)
                        LEFT JOIN tool_name_map AS m ON m.from_name = e.value
                    ), '[]'::jsonb),
                    true
                )
            ELSE settings
        END AS settings
    FROM allow_updated
),
quotas_updated AS (
    SELECT id,
        CASE
            WHEN settings ? 'tool_policy'
             AND jsonb_typeof(settings->'tool_policy'->'quotas') = 'object' THEN
                jsonb_set(
                    settings,
                    '{tool_policy,quotas}',
                    COALESCE((
                        SELECT jsonb_object_agg(key, value)
                        FROM (
                            SELECT
                                COALESCE(m.to_name, q.key) AS key,
                                q.value AS value,
                                m.to_name
                            FROM jsonb_each(
                                COALESCE(settings->'tool_policy'->'quotas', '{}'::jsonb)
                            ) AS q(key, value)
                            LEFT JOIN tool_name_map AS m ON m.from_name = q.key
                            ORDER BY (m.to_name IS NULL) ASC
                        ) AS mapped
                    ), '{}'::jsonb),
                    true
                )
            ELSE settings
        END AS settings
    FROM deny_updated
),
rules_updated AS (
    SELECT id,
        CASE
            WHEN settings ? 'rules'
             AND jsonb_typeof(settings->'rules') = 'array' THEN
                jsonb_set(
                    settings,
                    '{rules}',
                    COALESCE((
                        SELECT jsonb_agg(
                            CASE
                                WHEN jsonb_typeof(rule) = 'object'
                                 AND rule ? 'actions'
                                 AND jsonb_typeof(rule->'actions') = 'object' THEN
                                    (
                                        SELECT CASE
                                            WHEN jsonb_typeof(rule1->'actions'->'keep_only') = 'array' THEN
                                                jsonb_set(
                                                    rule1,
                                                    '{actions,keep_only}',
                                                    COALESCE((
                                                        SELECT jsonb_agg(
                                                            to_jsonb(COALESCE(m2.to_name, e2.value))
                                                            ORDER BY e2.ord
                                                        )
                                                        FROM jsonb_array_elements_text(
                                                            COALESCE(rule1->'actions'->'keep_only', '[]'::jsonb)
                                                        ) WITH ORDINALITY AS e2(value, ord)
                                                        LEFT JOIN tool_name_map AS m2 ON m2.from_name = e2.value
                                                    ), '[]'::jsonb),
                                                    true
                                                )
                                            ELSE rule1
                                        END
                                        FROM (
                                            SELECT CASE
                                                WHEN jsonb_typeof(rule->'actions'->'exclude') = 'array' THEN
                                                    jsonb_set(
                                                        rule,
                                                        '{actions,exclude}',
                                                        COALESCE((
                                                            SELECT jsonb_agg(
                                                                to_jsonb(COALESCE(m1.to_name, e1.value))
                                                                ORDER BY e1.ord
                                                            )
                                                            FROM jsonb_array_elements_text(
                                                                COALESCE(rule->'actions'->'exclude', '[]'::jsonb)
                                                            ) WITH ORDINALITY AS e1(value, ord)
                                                            LEFT JOIN tool_name_map AS m1 ON m1.from_name = e1.value
                                                        ), '[]'::jsonb),
                                                        true
                                                    )
                                                ELSE rule
                                            END AS rule1
                                        ) AS step1
                                    )
                                ELSE rule
                            END
                        )
                        FROM jsonb_array_elements(settings->'rules') AS rule
                    ), settings->'rules'),
                    true
                )
            ELSE settings
        END AS settings
    FROM quotas_updated
)
UPDATE template_versions AS tv
SET settings = rules_updated.settings::json
FROM rules_updated
WHERE tv.id = rules_updated.id
  AND tv.settings::jsonb <> rules_updated.settings;

COMMIT;
