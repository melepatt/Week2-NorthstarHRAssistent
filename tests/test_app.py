from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_ROOT = Path(__file__).resolve().parents[1]


def app_script(mode: str = "supported") -> str:
    return f"""\
import streamlit as st
from app import main
from northstar_rag.config import Settings
from northstar_rag.indexes import IndexNotReadyError
from northstar_rag.schemas import AnswerResult, ChunkRecord, Citation, SearchHit, StageTiming

class Graph:
    pass

def runtime_factory(settings):
    del settings
    if {mode!r} == "startup_error":
        raise IndexNotReadyError("missing index; super-secret-value")
    return Graph()

def answerer(graph, question):
    del graph
    st.session_state["graph_calls"] = st.session_state.get("graph_calls", 0) + 1
    st.session_state["last_question"] = question
    chunk = ChunkRecord(
        chunk_id="leave-2",
        document_id="leave-and-time-off",
        document_title="Leave and Time Off Policy",
        section="2. Paid Time Off",
        page=2,
        source_path="leave.pdf",
        text="Full-time employees receive 20 paid time off days.",
    )
    hit = SearchHit(chunk=chunk, rank=1, score=0.9, retriever="rerank")
    if {mode!r} == "refusal":
        return AnswerResult(
            question=question,
            answer="The available policies do not provide enough information.",
            refused=True,
            refusal_reason="insufficient_evidence",
            evidence=(hit,),
        )
    return AnswerResult(
        question=question,
        answer="Full-time employees receive 20 days [Leave and Time Off Policy, p. 2].",
        refused=False,
        citations=(Citation("Leave and Time Off Policy", 2, "leave-2"),),
        evidence=(hit,),
        timings=(StageTiming("generate_answer", 12.0),),
    )

main(
    runtime_factory=runtime_factory,
    answerer=answerer,
    settings_loader=lambda: Settings(nebius_api_key="offline"),
)
"""


def run_app(mode: str = "supported") -> AppTest:
    return AppTest.from_string(app_script(mode), default_timeout=5).run()


def all_visible_text(app: AppTest) -> str:
    element_types = (app.title, app.markdown, app.caption, app.info, app.warning, app.error)
    return "\n".join(str(element.value) for group in element_types for element in group)


def test_title_scope_and_three_supported_examples_render() -> None:
    app = run_app()
    text = all_visible_text(app)

    assert app.title[0].value == "Northstar Labs HR Policy Assistant"
    assert "internal" in text.casefold()
    assert "How many paid time off days" in text
    assert "When do benefits begin" in text
    assert "Can I work from another state" in text
    assert "What is my retirement balance" not in text


def test_whitespace_input_does_not_call_graph() -> None:
    app = run_app()

    app.chat_input[0].set_value("   \n ").run()

    assert "graph_calls" not in app.session_state


def test_supported_answer_renders_citation_and_evidence_details() -> None:
    app = run_app()

    app.chat_input[0].set_value("How much PTO do I receive?").run()
    text = all_visible_text(app)

    assert app.session_state["graph_calls"] == 1
    assert app.session_state["last_question"] == "How much PTO do I receive?"
    assert "[Leave and Time Off Policy, p. 2]" in text
    assert "Evidence and timing" in [expander.label for expander in app.expander]


def test_refusal_does_not_render_retrieved_evidence_as_an_answer() -> None:
    app = run_app("refusal")

    app.chat_input[0].set_value("What is my retirement balance?").run()
    text = all_visible_text(app)

    assert "do not provide enough information" in text
    assert "Full-time employees receive 20 paid time off days" not in text
    assert not app.expander


def test_startup_error_is_corrective_and_does_not_expose_secret_or_traceback() -> None:
    app = run_app("startup_error")
    text = all_visible_text(app)

    assert "python scripts/ingest.py" in text
    assert "super-secret-value" not in text
    assert not app.exception
