"""Text embedding service for failure similarity search.

Supports multiple embedding backends:
- sentence-transformers (local, default)
- OpenAI embeddings API
- Simple TF-IDF fallback (no dependencies)
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingResult:
    """Result of text embedding."""
    text: str
    embedding: list[float]
    model: str
    dimensions: int


class EmbedderBackend(ABC):
    """Abstract embedder backend."""
    
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed text into a vector."""
        pass
    
    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        pass
    
    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return model name."""
        pass


class TFIDFEmbedder(EmbedderBackend):
    """Simple TF-IDF based embedder (no external dependencies).
    
    Uses a fixed vocabulary of common error patterns for embedding.
    Good for quick similarity without external dependencies.
    """
    
    # Common patterns in test failures
    VOCABULARY = [
        # Error types
        "timeoutexpirederror", "assertionerror", "keyerror", "typeerror",
        "valueerror", "attributeerror", "indexerror", "nameerror",
        "runtimeerror", "connectionerror", "httperror", "ioerror",
        
        # Kubernetes/infrastructure
        "crashloopbackoff", "imagepullbackoff", "oomkilled", "pending",
        "failed", "error", "timeout", "connection", "refused",
        "unauthorized", "forbidden", "notfound", "resourcenotfound",
        
        # Common patterns
        "pod", "container", "deployment", "service", "route",
        "namespace", "secret", "configmap", "pvc", "storage",
        "gpu", "cuda", "nvidia", "memory", "cpu", "quota",
        
        # Test patterns
        "assert", "expected", "actual", "mismatch", "wait",
        "retry", "flaky", "intermittent", "sleep", "fixture",
        
        # Model serving
        "inference", "model", "serving", "kserve", "modelmesh",
        "vllm", "tgis", "predictor", "transformer", "runtime",
        
        # External services
        "s3", "minio", "database", "mariadb", "postgres",
        "huggingface", "registry", "authentication", "token",
    ]
    
    def __init__(self):
        self._vocab_set = set(self.VOCABULARY)
        self._dimensions = len(self.VOCABULARY)
    
    def embed(self, text: str) -> list[float]:
        """Create TF-IDF-like embedding from text."""
        text_lower = text.lower()
        words = set(text_lower.split())
        
        # Count term frequency
        embedding = []
        for term in self.VOCABULARY:
            if term in text_lower:
                # Simple frequency-based weight
                count = text_lower.count(term)
                weight = min(1.0, count * 0.3)  # Cap at 1.0
                embedding.append(weight)
            else:
                embedding.append(0.0)
        
        # Normalize
        norm = sum(x**2 for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
    
    @property
    def dimensions(self) -> int:
        return self._dimensions
    
    @property
    def model_name(self) -> str:
        return "tfidf-failure-vocab"


class SentenceTransformerEmbedder(EmbedderBackend):
    """Sentence-transformers based embedder (requires sentence-transformers)."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None
        self._dimensions = 384  # Default for MiniLM
    
    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                self._dimensions = self._model.get_sentence_embedding_dimension()
                logger.info("sentence_transformer_loaded", model=self._model_name)
            except ImportError:
                logger.warning("sentence_transformers_not_available, falling back to TF-IDF")
                raise
        return self._model
    
    def embed(self, text: str) -> list[float]:
        model = self._get_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    @property
    def dimensions(self) -> int:
        return self._dimensions
    
    @property
    def model_name(self) -> str:
        return f"sentence-transformers/{self._model_name}"


class TextEmbedder:
    """Main text embedder with fallback support.
    
    Tries sentence-transformers first, falls back to TF-IDF if not available.
    """
    
    def __init__(self, backend: str = "auto"):
        """Initialize embedder.
        
        Args:
            backend: "auto", "sentence-transformers", or "tfidf"
        """
        self._backend: EmbedderBackend | None = None
        self._backend_type = backend
        self._cache: dict[str, list[float]] = {}
    
    def _get_backend(self) -> EmbedderBackend:
        if self._backend is None:
            if self._backend_type == "tfidf":
                self._backend = TFIDFEmbedder()
            elif self._backend_type == "sentence-transformers":
                self._backend = SentenceTransformerEmbedder()
            else:  # auto
                try:
                    backend = SentenceTransformerEmbedder()
                    backend.embed("test")
                    self._backend = backend
                except (ImportError, Exception) as e:
                    logger.info("falling_back_to_tfidf", reason=str(e))
                    self._backend = TFIDFEmbedder()
            
            logger.info("embedder_initialized", 
                        model=self._backend.model_name,
                        dimensions=self._backend.dimensions)
        
        return self._backend
    
    def embed(self, text: str, use_cache: bool = True) -> EmbeddingResult:
        """Embed text into a vector.
        
        Args:
            text: Text to embed
            use_cache: Whether to use cached embeddings
            
        Returns:
            EmbeddingResult with embedding vector
        """
        backend = self._get_backend()
        
        # Check cache
        cache_key = hashlib.md5(text[:500].encode()).hexdigest()
        if use_cache and cache_key in self._cache:
            embedding = self._cache[cache_key]
        else:
            embedding = backend.embed(text)
            if use_cache:
                self._cache[cache_key] = embedding
        
        return EmbeddingResult(
            text=text[:200],
            embedding=embedding,
            model=backend.model_name,
            dimensions=backend.dimensions,
        )
    
    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed multiple texts."""
        backend = self._get_backend()
        embeddings = backend.embed_batch(texts)
        
        return [
            EmbeddingResult(
                text=text[:200],
                embedding=emb,
                model=backend.model_name,
                dimensions=backend.dimensions,
            )
            for text, emb in zip(texts, embeddings)
        ]
    
    @property
    def dimensions(self) -> int:
        return self._get_backend().dimensions
    
    @property
    def model_name(self) -> str:
        return self._get_backend().model_name
    
    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x**2 for x in a) ** 0.5
        norm_b = sum(x**2 for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
