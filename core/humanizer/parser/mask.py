"""Inline token masking and unmasking engine for code, links, and formulas."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Optional


@dataclass
class MaskState:
    """State tracking masked inline tokens and their original contents."""

    inline_codes: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    math_formulas: list[str] = field(default_factory=list)
    # Generic map of placeholder token -> original string
    token_map: dict[str, str] = field(default_factory=dict)


class InlineMasker:
    """Masks inline backtick code, markdown URLs, and math formulas from LLM alteration.

    Placeholders use distinct unicode sentinels:
    - Inline Code: ⟦INLINE_CODE_0⟧, ⟦INLINE_CODE_1⟧, ...
    - Markdown & Bare URLs: ⟦URL_0⟧, ⟦URL_1⟧, ...
    - Math Formulas: ⟦MATH_0⟧, ⟦MATH_1⟧, ...
    """

    # Regex patterns for inline elements
    # 1. Math formulas: $$display math$$ or $inline math$
    DISPLAY_MATH_REGEX = re.compile(r"\$\$([\s\S]+?)\$\$")
    INLINE_MATH_REGEX = re.compile(r"(?<![\$\w])\$(?!\s|\d)([^$\n]+?)(?<!\s)\$(?![\$\w\d])")

    # 2. Inline code: `code` or ``code`` or ```code``` (on a single line)
    INLINE_CODE_REGEX = re.compile(r"(?<!`)(`{1,3})([^`\n]+?)\1(?!`)")

    # 3. Markdown links: [anchor](url "title") or ![alt](url)
    MARKDOWN_LINK_REGEX = re.compile(
        r"(!?\[(?:[^\]\\]|\\.)*\])\((<[^>]+>|[^\s\)\"]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)"
    )

    # 4. Autolinks: <http://...> or <https://...> or <email@domain.com>
    AUTOLINK_REGEX = re.compile(
        r"<((?:https?://|[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)[^>]*)>", re.IGNORECASE
    )

    # 5. Bare URLs: http://... or https://... (not preceded by ⟦ or already masked)
    BARE_URL_REGEX = re.compile(
        r"(?<![⟦\w])(https?://[^\s<>\)\]\"\'\\]+)", re.IGNORECASE
    )

    # Unmasking regex matching any placeholder with optional internal whitespace
    PLACEHOLDER_REGEX = re.compile(
        r"⟦\s*(?:INLINE_CODE|CODE|URL|MATH)_(\d+)\s*⟧"
    )

    @classmethod
    def mask(cls, text: str) -> tuple[str, MaskState]:
        """Mask all inline code, links, and formulas in the provided text.

        Returns:
            Tuple of (masked_text, mask_state).
        """
        if not text:
            return text, MaskState()

        state = MaskState()
        masked = text

        # Step 1: Protect math formulas ($$ ... $$ and $ ... $)
        def _math_repl(m: re.Match[str]) -> str:
            idx = len(state.math_formulas)
            full_match = m.group(0)
            state.math_formulas.append(full_match)
            ph = f"⟦MATH_{idx}⟧"
            state.token_map[ph] = full_match
            return ph

        masked = cls.DISPLAY_MATH_REGEX.sub(_math_repl, masked)
        masked = cls.INLINE_MATH_REGEX.sub(_math_repl, masked)

        # Step 2: Protect inline backtick code
        def _code_repl(m: re.Match[str]) -> str:
            idx = len(state.inline_codes)
            full_match = m.group(0)
            state.inline_codes.append(full_match)
            ph = f"⟦INLINE_CODE_{idx}⟧"
            state.token_map[ph] = full_match
            return ph

        masked = cls.INLINE_CODE_REGEX.sub(_code_repl, masked)

        # Step 3: Protect markdown links [anchor](URL) by masking ONLY the target URL
        # Anchor text remains accessible for humanization
        def _link_repl(m: re.Match[str]) -> str:
            prefix = m.group(1)
            raw_url = m.group(2)
            # Strip angle brackets if present in raw_url (<http...>)
            actual_url = raw_url[1:-1] if raw_url.startswith("<") and raw_url.endswith(">") else raw_url
            idx = len(state.urls)
            state.urls.append(actual_url)
            ph = f"⟦URL_{idx}⟧"
            state.token_map[ph] = actual_url

            # Preserve full link syntax
            full_str = m.group(0)
            target_start = m.start(2) - m.start(0)
            target_end = m.end(2) - m.start(0)
            replaced = full_str[:target_start] + ph + full_str[target_end:]
            return replaced

        masked = cls.MARKDOWN_LINK_REGEX.sub(_link_repl, masked)

        # Step 4: Protect autolinks <http://...>
        def _autolink_repl(m: re.Match[str]) -> str:
            raw_url = m.group(1)
            idx = len(state.urls)
            state.urls.append(raw_url)
            ph = f"⟦URL_{idx}⟧"
            state.token_map[ph] = raw_url
            return f"<{ph}>"

        masked = cls.AUTOLINK_REGEX.sub(_autolink_repl, masked)

        # Step 5: Protect bare URLs
        def _bare_url_repl(m: re.Match[str]) -> str:
            raw_url = m.group(1)
            idx = len(state.urls)
            state.urls.append(raw_url)
            ph = f"⟦URL_{idx}⟧"
            state.token_map[ph] = raw_url
            return ph

        masked = cls.BARE_URL_REGEX.sub(_bare_url_repl, masked)

        return masked, state

    @classmethod
    def unmask(cls, text: str, state: MaskState) -> str:
        """Restore all masked tokens bit-for-bit using the mask state.

        Args:
            text: Text potentially containing placeholders.
            state: MaskState containing original token mappings.

        Returns:
            Restored text with all original tokens exactly in place.
        """
        if not text or not state.token_map:
            return text

        result = text

        # 1. First pass: direct string replacements for canonical placeholders
        for ph, original in state.token_map.items():
            if ph in result:
                result = result.replace(ph, original)

        # 2. Second pass: regex-based recovery for placeholders altered by LLM spacing
        # Handles variants like ⟦ INLINE_CODE_0 ⟧, ⟦ CODE_0 ⟧, ⟦ URL_0 ⟧, ⟦ MATH_0 ⟧
        def _recovery_repl(m: re.Match[str]) -> str:
            matched_str = m.group(0)
            idx_str = m.group(1)
            try:
                idx = int(idx_str)
            except ValueError:
                return matched_str

            if "INLINE_CODE" in matched_str or "CODE" in matched_str:
                if idx < len(state.inline_codes):
                    return state.inline_codes[idx]
            elif "URL" in matched_str:
                if idx < len(state.urls):
                    return state.urls[idx]
            elif "MATH" in matched_str:
                if idx < len(state.math_formulas):
                    return state.math_formulas[idx]

            return matched_str

        result = cls.PLACEHOLDER_REGEX.sub(_recovery_repl, result)
        return result


def mask_inline_tokens(text: str) -> tuple[str, dict[str, str]]:
    """Functional convenience wrapper returning (masked_text, token_map)."""
    masked, state = InlineMasker.mask(text)
    return masked, state.token_map


def unmask_inline_tokens(text: str, token_map: dict[str, str]) -> str:
    """Functional convenience wrapper unmasking text using token_map."""
    state = MaskState(token_map=token_map)
    # Reconstruct lists for recovery pass
    for ph, orig in token_map.items():
        if "INLINE_CODE" in ph or "CODE" in ph:
            state.inline_codes.append(orig)
        elif "URL" in ph:
            state.urls.append(orig)
        elif "MATH" in ph:
            state.math_formulas.append(orig)
    return InlineMasker.unmask(text, state)
