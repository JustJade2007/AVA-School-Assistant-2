"""Two-tier Markdown document parser, semantic chunker, and document reconstructor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Optional

from core.humanizer.parser.mask import InlineMasker, MaskState


class BlockType(str, Enum):
    """Types of Markdown blocks."""

    CODE = "code"
    TABLE = "table"
    BLANK = "blank"
    SEPARATOR = "separator"
    HEADER = "header"
    LIST_ITEM = "list_item"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"


@dataclass
class DocumentBlock:
    """Base class for all Markdown document blocks."""

    block_type: BlockType
    raw_text: str
    is_humanizable: bool
    prefix: str = ""
    content: str = ""
    suffix: str = ""
    indent: str = ""

    def render(self, humanized_content: Optional[str] = None) -> str:
        """Render the block text, replacing humanizable content if provided."""
        if not self.is_humanizable or humanized_content is None:
            return self.raw_text
        return f"{self.indent}{self.prefix}{humanized_content}{self.suffix}"


@dataclass
class CodeBlock(DocumentBlock):
    """Fenced code block (``` or ~~~). 100% immutable and byte-for-byte protected."""

    language: str = ""
    code: str = ""
    fence_char: str = "`"
    fence_len: int = 3

    def __init__(
        self,
        raw_text: str,
        language: str = "",
        code: str = "",
        fence_char: str = "`",
        fence_len: int = 3,
    ) -> None:
        super().__init__(
            block_type=BlockType.CODE,
            raw_text=raw_text,
            is_humanizable=False,
            prefix="",
            content="",
            suffix="",
            indent="",
        )
        self.language = language
        self.code = code
        self.fence_char = fence_char
        self.fence_len = fence_len


@dataclass
class TableBlock(DocumentBlock):
    """GFM Markdown table. 100% immutable to preserve pipes, delimiters, and alignments."""

    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def __init__(
        self,
        raw_text: str,
        headers: Optional[list[str]] = None,
        rows: Optional[list[list[str]]] = None,
    ) -> None:
        super().__init__(
            block_type=BlockType.TABLE,
            raw_text=raw_text,
            is_humanizable=False,
            prefix="",
            content="",
            suffix="",
            indent="",
        )
        self.headers = headers or []
        self.rows = rows or []


@dataclass
class BlankLineBlock(DocumentBlock):
    """Empty or whitespace-only line separating blocks."""

    def __init__(self, raw_text: str = "\n") -> None:
        super().__init__(
            block_type=BlockType.BLANK,
            raw_text=raw_text,
            is_humanizable=False,
            prefix="",
            content="",
            suffix="",
            indent="",
        )


@dataclass
class SeparatorBlock(DocumentBlock):
    """Thematic break or horizontal rule (---, ***, ___). Immutable."""

    def __init__(self, raw_text: str) -> None:
        super().__init__(
            block_type=BlockType.SEPARATOR,
            raw_text=raw_text,
            is_humanizable=False,
            prefix="",
            content="",
            suffix="",
            indent="",
        )


@dataclass
class HeaderBlock(DocumentBlock):
    """ATX heading (#, ##, ###, ...). Humanizable content with preserved prefix."""

    level: int = 1

    def __init__(
        self,
        raw_text: str,
        level: int = 1,
        prefix: str = "# ",
        content: str = "",
        suffix: str = "",
        indent: str = "",
    ) -> None:
        super().__init__(
            block_type=BlockType.HEADER,
            raw_text=raw_text,
            is_humanizable=True,
            prefix=prefix,
            content=content,
            suffix=suffix,
            indent=indent,
        )
        self.level = level

    def render(self, humanized_content: Optional[str] = None) -> str:
        if humanized_content is None:
            return self.raw_text
        # If humanized content already retains heading hashes, don't duplicate prefix
        if humanized_content.strip().startswith("#"):
            return f"{self.indent}{humanized_content}{self.suffix}"
        return f"{self.indent}{self.prefix}{humanized_content}{self.suffix}"


@dataclass
class ListItemBlock(DocumentBlock):
    """Bulleted or numbered list item. Humanizable content with preserved marker and indent."""

    marker: str = "-"

    def __init__(
        self,
        raw_text: str,
        marker: str = "-",
        indent: str = "",
        prefix: str = "- ",
        content: str = "",
        suffix: str = "",
    ) -> None:
        super().__init__(
            block_type=BlockType.LIST_ITEM,
            raw_text=raw_text,
            is_humanizable=True,
            prefix=prefix,
            content=content,
            suffix=suffix,
            indent=indent,
        )
        self.marker = marker

    def render(self, humanized_content: Optional[str] = None) -> str:
        if humanized_content is None:
            return self.raw_text
        # If humanized content already has list marker, preserve it without duplicating
        stripped = humanized_content.lstrip()
        if re.match(r"^(?:[-*+]|\d+[.)])\s", stripped):
            return f"{self.indent}{humanized_content}{self.suffix}"
        return f"{self.indent}{self.prefix}{humanized_content}{self.suffix}"


@dataclass
class QuoteBlock(DocumentBlock):
    """Blockquote line or block (> ...). Humanizable content with preserved > prefix."""

    def __init__(
        self,
        raw_text: str,
        prefix: str = "> ",
        content: str = "",
        suffix: str = "",
        indent: str = "",
    ) -> None:
        super().__init__(
            block_type=BlockType.QUOTE,
            raw_text=raw_text,
            is_humanizable=True,
            prefix=prefix,
            content=content,
            suffix=suffix,
            indent=indent,
        )

    def render(self, humanized_content: Optional[str] = None) -> str:
        if humanized_content is None:
            return self.raw_text
        if humanized_content.lstrip().startswith(">"):
            return f"{self.indent}{humanized_content}{self.suffix}"
        return f"{self.indent}{self.prefix}{humanized_content}{self.suffix}"


@dataclass
class ParagraphBlock(DocumentBlock):
    """Standard markdown prose paragraph."""

    def __init__(
        self,
        raw_text: str,
        content: str = "",
        suffix: str = "",
        indent: str = "",
    ) -> None:
        super().__init__(
            block_type=BlockType.PARAGRAPH,
            raw_text=raw_text,
            is_humanizable=True,
            prefix="",
            content=content,
            suffix=suffix,
            indent=indent,
        )


@dataclass
class DocumentChunk:
    """A semantic chunk of a Markdown document."""

    chunk_id: int
    content: str
    is_humanizable: bool
    block_indices: list[int] = field(default_factory=list)
    raw_text: str = ""
    mask_map: dict[str, str] = field(default_factory=dict)
    chunk_type: str = "prose"


class MarkdownDocument:
    """Parses, partitions, and reconstructs Markdown documents preserving structural invariance."""

    # Regex definitions
    OPEN_FENCE_REGEX = re.compile(r"^([ ]{0,3})(`{3,}|~{3,})([^\n`]*)\r?\n?$")
    TABLE_DELIM_REGEX = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+(\s*:?-+:?\s*)?\|?\s*\r?\n?$")
    ATX_HEADER_REGEX = re.compile(r"^([ ]{0,3})(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*(\r?\n)?$")
    LIST_ITEM_UNORDERED_REGEX = re.compile(r"^([ \t]*)([-*+])[ \t]+(.*?)(\r?\n)?$")
    LIST_ITEM_ORDERED_REGEX = re.compile(r"^([ \t]*)(\d+[.)])[ \t]+(.*?)(\r?\n)?$")
    QUOTE_REGEX = re.compile(r"^([ \t]*>[ \t]?)(.*?)(\r?\n)?$")
    BLANK_LINE_REGEX = re.compile(r"^[ \t]*\r?\n?$")
    SEPARATOR_REGEX = re.compile(r"^[ ]{0,3}([-*_])[ ]*(?:\1[ ]*){2,}\s*\r?\n?$")
    SENTENCE_SPLIT_LOOKBEHIND = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

    def __init__(self, raw_markdown: str) -> None:
        """Initialize and parse raw markdown text into two-tier block hierarchy."""
        self.raw_markdown = raw_markdown
        self.blocks: list[DocumentBlock] = self._parse_blocks(raw_markdown)
        self.chunks: list[DocumentChunk] = []

    def _parse_blocks(self, text: str) -> list[DocumentBlock]:
        """Parse raw text into strongly-typed DocumentBlock instances using a state machine."""
        if not text:
            return []

        lines = text.splitlines(keepends=True)
        blocks: list[DocumentBlock] = []
        i = 0
        n = len(lines)

        while i < n:
            current_line = lines[i]

            # 1. Fenced Code Block Detection
            fence_match = self.OPEN_FENCE_REGEX.match(current_line)
            if fence_match:
                indent = fence_match.group(1)
                fence_str = fence_match.group(2)
                fence_char = fence_str[0]
                fence_len = len(fence_str)
                lang = fence_match.group(3).strip()

                close_regex = re.compile(
                    r"^([ ]{0,3})" + re.escape(fence_char) + r"{" + str(fence_len) + r",}\s*\r?\n?$"
                )

                # Collect code block lines until closing fence or EOF
                j = i + 1
                while j < n:
                    if close_regex.match(lines[j]):
                        j += 1
                        break
                    j += 1

                raw_code = "".join(lines[i:j])
                body_lines = lines[i + 1 : j - 1] if j - 1 > i else []
                code_body = "".join(body_lines)

                blocks.append(
                    CodeBlock(
                        raw_text=raw_code,
                        language=lang,
                        code=code_body,
                        fence_char=fence_char,
                        fence_len=fence_len,
                    )
                )
                i = j
                continue

            # 2. Markdown Table Detection (GFM Syntax: header row with '|' + delimiter row)
            if "|" in current_line and i + 1 < n and self.TABLE_DELIM_REGEX.match(lines[i + 1]):
                j = i + 2
                while j < n and "|" in lines[j] and lines[j].strip():
                    j += 1

                raw_table = "".join(lines[i:j])
                blocks.append(TableBlock(raw_text=raw_table))
                i = j
                continue

            # 3. Blank Line Detection
            if self.BLANK_LINE_REGEX.match(current_line):
                blocks.append(BlankLineBlock(raw_text=current_line))
                i += 1
                continue

            # 4. Separator / Horizontal Rule (---, ***, ___)
            if self.SEPARATOR_REGEX.match(current_line):
                blocks.append(SeparatorBlock(raw_text=current_line))
                i += 1
                continue

            # 5. ATX Heading (# Heading)
            header_match = self.ATX_HEADER_REGEX.match(current_line)
            if header_match:
                indent = header_match.group(1)
                hashes = header_match.group(2)
                title = header_match.group(3)
                suffix = header_match.group(4) or ""
                blocks.append(
                    HeaderBlock(
                        raw_text=current_line,
                        level=len(hashes),
                        prefix=f"{hashes} ",
                        content=title,
                        suffix=suffix,
                        indent=indent,
                    )
                )
                i += 1
                continue

            # 6. List Item (Unordered: -, *, +)
            ul_match = self.LIST_ITEM_UNORDERED_REGEX.match(current_line)
            if ul_match:
                indent = ul_match.group(1)
                marker = ul_match.group(2)
                item_content = ul_match.group(3)
                suffix = ul_match.group(4) or ""
                blocks.append(
                    ListItemBlock(
                        raw_text=current_line,
                        marker=marker,
                        indent=indent,
                        prefix=f"{marker} ",
                        content=item_content,
                        suffix=suffix,
                    )
                )
                i += 1
                continue

            # 7. List Item (Ordered: 1., 2), etc.)
            ol_match = self.LIST_ITEM_ORDERED_REGEX.match(current_line)
            if ol_match:
                indent = ol_match.group(1)
                marker = ol_match.group(2)
                item_content = ol_match.group(3)
                suffix = ol_match.group(4) or ""
                blocks.append(
                    ListItemBlock(
                        raw_text=current_line,
                        marker=marker,
                        indent=indent,
                        prefix=f"{marker} ",
                        content=item_content,
                        suffix=suffix,
                    )
                )
                i += 1
                continue

            # 8. Blockquote (> ...)
            quote_match = self.QUOTE_REGEX.match(current_line)
            if quote_match:
                prefix = quote_match.group(1)
                quote_content = quote_match.group(2)
                suffix = quote_match.group(3) or ""
                blocks.append(
                    QuoteBlock(
                        raw_text=current_line,
                        prefix=prefix,
                        content=quote_content,
                        suffix=suffix,
                    )
                )
                i += 1
                continue

            # 9. Paragraph Block (Consolidates contiguous regular prose lines)
            para_lines = [current_line]
            j = i + 1
            while j < n:
                next_line = lines[j]
                if (
                    self.OPEN_FENCE_REGEX.match(next_line)
                    or ("|" in next_line and j + 1 < n and self.TABLE_DELIM_REGEX.match(lines[j + 1]))
                    or self.BLANK_LINE_REGEX.match(next_line)
                    or self.SEPARATOR_REGEX.match(next_line)
                    or self.ATX_HEADER_REGEX.match(next_line)
                    or self.LIST_ITEM_UNORDERED_REGEX.match(next_line)
                    or self.LIST_ITEM_ORDERED_REGEX.match(next_line)
                    or self.QUOTE_REGEX.match(next_line)
                ):
                    break
                para_lines.append(next_line)
                j += 1

            raw_para = "".join(para_lines)
            content = raw_para.rstrip("\r\n")
            suffix = raw_para[len(content):]
            blocks.append(ParagraphBlock(raw_text=raw_para, content=content, suffix=suffix))
            i = j

        return blocks

    def extract_chunks(self, max_chunk_chars: int = 1500) -> list[DocumentChunk]:
        """Partition the document along semantic paragraph boundaries without bisecting code or tables.

        Args:
            max_chunk_chars: Target maximum character length per humanizable chunk.

        Returns:
            List of DocumentChunk instances.
        """
        chunks: list[DocumentChunk] = []

        # Current accumulator for contiguous humanizable prose blocks
        acc_blocks: list[int] = []
        acc_raw_pieces: list[str] = []
        acc_content_pieces: list[str] = []
        acc_chars = 0

        def _flush_acc() -> None:
            nonlocal acc_blocks, acc_raw_pieces, acc_content_pieces, acc_chars
            if not acc_blocks:
                return

            full_raw = "".join(acc_raw_pieces)
            full_content = "".join(acc_content_pieces)

            chunks.append(
                DocumentChunk(
                    chunk_id=len(chunks),
                    content=full_content,
                    is_humanizable=True,
                    block_indices=list(acc_blocks),
                    raw_text=full_raw,
                    chunk_type="prose",
                )
            )
            acc_blocks = []
            acc_raw_pieces = []
            acc_content_pieces = []
            acc_chars = 0

        for idx, block in enumerate(self.blocks):
            # Immutable blocks: Code, Table, Separator
            if not block.is_humanizable:
                if block.block_type == BlockType.BLANK:
                    # If we have an active accumulator, preserve the blank line within it
                    if acc_blocks:
                        acc_blocks.append(idx)
                        acc_raw_pieces.append(block.raw_text)
                        acc_content_pieces.append(block.raw_text)
                        acc_chars += len(block.raw_text)
                    else:
                        # Blank line outside prose - emit as immutable chunk
                        chunks.append(
                            DocumentChunk(
                                chunk_id=len(chunks),
                                content=block.raw_text,
                                is_humanizable=False,
                                block_indices=[idx],
                                raw_text=block.raw_text,
                                chunk_type=block.block_type.value,
                            )
                        )
                    continue

                # Code, Table, or Separator encountered: flush active humanizable prose chunk
                _flush_acc()

                # Emit immutable block as atomic, non-LLM chunk
                chunks.append(
                    DocumentChunk(
                        chunk_id=len(chunks),
                        content=block.raw_text,
                        is_humanizable=False,
                        block_indices=[idx],
                        raw_text=block.raw_text,
                        chunk_type=block.block_type.value,
                    )
                )
                continue

            # Humanizable block encountered: Header, ListItem, Paragraph, Quote
            # Section boundary: Header encounters (#, ##, ###) flush if accumulator has reached reasonable size
            if block.block_type == BlockType.HEADER and acc_chars > 0 and (acc_chars >= max_chunk_chars // 2 or acc_chars + block_len > max_chunk_chars):
                _flush_acc()

            # Check if adding this block exceeds max_chunk_chars
            block_len = len(block.raw_text)
            if acc_chars > 0 and (acc_chars + block_len > max_chunk_chars):
                _flush_acc()

            # Handle oversized single paragraph exceeding max_chunk_chars
            if block.block_type == BlockType.PARAGRAPH and block_len > max_chunk_chars:
                _flush_acc()
                sentences = self.SENTENCE_SPLIT_LOOKBEHIND.split(block.content)
                sub_acc: list[str] = []
                sub_len = 0

                for sent in sentences:
                    s_text = sent.strip()
                    if not s_text:
                        continue
                    if sub_len > 0 and (sub_len + len(s_text) + 1 > max_chunk_chars):
                        sub_content = " ".join(sub_acc) + " "
                        chunks.append(
                            DocumentChunk(
                                chunk_id=len(chunks),
                                content=sub_content,
                                is_humanizable=True,
                                block_indices=[idx],
                                raw_text=sub_content,
                                chunk_type="paragraph",
                            )
                        )
                        sub_acc = []
                        sub_len = 0
                    sub_acc.append(s_text)
                    sub_len += len(s_text) + 1

                if sub_acc:
                    sub_content = " ".join(sub_acc) + block.suffix
                    chunks.append(
                        DocumentChunk(
                            chunk_id=len(chunks),
                            content=sub_content,
                            is_humanizable=True,
                            block_indices=[idx],
                            raw_text=sub_content,
                            chunk_type="paragraph",
                        )
                    )
                continue

            # Append block to current accumulator
            acc_blocks.append(idx)
            acc_raw_pieces.append(block.raw_text)
            acc_content_pieces.append(block.raw_text)
            acc_chars += block_len

        # Final flush
        _flush_acc()

        self.chunks = chunks
        return chunks

    def reconstruct(self, humanized_chunks: list[str]) -> str:
        """Reassemble humanized chunks back into the complete markdown document.

        Guarantees:
        - Code blocks are 100% byte-for-byte identical to the original source.
        - Markdown tables retain all pipes, delimiters, and alignments.
        - ATX headings (#) retain exact prefixes and hierarchies.
        - Bulleted and ordered lists retain item markers and indentation.

        Args:
            humanized_chunks: List of humanized strings, matching either all chunks
                              or only the humanizable chunks.

        Returns:
            Reassembled Markdown document string.
        """
        if not self.chunks:
            self.extract_chunks()

        if not self.chunks:
            return self.raw_markdown

        # Flexible matching for caller patterns:
        # Case A: 1-to-1 match with all chunks
        if len(humanized_chunks) == len(self.chunks):
            out_pieces: list[str] = []
            for chunk, h_text in zip(self.chunks, humanized_chunks):
                if not chunk.is_humanizable:
                    out_pieces.append(chunk.raw_text)
                else:
                    out_pieces.append(h_text)
            return "".join(out_pieces)

        # Case B: Caller passed only humanizable chunk results
        humanizable_chunks = [c for c in self.chunks if c.is_humanizable]
        if len(humanized_chunks) == len(humanizable_chunks):
            out_pieces = []
            h_idx = 0
            for chunk in self.chunks:
                if not chunk.is_humanizable:
                    out_pieces.append(chunk.raw_text)
                else:
                    out_pieces.append(humanized_chunks[h_idx])
                    h_idx += 1
            return "".join(out_pieces)

        # Case C: Single consolidated string passed
        if len(humanized_chunks) == 1:
            return humanized_chunks[0]

        # Case D: Fallback to direct concatenation
        return "".join(humanized_chunks)
