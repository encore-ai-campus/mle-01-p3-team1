"""Automatically observe the *connected* LangGraph Supervisor.

The existing CLI and Streamlit UI both construct the same Supervisor through
build_connected_supervisor(). This wrapper keeps their graph source unchanged.
If tracing is disabled or cannot be initialized, the original compiled graph
is returned, not a changed implementation of the agent.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import wraps
from typing import Any

from .langfuse_support import (
    _client, _safe_update, _attributes, compact_trajectory, is_enabled,
    new_handler, observation, register_shutdown, compact_search_node,
)

LOG = logging.getLogger(__name__)


def observe_search_node(search_fn, *, kind: str):
    """Observe a normal Python search adapter without changing its contract."""
    if search_fn is None or not is_enabled():
        return search_fn

    @wraps(search_fn)
    def call(state, config=None):
        with observation(f"{kind}-search-detail", as_type="retriever",
                         input={"top_k": state.get("top_k", 5)},
                         metadata={"retrieval_kind": kind}) as span:
            result = search_fn(state, config)
            if span is not None:
                try:
                    payload = compact_search_node(result, kind=kind)
                    _safe_update(span, output=payload)
                except Exception as exc:
                    LOG.warning("Langfuse search diagnostics unavailable (%s)", type(exc).__name__)
            return result

    return call


def _root_input(request):
    if not isinstance(request, Mapping):
        return {"input_type": type(request).__name__}
    # The LangChain CallbackHandler may capture full input/state separately.
    return {key: request[key] for key in ("question", "top_k", "route_override") if key in request}


def _handler_config(config):
    handler = new_handler()
    if handler is None:
        return config
    # LangChain-supported callback merge preserves existing callback managers,
    # caller tags/metadata/run names and the checkpointer's configurable data.
    try:
        from langchain_core.runnables.config import merge_configs
        return merge_configs(dict(config or {}), {"callbacks": [handler]})
    except Exception as exc:
        # Telemetry must never stop an actual question from running.
        LOG.warning("Langfuse callback merge skipped (%s)", type(exc).__name__)
        return config


def _record_output(span, result):
    if span is None or not isinstance(result, Mapping):
        return
    from .langfuse_support import _ranked_rows

    summary = {
        "status": result.get("status"),
        "route": result.get("route"),
        "route_reason": str(result.get("route_reason") or "")[:180],
        "verified": result.get("verified"),
        "retry_count": result.get("retry_count"),
        "evidence_count": len(result.get("evidence") or []),
        "final_candidates": _ranked_rows(result.get("evidence") or []),
        "error_types": [e.get("type") for e in (result.get("errors") or [])[:12] if isinstance(e, Mapping)],
        "trajectory": compact_trajectory(result),
    }
    _safe_update(span, output=summary)


def _safe_record_output(span, result):
    try:
        _record_output(span, result)
    except Exception as exc:
        LOG.warning("Langfuse final diagnostics skipped (%s)", type(exc).__name__)


class ObservedSupervisor:
    """Thin LangGraph proxy: same inputs/outputs, opt-in one trace per invocation.

    This is intentionally not a new routing/agent graph. Unhandled graph
    attributes and methods (such as get_graph/get_state) delegate unchanged.
    """

    def __init__(self, graph):
        self._graph = graph
        self._lf_observed_wrapper = True

    def __getattr__(self, name):
        return getattr(self._graph, name)

    def invoke(self, input, config=None, **kwargs):
        if not is_enabled():
            return self._graph.invoke(input, config=config, **kwargs)
        with observation("museum-supervisor", input=_root_input(input),
                         metadata={"entrypoint": "connected_supervisor"}) as span:
            with _attributes(trace_name="museum-supervisor"):
                result = self._graph.invoke(input, config=_handler_config(config), **kwargs)
            _safe_record_output(span, result)
            return result

    async def ainvoke(self, input, config=None, **kwargs):
        if not is_enabled():
            return await self._graph.ainvoke(input, config=config, **kwargs)
        with observation("museum-supervisor", input=_root_input(input),
                         metadata={"entrypoint": "connected_supervisor"}) as span:
            with _attributes(trace_name="museum-supervisor"):
                result = await self._graph.ainvoke(input, config=_handler_config(config), **kwargs)
            _safe_record_output(span, result)
            return result

    def stream(self, input, config=None, **kwargs):
        if not is_enabled():
            yield from self._graph.stream(input, config=config, **kwargs)
            return
        with observation("museum-supervisor", input=_root_input(input),
                         metadata={"entrypoint": "connected_supervisor"}) as span:
            count = 0
            with _attributes(trace_name="museum-supervisor"):
                for chunk in self._graph.stream(input, config=_handler_config(config), **kwargs):
                    count += 1
                    yield chunk
            _safe_update(span, output={"stream_chunks": count})

    async def astream(self, input, config=None, **kwargs):
        if not is_enabled():
            async for chunk in self._graph.astream(input, config=config, **kwargs):
                yield chunk
            return
        with observation("museum-supervisor", input=_root_input(input),
                         metadata={"entrypoint": "connected_supervisor"}) as span:
            count = 0
            with _attributes(trace_name="museum-supervisor"):
                async for chunk in self._graph.astream(input, config=_handler_config(config), **kwargs):
                    count += 1
                    yield chunk
            _safe_update(span, output={"stream_chunks": count})


def observe_connected_supervisor(graph):
    """Return the compiled graph unchanged until Langfuse has been enabled."""
    if not is_enabled() or _client() is None:
        return graph
    register_shutdown()
    return ObservedSupervisor(graph)
