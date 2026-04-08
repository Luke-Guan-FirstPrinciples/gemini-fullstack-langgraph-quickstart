"""Research Agent - LLM-powered academic literature search pipeline."""

from research_agent.models import Author, Lab, Paper, RankedResults, ResearchOutput

__all__ = [
    "build_graph",
    "run_research",
    "ResearchOutput",
    "RankedResults",
    "Paper",
    "Author",
    "Lab",
]


def __getattr__(name: str):
    if name == "build_graph":
        from research_agent.graph import build_graph

        return build_graph
    if name == "run_research":
        from research_agent.graph import run_research

        return run_research
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
