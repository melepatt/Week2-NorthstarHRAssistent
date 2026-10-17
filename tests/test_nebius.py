from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from northstar_rag.config import Settings
from northstar_rag.nebius import (
    ModelUnavailableError,
    NebiusGateway,
    NebiusHTTPError,
    NebiusResponseError,
    validate_configured_models,
)


def settings(api_key: str = "test-nebius-key") -> Settings:
    return Settings.from_env({"NEBIUS_API_KEY": api_key})


def gateway_for(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    sleeper: Callable[[float], None] = lambda _: None,
    api_key: str = "test-nebius-key",
) -> NebiusGateway:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NebiusGateway(settings(api_key), client=client, sleeper=sleeper)


def test_gateway_uses_official_endpoints_payloads_and_response_order() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-nebius-key"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "chat"}, {"id": "embed"}]})
        payload = json.loads(request.content)
        if request.url.path == "/v1/embeddings":
            if payload["input"] == ["first", "second"]:
                assert payload == {
                    "model": "embed",
                    "input": ["first", "second"],
                    "encoding_format": "float",
                }
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 1, "embedding": [2.0, 2.5]},
                            {"index": 0, "embedding": [1.0, 1.5]},
                        ]
                    },
                )
            assert payload == {
                "model": "embed",
                "input": ["leave policy", "document zero", "document one"],
                "encoding_format": "float",
            }
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 2, "embedding": [0.0, 1.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                        {"index": 1, "embedding": [1.0, 0.0]},
                    ]
                },
            )
        if request.url.path == "/v1/chat/completions":
            assert payload == {
                "model": "chat",
                "messages": [
                    {"role": "system", "content": "Use policy evidence only."},
                    {"role": "user", "content": "Question and selected evidence"},
                ],
                "temperature": 0,
            }
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Grounded answer"}}]},
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    gateway = gateway_for(handler)

    assert gateway.list_models() == {"chat", "embed"}
    assert gateway.embed(["first", "second"], "embed") == [[1.0, 1.5], [2.0, 2.5]]
    assert gateway.rerank("leave policy", ["document zero", "document one"], "embed") == [
        1.0,
        0.5,
    ]
    assert (
        gateway.complete(
            "Use policy evidence only.",
            "Question and selected evidence",
            "chat",
        )
        == "Grounded answer"
    )
    assert [request.method for request in requests] == ["GET", "POST", "POST", "POST"]


@pytest.mark.parametrize("failure", ["timeout", "429", "503"])
def test_retryable_failures_use_two_bounded_retries(failure: str) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            if failure == "timeout":
                raise httpx.ReadTimeout("timed out", request=request)
            return httpx.Response(int(failure), json={"error": "temporary"})
        return httpx.Response(200, json={"data": [{"id": "available"}]})

    gateway = gateway_for(handler, sleeper=sleeps.append)

    assert gateway.list_models() == {"available"}
    assert attempts == 3
    assert sleeps == [0.5, 1.0]


@pytest.mark.parametrize("status_code", [400, 401])
def test_permanent_client_errors_are_not_retried(status_code: int) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, json={"error": "permanent"})

    gateway = gateway_for(handler)

    with pytest.raises(NebiusHTTPError, match=str(status_code)):
        gateway.list_models()
    assert attempts == 1


def test_malformed_json_is_rejected() -> None:
    gateway = gateway_for(
        lambda _: httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
    )

    with pytest.raises(NebiusResponseError, match="invalid JSON"):
        gateway.list_models()


def test_model_validation_lists_unavailable_models_and_environment_names() -> None:
    configured = Settings.from_env(
        {
            "NEBIUS_API_KEY": "test-nebius-key",
            "NEBIUS_RERANK_MODEL": "missing-reranker",
            "NEBIUS_CHAT_MODEL": "missing-chat",
        }
    )
    gateway = gateway_for(
        lambda _: httpx.Response(200, json={"data": [{"id": configured.embedding_model}]})
    )

    with pytest.raises(ModelUnavailableError) as caught:
        validate_configured_models(gateway, configured)

    message = str(caught.value)
    assert configured.rerank_model in message
    assert configured.chat_model in message
    assert "NEBIUS_RERANK_MODEL" in message
    assert "NEBIUS_CHAT_MODEL" in message


def test_errors_never_expose_api_key_even_when_server_echoes_it() -> None:
    secret = "nebius-super-secret"
    gateway = gateway_for(
        lambda _: httpx.Response(401, json={"error": f"invalid token {secret}"}),
        api_key=secret,
    )

    with pytest.raises(NebiusHTTPError) as caught:
        gateway.list_models()

    assert secret not in str(caught.value)
