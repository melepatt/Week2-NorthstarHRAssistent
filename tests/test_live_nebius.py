from __future__ import annotations

import os

import pytest

from northstar_rag.config import Settings
from northstar_rag.graph import answer_question
from northstar_rag.nebius import NebiusGateway, validate_configured_models
from northstar_rag.runtime import clear_runtime_cache, create_runtime

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="set RUN_LIVE_TESTS=1 to use Nebius credentials and provider capacity",
)
def test_live_models_and_grounded_runtime_answer() -> None:
    settings = Settings.from_env()
    gateway = NebiusGateway(settings)
    try:
        validate_configured_models(gateway, settings)

        vectors = gateway.embed(
            ["paid time off policy", "information security incident"],
            settings.embedding_model,
        )
        assert len(vectors) == 2
        assert vectors[0]
        assert len(vectors[0]) == len(vectors[1])

        scores = gateway.rerank(
            "How many paid time off days are provided?",
            [
                "Full-time employees receive 20 paid time off days.",
                "Security incidents must be reported promptly.",
            ],
            settings.rerank_model,
        )
        assert len(scores) == 2
        assert all(isinstance(score, float) for score in scores)

        graph = create_runtime(settings)
        result = answer_question(
            graph,
            "How many paid time off days does a regular full-time employee receive?",
        )
        assert result.refused is False
        assert result.citations
        assert all(citation.document_title and citation.page > 0 for citation in result.citations)
    finally:
        gateway.close()
        clear_runtime_cache()
