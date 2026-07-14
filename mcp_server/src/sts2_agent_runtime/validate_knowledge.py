from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from .knowledge import CardKnowledgeFile, CardPriorityKnowledgeFile, EventKnowledgeFile, MonsterKnowledgeFile


def validate_knowledge_root(root_dir: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_category(root_dir / "monsters", MonsterKnowledgeFile, "enemy_id"))
    errors.extend(_validate_category(root_dir / "events", EventKnowledgeFile, "event_id"))
    errors.extend(_validate_category(root_dir / "cards", CardKnowledgeFile, "card_id"))
    errors.extend(_validate_category(root_dir / "strategy" / "card_priorities", CardPriorityKnowledgeFile, "card_id"))
    return errors


def _validate_category(
    root_dir: Path,
    model_type: type[MonsterKnowledgeFile] | type[EventKnowledgeFile] | type[CardKnowledgeFile] | type[CardPriorityKnowledgeFile],
    id_field: str,
) -> list[str]:
    errors: list[str] = []
    if not root_dir.exists():
        return [f"{root_dir}: directory does not exist"]
    for path in sorted(root_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        try:
            parsed = model_type.model_validate(data)
        except PydanticValidationError as exc:
            errors.append(f"{path}: schema validation failed: {exc}")
            continue
        entry_id = getattr(parsed, id_field)
        if path.stem != entry_id:
            errors.append(f"{path}: filename must match {id_field} {entry_id!r}")
        errors.extend(_validate_sources(path, data))
    return errors


def _validate_sources(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for index, source in enumerate(data.get("sources") or []):
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if isinstance(url, str) and url.startswith("https://example.invalid"):
            errors.append(f"{path}: sources[{index}].url still uses the template placeholder")
        retrieved_at = source.get("retrieved_at")
        if isinstance(retrieved_at, str) and retrieved_at == "YYYY-MM-DD":
            errors.append(f"{path}: sources[{index}].retrieved_at still uses the template placeholder")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate STS2 runtime knowledge JSON files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "knowledge" / "v1",
        help="Knowledge v1 root directory.",
    )
    args = parser.parse_args(argv)

    errors = validate_knowledge_root(args.root)
    if errors:
        print("Knowledge validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Knowledge validation passed: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
