"""
Jade's AI Humanizer Bridge for AVA Playground Mode.
Interfaces with the pip-installed jades-ai-humanizer package (with fallback to internal engine),
handling tone presets, reading levels, inline citation protection, and transformation metrics.
"""

from typing import Optional, Dict, Any
from core.logger import get_logger

logger = get_logger("playground.humanizer")

# Import from installed package or internal module
try:
    from humanizer import Humanizer
    logger.info("Loaded Jade's AI Humanizer from installed package.")
except ImportError:
    from core.humanizer import Humanizer
    logger.info("Loaded Jade's AI Humanizer from core.humanizer.")


class PlaygroundHumanizerBridge:
    """Manages text humanization and tone tuning for section drafts."""

    TONES = ["academic", "casual", "neutral", "professional"]
    LEVELS = ["high_school", "college", "middle_school", "general"]
    MODES = ["budget", "deep"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.5-flash-lite",
        fallback_model: str = "gemini-3.1-flash-lite",
        default_tone: str = "academic",
        default_level: str = "college",
        default_mode: str = "budget",
    ):
        self.api_key = api_key or ""
        self.model_name = model_name
        self.fallback_model = fallback_model
        self.default_tone = default_tone if default_tone.lower() in self.TONES else "academic"
        self.default_level = default_level if default_level.lower() in self.LEVELS else "college"
        self.default_mode = default_mode if default_mode.lower() in self.MODES else "budget"

        self._client: Optional[Humanizer] = None
        self._init_client()

    def _init_client(self):
        try:
            self._client = Humanizer(
                api_key=self.api_key if self.api_key else None,
                model=self.model_name,
                fallback_model=self.fallback_model,
                mock_mode=not bool(self.api_key),
            )
        except Exception as e:
            logger.warning(f"Could not initialize Humanizer client: {e}")
            try:
                self._client = Humanizer(mock_mode=True)
            except Exception:
                self._client = None

    def update_config(self, api_key: str, model_name: Optional[str] = None):
        self.api_key = api_key
        if model_name:
            self.model_name = model_name
        self._init_client()

    def humanize_text(
        self,
        text: str,
        tone: Optional[str] = None,
        level: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes humanization on the input text.
        Returns a dict with: 'humanized_text', 'original_text', 'word_count', 'is_offline', 'status'.
        """
        if not text or not text.strip():
            return {
                "humanized_text": "",
                "original_text": "",
                "word_count": 0,
                "is_offline": True,
                "status": "empty",
            }

        target_tone = (tone or self.default_tone).lower()
        if target_tone not in self.TONES:
            target_tone = "academic"

        target_level = (level or self.default_level).lower()
        if target_level not in self.LEVELS:
            target_level = "college"

        target_mode = (mode or self.default_mode).lower()
        if target_mode not in self.MODES:
            target_mode = "budget"

        if not self._client:
            self._init_client()

        if not self._client:
            return {
                "humanized_text": text,
                "original_text": text,
                "word_count": len(text.split()),
                "is_offline": True,
                "status": "fallback_client_unavailable",
            }

        try:
            result = self._client.humanize(
                text=text,
                mode=target_mode,
                tone=target_tone,
                reading_level=target_level,
                preserve_markdown=True,
            )
            return {
                "humanized_text": result.text,
                "original_text": text,
                "word_count": len(result.text.split()),
                "is_offline": getattr(result, "is_offline", False),
                "status": "success",
            }
        except Exception as e:
            logger.error(f"Error during humanization: {e}")
            return {
                "humanized_text": text,
                "original_text": text,
                "word_count": len(text.split()),
                "is_offline": True,
                "status": f"error: {e}",
            }
