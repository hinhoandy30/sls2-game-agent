from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent_context import DeckAssessment, ExperienceContext, ExperienceLesson
from .contracts import GameStateSnapshot


class ExperienceRepository:
    """Filesystem-backed strategy experience. Curated game facts live elsewhere."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path.cwd() / "agent_knowledge" / "experience" / "v1"
        self.lessons_dir = self.root_dir / "lessons"

    def save_lessons(self, lessons: list[ExperienceLesson]) -> list[Path]:
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for lesson in lessons:
            path = self.lessons_dir / f"{_safe_filename(lesson.lesson_id)}.json"
            path.write_text(json.dumps(lesson.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written.append(path)
        return written

    def retrieve(self, state: GameStateSnapshot, assessment: DeckAssessment, *, limit: int = 3) -> ExperienceContext:
        lessons = [lesson for lesson in self._load_lessons() if _matches(lesson, state, assessment)]
        lessons.sort(key=lambda lesson: (lesson.status != "active", -lesson.confidence, lesson.lesson_id))
        selected = lessons[:limit]
        return ExperienceContext(lesson_ids=[lesson.lesson_id for lesson in selected], lessons=[lesson.to_prompt_entry() for lesson in selected])

    def _load_lessons(self) -> list[ExperienceLesson]:
        if not self.lessons_dir.is_dir():
            return []
        lessons: list[ExperienceLesson] = []
        for path in sorted(self.lessons_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                lessons.append(ExperienceLesson.model_validate(payload))
            except (OSError, ValueError):
                continue
        return lessons


def _matches(lesson: ExperienceLesson, state: GameStateSnapshot, assessment: DeckAssessment) -> bool:
    if lesson.status == "rejected":
        return False
    scope = lesson.scope
    run = state.state.get("run") if isinstance(state.state.get("run"), dict) else {}
    character_id = str(run.get("character_id") or "")
    floor = run.get("floor")
    if scope.character_id and scope.character_id != character_id:
        return False
    if scope.screens and state.screen not in scope.screens:
        return False
    if isinstance(scope.min_floor, int) and (not isinstance(floor, int) or floor < scope.min_floor):
        return False
    if isinstance(scope.max_floor, int) and (not isinstance(floor, int) or floor > scope.max_floor):
        return False
    if scope.deck_tags_any and not set(scope.deck_tags_any).intersection(assessment.deck_tags):
        return False
    return True


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe[:120] or "lesson"
