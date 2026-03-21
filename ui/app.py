"""Streamlit UI for ChronosGraph temporal world-model demo."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure project-root absolute imports work when running via:
# streamlit run ui/app.py
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.openai_agent import OpenAIToolAgent
from chronosgraph.bootstrap import bootstrap_world
from mcp_server.tools import build_tool_registry
from query_api.world_query_api import WorldQueryAPI
from world.world_state_engine import WorldStateEngine


def _shorten_entity_labels(entity_ids: list[str]) -> dict[str, str]:
    """Generate short unique labels for long entity ids."""
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}

    for entity_id in entity_ids:
        base = entity_id.split("_")[0] if "_" in entity_id else entity_id
        counts[base] = counts.get(base, 0) + 1
        suffix = counts[base]
        labels[entity_id] = base if suffix == 1 else f"{base}_{suffix}"

    return labels


@st.cache_resource(show_spinner=True)
def get_runtime() -> tuple[
    WorldStateEngine,
    WorldQueryAPI,
    dict[str, Any],
    OpenAIToolAgent,
    list[dict[str, Any]],
    list[Any],
]:
    """Bootstrap world once and return shared runtime objects."""
    world_engine, event_log_text, frames = bootstrap_world(demo=False, return_artifacts=True)
    api = WorldQueryAPI(world_engine)
    registry = build_tool_registry(api)
    agent = OpenAIToolAgent(registry=registry, model="gpt-4.1")
    return world_engine, api, registry, agent, event_log_text, frames


def build_graphviz(world_engine: WorldStateEngine, queried_entity: str | None = None) -> str:
    """Build a focused containment graph of entities that changed during the episode."""
    active_entity_ids = {
        entity_id
        for entity_id, state in world_engine.entities.items()
        if len(state.history) > 1
    }
    if queried_entity:
        active_entity_ids.add(queried_entity)

    if not active_entity_ids:
        return 'digraph G { node [fontname=Helvetica]; "No events recorded" [shape=plaintext]; }'

    parent_ids: set[str] = set()
    for entity_id in active_entity_ids:
        state = world_engine.entities.get(entity_id)
        if state and state.current_parent:
            parent_ids.add(state.current_parent)

    all_visible = sorted(active_entity_ids | parent_ids)
    labels = _shorten_entity_labels(all_visible)

    lines = ["digraph G {"]
    lines.append("  rankdir=TB;")
    lines.append("  graph [splines=true, pad=0.4, nodesep=0.6, ranksep=0.8];")
    lines.append('  node [style=filled, fontname=Helvetica, fontsize=11, shape=box, margin="0.2,0.12"];')

    for entity_id in all_visible:
        is_container = entity_id in parent_ids and entity_id not in active_entity_ids
        is_both = entity_id in parent_ids and entity_id in active_entity_ids

        if is_container:
            fill, shape = "#AED6F1", "ellipse"
        elif is_both:
            fill, shape = "#A9DFBF", "ellipse"
        else:
            fill, shape = "#A9DFBF", "box"

        border = "#C0392B" if queried_entity == entity_id else "black"
        penwidth = "2.5" if queried_entity == entity_id else "1"

        label = labels.get(entity_id, entity_id)
        lines.append(
            f'  "{entity_id}" '
            f'[label="{label}", fillcolor="{fill}", color="{border}", '
            f'penwidth={penwidth}, shape={shape}];'
        )

    for entity_id in active_entity_ids:
        state = world_engine.entities.get(entity_id)
        if state and state.current_parent and state.current_parent in all_visible:
            lines.append(f'  "{state.current_parent}" -> "{entity_id}";')

    lines.append("}")
    return "\n".join(lines)


def _extract_queried_entity(question: str, entity_ids: list[str]) -> str | None:
    question_lower = question.lower()
    for entity_id in entity_ids:
        if entity_id.lower() in question_lower:
            return entity_id
    return None


def _timeline_lines(event_log_text: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for frame in event_log_text:
        frame_id = frame["frame_id"]
        timestamp = frame["timestamp"]
        events = frame.get("events", [])
        lines.append(f"Frame {frame_id} | t={timestamp:.2f}")
        if events:
            for event in events:
                lines.append(f"  {event}")
        else:
            lines.append("  (no events)")
    return lines


def main() -> None:
    st.set_page_config(page_title="ChronosGraph Demo", layout="wide")

    st.title("ChronosGraph")
    st.caption(
        "Temporal world model demo — compare **Baseline** (LLM reasoning only) "
        "vs **Knowledge Graph** (tool-grounded answers)."
    )

    try:
        (
            world_engine,
            _api,
            _registry,
            agent,
            event_log_text,
            frames,
        ) = get_runtime()
    except Exception as exc:
        st.error(f"Failed to initialize runtime: {exc}")
        st.stop()

    entity_ids = sorted(world_engine.entities.keys())
    queried_entity = _extract_queried_entity(
        st.session_state.get("last_question", ""),
        entity_ids,
    )

    # ── Top two-column layout (controls + playback) ──────────────────────────
    ctrl_col, play_col = st.columns([1, 1.4], gap="medium")

    # ── Left: Controls + Agent answer ────────────────────────────────────────
    with ctrl_col:
        with st.container(border=True):
            st.subheader("Query")
            mode = st.radio("Mode", ["Baseline", "Knowledge Graph"], index=1, horizontal=True)
            question = st.text_input("Question", value="Where is keys_001 now?", label_visibility="collapsed")
            ask = st.button("Ask", use_container_width=True, type="primary")

        if ask:
            if not question.strip():
                st.warning("Enter a question first.")
            else:
                with st.spinner("Thinking..."):
                    start = time.perf_counter()
                    try:
                        if mode == "Baseline":
                            response = agent.run_without_tools(question)
                        else:
                            response = agent.run_with_tools(question)
                    except Exception as exc:
                        st.error(f"Agent call failed: {exc}")
                    else:
                        st.session_state["last_latency"] = time.perf_counter() - start
                        st.session_state["last_mode"] = mode
                        st.session_state["last_question"] = question
                        st.session_state["last_response"] = response

        response = st.session_state.get("last_response")
        if response is not None:
            with st.container(border=True):
                latency = st.session_state.get("last_latency", 0.0)
                st.caption(f"Mode: {st.session_state.get('last_mode', '')} · {latency:.2f}s")

                if st.session_state.get("last_mode") == "Knowledge Graph" and response.traces:
                    with st.expander(f"Tool calls ({len(response.traces)})", expanded=False):
                        for i, trace in enumerate(response.traces, 1):
                            st.markdown(f"**Call {i}**")
                            st.json(trace.tool_call, expanded=False)
                            st.markdown("**Result**")
                            st.json(trace.tool_result, expanded=False)

                st.markdown("**Answer**")
                st.write(response.answer)

    # ── Middle: Simulation playback ──────────────────────────────────────────
    with play_col:
        with st.container(border=True):
            st.subheader("Simulation Playback")
            max_index = max(len(frames), 1) - 1
            frame_index = st.slider("Frame", min_value=0, max_value=max_index, value=0)

            selected_frame = frames[frame_index] if frame_index < len(frames) else None
            if selected_frame is not None:
                # Constrain image to ~320 px so it doesn't dominate the layout
                st.image(selected_frame, channels="RGB", width=320)
            else:
                st.caption("No frame image available.")

            st.markdown("**Events — selected frame**")
            selected_events = (
                event_log_text[frame_index]["events"] if frame_index < len(event_log_text) else []
            )
            with st.container(height=140):
                if selected_events:
                    for event in selected_events:
                        if queried_entity and queried_entity in event:
                            st.markdown(f"- **{event}**")
                        else:
                            st.markdown(f"- {event}")
                else:
                    st.caption("No events in this frame.")

        with st.expander("Full event timeline", expanded=False):
            for line in _timeline_lines(event_log_text):
                if queried_entity and queried_entity in line:
                    st.markdown(f"**{line}**")
                else:
                    st.text(line)

    # ── Full-width: World graph ───────────────────────────────────────────────
    st.divider()
    with st.container(border=True):
        st.subheader("World Graph")
        st.caption("Blue = container · Green = object · Red border = queried entity")
        dot = build_graphviz(world_engine, queried_entity=queried_entity)
        st.graphviz_chart(dot, use_container_width=True)


if __name__ == "__main__":
    main()
