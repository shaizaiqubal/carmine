from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hn: list[str] = Field(default_factory=list)
    stackexchange: list[str] = Field(default_factory=list)
    ddg: list[str] = Field(default_factory=list)
    rss: list[str] = Field(default_factory=list)


class ObjectionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1)
    assumption_id: str = Field(min_length=1)
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)


class ExtractionOutput(RootModel[list[ObjectionCandidate]]):
    pass
