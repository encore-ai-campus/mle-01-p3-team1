"""Compatibility entry point for the LangGraph Ragas testset generator."""

from src.evaluation.langgraph.ragas_testset import *  # noqa: F401,F403
from src.evaluation.langgraph.ragas_testset import main


if __name__ == "__main__":
    raise SystemExit(main())
