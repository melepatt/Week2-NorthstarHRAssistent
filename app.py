from __future__ import annotations

from collections.abc import Callable

import streamlit as st
from langgraph.graph.state import CompiledStateGraph

from northstar_rag.config import ConfigurationError, Settings
from northstar_rag.graph import answer_question
from northstar_rag.indexes import IndexNotReadyError
from northstar_rag.nebius import NebiusError
from northstar_rag.runtime import create_runtime
from northstar_rag.schemas import AnswerResult

EXAMPLE_QUESTIONS = (
    "How many paid time off days do full-time employees receive?",
    "When do benefits begin for a newly eligible employee?",
    "Can I work from another state?",
)


def render_answer(result: AnswerResult) -> None:
    if result.refused:
        st.warning(result.answer)
        return

    st.markdown(result.answer)
    if result.citations:
        sources = ", ".join(
            f"{citation.document_title}, p. {citation.page}" for citation in result.citations
        )
        st.caption(f"Sources: {sources}")
    if result.evidence or result.timings:
        with st.expander("Evidence and timing", expanded=False):
            for hit in result.evidence:
                st.markdown(
                    f"**{hit.chunk.document_title}, p. {hit.chunk.page}**  \n"
                    f"{hit.chunk.section} · score {hit.score:.3f}\n\n"
                    f"> {hit.chunk.text}"
                )
            if result.timings:
                timing_text = ", ".join(
                    f"{timing.stage}: {timing.elapsed_ms:.1f} ms" for timing in result.timings
                )
                st.caption(timing_text)


def _render_examples() -> None:
    st.markdown("**Example questions**")
    for example in EXAMPLE_QUESTIONS:
        st.markdown(f"- {example}")


def _render_startup_error(error: Exception) -> None:
    if isinstance(error, IndexNotReadyError):
        st.error(
            "The policy index is not ready. Run `python scripts/ingest.py`, then restart the "
            "application."
        )
    elif isinstance(error, ConfigurationError):
        st.error(
            "Model-service configuration is incomplete. Set the required Nebius environment "
            "variables and restart the application."
        )
    else:
        st.error(
            "The configured model services could not be initialized. Verify the model settings "
            "with `python scripts/check_models.py`, then restart the application."
        )


def main(
    *,
    runtime_factory: Callable[[Settings], CompiledStateGraph] = create_runtime,
    answerer: Callable[[CompiledStateGraph, str], AnswerResult] = answer_question,
    settings_loader: Callable[[], Settings] = Settings.from_env,
) -> None:
    st.set_page_config(page_title="Northstar HR Policy Assistant", page_icon="📘")
    st.title("Northstar Labs HR Policy Assistant")
    st.markdown(
        "Internal policy guidance grounded in Northstar Labs' controlled HR documents. "
        "For individual decisions or exceptions, contact People Operations."
    )
    _render_examples()

    try:
        graph = runtime_factory(settings_loader())
    except (ConfigurationError, IndexNotReadyError, NebiusError) as error:
        _render_startup_error(error)
        return

    messages = st.session_state.setdefault("messages", [])
    for message in messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                render_answer(message["result"])

    prompt = st.chat_input("Ask a question about Northstar Labs HR policies")
    if prompt and prompt.strip():
        question = prompt.strip()
        with st.chat_message("user"):
            st.markdown(question)
        result = answerer(graph, question)
        with st.chat_message("assistant"):
            render_answer(result)
        messages.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "result": result},
            ]
        )


if __name__ == "__main__":
    main()
