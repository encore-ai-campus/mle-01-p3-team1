"""Additive supervisor package; does not modify src.agent.build_graph."""
from .state import AnswerDraft, RouteDecision, SupervisorState, VerificationResult
from .adapters import adapt_graph, adapt_hybrid, adapt_vector


def build_supervisor(**kwargs):
    """Lazy import lets contract tests run without LangGraph installed."""
    from .graph import build_supervisor as build
    return build(**kwargs)


__all__ = ["build_supervisor", "adapt_vector", "adapt_graph", "adapt_hybrid",
           "SupervisorState", "RouteDecision", "AnswerDraft", "VerificationResult"]
