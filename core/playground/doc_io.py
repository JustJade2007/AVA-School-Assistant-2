"""
Document I/O module for AVA Playground Mode.
Handles multi-format ingestion (.pdf, .docx, .doc, .txt) and professional .docx
document generation supporting MLA, APA, and Standard Report formatting presets.
"""

import os
import re
import datetime
from typing import Optional, List, Dict, Any

# python-docx for writing and reading .docx
try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
except ImportError:
    docx = None

# pypdf for reading .pdf
try:
    import pypdf
except ImportError:
    pypdf = None

from core.logger import get_logger

logger = get_logger("playground.doc_io")


class DocumentImporter:
    """Extracts text content from various file formats (.pdf, .docx, .doc, .txt)."""

    @classmethod
    def read_file(cls, file_path: str) -> str:
        """Reads text from supported document types based on extension."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return cls.read_pdf(file_path)
        elif ext == ".docx":
            return cls.read_docx(file_path)
        elif ext == ".doc":
            return cls.read_doc(file_path)
        elif ext in [".txt", ".md", ".rtf", ".csv"]:
            return cls.read_txt(file_path)
        else:
            # Fallback to plain text attempt
            return cls.read_txt(file_path)

    @classmethod
    def read_pdf(cls, file_path: str) -> str:
        if pypdf is None:
            raise RuntimeError("pypdf library is required to read PDF files.")
        reader = pypdf.PdfReader(file_path)
        text_parts = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text.strip())
        return "\n\n".join(text_parts)

    @classmethod
    def read_docx(cls, file_path: str) -> str:
        if docx is None:
            raise RuntimeError("python-docx library is required to read .docx files.")
        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    @classmethod
    def read_doc(cls, file_path: str) -> str:
        """Reads legacy binary .doc format using win32com if available, with robust string extraction fallback."""
        # Method 1: Try COM automation if on Windows with Microsoft Word installed
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(os.path.abspath(file_path))
            text = doc.Content.Text
            doc.Close(False)
            word.Quit()
            if text and text.strip():
                return text.strip()
        except Exception as e:
            logger.debug(f"win32com .doc reading unavailable or failed: {e}")

        # Method 2: Robust binary ASCII/Unicode stream text extraction
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            # Extract printable ascii and basic unicode fragments
            decoded = content.decode("latin-1", errors="ignore")
            # Filter clean readable sentences/paragraphs
            clean_strings = re.findall(r"[\x20-\x7E\t\r\n]{4,}", decoded)
            filtered = [s.strip() for s in clean_strings if len(s.strip()) > 8 and not s.startswith("Microsoft")]
            if filtered:
                return "\n\n".join(filtered)
        except Exception as e:
            logger.warning(f"Fallback binary .doc read failed: {e}")

        raise RuntimeError(f"Could not extract text from legacy .doc file: {file_path}. Please convert to .docx or .pdf.")

    @classmethod
    def read_txt(cls, file_path: str) -> str:
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


class DocumentExporter:
    """Generates formatted Microsoft Word (.docx) documents according to academic presets."""

    @classmethod
    def export_to_docx(
        cls,
        project_title: str,
        sections: List[Dict[str, Any]],
        output_path: str,
        preset: str = "MLA",
        author_name: str = "",
        course_name: str = "",
        instructor_name: str = "",
        bibliography: Optional[List[str]] = None,
    ) -> str:
        """
        Builds and saves a .docx document applying selected layout rules (MLA, APA, Standard Report).
        Returns the absolute path to the generated document.
        """
        if docx is None:
            raise RuntimeError("python-docx library is required to export .docx files.")

        doc = docx.Document()

        # Set 1-inch margins
        for section in doc.sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        norm_preset = (preset or "MLA").upper()

        if "MLA" in norm_preset:
            cls._apply_mla(doc, project_title, sections, author_name, course_name, instructor_name, bibliography)
        elif "APA" in norm_preset:
            cls._apply_apa(doc, project_title, sections, author_name, course_name, instructor_name, bibliography)
        else:
            cls._apply_report(doc, project_title, sections, author_name, course_name, instructor_name, bibliography)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc.save(output_path)
        logger.info(f"Exported {preset} document to: {output_path}")
        return os.path.abspath(output_path)

    @classmethod
    def _apply_mla(
        cls,
        doc: Any,
        title: str,
        sections: List[Dict[str, Any]],
        author: str,
        course: str,
        instructor: str,
        bibliography: Optional[List[str]],
    ):
        """MLA 9th Edition Style: Times New Roman 12pt, double spaced, 0.5" first-line indent, Works Cited."""
        today_str = datetime.date.today().strftime("%d %B %Y")

        # MLA Heading Block (left aligned)
        header_lines = [
            author if author else "Student Name",
            instructor if instructor else "Instructor Name",
            course if course else "Course Name",
            today_str,
        ]
        for line in header_lines:
            p = doc.add_paragraph()
            p.paragraph_format.line_spacing = 2.0
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(line)
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)

        # Title (Centered, Title Case, not bolded/underlined per standard MLA)
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.paragraph_format.line_spacing = 2.0
        p_title.paragraph_format.space_after = Pt(0)
        run_title = p_title.add_run(title)
        run_title.font.name = "Times New Roman"
        run_title.font.size = Pt(12)

        # Body Sections
        for sec in sections:
            sec_title = sec.get("title", "").strip()
            sec_text = sec.get("text", "").strip()

            if sec_title:
                p_sec = doc.add_paragraph()
                p_sec.paragraph_format.line_spacing = 2.0
                p_sec.paragraph_format.space_after = Pt(0)
                r_sec = p_sec.add_run(sec_title)
                r_sec.font.name = "Times New Roman"
                r_sec.font.size = Pt(12)
                r_sec.font.bold = True

            # Paragraphs
            for para_str in sec_text.split("\n\n"):
                para_str = para_str.strip()
                if not para_str:
                    continue
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 2.0
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.first_line_indent = Inches(0.5)
                r = p.add_run(para_str)
                r.font.name = "Times New Roman"
                r.font.size = Pt(12)

        # Works Cited (New Page)
        if bibliography and len(bibliography) > 0:
            doc.add_page_break()
            p_wc = doc.add_paragraph()
            p_wc.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_wc.paragraph_format.line_spacing = 2.0
            r_wc = p_wc.add_run("Works Cited")
            r_wc.font.name = "Times New Roman"
            r_wc.font.size = Pt(12)

            for entry in bibliography:
                if not entry.strip():
                    continue
                p_entry = doc.add_paragraph()
                p_entry.paragraph_format.line_spacing = 2.0
                p_entry.paragraph_format.space_after = Pt(0)
                # Hanging indent: left indent 0.5 in, first line -0.5 in
                p_entry.paragraph_format.left_indent = Inches(0.5)
                p_entry.paragraph_format.first_line_indent = Inches(-0.5)
                r_e = p_entry.add_run(entry.strip())
                r_e.font.name = "Times New Roman"
                r_e.font.size = Pt(12)

    @classmethod
    def _apply_apa(
        cls,
        doc: Any,
        title: str,
        sections: List[Dict[str, Any]],
        author: str,
        course: str,
        instructor: str,
        bibliography: Optional[List[str]],
    ):
        """APA 7th Edition Student Paper: Title page, bold headings, double spacing, References page."""
        today_str = datetime.date.today().strftime("%B %d, %Y")

        # Blank space before title
        for _ in range(3):
            p_space = doc.add_paragraph()
            p_space.paragraph_format.line_spacing = 2.0

        # Title (Bold, Centered)
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.paragraph_format.line_spacing = 2.0
        p_title.paragraph_format.space_after = Pt(12)
        r_t = p_title.add_run(title)
        r_t.font.name = "Times New Roman"
        r_t.font.size = Pt(12)
        r_t.font.bold = True

        # Title Page Metadata
        meta_items = [
            author if author else "Student Name",
            "Department of Arts & Sciences, University",
            course if course else "Course Name",
            instructor if instructor else "Instructor Name",
            today_str,
        ]
        for item in meta_items:
            p_meta = doc.add_paragraph()
            p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_meta.paragraph_format.line_spacing = 2.0
            p_meta.paragraph_format.space_after = Pt(0)
            r_m = p_meta.add_run(item)
            r_m.font.name = "Times New Roman"
            r_m.font.size = Pt(12)

        # Body page break
        doc.add_page_break()

        # Paper Title repeated at top of page 2
        p_rep = doc.add_paragraph()
        p_rep.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_rep.paragraph_format.line_spacing = 2.0
        r_rep = p_rep.add_run(title)
        r_rep.font.name = "Times New Roman"
        r_rep.font.size = Pt(12)
        r_rep.font.bold = True

        for sec in sections:
            sec_title = sec.get("title", "").strip()
            sec_text = sec.get("text", "").strip()

            if sec_title:
                p_sec = doc.add_paragraph()
                p_sec.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_sec.paragraph_format.line_spacing = 2.0
                r_sec = p_sec.add_run(sec_title)
                r_sec.font.name = "Times New Roman"
                r_sec.font.size = Pt(12)
                r_sec.font.bold = True

            for para_str in sec_text.split("\n\n"):
                para_str = para_str.strip()
                if not para_str:
                    continue
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 2.0
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.first_line_indent = Inches(0.5)
                r = p.add_run(para_str)
                r.font.name = "Times New Roman"
                r.font.size = Pt(12)

        # References page
        if bibliography and len(bibliography) > 0:
            doc.add_page_break()
            p_ref = doc.add_paragraph()
            p_ref.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_ref.paragraph_format.line_spacing = 2.0
            r_ref = p_ref.add_run("References")
            r_ref.font.name = "Times New Roman"
            r_ref.font.size = Pt(12)
            r_ref.font.bold = True

            for entry in bibliography:
                if not entry.strip():
                    continue
                p_entry = doc.add_paragraph()
                p_entry.paragraph_format.line_spacing = 2.0
                p_entry.paragraph_format.space_after = Pt(0)
                p_entry.paragraph_format.left_indent = Inches(0.5)
                p_entry.paragraph_format.first_line_indent = Inches(-0.5)
                r_e = p_entry.add_run(entry.strip())
                r_e.font.name = "Times New Roman"
                r_e.font.size = Pt(12)

    @classmethod
    def _apply_report(
        cls,
        doc: Any,
        title: str,
        sections: List[Dict[str, Any]],
        author: str,
        course: str,
        instructor: str,
        bibliography: Optional[List[str]],
    ):
        """Modern Executive / Technical Report: Calibri 11pt, 1.15 line spacing, 6pt after, bold blue headers."""
        # Report Title
        p_title = doc.add_paragraph()
        p_title.paragraph_format.space_before = Pt(12)
        p_title.paragraph_format.space_after = Pt(4)
        r_title = p_title.add_run(title)
        r_title.font.name = "Calibri"
        r_title.font.size = Pt(22)
        r_title.font.bold = True
        r_title.font.color.rgb = RGBColor(30, 58, 138)  # Deep Indigo Blue

        # Subtitle / Author Info
        p_sub = doc.add_paragraph()
        p_sub.paragraph_format.space_after = Pt(18)
        sub_text = f"Prepared by: {author or 'Author'}"
        if course:
            sub_text += f" | {course}"
        sub_text += f" | {datetime.date.today().strftime('%B %d, %Y')}"
        r_sub = p_sub.add_run(sub_text)
        r_sub.font.name = "Calibri"
        r_sub.font.size = Pt(10)
        r_sub.font.italic = True
        r_sub.font.color.rgb = RGBColor(107, 114, 128)

        # Body Sections
        for sec in sections:
            sec_title = sec.get("title", "").strip()
            sec_text = sec.get("text", "").strip()

            if sec_title:
                p_sec = doc.add_paragraph()
                p_sec.paragraph_format.space_before = Pt(14)
                p_sec.paragraph_format.space_after = Pt(4)
                r_sec = p_sec.add_run(sec_title)
                r_sec.font.name = "Calibri"
                r_sec.font.size = Pt(14)
                r_sec.font.bold = True
                r_sec.font.color.rgb = RGBColor(30, 64, 175)

            for para_str in sec_text.split("\n\n"):
                para_str = para_str.strip()
                if not para_str:
                    continue
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1.15
                p.paragraph_format.space_after = Pt(6)
                r = p.add_run(para_str)
                r.font.name = "Calibri"
                r.font.size = Pt(11)

        # Sources / References
        if bibliography and len(bibliography) > 0:
            p_ref_h = doc.add_paragraph()
            p_ref_h.paragraph_format.space_before = Pt(18)
            p_ref_h.paragraph_format.space_after = Pt(6)
            r_rh = p_ref_h.add_run("References & Sources")
            r_rh.font.name = "Calibri"
            r_rh.font.size = Pt(14)
            r_rh.font.bold = True
            r_rh.font.color.rgb = RGBColor(30, 64, 175)

            for entry in bibliography:
                if not entry.strip():
                    continue
                p_entry = doc.add_paragraph()
                p_entry.paragraph_format.space_after = Pt(4)
                r_e = p_entry.add_run(f"• {entry.strip()}")
                r_e.font.name = "Calibri"
                r_e.font.size = Pt(10)
