"""Flexible Tool Calling Agent - ReAct loop with free-form final answer.

Based on research from reasoning-benchmark-research:
- Reasoning через tools (structured) → OK
- Final answer в свободной форме (free-form) → +0.2% accuracy

Key insight: Tool calls для финального ответа снижают точность.
This agent excludes FinalAnswerTool and generates free-form answers instead.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Type

from openai import AsyncOpenAI

from maruntime.core.agents.base_agent import BaseAgent
from maruntime.core.llm import LLMClientFactory
from maruntime.core.models import AgentContext, AgentStatesEnum
from maruntime.core.streaming.openai_sse import SSEEvent
from maruntime.core.tools.base_tool import BaseTool, PydanticTool
from maruntime.runtime import ChatMessage

# Default logs directory
LOGS_DIR = Path("./logs")


def setup_session_logger(agent_name: str, session_id: str) -> logging.Logger:
    """Create a logger that writes to a session-specific file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger_name = f"maruntime.agent.{agent_name}.{session_id}"
    session_logger = logging.getLogger(logger_name)
    session_logger.setLevel(logging.DEBUG)
    
    if session_logger.handlers:
        return session_logger
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_filename = LOGS_DIR / f"{timestamp}-{agent_name}-{session_id[:8]}.log"
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    session_logger.addHandler(file_handler)
    session_logger.addHandler(console_handler)
    
    return session_logger


logger = logging.getLogger(__name__)

# Tools that indicate reasoning is complete
REASONING_TOOLS = {"reasoningtool", "reasoning_tool", "reasoning"}

# Tools to EXCLUDE from schema (we use free-form answer instead)
FINAL_ANSWER_TOOLS = {"finalanswertool", "final_answer", "finalanswer"}


