"""Compatibility entry point for the LangGraph Ragas evaluator."""

from src.evaluation.langgraph.ragas_eval import *  # noqa: F401,F403
from src.evaluation.langgraph.ragas_eval import main


if __name__ == "__main__":
    raise SystemExit(main())
