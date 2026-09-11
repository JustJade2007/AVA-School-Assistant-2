"""Data contracts, models, and type definitions for Jade's AI Humanizer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TonePreset = Literal["neutral", "casual", "academic", "professional"]
ReadingLevelPreset = Literal["middle_school", "high_school", "college", "general"]
ModePreset = Literal["budget", "deep"]


@dataclass
class UsageMetadata:
    """Token usage metadata for a humanization request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_overhead_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class HumanizeResult:
    """Core result contract conforming to PROJECT.md § Interface Contracts.

    Attributes:
        text: The final humanized text after guardrails and sanitization.
        original_text: The original unmodified input text.
        mode: Humanization mode used ('budget' or 'deep').
        tone: Tone preset applied ('neutral', 'casual', 'academic', 'professional').
        reading_level: Reading level preset applied ('general', 'middle_school', etc.).
        prompt_tokens: Number of prompt tokens evaluated.
        completion_tokens: Number of completion tokens generated.
        total_tokens: Sum of prompt and completion tokens.
        buzzwords_replaced: List of AI buzzwords detected and replaced by guardrails.
        flesch_reading_ease: Flesch Reading Ease readability score (0.0 - 100.0+).
        flesch_kincaid_grade: Optional Flesch-Kincaid Grade Level score.
        grammar_repaired: Whether automated grammar/syntax repair was performed.
    """

    text: str
    original_text: str
    mode: str
    tone: str
    reading_level: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    buzzwords_replaced: list[str] = field(default_factory=list)
    flesch_reading_ease: float = 0.0
    flesch_kincaid_grade: float = 0.0
    grammar_repaired: bool = False
    is_offline: bool = False
    engine: str = "offline"
    api_tokens_used: int = 0

    @property
    def humanized_text(self) -> str:
        return self.text

    @property
    def success(self) -> bool:
        return bool(self.text)

    def __str__(self) -> str:
        return self.text

    def to_dict(self) -> dict[str, Any]:
        """Convert the result into a standard serializable dictionary."""
        return asdict(self)
