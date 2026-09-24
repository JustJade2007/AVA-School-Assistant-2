"""Jade's AI Humanizer - Zero-Backend Client-Side Text Humanizer & REST Daemon."""

from core.humanizer.client import Humanizer
from core.humanizer.models import (
    HumanizeResult,
    ModePreset,
    ReadingLevelPreset,
    TonePreset,
    UsageMetadata,
)
from core.humanizer.parser import DocumentChunk, InlineMasker, MarkdownDocument

__version__ = "0.1.0"

__all__ = [
    "Humanizer",
    "HumanizeResult",
    "UsageMetadata",
    "TonePreset",
    "ReadingLevelPreset",
    "ModePreset",
    "MarkdownDocument",
    "DocumentChunk",
    "InlineMasker",
    "__version__",
]
