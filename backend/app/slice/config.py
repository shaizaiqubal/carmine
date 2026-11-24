from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModuleConfig:
    name: str
    connectors: tuple[str, ...]
    query_planning_prompt: str
    extraction_prompt: str
    severity_rubric: dict[str, str]
    max_queries_per_connector: int = 3
    max_docs_per_assumption: int = 10
    passages_per_doc: int = 3
    max_passages_per_extraction_call: int = 5
    min_similarity: float = 0.30
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "


MARKET_MODULE = ModuleConfig(
    name="market",
    connectors=("hn", "stackexchange", "ddg", "rss"),
    query_planning_prompt="""Plan searches designed to DISPROVE the assumption. Look for no demand, free alternatives, complaints, failed attempts, and existing solutions. Return JSON only with exactly these keys: hn, stackexchange, ddg, rss; each value is a list of at most three queries.
Connector style rules:
- stackexchange: phrase the problem as a user question.
- hn: use short keyword phrases.
- ddg: use review/complaint/alternatives patterns such as '<product> not worth it', 'alternatives to <competitor>', and '<problem> complaints'.
- rss: keywords for filtering general feeds; do not use bare category words.
Queries should be specific, problem-phrased, and no more than about eight words each.""",
    extraction_prompt="""Report only objections supported by the supplied passages. If the passage is not evidence AGAINST the assumption, return an empty list. quote must be copied verbatim and contiguous from one supplied passage, no more than 300 characters; do not paraphrase, merge, or correct typos. text must be a specific, falsifiable objection tied to the assumption, never a generic concern. Never invent; return [] when evidence is thin. confidence is a rough 0-1 self-estimate and will be overwritten by verification. Use the supplied severity rubric.""",
    severity_rubric={
        "critical": "Undermines the core business: no demand, a dominant free alternative, or platform absorption.",
        "high": "Materially hurts the plan.",
        "medium": "A real but manageable problem.",
        "low": "A minor concern.",
    },
)
