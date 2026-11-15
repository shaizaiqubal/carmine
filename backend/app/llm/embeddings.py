from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Callable

from ..db import Database
from .configuration import LLMConfig


class EmbeddingModelMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    revision: str
    dim: int
    cache_hits: list[bool]


class EmbeddingEngine:
    def __init__(self, db: Database, config: LLMConfig | None = None, model: Any | None = None):
        self.db = db
        self.config = config or LLMConfig.load()
        self._model = model

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.config.embedding_model, revision=self.config.embedding_revision, device="cpu")
        return self._model

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def embed(self, texts: list[str], startup_id: str | None = None) -> EmbeddingResult:
        vectors: list[list[float] | None] = [None] * len(texts)
        hits = [False] * len(texts)
        missing: list[tuple[int, str, str]] = []
        for index, text in enumerate(texts):
            content_hash = self._hash(text)
            row = self.db.execute(
                "SELECT vector_json FROM embeddings WHERE content_hash = ? AND model = ? AND revision = ? AND dim = ? AND startup_id IS ? LIMIT 1",
                (content_hash, self.config.embedding_model, self.config.embedding_revision, self.config.embedding_dim, startup_id),
            ).fetchone()
            if row:
                vectors[index] = json.loads(row[0])
                hits[index] = True
            else:
                missing.append((index, text, content_hash))
        if missing:
            encoded = self.model.encode([item[1] for item in missing], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            for (index, _, content_hash), vector in zip(missing, encoded):
                raw_values = vector.tolist() if hasattr(vector, "tolist") else vector
                values = [float(value) for value in raw_values]
                if len(values) != self.config.embedding_dim:
                    raise ValueError(f"embedding dimension {len(values)} does not match configured {self.config.embedding_dim}")
                vectors[index] = values
                self.db.execute(
                    "INSERT INTO embeddings (id, startup_id, content_hash, model, revision, dim, vector_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (__import__("uuid").uuid4().hex, startup_id, content_hash, self.config.embedding_model, self.config.embedding_revision, self.config.embedding_dim, json.dumps(values, separators=(",", ":"))),
                )
            self.db.commit()
        return EmbeddingResult([vector for vector in vectors if vector is not None], self.config.embedding_model, self.config.embedding_revision, self.config.embedding_dim, hits)


def compare_vectors(left: EmbeddingResult, right: EmbeddingResult) -> float:
    if (left.model, left.revision, left.dim) != (right.model, right.revision, right.dim):
        raise EmbeddingModelMismatchError("cannot compare embeddings from different model/revision/dimension")
    if len(left.vectors) != 1 or len(right.vectors) != 1:
        raise ValueError("compare_vectors expects one vector per result")
    a, b = left.vectors[0], right.vectors[0]
    return sum(x * y for x, y in zip(a, b)) / max(math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)), 1e-12)
