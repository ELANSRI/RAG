"""Semantic embeddings (bonus): a dense vector index next to BM25.

Chunks and queries are embedded with a small CPU-friendly sentence
encoder (all-MiniLM-L6-v2 by default): token embeddings are mean-pooled
over the attention mask and L2-normalized, so the cosine similarity of a
query and a chunk is a plain dot product.
"""

import json
from pathlib import Path
from typing import Any, List, Optional, Sequence

import numpy as np
from tqdm import tqdm

DEFAULT_ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_FILE = "vectors.npy"
ENCODER_FILE = "encoder.json"


class MeanPoolEncoder:
    """Mean-pooled, normalized sentence embeddings from a transformer."""

    def __init__(
        self,
        encoder_name: str = DEFAULT_ENCODER,
        max_length: int = 256,
        device: Optional[str] = None,
    ) -> None:
        """Load the encoder.

        Args:
            encoder_name: Hugging Face id of the encoder.
            max_length: Inputs are truncated to this many tokens.
            device: Torch device; the CPU is used when omitted.
        """
        from transformers import AutoModel, AutoTokenizer

        self.encoder_name = encoder_name
        self.max_length = max_length
        self.device = device or "cpu"
        self._tokenizer: Any = AutoTokenizer.from_pretrained(encoder_name)
        self._model: Any = AutoModel.from_pretrained(encoder_name)
        self._model.to(self.device)
        self._model.eval()

    def encode(
        self,
        texts: Sequence[str],
        batch_size: int = 64,
        progress: bool = False,
    ) -> np.ndarray:
        """Embed texts.

        Args:
            texts: Texts to embed.
            batch_size: Number of texts per forward pass.
            progress: Show a progress bar.

        Returns:
            A float32 array of shape (len(texts), dim), rows of norm 1.
        """
        import torch

        encoded_batches: List[np.ndarray] = []
        batch_offsets = range(0, len(texts), batch_size)
        for start in tqdm(
            batch_offsets,
            desc="Embedding chunks",
            unit="batch",
            disable=not progress,
        ):
            encoded = self._tokenizer(
                list(texts[start: start + batch_size]),
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                token_states = self._model(**encoded).last_hidden_state
            attention_weights = (
                encoded["attention_mask"].unsqueeze(-1).to(token_states.dtype)
            )
            sentence_vectors = (token_states * attention_weights).sum(
                dim=1
            ) / attention_weights.sum(dim=1).clamp(min=1e-9)
            sentence_vectors = torch.nn.functional.normalize(
                sentence_vectors, dim=1
            )
            encoded_batches.append(
                sentence_vectors.cpu().numpy().astype(np.float32)
            )
        if not encoded_batches:
            return np.zeros((0, 0), dtype=np.float32)
        return np.concatenate(encoded_batches)


class VectorCatalog:
    """Dense representations of every chunk, aligned with the chunk table."""

    def __init__(self, representations: np.ndarray, encoder_name: str) -> None:
        """Wrap precomputed chunk representations.

        Args:
            representations: (n_chunks, dim) normalized embeddings.
            encoder_name: Encoder that produced them (reused for queries).
        """
        self.representations = representations
        self.encoder_name = encoder_name
        self._query_encoder: Optional[MeanPoolEncoder] = None

    @classmethod
    def build(
        cls,
        texts: Sequence[str],
        encoder_name: str = DEFAULT_ENCODER,
        batch_size: int = 64,
    ) -> "VectorCatalog":
        """Embed every chunk text.

        Args:
            texts: One text per chunk, in chunk-table order.
            encoder_name: Hugging Face id of the encoder.
            batch_size: Number of chunks per forward pass.

        Returns:
            The built index.
        """
        encoder = MeanPoolEncoder(encoder_name)
        index = cls(
            encoder.encode(texts, batch_size, progress=True), encoder_name
        )
        index._query_encoder = encoder
        return index

    def score(self, query: str) -> np.ndarray:
        """Return the cosine similarity of ``query`` with every chunk."""
        if self._query_encoder is None:
            self._query_encoder = MeanPoolEncoder(self.encoder_name)
        question_vector = self._query_encoder.encode([query])[0]
        return np.asarray(
            self.representations @ question_vector, dtype=np.float32
        )

    def save(self, directory: Path) -> None:
        """Write the representations and the encoder name into
        ``directory``."""
        directory.mkdir(parents=True, exist_ok=True)
        np.save(
            directory / VECTOR_FILE, self.representations.astype(np.float16)
        )
        with open(directory / ENCODER_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "encoder_name": self.encoder_name,
                    "shape": list(self.representations.shape),
                },
                fh,
            )

    @staticmethod
    def exists(directory: Path) -> bool:
        """Tell whether a semantic index was saved in ``directory``."""
        return (directory / VECTOR_FILE).is_file() and (
            directory / ENCODER_FILE
        ).is_file()

    @classmethod
    def load(cls, directory: Path) -> "VectorCatalog":
        """Read an index written by :meth:`save`."""
        with open(directory / ENCODER_FILE, encoding="utf-8") as fh:
            meta = json.load(fh)
        representations = np.load(directory / VECTOR_FILE).astype(np.float32)
        return cls(representations, str(meta["encoder_name"]))
