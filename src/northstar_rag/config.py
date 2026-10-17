from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"
DEFAULT_RERANK_MODEL = DEFAULT_EMBEDDING_MODEL
DEFAULT_CHAT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
DEFAULT_RERANK_MIN_SCORE = 0.802


class ConfigurationError(ValueError):
    """Raised when the operator configuration is missing or unsafe."""


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required and must not be blank")
    return value


def _text(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name, default).strip()
    if not value:
        raise ConfigurationError(f"{name} must not be blank")
    return value


def _integer(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    raw = values.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{name} must be an integer") from error
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise ConfigurationError(f"{name} must be {bounds}")
    return value


def _number(
    values: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float | None = None,
    inclusive_minimum: bool = True,
) -> float:
    raw = values.get(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{name} must be a number") from error
    below_minimum = value < minimum if inclusive_minimum else value <= minimum
    if below_minimum or (maximum is not None and value > maximum):
        if maximum is None:
            comparator = "at least" if inclusive_minimum else "greater than"
            constraint = f"{comparator} {minimum}"
        else:
            constraint = f"between {minimum} and {maximum}"
        raise ConfigurationError(f"{name} must be {constraint}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    nebius_api_key: str
    nebius_base_url: str = DEFAULT_BASE_URL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    rerank_model: str = DEFAULT_RERANK_MODEL
    chat_model: str = DEFAULT_CHAT_MODEL
    dense_k: int = 8
    lexical_k: int = 8
    fusion_k: int = 60
    rerank_candidates: int = 10
    evidence_k: int = 4
    rerank_min_score: float = DEFAULT_RERANK_MIN_SCORE
    request_timeout_seconds: float = 30.0
    max_retries: int = 2
    backoff_base_seconds: float = 0.5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        return cls(
            nebius_api_key=_required(values, "NEBIUS_API_KEY"),
            nebius_base_url=_text(values, "NEBIUS_BASE_URL", DEFAULT_BASE_URL),
            embedding_model=_text(values, "NEBIUS_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            rerank_model=_text(values, "NEBIUS_RERANK_MODEL", DEFAULT_RERANK_MODEL),
            chat_model=_text(values, "NEBIUS_CHAT_MODEL", DEFAULT_CHAT_MODEL),
            dense_k=_integer(values, "DENSE_K", 8, minimum=1),
            lexical_k=_integer(values, "LEXICAL_K", 8, minimum=1),
            fusion_k=_integer(values, "FUSION_K", 60, minimum=1),
            rerank_candidates=_integer(values, "RERANK_CANDIDATES", 10, minimum=1),
            evidence_k=_integer(values, "EVIDENCE_K", 4, minimum=1),
            rerank_min_score=_number(
                values,
                "RERANK_MIN_SCORE",
                DEFAULT_RERANK_MIN_SCORE,
                minimum=0.0,
                maximum=1.0,
            ),
            request_timeout_seconds=_number(
                values,
                "NEBIUS_REQUEST_TIMEOUT_SECONDS",
                30.0,
                minimum=0.0,
                inclusive_minimum=False,
            ),
            max_retries=_integer(values, "NEBIUS_MAX_RETRIES", 2, minimum=0, maximum=2),
            backoff_base_seconds=_number(
                values,
                "NEBIUS_BACKOFF_BASE_SECONDS",
                0.5,
                minimum=0.0,
                inclusive_minimum=False,
            ),
        )
