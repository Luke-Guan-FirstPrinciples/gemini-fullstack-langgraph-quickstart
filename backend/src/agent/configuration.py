import os
from typing import Any, Optional

from pydantic import BaseModel, Field

from langchain_core.runnables import RunnableConfig


class Configuration(BaseModel):
    """The configuration for the agent."""

    query_generator_model: str = Field(
        default="gemini-2.5-flash",
        metadata={
            "description": "The name of the language model to use for the agent's query generation."
        },
    )

    reflection_model: str = Field(
        default="gemini-2.5-flash",
        metadata={
            "description": "The name of the language model to use for the agent's reflection."
        },
    )

    answer_model: str = Field(
        default="gemini-2.5-pro",
        metadata={
            "description": "The name of the language model to use for the agent's answer."
        },
    )

    number_of_initial_queries: int = Field(
        default=3,
        metadata={"description": "The number of initial search queries to generate."},
    )

    max_research_loops: int = Field(
        default=2,
        metadata={"description": "The maximum number of research loops to perform."},
    )

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )

        # Get raw values from environment or config
        raw_values: dict[str, Any] = {
            name: os.environ.get(name.upper(), configurable.get(name))
            for name in cls.model_fields.keys()
        }

        # Normalize model aliases so stale UI state or env values don't break requests.
        for key in ("query_generator_model", "reflection_model", "answer_model"):
            raw_values[key] = normalize_gemini_model_name(raw_values.get(key))

        # Filter out None values
        values = {k: v for k, v in raw_values.items() if v is not None}

        return cls(**values)


LEGACY_GEMINI_MODEL_ALIASES = {
    "gemini-2.0-flash": "gemini-2.5-flash",
    "gemini-2.0-flash-lite": "gemini-2.5-flash",
    "gemini-2.5-flash-preview-04-17": "gemini-2.5-flash",
    "gemini-2.5-pro-preview-05-06": "gemini-2.5-pro",
}


def normalize_gemini_model_name(model_name: Optional[str]) -> Optional[str]:
    """Map deprecated Gemini model aliases to supported stable model names."""
    if model_name is None:
        return None
    canonical_name = model_name.removeprefix("models/")
    return LEGACY_GEMINI_MODEL_ALIASES.get(canonical_name, canonical_name)