class FlexibleToolCallingAgent(BaseAgent):
    """Agent with ReAct loop that uses free-form final answers instead of FinalAnswerTool.
    
    Architecture (based on benchmark research - Two-Step SO pattern):
    1. Tools used for: search, reasoning, analysis (structured)
    2. Final answer: Generated in FREE-FORM (not through FinalAnswerTool)
    
    This yields ~0.2% higher accuracy than forcing structured final answers.
    
    Flow:
    1. User request received
    2. Agent uses tools to gather information and reason (ReAct loop)
    3. When ReasoningTool indicates task_completed=true:
       - Collected reasoning is added to context
       - Agent generates final answer in FREE-FORM (no tools)
    """

    name = "flexible_tool_calling_agent"

    def __init__(
        self,
        task: str,
        toolkit: list[Type[BaseTool]] | None = None,
        max_iterations: int = 10,
        **kwargs: Any,
    ) -> None:
        super().__init__(task=task, toolkit=toolkit or [], **kwargs)
        self.max_iterations = max_iterations
        self._iteration = 0
        self._finished = False
        self._client: AsyncOpenAI | None = None
        self._conversation: list[dict[str, Any]] = []
        self._agent_context = AgentContext()
        self._log: list[dict[str, Any]] = []
        self._session_logger: logging.Logger | None = None
        # Collected reasoning for free-form answer generation
        self._collected_reasoning: list[str] = []

    def _get_logger(self) -> logging.Logger:
        """Get session logger or fallback to module logger."""
        return self._session_logger or logger

    # ==================== Logging Methods ====================

    def _log_step_start(self) -> None:
        self._get_logger().info(
            f"\n{'='*50}\n"
            f"📍 Step {self._iteration}/{self.max_iterations} started\n"
            f"{'='*50}"
        )

    def _log_tool_execution(self, tool_name: str, tool_args: dict, result: str) -> None:
        if tool_name.lower() in REASONING_TOOLS:
            self._log_reasoning_result(tool_args)
        else:
            self._get_logger().info(
                f"\n###############################################\n"
                f"🛠️ TOOL EXECUTION:\n"
                f"    🔧 Tool: {tool_name}\n"
                f"    📋 Args: {json.dumps(tool_args, indent=2, ensure_ascii=False)[:500]}\n"
                f"    🔍 Result: '{result[:400]}...'\n"
                f"###############################################"
            )
        self._log.append({
            "step": self._iteration,
            "tool": tool_name,
            "args": tool_args,
            "result": result[:1000],
        })

    def _log_reasoning_result(self, tool_args: dict) -> None:
        reasoning_steps = tool_args.get("reasoning_steps", [])
        task_completed = tool_args.get("task_completed", False)
        enough_data = tool_args.get("enough_data", False)
        
        self._get_logger().info(
            f"\n###############################################\n"
            f"🤖 REASONING:\n"
            f"   🧠 Steps: {reasoning_steps}\n"
            f"   ✅ Enough Data: {enough_data}\n"
            f"   🏁 Task Completed: {task_completed}\n"
            f"###############################################"
        )

    def _log_agent_start(self) -> None:
        tool_names = [getattr(t, "tool_name", None) or t.__name__ for t in self.toolkit]
        self._get_logger().info(
            f"\n{'#'*60}\n"
            f"🚀 FLEXIBLE AGENT STARTING\n"
            f"    📝 Task: '{self.task[:200]}...'\n"
            f"    🛠️ Tools: {tool_names}\n"
            f"    ⚙️ Max Iterations: {self.max_iterations}\n"
            f"    🎯 Mode: Free-form final answer\n"
            f"{'#'*60}"
        )

    def _log_agent_finish(self, success: bool, result: str | None) -> None:
        status = "✅ COMPLETED" if success else "❌ FAILED"
        self._get_logger().info(
            f"\n{'#'*60}\n"
            f"{status}\n"
            f"    📍 Total Steps: {self._iteration}\n"
            f"    📄 Result: '{(result or 'None')[:200]}...'\n"
            f"{'#'*60}"
        )

    # ==================== Main Run Method ====================

    async def run(self) -> AsyncGenerator[SSEEvent, None]:
        """Execute ReAct loop with free-form final answer."""
        await self._ensure_session_state()
        await self._refresh_prompt_tools()

        # Initialize LLM client
        if self.template_config and self.template_config.llm_policy:
            factory = LLMClientFactory()
            self._client = factory.for_policy(self.template_config.llm_policy)
        else:
            self._get_logger().error("No LLM policy configured!")
            yield self.streaming_generator.error(0, "No LLM configuration")
            return

        # Initialize session logger
        session_id = self.session_context.session_id if self.session_context else "ephemeral"
        agent_name = getattr(self.template_config, "template_name", None) or self.name
        self._session_logger = setup_session_logger(agent_name or "agent", session_id)
        
        self._log_agent_start()

        clarification_pending = bool(self._context_data.get("clarification_requested"))
        waiting_for_clarification = False

        # Build initial conversation
        system_prompt = self._system_prompt()
        if system_prompt:
            self._conversation.append({"role": "system", "content": system_prompt})
            await self._record_message(ChatMessage.text("system", system_prompt))

        user_prompt = self._initial_user_request()  # Formatted for LLM
        self._conversation.append({"role": "user", "content": user_prompt})
        # Save original task to DB (without formatting), not the templated version
        await self._record_message(ChatMessage.text("user", self.task))
        self._get_logger().info(f"📥 User request: '{self.task[:200]}...'")

        # Build tools schema (WITHOUT FinalAnswerTool!)
        tools_schema = self._build_tools_schema()
        if not tools_schema:
            # No tools - generate direct answer
            yield self.streaming_generator.step_start(1, self.max_iterations, "Generating response...")
            final_result = await self._generate_free_form_answer()
            yield self.streaming_generator.step_end(1, "completed")
            self._finished = True
        else:
            self._get_logger().info(f"🛠️ Tools: {[t['function']['name'] for t in tools_schema]}")

            # ReAct loop
            all_content: list[str] = []
            final_result: str | None = None
            ready_for_final_answer = False
            
            while not self._finished and self._iteration < self.max_iterations:
                self._iteration += 1
                self._log_step_start()
                
                step_event = self.streaming_generator.step_start(
                    self._iteration, self.max_iterations, "Analyzing..."
                )
                yield step_event
                await self._record_agent_step("step_start", self._iteration, {
                    "description": "Analyzing...",
                    "max_iterations": self.max_iterations,
                })

                try:
                    response = await self._client.chat.completions.create(
                        model=self.template_config.llm_policy.model,
                        messages=self._conversation,
                        tools=tools_schema,
                        tool_choice="required" if self._iteration == 1 else "auto",
                        temperature=self.template_config.llm_policy.temperature or 0.7,
                        max_tokens=self.template_config.llm_policy.max_tokens or 4096,
                    )

                    assistant_message = response.choices[0].message

                    if assistant_message.tool_calls:
                        for tool_call in assistant_message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args_str = tool_call.function.arguments

                            try:
                                tool_args = json.loads(tool_args_str) if tool_args_str else {}
                            except json.JSONDecodeError:
                                tool_args = {"raw": tool_args_str}

                            yield self.streaming_generator.tool_call(
                                self._iteration, tool_name, tool_args
                            )
                            await self._record_agent_step("tool_call", self._iteration, {
                                "tool_name": tool_name,
                                "tool_args": tool_args,
                            })

                            # Execute tool
                            result = await self._execute_tool(tool_name, tool_args_str)
                            self._log_tool_execution(tool_name, tool_args, result)
                            
                            yield self.streaming_generator.tool_result(
                                self._iteration, tool_name, result, 
                                success=not result.startswith("Error")
                            )
                            await self._record_agent_step("tool_result", self._iteration, {
                                "tool_name": tool_name,
                                "result": result[:2000],  # Truncate for DB
                                "success": not result.startswith("Error"),
                            })

                            all_content.append(f"\n🔧 {tool_name}: {result[:200]}...")

                            # Add to conversation
                            self._conversation.append({
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_args_str,
                                    }
                                }]
                            })
                            self._conversation.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result,
                            })

                            if self._agent_context.state == AgentStatesEnum.WAITING_FOR_CLARIFICATION:
                                self._context_data["clarification_requested"] = True
                                await self._persist_context()
                                final_result = result
                                waiting_for_clarification = True
                                self._finished = True
                                break

                            # Check if reasoning indicates completion
                            if tool_name.lower() in REASONING_TOOLS:
                                self._collected_reasoning.append(result)
                                if tool_args.get("task_completed", False) or tool_args.get("enough_data", False):
                                    ready_for_final_answer = True
                                    self._finished = True
                                    break
                            
                            # Check agent context
                            if self._agent_context.is_finished():
                                ready_for_final_answer = True
                                self._finished = True
                                break

                    else:
                        # LLM responded with text (no tool call) - this IS the answer
                        if assistant_message.content:
                            self._get_logger().info(f"💬 Text response: {assistant_message.content[:200]}...")
                            self._conversation.append({
                                "role": "assistant",
                                "content": assistant_message.content,
                            })
                            final_result = assistant_message.content
                            yield self.streaming_generator.thinking(
                                self._iteration, assistant_message.content[:500]
                            )
                            await self._record_agent_step("thinking", self._iteration, {
                                "thought": assistant_message.content[:2000],
                            })
                        self._finished = True

                    # Step always completes when we reach here (either tool executed or text response)
                    yield self.streaming_generator.step_end(self._iteration, "completed")
                    await self._record_agent_step("step_end", self._iteration, {
                        "status": "completed",
                    })

                except Exception as e:
                    self._get_logger().error(f"❌ Error: {e}", exc_info=True)
                    yield self.streaming_generator.error(self._iteration, str(e))
                    yield self.streaming_generator.step_end(self._iteration, "error")
                    await self._record_agent_step("step_end", self._iteration, {
                        "status": "error",
                        "error": str(e),
                    })
                    self._finished = True

            # === KEY DIFFERENCE: Generate FREE-FORM final answer ===
            if ready_for_final_answer and self._collected_reasoning:
                self._get_logger().info("🎯 Generating FREE-FORM final answer...")
                final_step = self._iteration + 1
                yield self.streaming_generator.step_start(
                    final_step, self.max_iterations, 
                    "Generating final answer (free-form)..."
                )
                await self._record_agent_step("step_start", final_step, {
                    "description": "Generating final answer (free-form)...",
                    "max_iterations": self.max_iterations,
                })
                
                final_result = await self._generate_free_form_answer_with_reasoning()
                
                yield self.streaming_generator.step_end(final_step, "completed")
                await self._record_agent_step("step_end", final_step, {
                    "status": "completed",
                })

            # Handle max iterations
            if not self._finished and self._iteration >= self.max_iterations:
                self._get_logger().warning(f"⚠️ Max iterations reached")
                final_result = await self._generate_free_form_answer()
                self._agent_context.state = AgentStatesEnum.COMPLETED

        if clarification_pending and not waiting_for_clarification:
            self._context_data["clarification_requested"] = False
            await self._persist_context()

        # Finalize
        if not final_result:
            final_result = "Unable to complete the task. Please try rephrasing your question."

        self._agent_context.state = AgentStatesEnum.COMPLETED
        self._agent_context.execution_result = final_result
        
        self._log_agent_finish(success=True, result=final_result)
        await self._record_message(ChatMessage.text("assistant", final_result))
        
        for event in self.streaming_generator.stream_text(final_result):
            yield event

    # ==================== Tool Schema (NO FinalAnswerTool) ====================

    def _build_tools_schema(self) -> list[dict[str, Any]]:
        """Build tools schema EXCLUDING FinalAnswerTool."""
        tools = []
        skip_clarification = bool(self._context_data.get("clarification_requested"))
        for tool_cls in self.toolkit:
            name = getattr(tool_cls, "tool_name", None) or tool_cls.__name__

            # EXCLUDE FinalAnswerTool - we use free-form instead!
            if name.lower() in FINAL_ANSWER_TOOLS:
                self._get_logger().debug(f"⏭️ Excluding {name} (using free-form answer)")
                continue
            if skip_clarification and name.lower() in {"clarificationtool", "clarification_tool"}:
                self._get_logger().debug(f"⏭️ Excluding {name} (clarification already requested)")
                continue

            description = tool_cls.__doc__ or f"Tool: {name}"
            if len(description) > 500:
                description = description[:497] + "..."

            if issubclass(tool_cls, PydanticTool):
                try:
                    schema = tool_cls.model_json_schema()
                    parameters = {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", []),
                    }
                except Exception:
                    parameters = {"type": "object", "properties": {}}
            else:
                parameters = {"type": "object", "properties": {}}

            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                }
            })

        return tools

    # ==================== Tool Execution ====================

    async def _execute_tool(self, tool_name: str, args_json: str) -> str:
        """Execute a tool by name."""
        if tool_name.lower() in {"clarificationtool", "clarification_tool"}:
            if self._context_data.get("clarification_requested"):
                return (
                    "Error: ClarificationTool already requested for this session. "
                    "Proceed with other tools."
                )

        tool_cls = None
        for tc in self.toolkit:
            tc_name = getattr(tc, "tool_name", None) or tc.__name__
            if tc_name.lower() == tool_name.lower():
                tool_cls = tc
                break

        if tool_cls is None:
            return f"Error: Tool '{tool_name}' not found"

        try:
            args = json.loads(args_json) if args_json else {}

            self._agent_context.user_id = self._user_id
            if self.session_context:
                self._agent_context.session_id = self.session_context.session_id
            self._agent_context.custom_context = dict(self._context_data)

            tool_config = await self._get_tool_config(tool_name, tool_cls)
            if self._is_clarification_tool(tool_name, tool_cls):
                default_max_reasoning = 500
                max_reasoning_len = self._get_tool_setting_int(
                    tool_config,
                    "max_reasoning_len",
                    default_max_reasoning,
                )
                max_reasoning_len = min(max_reasoning_len, default_max_reasoning)
                self._trim_reasoning_arg(args, max_reasoning_len)

            if issubclass(tool_cls, PydanticTool):
                tool_instance = tool_cls(**args)
                result = await tool_instance(context=self._agent_context, config=tool_config or {})
            else:
                tool_instance = tool_cls()
                result = await tool_instance(context=self._agent_context, **args)

            return str(result) if result else "OK"

        except Exception as e:
            self._get_logger().error(f"Tool error: {e}", exc_info=True)
            return f"Error: {str(e)}"

    # ==================== Free-Form Answer Generation ====================

    async def _generate_free_form_answer(self) -> str:
        """Generate answer in free-form (no tool structure)."""
        response = await self._client.chat.completions.create(
            model=self.template_config.llm_policy.model,
            messages=self._conversation,
            temperature=self.template_config.llm_policy.temperature or 0.7,
            max_tokens=self.template_config.llm_policy.max_tokens or 4096,
            # NO tools! Free-form response.
        )
        return response.choices[0].message.content or ""

    async def _generate_free_form_answer_with_reasoning(self) -> str:
        """Generate final answer with collected reasoning in context.
        
        This is the Two-Step SO pattern from research:
        1. Add reasoning as assistant message
        2. Ask for final answer in FREE-FORM
        """
        # Build reasoning context
        reasoning_summary = "\n\n".join(self._collected_reasoning[-3:])  # Last 3 reasonings
        
        # Add reasoning as assistant message
        self._conversation.append({
            "role": "assistant",
            "content": f"Based on my analysis:\n{reasoning_summary[:2000]}"
        })
        
        # Ask for final answer (FREE-FORM!)
        self._conversation.append({
            "role": "user", 
            "content": "Now provide the final answer to the original question. Be concise, accurate, and comprehensive."
        })

        # Generate free-form answer (NO tools!)
        response = await self._client.chat.completions.create(
            model=self.template_config.llm_policy.model,
            messages=self._conversation,
            temperature=self.template_config.llm_policy.temperature or 0.7,
            max_tokens=self.template_config.llm_policy.max_tokens or 4096,
            # NO tools parameter!
        )
        
        return response.choices[0].message.content or ""


__all__ = ["FlexibleToolCallingAgent"]
