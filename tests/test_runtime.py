from __future__ import annotations

from pathlib import Path

import pytest

from northstar_rag import runtime
from northstar_rag.config import Settings
from northstar_rag.indexes import INDEX_INSTRUCTION, IndexNotReadyError


@pytest.fixture(autouse=True)
def clear_runtime_cache() -> None:
    runtime.clear_runtime_cache()
    yield
    runtime.clear_runtime_cache()


def test_runtime_factory_wires_all_configured_models(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeGateway:
        def __init__(self, settings: Settings) -> None:
            captured["gateway_settings"] = settings

        def close(self) -> None:
            captured["closed"] = True

    class FakeEmbeddings:
        def __init__(self, *, gateway: object, model: str) -> None:
            captured["embedding_gateway"] = gateway
            captured["embedding_model"] = model

    def fake_load_indexes(index_dir: Path, embeddings: object) -> object:
        captured["index_dir"] = index_dir
        captured["index_embeddings"] = embeddings
        return "indexes"

    def fake_build_graph(services: object, settings: Settings) -> object:
        captured["services"] = services
        captured["graph_settings"] = settings
        return "compiled-graph"

    def fake_validate_models(gateway: object, settings: Settings) -> None:
        captured["validated_gateway"] = gateway
        captured["validated_models"] = (
            settings.embedding_model,
            settings.rerank_model,
            settings.chat_model,
        )

    monkeypatch.setattr(runtime, "NebiusGateway", FakeGateway)
    monkeypatch.setattr(runtime, "NebiusEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(runtime, "load_indexes", fake_load_indexes)
    monkeypatch.setattr(runtime, "build_graph", fake_build_graph)
    monkeypatch.setattr(runtime, "validate_configured_models", fake_validate_models)
    settings = Settings(
        nebius_api_key="secret",
        embedding_model="embedding-model",
        rerank_model="rerank-model",
        chat_model="chat-model",
    )

    graph = runtime.create_runtime(settings)

    assert graph == "compiled-graph"
    assert captured["embedding_model"] == "embedding-model"
    services = captured["services"]
    assert services.settings.rerank_model == "rerank-model"
    assert services.settings.chat_model == "chat-model"
    assert captured["index_dir"] == runtime.INDEX_DIR
    assert captured["validated_models"] == (
        "embedding-model",
        "rerank-model",
        "chat-model",
    )


def test_runtime_cache_key_excludes_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    constructions = 0

    class FakeGateway:
        def __init__(self, settings: Settings) -> None:
            nonlocal constructions
            del settings
            constructions += 1

        def close(self) -> None:
            pass

    monkeypatch.setattr(runtime, "NebiusGateway", FakeGateway)
    monkeypatch.setattr(runtime, "NebiusEmbeddings", lambda **kwargs: kwargs)
    monkeypatch.setattr(runtime, "load_indexes", lambda *args: "indexes")
    monkeypatch.setattr(runtime, "build_graph", lambda *args: object())
    monkeypatch.setattr(runtime, "validate_configured_models", lambda *args: None)

    first = runtime.create_runtime(Settings(nebius_api_key="first-secret"))
    second = runtime.create_runtime(Settings(nebius_api_key="rotated-secret"))

    assert first is second
    assert constructions == 1
    assert all("first-secret" not in repr(key) for key in runtime.runtime_cache_keys())
    assert all("rotated-secret" not in repr(key) for key in runtime.runtime_cache_keys())


def test_missing_index_returns_exact_ingestion_instruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runtime, "INDEX_DIR", tmp_path / "missing-index")

    with pytest.raises(IndexNotReadyError) as caught:
        runtime.create_runtime(Settings(nebius_api_key="offline"))

    assert INDEX_INSTRUCTION in str(caught.value)


def test_evaluator_uses_the_shared_runtime_factory() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py").read_text(
        encoding="utf-8"
    )

    assert "from northstar_rag.runtime import create_runtime" in source
    assert "graph = create_runtime(settings)" in source
