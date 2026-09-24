"""
Project data models and persistence for AVA Playground Mode.
Stores long-form writing projects, rubrics, sources, outlines, section drafts,
and review approval statuses with JSON serialization.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class RubricCriterion:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    target_score: Optional[str] = None
    fulfilled: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RubricCriterion":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class SourceItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    source_type: str = "text"  # "text", "pdf", "docx", "doc", "txt", "screen_snip", "web", "youtube"
    content: str = ""
    file_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @property
    def title(self) -> str:
        """Alias for name attribute to maintain compatibility."""
        return self.name

    @title.setter
    def title(self, val: str):
        self.name = val

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceItem":
        d = dict(data)
        if "title" in d and "name" not in d:
            d["name"] = d["title"]
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


@dataclass
class SectionDraft:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    goal_summary: str = ""
    target_word_count: int = 250
    criteria_ids: List[str] = field(default_factory=list)
    raw_ai_text: str = ""
    humanized_text: str = ""
    final_text: str = ""
    is_approved: bool = False
    refinement_history: List[str] = field(default_factory=list)

    def get_active_text(self) -> str:
        """Returns the most relevant text (final_text > humanized_text > raw_ai_text)."""
        if self.final_text.strip():
            return self.final_text
        if self.humanized_text.strip():
            return self.humanized_text
        return self.raw_ai_text

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionDraft":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class PlaygroundProject:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = "Untitled Project"
    topic_description: str = ""
    formatting_preset: str = "MLA"  # "MLA", "APA", "Standard Report"
    target_total_words: int = 1000
    rubric_criteria: List[RubricCriterion] = field(default_factory=list)
    rubric_files: List[SourceItem] = field(default_factory=list)
    rubric_raw_text: str = ""
    sources: List[SourceItem] = field(default_factory=list)
    sections: List[SectionDraft] = field(default_factory=list)
    bibliography_entries: List[str] = field(default_factory=list)
    author_name: str = ""
    course_name: str = ""
    instructor_name: str = ""
    teacher_grade_report: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "topic_description": self.topic_description,
            "formatting_preset": self.formatting_preset,
            "target_total_words": self.target_total_words,
            "rubric_criteria": [c.to_dict() for c in self.rubric_criteria],
            "rubric_files": [rf.to_dict() for rf in self.rubric_files],
            "rubric_raw_text": self.rubric_raw_text,
            "sources": [s.to_dict() for s in self.sources],
            "sections": [sec.to_dict() for sec in self.sections],
            "bibliography_entries": self.bibliography_entries,
            "author_name": self.author_name,
            "course_name": self.course_name,
            "instructor_name": self.instructor_name,
            "teacher_grade_report": self.teacher_grade_report,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaygroundProject":
        rubrics = [RubricCriterion.from_dict(c) for c in data.get("rubric_criteria", [])]
        rubric_files = [SourceItem.from_dict(rf) for rf in data.get("rubric_files", [])]
        sources = [SourceItem.from_dict(s) for s in data.get("sources", [])]
        sections = [SectionDraft.from_dict(sec) for sec in data.get("sections", [])]
        
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            title=data.get("title", "Untitled Project"),
            topic_description=data.get("topic_description", ""),
            formatting_preset=data.get("formatting_preset", "MLA"),
            target_total_words=data.get("target_total_words", 1000),
            rubric_criteria=rubrics,
            rubric_files=rubric_files,
            rubric_raw_text=data.get("rubric_raw_text", ""),
            sources=sources,
            sections=sections,
            bibliography_entries=data.get("bibliography_entries", []),
            author_name=data.get("author_name", ""),
            course_name=data.get("course_name", ""),
            instructor_name=data.get("instructor_name", ""),
            teacher_grade_report=data.get("teacher_grade_report"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )

    def save_to_file(self, file_path: str):
        self.updated_at = time.time()
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, file_path: str) -> "PlaygroundProject":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_full_document_text(self) -> str:
        """Combines all approved/active section texts into a cohesive document string."""
        parts = []
        for sec in self.sections:
            text = sec.get_active_text().strip()
            if text:
                parts.append(f"## {sec.title}\n\n{text}")
        return "\n\n".join(parts)

    def total_word_count(self) -> int:
        full_text = self.get_full_document_text()
        return len(full_text.split()) if full_text else 0
