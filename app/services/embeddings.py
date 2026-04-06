from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import hashlib
import logging
import math
import re
import threading
import time
from typing import Any

import httpx

from app.config import Settings


TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+'-]{1,}")
SIGNATURE_COMPONENT_PATTERN = re.compile(r"[^a-z0-9._-]+")


logger = logging.getLogger(__name__)


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def build_hash_embedding(text: str, dimensions: int = 256) -> list[float]:
    vector = [0.0] * dimensions
    token_counts = Counter(tokenize(text))
    if not token_counts:
        return vector

    for token, count in token_counts.items():
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += count * sign

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def hash_embedding_signature(dimensions: int = 256) -> str:
    return f"hash:{dimensions}"


def normalize_embedding(vector: list[float]) -> list[float]:
    if not vector:
        return []
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


@dataclass(frozen=True)
class EmbeddingRecord:
    vector: list[float]
    signature: str


@dataclass(frozen=True)
class EmbeddingCallMetrics:
    duration_ms: float
    cache_hit: bool


@dataclass
class _CacheEntry:
    value: EmbeddingRecord
    expires_at: float


class _LocalEmbeddingCache:
    def __init__(self, ttl_seconds: int, max_entries: int) -> None:
        self.ttl_seconds = max(ttl_seconds, 0)
        self.max_entries = max(max_entries, 1)
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> EmbeddingRecord | None:
        if self.ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: str, value: EmbeddingRecord) -> None:
        if self.ttl_seconds <= 0:
            return
        now = time.monotonic()
        with self._lock:
            self._entries[key] = _CacheEntry(value=value, expires_at=now + self.ttl_seconds)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)


class SemanticEmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._query_cache = _LocalEmbeddingCache(
            ttl_seconds=settings.llm_cache_ttl_seconds,
            max_entries=settings.llm_cache_max_entries,
        )

    def is_enabled(self) -> bool:
        provider = self.settings.embedding_provider.strip().lower().replace("-", "_")
        return provider not in {"", "none", "hash", "local"} and bool(self.settings.embedding_model)

    def current_signature(self) -> str:
        if not self.is_enabled():
            return ""
        provider = self.settings.embedding_provider.strip().lower().replace("-", "_")
        model = (self.settings.embedding_model or "model").strip().lower()
        sanitized_model = SIGNATURE_COMPONENT_PATTERN.sub("_", model).strip("._-")[:48] or "model"
        digest = hashlib.sha1(
            f"{provider}|{self.settings.embedding_base_url.rstrip('/')}|{self.settings.embedding_model}".encode("utf-8")
        ).hexdigest()[:12]
        return f"{provider}:{sanitized_model}:{digest}"

    def warmup(self) -> float | None:
        provider = self.settings.embedding_provider.strip().lower().replace("-", "_")
        if provider != "ollama" or not self.is_enabled():
            return None
        _embedding, metrics = self.embed_query_with_metadata("singapore anime games warmup")
        return metrics.duration_ms

    def embed_documents(self, texts: list[str]) -> list[EmbeddingRecord]:
        return self._embed_texts(texts, reason="document")

    def embed_query(self, text: str) -> EmbeddingRecord | None:
        embedding, _metrics = self.embed_query_with_metadata(text)
        return embedding

    def embed_query_with_metadata(self, text: str) -> tuple[EmbeddingRecord | None, EmbeddingCallMetrics]:
        started_at = time.perf_counter()
        if not self.is_enabled():
            return None, EmbeddingCallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        cache_key = self._cache_key(text)
        cached = self._query_cache.get(cache_key)
        if cached is not None:
            return cached, EmbeddingCallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=True)

        embeddings = self._embed_texts([text], reason="query")
        if not embeddings:
            return None, EmbeddingCallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        embedding = embeddings[0]
        self._query_cache.set(cache_key, embedding)
        return embedding, EmbeddingCallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

    def _embed_texts(self, texts: list[str], reason: str) -> list[EmbeddingRecord]:
        if not texts or not self.is_enabled():
            return []

        batch_size = max(self.settings.embedding_batch_size, 1)
        vectors: list[list[float]] = []
        try:
            for index in range(0, len(texts), batch_size):
                vectors.extend(self._request_embeddings(texts[index : index + batch_size]))
        except Exception as exc:
            logger.warning("Semantic %s embeddings failed; semantic vector retrieval is unavailable.", reason, exc_info=exc)
            return []

        signature = self.current_signature()
        return [EmbeddingRecord(vector=normalize_embedding(vector), signature=signature) for vector in vectors]

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        provider = self.settings.embedding_provider.strip().lower().replace("-", "_")
        if provider == "ollama":
            return self._request_ollama_embeddings(texts)
        if provider in {"openai", "openai_compatible"}:
            return self._request_openai_embeddings(texts)
        raise ValueError(f"Unsupported embedding provider: {self.settings.embedding_provider}")

    def _request_openai_embeddings(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.settings.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.settings.embedding_api_key}"
        response = httpx.post(
            self._resolve_embeddings_url(),
            headers=headers,
            json={
                "model": self.settings.embedding_model,
                "input": texts,
            },
            timeout=self.settings.embedding_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        ordered_items = sorted(
            [item for item in data if isinstance(item, dict)],
            key=lambda item: int(item.get("index", 0)),
        )
        vectors = [self._coerce_embedding(item.get("embedding")) for item in ordered_items]
        if len(vectors) != len(texts):
            raise ValueError("Embedding response count did not match request count")
        return vectors

    def _request_ollama_embeddings(self, texts: list[str]) -> list[list[float]]:
        base_url = self.settings.embedding_base_url.rstrip("/")
        response = httpx.post(
            f"{base_url}/api/embed",
            json={"model": self.settings.embedding_model, "input": texts},
            timeout=self.settings.embedding_timeout_seconds,
        )
        if response.status_code == 404:
            return self._request_legacy_ollama_embeddings(texts)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload.get("embeddings"), list):
            vectors = [self._coerce_embedding(item) for item in payload["embeddings"]]
            if len(vectors) != len(texts):
                raise ValueError("Ollama embedding response count did not match request count")
            return vectors
        if isinstance(payload.get("embedding"), list):
            return [self._coerce_embedding(payload["embedding"])]
        raise ValueError("Unexpected Ollama embedding response payload")

    def _request_legacy_ollama_embeddings(self, texts: list[str]) -> list[list[float]]:
        base_url = self.settings.embedding_base_url.rstrip("/")
        vectors: list[list[float]] = []
        for text in texts:
            response = httpx.post(
                f"{base_url}/api/embeddings",
                json={"model": self.settings.embedding_model, "prompt": text},
                timeout=self.settings.embedding_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            vectors.append(self._coerce_embedding(payload.get("embedding")))
        return vectors

    def _resolve_embeddings_url(self) -> str:
        base_url = self.settings.embedding_base_url.rstrip("/")
        if base_url.endswith("/embeddings"):
            return base_url
        if base_url.endswith("/v1"):
            return f"{base_url}/embeddings"
        return f"{base_url}/v1/embeddings"

    def _coerce_embedding(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            raise ValueError("Embedding payload was not a list")
        return [float(item) for item in value]

    def _cache_key(self, text: str) -> str:
        normalized = " ".join(text.split())
        return f"{self.current_signature()}:{hashlib.sha1(normalized.encode('utf-8')).hexdigest()}"


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 1)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))
