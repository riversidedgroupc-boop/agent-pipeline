"""
Agent I/O schema definitions using Pydantic v2.
Each Agent declares its input/output structure for upstream-downstream validation.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class AgentId(StrEnum):
    PM = "01-pm"
    MECHANICAL = "02-mechanical"
    OPTICS = "03-optics"
    MOTION = "04-motion"
    ALGORITHM = "05-algorithm"
    REVIEW = "06-review"


class AgentMeta(BaseModel):
    """Frontmatter schema for agent.md."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Agent ID: NN-name")
    name: str = Field(description="Short identifier")
    title: str = Field(description="Display title")
    role: str = Field(description="Professional role description")
    industries: list[str] = Field(default_factory=list)
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class PipelineStage(BaseModel):
    """Runtime status of a single stage."""

    agent_id: str
    status: Annotated[str, Field(default="pending")]  # pending | in_progress | done | blocked
    started_at: datetime | None = None
    completed_at: datetime | None = None
    document_path: str | None = None
    blockers: list[str] = Field(default_factory=list)
    notes: str = ""


class PipelineStatus(BaseModel):
    """Top-level pipeline status."""

    project: str
    updated: datetime = Field(default_factory=datetime.now)
    stages: list[PipelineStage] = Field(default_factory=list)


class ModelConfig(BaseModel):
    """LLM model configuration."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192
    temperature: float = 0.3


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration."""

    model_config = ConfigDict(extra="forbid")

    model: ModelConfig = Field(default_factory=ModelConfig)
    retry: int = Field(default=2, description="Max retries per agent on failure")
    output_dir: str = "examples"
    verbose: bool = False
