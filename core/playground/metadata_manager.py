"""
Academic Metadata Preset Manager for AVA Playground Mode.
Manages user presets for:
- Author Names (student / co-author identities)
- Course Titles (classes, course codes, subjects)
- Professor / Instructor Names
Supports saving, loading, and deleting all three categories independently.
"""

import json
import os
from typing import List, Optional
from core.logger import get_logger

logger = get_logger("playground.metadata_manager")


class AcademicMetadataManager:
    """Manages independent presets for authors, courses, and professors."""

    def __init__(self, config_manager=None, storage_path: Optional[str] = None):
        self.config_manager = config_manager
        if storage_path:
            self.storage_path = storage_path
        else:
            base_dir = os.path.abspath(os.getcwd())
            self.storage_path = os.path.join(base_dir, "academic_profiles.json")

        self.authors: List[str] = []
        self.courses: List[str] = []
        self.professors: List[str] = []
        self.load()

    def load(self):
        """Loads presets from ConfigManager or disk fallback."""
        loaded_from_config = False
        if self.config_manager and hasattr(self.config_manager, "config"):
            cfg = self.config_manager.config
            if getattr(cfg, "saved_authors", None):
                self.authors = [str(x).strip() for x in cfg.saved_authors if str(x).strip()]
                loaded_from_config = True
            if getattr(cfg, "saved_courses", None):
                self.courses = [str(x).strip() for x in cfg.saved_courses if str(x).strip()]
                loaded_from_config = True
            if getattr(cfg, "saved_professors", None):
                self.professors = [str(x).strip() for x in cfg.saved_professors if str(x).strip()]
                loaded_from_config = True

        # Check local file fallback if empty or not in config
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if not self.authors and "authors" in data:
                            self.authors = [str(x).strip() for x in data["authors"] if str(x).strip()]
                        if not self.courses and "courses" in data:
                            self.courses = [str(x).strip() for x in data["courses"] if str(x).strip()]
                        if not self.professors and "professors" in data:
                            self.professors = [str(x).strip() for x in data["professors"] if str(x).strip()]
            except Exception as e:
                logger.warning(f"Could not load academic profiles from {self.storage_path}: {e}")

    def save(self) -> bool:
        """Persists presets to ConfigManager and local disk file."""
        # 1. Update ConfigManager if available
        if self.config_manager and hasattr(self.config_manager, "update"):
            try:
                self.config_manager.update(
                    saved_authors=list(self.authors),
                    saved_courses=list(self.courses),
                    saved_professors=list(self.professors),
                )
            except Exception as e:
                logger.warning(f"Could not sync presets to ConfigManager: {e}")

        # 2. Write to local JSON storage
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({
                    "authors": self.authors,
                    "courses": self.courses,
                    "professors": self.professors,
                }, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed saving academic profiles to {self.storage_path}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Author Presets
    # -------------------------------------------------------------------------
    def get_authors(self) -> List[str]:
        return list(self.authors)

    def save_author(self, name: str) -> bool:
        clean = name.strip()
        if not clean:
            return False
        if clean in self.authors:
            self.authors.remove(clean)
        self.authors.insert(0, clean)
        return self.save()

    def delete_author(self, name: str) -> bool:
        clean = name.strip()
        if clean in self.authors:
            self.authors.remove(clean)
            return self.save()
        return False

    # -------------------------------------------------------------------------
    # Course Presets
    # -------------------------------------------------------------------------
    def get_courses(self) -> List[str]:
        return list(self.courses)

    def save_course(self, name: str) -> bool:
        clean = name.strip()
        if not clean:
            return False
        if clean in self.courses:
            self.courses.remove(clean)
        self.courses.insert(0, clean)
        return self.save()

    def delete_course(self, name: str) -> bool:
        clean = name.strip()
        if clean in self.courses:
            self.courses.remove(clean)
            return self.save()
        return False

    # -------------------------------------------------------------------------
    # Professor Presets
    # -------------------------------------------------------------------------
    def get_professors(self) -> List[str]:
        return list(self.professors)

    def save_professor(self, name: str) -> bool:
        clean = name.strip()
        if not clean:
            return False
        if clean in self.professors:
            self.professors.remove(clean)
        self.professors.insert(0, clean)
        return self.save()

    def delete_professor(self, name: str) -> bool:
        clean = name.strip()
        if clean in self.professors:
            self.professors.remove(clean)
            return self.save()
        return False
