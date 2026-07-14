from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent_context import ExperienceLesson
from .contracts import RunSummary
from .llm import OpenAICompatiblePolicy, _parse_json_object


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["strategy", "runtime", "information"]
    severity: Literal["high", "medium", "low"]
    finding_zh: str = Field(min_length=1, max_length=700)
    evidence_step_indices: list[int] = Field(default_factory=list, max_length=12)


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["run-review.v1"] = "run-review.v1"
    run_id: str
    outcome_zh: str = Field(min_length=1, max_length=800)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=12)
    lessons: list[ExperienceLesson] = Field(default_factory=list, max_length=5)


@dataclass(slots=True)
class ReviewResult:
    report: ReviewReport
    llm_metadata: dict[str, Any]


class RunReviewAgent:
    """Offline-only reviewer. It reads artifacts and never receives a live client."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        max_retries: int = 2,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        self.policy = OpenAICompatiblePolicy(
            model=model,
            api_base=api_base,
            api_key=api_key,
            enable_action_plan=False,
            max_retries=max_retries,
            request_timeout_seconds=request_timeout_seconds,
            agent_name="run_review",
        )

    def review(self, run_dir: Path, summary: RunSummary) -> ReviewResult:
        review_input = {
            "packet": "run_review_input.v1",
            "summary": summary.to_dict(),
            "trajectory": _compact_jsonl(run_dir / "trajectory.jsonl", _compact_step),
            "contexts": _compact_jsonl(run_dir / "context.jsonl", lambda row: row),
        }
        content = json.dumps(review_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        prompt = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the STS2 run_review agent. Output exactly one JSON object. You do not control the game and must not invent evidence. "
                        "Separate strategy mistakes from runtime or information problems. Lessons are historical advice, not game facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Review this completed GAME_OVER run. Return schema: "
                        "{schema_version:'run-review.v1',run_id:string,outcome_zh:string,"
                        "findings:[{category:'strategy|runtime|information',severity:'high|medium|low',finding_zh:string,evidence_step_indices:number[]}],"
                        "lessons:[ExperienceLesson]}. Each lesson must include evidence with this run_id, a scope, recommendation, rationale, "
                        "counterexamples, confidence, and status='provisional'. Output JSON only.\n" + content
                    ),
                },
            ],
            "prompt_metadata": {
                "layout_version": "run-review-prompt.v1",
                "message_characters": {"input": len(content)},
            },
        }
        response = self.policy._chat(prompt)
        aggregate_metadata = dict(self.policy.last_call_metadata)
        parsed = self.policy._parse_or_repair_json(response, prompt, aggregate_metadata)
        report = ReviewReport.model_validate(parsed)
        if report.run_id != summary.run_id:
            raise ValueError(f"Review run_id {report.run_id!r} does not match completed run {summary.run_id!r}.")
        for lesson in report.lessons:
            if lesson.evidence.run_id != summary.run_id:
                raise ValueError(f"Lesson {lesson.lesson_id!r} references a different run.")
        return ReviewResult(report=report, llm_metadata=aggregate_metadata)


def _compact_jsonl(path: Path, compact: Any, *, limit: int = 220) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            row = json.loads(raw_line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(compact(row))
    return rows


def _compact_step(row: dict[str, Any]) -> dict[str, Any]:
    decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
    metadata = decision.get("metadata") if isinstance(decision.get("metadata"), dict) else {}
    return {
        "segment_id": row.get("segment_id"),
        "step_index": row.get("step_index"),
        "screen_before": row.get("screen_before"),
        "state_summary": row.get("state_summary"),
        "agent": metadata.get("agent"),
        "decision_type": decision.get("type"),
        "decision_reason": decision.get("reason"),
        "action_request": row.get("action_request"),
        "error": row.get("error"),
    }
