from platform.runtime import ExecutionPolicy, LLMPolicy, PromptConfig, SessionContext, TemplateRuntimeConfig, ToolPolicy
from platform.security import RulePhase, RulesEngine


def test_rules_engine_limits_tools_after_max_iterations() -> None:
    template = TemplateRuntimeConfig(
        template_id="tmpl",
        template_name="demo",
        version_id="v1",
        version=1,
        llm_policy=LLMPolicy(model="gpt-4o-mini"),
        prompts=PromptConfig(),
        execution_policy=ExecutionPolicy(max_iterations=3),
        tool_policy=ToolPolicy(),
        tools=["Search", "FinalAnswer", "CreateReport"],
        rules=[
            {
                "apply_to": ["post_retrieval"],
                "when": {"iteration_gte": "max_iterations"},
                "actions": {"keep_only": ["FinalAnswer", "CreateReport"], "set_stage": "finalization"},
            }
        ],
    )
    session = SessionContext(session_id="s1", template_version_id="v1", data={"iteration": 3})
    engine = RulesEngine()

    pre_decision = engine.evaluate(session, template, phase=RulePhase.PRE_RETRIEVAL)
    assert pre_decision.apply(["Search", "FinalAnswer", "CreateReport"]) == ["Search", "FinalAnswer", "CreateReport"]

    post_decision = engine.evaluate(session, template, phase=RulePhase.POST_RETRIEVAL)
    filtered_tools = post_decision.apply(["Search", "FinalAnswer", "CreateReport"])

    assert filtered_tools == ["FinalAnswer", "CreateReport"]
    assert post_decision.stage == "finalization"
