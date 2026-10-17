from __future__ import annotations

import hashlib
import re

from langchain_core.embeddings import Embeddings


class DeterministicEmbeddings(Embeddings):
    """Small, stable embedding model for offline index tests."""

    dimensions = 32

    @classmethod
    def _embed(cls, text: str) -> list[float]:
        vector = [0.0] * cls.dimensions
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % cls.dimensions
            vector[bucket] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
