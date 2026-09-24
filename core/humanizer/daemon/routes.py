"""REST and SSE route definitions for Jade's AI Humanizer daemon."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from core.humanizer.client import Humanizer
from core.humanizer.daemon.ui import INDEX_HTML
from core.humanizer.models import ModePreset, ReadingLevelPreset, TonePreset

router = APIRouter()


@router.get("/", response_class=HTMLResponse, summary="Web User Interface", include_in_schema=False)
def index_page() -> HTMLResponse:
    """Serve the interactive web interface."""
    return HTMLResponse(content=INDEX_HTML)


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Return a minimal SVG favicon."""
    svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✨</text></svg>"
    return Response(content=svg, media_type="image/svg+xml")


class HumanizeRequest(BaseModel):
    text: Optional[str] = Field(None, description="Text to humanize")
    mode: str = Field("budget", description="Humanization mode: 'budget' or 'deep'")
    tone: str = Field("neutral", description="Tone preset: 'neutral', 'casual', 'academic', 'professional'")
    reading_level: str = Field("general", description="Reading level: 'general', 'middle_school', 'high_school', 'college'")
    preserve_markdown: bool = Field(True, description="Preserve markdown structures intact")
    api_key: Optional[str] = Field(None, description="Optional Google Gemini API key")


class HumanizeResponse(BaseModel):
    humanized_text: str
    original_text: str
    mode: str
    tone: str
    reading_level: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    buzzwords_replaced: list[str]
    flesch_reading_ease: float
    is_offline: bool = Field(False, description="Whether humanization ran in offline deterministic mode")
    engine: str = Field("offline", description="Engine used")
    api_tokens_used: int = Field(0, description="Actual API tokens billed/used (0 if offline)")


def get_client(api_key: Optional[str] = None) -> Humanizer:
    mock_mode = os.getenv("HUMANIZER_MOCK_MODE", "").lower() in ("1", "true", "yes")
    clean_key = api_key.strip() if api_key and api_key.strip() else None
    return Humanizer(api_key=clean_key, mock_mode=mock_mode)


@router.get("/health", summary="Daemon Health Check")
def health_check(api_key: Optional[str] = Query(None)) -> dict[str, Any]:
    """Check health and configuration status of the local humanizer daemon."""
    key = (api_key.strip() if api_key else None) or os.getenv("GEMINI_API_KEY")
    has_key = bool(key and key.strip())
    return {
        "status": "healthy",
        "version": "1.2.1",
        "engine": "gemini-3.5-flash-lite" if has_key else "gemini-flash-lite (offline heuristic)",
        "api_key_configured": has_key,
        "is_offline": not has_key,
        "default_mode": "budget",
    }


@router.post("/v1/humanize", response_model=HumanizeResponse, summary="Humanize Text")
def humanize_text(payload: HumanizeRequest) -> HumanizeResponse:
    """Humanize input text synchronously."""
    if payload.text is None:
        raise HTTPException(status_code=422, detail="Field 'text' is required")
    if payload.mode not in ("budget", "deep"):
        raise HTTPException(status_code=422, detail=f"Invalid mode '{payload.mode}'. Must be 'budget' or 'deep'")

    if not payload.text:
        return HumanizeResponse(
            humanized_text="",
            original_text="",
            mode=payload.mode,
            tone=payload.tone,
            reading_level=payload.reading_level,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            buzzwords_replaced=[],
            flesch_reading_ease=100.0,
            is_offline=True,
            engine="offline",
            api_tokens_used=0,
        )

    try:
        client = get_client(payload.api_key)
        result = client.humanize(
            text=payload.text,
            mode=payload.mode,  # type: ignore[arg-type]
            tone=payload.tone,  # type: ignore[arg-type]
            reading_level=payload.reading_level,  # type: ignore[arg-type]
            preserve_markdown=payload.preserve_markdown,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Humanization error: {str(exc)}"
        )

    return HumanizeResponse(
        humanized_text=result.text,
        original_text=result.original_text,
        mode=result.mode,
        tone=result.tone,
        reading_level=result.reading_level,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        buzzwords_replaced=result.buzzwords_replaced,
        flesch_reading_ease=result.flesch_reading_ease,
        is_offline=result.is_offline,
        engine=result.engine,
        api_tokens_used=result.api_tokens_used,
    )


@router.post("/v1/humanize/stream", summary="Stream Humanized Text (SSE)")
async def humanize_stream_endpoint(payload: HumanizeRequest) -> StreamingResponse:
    """Stream humanized text chunks via Server-Sent Events (SSE)."""
    if payload.text is None:
        raise HTTPException(status_code=422, detail="Field 'text' is required")
    if payload.mode not in ("budget", "deep"):
        raise HTTPException(status_code=422, detail=f"Invalid mode '{payload.mode}'. Must be 'budget' or 'deep'")

    client = get_client(payload.api_key)

    async def event_generator():
        yield 'data: {"event": "start"}\n\n'
        try:
            if payload.text:
                async for chunk in client.humanize_stream(
                    text=payload.text,
                    mode=payload.mode,  # type: ignore[arg-type]
                    tone=payload.tone,  # type: ignore[arg-type]
                    reading_level=payload.reading_level,  # type: ignore[arg-type]
                    preserve_markdown=payload.preserve_markdown,
                ):
                    data_str = json.dumps({"chunk": chunk})
                    yield f"data: {data_str}\n\n"
        except Exception as exc:
            err_json = json.dumps({"error": str(exc)})
            yield f"data: {err_json}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
