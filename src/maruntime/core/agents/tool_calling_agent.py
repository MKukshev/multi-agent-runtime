"""Tool Calling Agent with ReAct loop using OpenAI function calling."""

from __future__ import annotations

import json
import logging
import os
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
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create logger with unique name
    logger_name = f"maruntime.agent.{agent_name}.{session_id}"
    session_logger = logging.getLogger(logger_name)
    session_logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers
    if session_logger.handlers:
        return session_logger
    
    # File handler for session log
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_filename = LOGS_DIR / f"{timestamp}-{agent_name}-{session_id[:8]}.log"
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
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

# Tools that were previously filtered, but are now included
# ReasoningTool helps LLM make decisions about when to finish
# PLANNING_TOOLS = {"reasoningtool", "reasoning_tool", "reasoning"}


class ToolCallingAgent(BaseAgent):
    """Agent that uses OpenAI function calling for tool selection and execution.
    
    Implements a ReAct-style loop:
    1. Send conversation + tools to LLM
    2. LLM selects a tool via function calling
    3. Execute the tool
    4. Add result to conversation
    5. Repeat until done (max iterations or finish tool called)
    """

    name = "tool_calling_agent"

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
        # Agent context for tools (not SessionContext)
        self._agent_context = AgentContext()
        # Execution log for debugging/persistence
        self._log: list[dict[str, Any]] = []
        # Session-specific logger (initialized in run())
        self._session_logger: logging.Logger | None = None

    def _get_logger(self) -> logging.Logger:
        """Get session logger or fallback to module logger."""
        return self._session_logger or logger

    def _log_step_start(self) -> None:
        """Log the start of a new iteration step."""
        self._get_logger().info(
            f"\n{'='*50}\n"
            f"📍 Step {self._iteration}/{self.max_iterations} started\n"
            f"{'='*50}"
        )

    def _log_llm_request(self, tools_count: int) -> None:
        """Log LLM request details."""
        self._get_logger().debug(
            f"🔄 Calling LLM:\n"
            f"   Model: {self.template_config.llm_policy.model}\n"
            f"   Messages: {len(self._conversation)}\n"
            f"   Tools: {tools_count}"
        )

    def _log_tool_execution(self, tool_name: str, tool_args: dict, result: str) -> None:
        """Log detailed tool execution info like sgr-agent-core."""
        # Special handling for ReasoningTool - log structured reasoning data
        if tool_name.lower() == "reasoningtool":
            self._log_reasoning_result(tool_args)
        else:
            self._get_logger().info(
                f"\n###############################################\n"
                f"🛠️ TOOL EXECUTION DEBUG:\n"
                f"    🔧 Tool Name: {tool_name}\n"
                f"    📋 Tool Args: {json.dumps(tool_args, indent=2, ensure_ascii=False)[:500]}\n"
                f"    🔍 Result: '{result[:400]}...'\n"
                f"###############################################"
            )
        self._log.append({
            "step_number": self._iteration,
            "timestamp": datetime.now().isoformat(),
            "step_type": "tool_execution",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "result": result[:1000],
        })

    def _log_reasoning_result(self, tool_args: dict) -> None:
        """Log ReasoningTool result in detailed format like sgr-agent-core."""
        reasoning_steps = tool_args.get("reasoning_steps", [])
        current_situation = tool_args.get("current_situation", "")
        plan_status = tool_args.get("plan_status", "")
        enough_data = tool_args.get("enough_data", False)
        remaining_steps = tool_args.get("remaining_steps", [])
        task_completed = tool_args.get("task_completed", False)
        next_step = remaining_steps[0] if remaining_steps else "N/A"
        
        self._get_logger().info(
            f"\n###############################################\n"
            f"🤖 LLM RESPONSE DEBUG:\n"
            f"   🧠 Reasoning Steps: {reasoning_steps}\n"
            f"   📊 Current Situation: '{current_situation[:400]}...'\n"
            f"   📋 Plan Status: '{plan_status[:200]}...'\n"
            f"   🔍 Searches Done: {self._agent_context.searches_used}\n"
            f"   🔍 Clarifications Done: {self._agent_context.clarifications_used}\n"
            f"   ✅ Enough Data: {enough_data}\n"
            f"   📝 Remaining Steps: {remaining_steps}\n"
            f"   🏁 Task Completed: {task_completed}\n"
            f"   ➡️ Next Step: {next_step}\n"
            f"###############################################"
        )

    def _log_llm_text_response(self, content: str) -> None:
        """Log when LLM responds with text instead of tool call."""
        self._get_logger().info(
            f"\n###############################################\n"
            f"💬 LLM TEXT RESPONSE:\n"
            f"    {content[:500]}...\n"
            f"###############################################"
        )

    def _log_iteration_summary(self) -> None:
        """Log summary of agent context state."""
        self._get_logger().info(
            f"\n📊 AGENT STATE:\n"
            f"    🔍 Searches Done: {self._agent_context.searches_used}\n"
            f"    🔍 Clarifications Done: {self._agent_context.clarifications_used}\n"
            f"    📚 Sources Found: {len(self._agent_context.sources)}\n"
            f"    🏁 State: {self._agent_context.state.value}"
        )

    def _log_agent_start(self) -> None:
        """Log agent start with task details."""
        tool_names = [getattr(t, "tool_name", None) or t.__name__ for t in self.toolkit]
        self._get_logger().info(
            f"\n{'#'*60}\n"
            f"🚀 AGENT STARTING\n"
            f"    📝 Task: '{self.task[:200]}...'\n"
            f"    🛠️ Tools: {tool_names}\n"
            f"    ⚙️ Max Iterations: {self.max_iterations}\n"
            f"    🤖 Model: {self.template_config.llm_policy.model if self.template_config else 'N/A'}\n"
            f"{'#'*60}"
        )

    def _log_agent_finish(self, success: bool, result: str | None) -> None:
        """Log agent completion."""
        status = "✅ COMPLETED" if success else "❌ FAILED"
        self._get_logger().info(
            f"\n{'#'*60}\n"
            f"{status}\n"
            f"    📍 Total Steps: {self._iteration}\n"
            f"    🔍 Total Searches: {self._agent_context.searches_used}\n"
            f"    📚 Sources Found: {len(self._agent_context.sources)}\n"
            f"    📄 Result: '{(result or 'None')[:200]}...'\n"
            f"{'#'*60}"
        )

    async def run(self) -> AsyncGenerator[SSEEvent, None]:
        """Execute the ReAct loop with real-time streaming step events."""
        await self._ensure_session_state()
        await self._refresh_prompt_tools()

        # Initialize LLM client
        if self.template_config and self.template_config.llm_policy:
            factory = LLMClientFactory()
            self._client = factory.for_policy(self.template_config.llm_policy)
        else:
            self._get_logger().error("No LLM policy configured!")
            error_msg = "Error: No LLM configuration. Please configure llm_policy in template."
            await self._record_message(ChatMessage.text("assistant", error_msg))
            yield self.streaming_generator.error(0, error_msg)
            return

        # Initialize session-specific logger
        session_id = self.session_context.session_id if self.session_context else "ephemeral"
        agent_name = getattr(self.template_config, "template_name", None) or self.name
        self._session_logger = setup_session_logger(agent_name or "agent", session_id)
        
        self._log_agent_start()

        # Build initial conversation
        system_prompt = self._system_prompt()
        if system_prompt:
            self._conversation.append({"role": "system", "content": system_prompt})
            await self._record_message(ChatMessage.text("system", system_prompt))
            self._get_logger().debug(f"📜 System prompt loaded ({len(system_prompt)} chars)")

        user_prompt = self._initial_user_request()  # Formatted for LLM
        self._conversation.append({"role": "user", "content": user_prompt})
        # Save original task to DB (without formatting), not the templated version
        await self._record_message(ChatMessage.text("user", self.task))
        self._get_logger().info(f"📥 User request: '{self.task[:200]}...'")

        # Prepare tools for OpenAI
        tools_schema = self._build_tools_schema()
        if not tools_schema:
            error_msg = "Error: No tools available for this agent."
            await self._record_message(ChatMessage.text("assistant", error_msg))
            yield self.streaming_generator.error(0, error_msg)
            return

        self._get_logger().info(f"🛠️ Available tools: {[t['function']['name'] for t in tools_schema]}")

        # ReAct loop with real-time streaming events
        all_content: list[str] = []
        final_result: str | None = None
        
        while not self._finished and self._iteration < self.max_iterations:
            self._iteration += 1
            self._log_step_start()
            
            # Emit step_start event immediately
            step_description = f"Analyzing and selecting next action..."
            yield self.streaming_generator.step_start(
                self._iteration, self.max_iterations, step_description
            )

            try:
                self._log_llm_request(len(tools_schema))
                
                # Call LLM with tools
                response = await self._client.chat.completions.create(
                    model=self.template_config.llm_policy.model,
                    messages=self._conversation,
                    tools=tools_schema,
                    tool_choice="required" if self._iteration == 1 else "auto",
                    temperature=self.template_config.llm_policy.temperature or 0.7,
                    max_tokens=self.template_config.llm_policy.max_tokens or 4096,
                )

                assistant_message = response.choices[0].message

                # Check if LLM wants to call a tool
                if assistant_message.tool_calls:
                    for tool_call in assistant_message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args_str = tool_call.function.arguments

                        # Parse args
                        try:
                            tool_args = json.loads(tool_args_str) if tool_args_str else {}
                        except json.JSONDecodeError:
                            tool_args = {"raw": tool_args_str}

                        all_content.append(f"\n🔧 Calling: {tool_name}")
                        
                        # Emit tool_call event immediately
                        yield self.streaming_generator.tool_call(
                            self._iteration, tool_name, tool_args
                        )

                        # Execute the tool
                        result = await self._execute_tool(tool_name, tool_args_str)
                        
                        # Detailed logging
                        self._log_tool_execution(tool_name, tool_args, result)
                        
                        # Emit tool_result event immediately
                        yield self.streaming_generator.tool_result(
                            self._iteration, tool_name, result, success=not result.startswith("Error")
                        )
                        
                        all_content.append(f"\n📋 Result: {result[:200]}..." if len(result) > 200 else f"\n📋 Result: {result}")

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

                        # Check finish conditions
                        if tool_name.lower() in ("finalanswertool", "final_answer", "finalanswer"):
                            self._finished = True
                            final_result = self._agent_context.execution_result or result
                            all_content.append(f"\n\n✅ Final Answer:\n{final_result}")
                            break
                        
                        if self._agent_context.is_finished():
                            self._finished = True
                            final_result = self._agent_context.execution_result
                            break

                else:
                    # LLM responded with text (no tool call)
                    if assistant_message.content:
                        self._log_llm_text_response(assistant_message.content)
                        all_content.append(f"\n💬 {assistant_message.content}")
                        self._conversation.append({
                            "role": "assistant",
                            "content": assistant_message.content,
                        })
                        final_result = assistant_message.content
                        
                        # Emit thinking event immediately
                        yield self.streaming_generator.thinking(
                            self._iteration, assistant_message.content[:500]
                        )
                    self._finished = True

                # Emit step_end event - step is always completed when we reach here
                yield self.streaming_generator.step_end(self._iteration, "completed")
                
                self._log_iteration_summary()

            except Exception as e:
                self._get_logger().error(f"❌ Error in iteration {self._iteration}: {e}", exc_info=True)
                all_content.append(f"\n❌ Error: {str(e)}")
                yield self.streaming_generator.error(self._iteration, str(e))
                yield self.streaming_generator.step_end(self._iteration, "error")
                self._finished = True

        # Handle max iterations
        if not self._finished and self._iteration >= self.max_iterations:
            self._get_logger().warning(f"⚠️ Max iterations ({self.max_iterations}) reached")
            fallback_msg = self._generate_fallback_response()
            all_content.append(f"\n\n⚠️ Max iterations reached. Summary:\n{fallback_msg}")
            final_result = fallback_msg
            self._agent_context.state = AgentStatesEnum.COMPLETED

        # Build final response
        final_content = "".join(all_content)
        if not final_content:
            final_content = "No response generated."

        self._log_agent_finish(
            success=self._agent_context.state == AgentStatesEnum.COMPLETED,
            result=final_result
        )

        await self._record_message(ChatMessage.text("assistant", final_content))
        
        # Stream final text events
        for event in self.streaming_generator.stream_text(final_result or final_content):
            yield event

    def _generate_fallback_response(self) -> str:
        """Generate a fallback response when max iterations is reached.
        
        Summarizes the search results collected so far.
        """
        sources = self._agent_context.sources
        searches = self._agent_context.searches_used
        
        if sources:
            source_summaries = []
            for i, (url, source) in enumerate(list(sources.items())[:5], 1):
                title = source.title or "Untitled"
                snippet = source.snippet[:200] if source.snippet else ""
                source_summaries.append(f"[{i}] {title}: {snippet}...")
            
            return (
                f"Based on {searches} searches and {len(sources)} sources found:\n\n"
                + "\n".join(source_summaries)
                + "\n\nNote: The agent reached maximum iterations. Please refine your query for more specific results."
            )
        else:
            return (
                f"The agent performed {searches} searches but could not find a definitive answer. "
                "Please try rephrasing your question."
            )

    def _build_tools_schema(self) -> list[dict[str, Any]]:
        """Build OpenAI-compatible tools schema from toolkit.
        
        Filters out planning-only tools (like ReasoningTool) since in function calling
        mode, the LLM directly selects action tools.
        """
        tools = []
        for tool_cls in self.toolkit:
            # Get tool name
            name = getattr(tool_cls, "tool_name", None) or tool_cls.__name__
            
            # ReasoningTool is now included - it helps LLM decide when to finish
            # Previously was filtered, but this caused LLM to loop indefinitely

            # Get description from docstring
            description = tool_cls.__doc__ or f"Tool: {name}"
            # Truncate long descriptions
            if len(description) > 500:
                description = description[:497] + "..."

            # Build parameters schema
            if issubclass(tool_cls, PydanticTool):
                # Pydantic tools have schema
                try:
                    schema = tool_cls.model_json_schema()
                    # Remove title and description from top level (OpenAI doesn't like them)
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

    async def _execute_tool(self, tool_name: str, args_json: str) -> str:
        """Execute a tool by name with JSON arguments."""
        # Find the tool class
        tool_cls = None
        for tc in self.toolkit:
            tc_name = getattr(tc, "tool_name", None) or tc.__name__
            if tc_name.lower() == tool_name.lower():
                tool_cls = tc
                break

        if tool_cls is None:
            return f"Error: Tool '{tool_name}' not found"

        try:
            # Parse arguments
            args = json.loads(args_json) if args_json else {}

            # Update context with identity info for tools
            self._agent_context.user_id = self._user_id
            if self.session_context:
                self._agent_context.session_id = self.session_context.session_id

            # Instantiate and call the tool
            if issubclass(tool_cls, PydanticTool):
                tool_instance = tool_cls(**args)
                result = await tool_instance(context=self._agent_context, config=None)
            else:
                tool_instance = tool_cls()
                result = await tool_instance(context=self._agent_context, **args)

            return str(result) if result else "OK"

        except Exception as e:
            self._get_logger().error(f"Tool execution error: {e}", exc_info=True)
            return f"Error executing tool: {str(e)}"


__all__ = ["ToolCallingAgent"]
