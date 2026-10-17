from __future__ import annotations

import pytest

from northstar_rag.config import ConfigurationError, Settings


def test_settings_uses_northstar_retrieval_and_nebius_defaults() -> None:
    settings = Settings.from_env({"NEBIUS_API_KEY": "test-key"})

    assert settings.nebius_base_url == "https://api.tokenfactory.nebius.com/v1/"
    assert settings.embedding_model == "Qwen/Qwen3-Embedding-8B"
    assert settings.rerank_model == "Qwen/Qwen3-Embedding-8B"
    assert settings.chat_model == "Qwen/Qwen3-30B-A3B-Instruct-2507"
    assert settings.dense_k == 8
    assert settings.lexical_k == 8
    assert settings.fusion_k == 60
    assert settings.rerank_candidates == 10
    assert settings.evidence_k == 4
    assert settings.rerank_min_score == 0.802
    assert settings.max_retries == 2


@pytest.mark.parametrize("api_key", ["", " ", "\t\n"])
def test_settings_rejects_blank_api_key(api_key: str) -> None:
    with pytest.raises(ConfigurationError, match="NEBIUS_API_KEY is required"):
        Settings.from_env({"NEBIUS_API_KEY": api_key})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DENSE_K", "0"),
        ("LEXICAL_K", "-1"),
        ("FUSION_K", "0"),
        ("RERANK_CANDIDATES", "0"),
        ("EVIDENCE_K", "0"),
        ("RERANK_MIN_SCORE", "-0.01"),
        ("RERANK_MIN_SCORE", "1.01"),
        ("NEBIUS_REQUEST_TIMEOUT_SECONDS", "0"),
        ("NEBIUS_MAX_RETRIES", "3"),
    ],
)
def test_settings_rejects_out_of_range_numbers(name: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env({"NEBIUS_API_KEY": "test-key", name: value})


def test_configuration_error_never_exposes_api_key() -> None:
    secret = "nebius-secret-value"

    with pytest.raises(ConfigurationError) as caught:
        Settings.from_env({"NEBIUS_API_KEY": secret, "DENSE_K": "not-an-integer"})

    assert secret not in str(caught.value)
