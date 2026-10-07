"""Lazy local inference with Qwen; no weights are needed for search."""

import re
from typing import Any, Sequence

from src.documents.files import PassageReader
from src.domain.contracts import MinimalSource
from .context import ContextComposer

DEFAULT_MODEL = "Qwen/Qwen3-0.6B"
NO_EVIDENCE = "I could not find sufficient evidence in the retrieved sources."


class LocalResponder:
    """Own one model instance for single or batch answer generation."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        context_budget: int = 3000,
        response_limit: int = 256,
        device: str | None = None,
    ) -> None:
        """Record settings without importing the deep-learning stack."""
        if context_budget < 1 or response_limit < 1:
            raise ValueError("token limits must be positive")
        self.model_id = model_id
        self.context_budget = context_budget
        self.response_limit = response_limit
        self.device = device
        self.tokenizer: Any = None
        self.network: Any = None
        self.reader = PassageReader()

    def load(self) -> None:
        """Load the tokenizer and weights only when evidence is available."""
        if self.network is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if self.device is None:
            self.device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps" if torch.backends.mps.is_available() else "cpu"
            )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.network = AutoModelForCausalLM.from_pretrained(self.model_id)
        self.network.to(self.device)
        self.network.eval()

    def respond(
        self, question_text: str, sources: Sequence[MinimalSource]
    ) -> str:
        """Generate only new tokens after a fully budgeted evidence prompt."""
        if not sources:
            return NO_EVIDENCE
        self.load()
        composer = ContextComposer(self.tokenizer, self.reader)
        window = int(self.network.config.max_position_embeddings)
        prompt = composer.compose(
            question_text,
            sources,
            self.context_budget,
            window - self.response_limit,
        )
        if prompt is None:
            return NO_EVIDENCE
        import torch

        encoded = self.tokenizer(
            prompt, return_tensors="pt", add_special_tokens=False
        ).to(self.device)
        with torch.inference_mode():
            completion = self.network.generate(
                **encoded,
                max_new_tokens=self.response_limit,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id
            )
        prefix_length = encoded["input_ids"].shape[1]
        generated = completion[0][prefix_length:]
        wording = str(
            self.tokenizer.decode(generated, skip_special_tokens=True)
        )
        cleaned = re.sub(
            r"<think>.*?(</think>|$)", "", wording, flags=re.DOTALL
        ).strip()
        return cleaned or NO_EVIDENCE
