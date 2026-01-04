from __future__ import annotations

from typing import Annotated, Any, Dict, Iterable, List, Literal, Type, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from platform.retrieval.tool_loader import ToolDescriptor


_DEFAULT_PARAMETERS_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": True}


class ToolSchemaBuilder:
    """Construct tool schemas for OpenAI function tools and SGR structured output."""

    def __init__(self, tools: Iterable[ToolDescriptor]):
        self.tools: List[ToolDescriptor] = list(tools)

    def build_openai_tools(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible function tool definitions."""

        openai_tools: List[Dict[str, Any]] = []
        for tool in self.tools:
            parameters = tool.input_schema or _DEFAULT_PARAMETERS_SCHEMA
            description = tool.description or tool.description_long or ""
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": description,
                        "parameters": parameters,
                    },
                }
            )
        return openai_tools

    def build_sgr_schema(self) -> Type[BaseModel]:
        """Build a structured generation schema that discriminates between tools."""

        if not self.tools:
            raise ValueError("At least one tool is required to build a schema")

        variant_models: List[Type[BaseModel]] = []
        for tool in self.tools:
            model_name = f"{tool.name.title().replace('.', '_').replace('-', '_')}Call"
            variant_model: Type[BaseModel] = create_model(  # type: ignore[misc]
                model_name,
                name=(
                    Literal[tool.name],  # type: ignore[name-defined]
                    Field(description=tool.description or tool.description_long or ""),
                ),
                arguments=(Dict[str, Any], Field(default_factory=dict, description="Tool arguments")),
                __base__=BaseModel,
                __module__=__name__,
                __config__=ConfigDict(extra="allow"),
            )
            variant_models.append(variant_model)

        discriminated_union = Annotated[Union[tuple(variant_models)], Field(discriminator="name")]
        schema_model: Type[BaseModel] = create_model(  # type: ignore[misc]
            "StructuredToolChoice",
            function=(discriminated_union, Field(description="Selected tool call")),
            __base__=BaseModel,
            __module__=__name__,
            __config__=ConfigDict(extra="ignore"),
        )
        return schema_model


__all__ = ["ToolSchemaBuilder"]
