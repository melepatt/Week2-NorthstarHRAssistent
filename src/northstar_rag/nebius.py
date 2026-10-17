from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from northstar_rag.config import Settings


class NebiusError(RuntimeError):
    """Base class for sanitized Nebius service failures."""


class NebiusHTTPError(NebiusError):
    """A permanent HTTP response from Nebius."""


class NebiusUnavailableError(NebiusError):
    """A transient Nebius failure that exhausted bounded retries."""


class NebiusResponseError(NebiusError):
    """A successful response whose shape is unsafe to consume."""


class ModelUnavailableError(NebiusError):
    """One or more configured model IDs are not available."""


class NebiusGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sleeper = sleeper
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _url(self, path: str) -> str:
        return f"{self._settings.nebius_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._settings.nebius_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        attempts = self._settings.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._client.request(
                    method,
                    self._url(path),
                    headers=headers,
                    json=payload,
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt >= self._settings.max_retries:
                    raise NebiusUnavailableError(
                        f"Nebius request to {path} timed out after {attempts} attempts"
                    ) from error
                self._sleep_before_retry(attempt)
                continue

            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt >= self._settings.max_retries:
                    raise NebiusUnavailableError(
                        f"Nebius request to {path} remained unavailable after {attempts} attempts"
                    )
                self._sleep_before_retry(attempt)
                continue
            if response.is_error:
                raise NebiusHTTPError(
                    f"Nebius request to {path} failed with status {response.status_code}"
                )
            try:
                body = response.json()
            except (json.JSONDecodeError, ValueError) as error:
                message = f"Nebius response from {path} contained invalid JSON"
                raise NebiusResponseError(message) from error
            if not isinstance(body, dict):
                raise NebiusResponseError(f"Nebius response from {path} must be a JSON object")
            return body
        raise AssertionError("unreachable retry state")

    def _sleep_before_retry(self, attempt: int) -> None:
        self._sleeper(self._settings.backoff_base_seconds * (2**attempt))

    def list_models(self) -> set[str]:
        body = self._request("GET", "models")
        data = body.get("data")
        if not isinstance(data, list):
            raise NebiusResponseError("Nebius models response is missing data")
        model_ids: set[str] = set()
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise NebiusResponseError("Nebius models response contains an invalid model")
            model_ids.add(item["id"])
        return model_ids

    def embed(self, texts: Sequence[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        body = self._request(
            "POST",
            "embeddings",
            payload={"model": model, "input": list(texts), "encoding_format": "float"},
        )
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise NebiusResponseError("Nebius embeddings response has the wrong item count")
        ordered: list[list[float] | None] = [None] * len(texts)
        for item in data:
            if not isinstance(item, dict):
                raise NebiusResponseError("Nebius embeddings response contains an invalid item")
            index = item.get("index")
            embedding = item.get("embedding")
            if (
                not isinstance(index, int)
                or index < 0
                or index >= len(texts)
                or ordered[index] is not None
                or not isinstance(embedding, list)
                or not embedding
                or any(not isinstance(value, int | float) for value in embedding)
            ):
                raise NebiusResponseError(
                    "Nebius embeddings response has invalid indices or vectors"
                )
            vector = [float(value) for value in embedding]
            if any(not math.isfinite(value) for value in vector):
                raise NebiusResponseError("Nebius embeddings response contains a non-finite value")
            ordered[index] = vector
        if any(vector is None for vector in ordered):
            raise NebiusResponseError("Nebius embeddings response is missing an index")
        return [vector for vector in ordered if vector is not None]

    def rerank(self, query: str, documents: Sequence[str], model: str) -> list[float]:
        if not documents:
            return []
        vectors = self.embed([query, *documents], model)
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise NebiusResponseError("Nebius rerank embeddings have inconsistent dimensions")

        query_vector, *document_vectors = vectors
        query_norm = math.sqrt(math.fsum(value * value for value in query_vector))
        if query_norm == 0:
            raise NebiusResponseError("Nebius rerank embedding has zero magnitude")

        scores: list[float] = []
        for document_vector in document_vectors:
            document_norm = math.sqrt(math.fsum(value * value for value in document_vector))
            if document_norm == 0:
                raise NebiusResponseError("Nebius rerank embedding has zero magnitude")
            cosine = math.fsum(
                query_value * document_value
                for query_value, document_value in zip(
                    query_vector,
                    document_vector,
                    strict=True,
                )
            ) / (query_norm * document_norm)
            scores.append(min(1.0, max(0.0, (cosine + 1.0) / 2.0)))
        return scores

    def complete(self, system: str, user: str, model: str) -> str:
        body = self._request(
            "POST",
            "chat/completions",
            payload={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            },
        )
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise NebiusResponseError("Nebius chat response is missing message content") from error
        if not isinstance(content, str) or not content.strip():
            raise NebiusResponseError("Nebius chat response contains empty message content")
        return content.strip()


def validate_configured_models(gateway: NebiusGateway, settings: Settings) -> None:
    available = gateway.list_models()
    configured = {
        "NEBIUS_EMBEDDING_MODEL": settings.embedding_model,
        "NEBIUS_RERANK_MODEL": settings.rerank_model,
        "NEBIUS_CHAT_MODEL": settings.chat_model,
    }
    missing = [
        (environment_name, model)
        for environment_name, model in configured.items()
        if model not in available
    ]
    if missing:
        details = ", ".join(f"{environment_name}={model}" for environment_name, model in missing)
        raise ModelUnavailableError(f"Configured Nebius models are unavailable: {details}")
