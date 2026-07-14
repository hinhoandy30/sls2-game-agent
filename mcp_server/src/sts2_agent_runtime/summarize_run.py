from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .contracts import GameStateSnapshot
from .legal_actions import build_legal_actions
from .route_planning import build_route_planning_payload


def summarize_run_dir(run_dir: Path) -> dict[str, Any]:
    rows = _read_jsonl(run_dir / "trajectory.jsonl")
    summary = _read_json(run_dir / "summary.json")
    decisions = [_summarize_step(index, row, rows) for index, row in enumerate(rows)]
    token_totals = _token_totals(decisions)
    return {
        "schema_version": "human-run-summary.v1",
        "run_dir": str(run_dir),
        "run_id": _infer_run_id(rows, summary),
        "seed": _infer_seed(rows, summary),
        "run_summary": summary,
        "step_count": len(rows),
        "token_totals": token_totals,
        "screen_counts": dict(Counter(item.get("screen") for item in decisions if item.get("screen"))),
        "decisions": decisions,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    run_summary = summary.get("run_summary") if isinstance(summary.get("run_summary"), dict) else {}
    lines = [
        "# STS2 Run Decision Summary",
        "",
        f"- Run dir: `{summary.get('run_dir')}`",
        f"- Run id: `{summary.get('run_id') or 'unknown'}`",
        f"- Seed: `{summary.get('seed') or 'unknown'}`",
        f"- Steps: {summary.get('step_count')}",
        f"- Result: {run_summary.get('result', 'unknown')} / {run_summary.get('terminal_reason', 'unknown')}",
        f"- Terminal screen: {run_summary.get('terminal_screen', 'unknown')}",
        f"- Token total: {summary.get('token_totals', {}).get('total_tokens', 0)}",
        "",
        "## Token Breakdown",
        "",
    ]
    token_totals = summary.get("token_totals") if isinstance(summary.get("token_totals"), dict) else {}
    for key, value in token_totals.items():
        if key == "by_agent":
            continue
        lines.append(f"- {key}: {value}")
    by_agent = token_totals.get("by_agent") if isinstance(token_totals.get("by_agent"), dict) else {}
    if by_agent:
        lines.extend(["", "By agent:"])
        for agent_name, usage in sorted(by_agent.items()):
            if not isinstance(usage, dict):
                continue
            lines.append(
                "- "
                f"{agent_name}: "
                f"total={usage.get('total_tokens', 0)}, "
                f"prompt={usage.get('prompt_tokens', 0)}, "
                f"completion={usage.get('completion_tokens', 0)}, "
                f"reasoning={usage.get('reasoning_tokens', 0)}, "
                f"cached={usage.get('cached_tokens', 0)}"
            )
    lines.extend(["", "## Decision Timeline", ""])

    for decision in summary.get("decisions") or []:
        lines.extend(_render_decision(decision))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_decision(decision: dict[str, Any]) -> list[str]:
    title = (
        f"### Step {decision.get('step_index')} | "
        f"{decision.get('screen')} | floor {decision.get('floor')} | "
        f"HP {decision.get('player_hp')}"
    )
    lines = [
        title,
        "",
        f"- Agent: {decision.get('agent') or 'heuristic'}",
        f"- Action: `{decision.get('action_summary')}`",
        f"- Reason: {decision.get('reason') or ''}",
    ]
    if decision.get("route_groups"):
        lines.append("- Route groups:")
        for group in decision["route_groups"]:
            lines.append(
                "  - "
                f"`{group.get('next_node_id')}` {group.get('next_node_type')} "
                f"routes={group.get('route_count')} "
                f"elite={_range_text(group, 'elite')} "
                f"rest={_range_text(group, 'rest')} "
                f"shop={_range_text(group, 'shop')} "
                f"monster={_range_text(group, 'monster')} "
                f"event={_range_text(group, 'event')} "
                f"action=`{group.get('next_legal_action_id')}`"
            )
    if decision.get("bundles"):
        lines.append("- Bundle options:")
        for bundle in decision["bundles"]:
            lines.append(f"  - option {bundle.get('index')}: {_bundle_cards_text(bundle)}")
    if decision.get("combat_audit"):
        audit = decision["combat_audit"]
        lines.append(
            "- Combat audit: "
            f"lethal={audit.get('lethal_this_turn')} "
            f"defense={audit.get('defense_posture')} "
            f"{audit.get('risk_summary_zh')}"
        )
    if decision.get("llm"):
        llm = decision["llm"]
        usage = llm.get("usage") if isinstance(llm.get("usage"), dict) else {}
        lines.append(
            "- LLM: "
            f"{llm.get('model')} "
            f"{usage.get('total_tokens', 0)} tokens "
            f"({llm.get('duration_seconds', 0):.2f}s)"
        )
    if decision.get("error"):
        lines.append(f"- Error: `{decision.get('error')}`")
    return lines


def _summarize_step(index: int, row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
    metadata = decision.get("metadata") if isinstance(decision.get("metadata"), dict) else {}
    agent = metadata.get("agent") if isinstance(metadata.get("agent"), dict) else {}
    state_summary = row.get("state_summary") if isinstance(row.get("state_summary"), dict) else {}
    llm = metadata.get("llm") if isinstance(metadata.get("llm"), dict) else {}
    return {
        "step_index": row.get("step_index"),
        "segment_id": row.get("segment_id"),
        "screen": row.get("screen_before"),
        "floor": state_summary.get("floor"),
        "player_hp": state_summary.get("player_hp"),
        "turn": state_summary.get("turn"),
        "agent": agent.get("name"),
        "reason": decision.get("reason"),
        "action_summary": _action_summary(row.get("action_request")),
        "route_groups": _route_groups_for_step(index, row, rows),
        "bundles": _bundles_for_step(index, row, rows),
        "combat_audit": metadata.get("combat_audit") if isinstance(metadata.get("combat_audit"), dict) else None,
        "llm": llm or None,
        "error": row.get("error"),
    }


def _action_summary(action_request: Any) -> str:
    if not isinstance(action_request, dict):
        return ""
    if isinstance(action_request.get("action_plan"), list):
        return " -> ".join(_single_action_summary(item) for item in action_request["action_plan"] if isinstance(item, dict))
    return _single_action_summary(action_request)


def _single_action_summary(action: dict[str, Any]) -> str:
    legal_action_id = action.get("legal_action_id")
    if legal_action_id:
        return str(legal_action_id)
    name = action.get("action") or "unknown"
    pieces = [str(name)]
    for key in ("card_index", "target_index", "option_index"):
        if action.get(key) is not None:
            pieces.append(f"{key}={action[key]}")
    return " ".join(pieces)


def _route_groups_for_step(index: int, row: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    state_summary = row.get("state_summary") if isinstance(row.get("state_summary"), dict) else {}
    route_planning = state_summary.get("route_planning") if isinstance(state_summary.get("route_planning"), dict) else None
    if route_planning and isinstance(route_planning.get("route_groups"), list):
        return _compact_route_groups(route_planning["route_groups"])

    if row.get("screen_before") != "MAP" or index <= 0:
        return []
    previous_state = ((rows[index - 1].get("action_result") or {}).get("state") or {})
    if not isinstance(previous_state, dict) or previous_state.get("screen") != "MAP":
        return []
    try:
        snapshot = GameStateSnapshot.from_raw({"ok": True, "data": previous_state}, source="summary")
        route_planning = build_route_planning_payload(previous_state, build_legal_actions(snapshot), include_route_candidates=False)
    except Exception:
        return []
    if not route_planning:
        return []
    return _compact_route_groups(route_planning.get("route_groups") or [])


def _bundles_for_step(index: int, row: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    state_summary = row.get("state_summary") if isinstance(row.get("state_summary"), dict) else {}
    bundles = state_summary.get("bundles")
    if isinstance(bundles, list) and bundles:
        return _compact_bundles(bundles)

    if row.get("screen_before") != "BUNDLE_SELECTION" or index <= 0:
        return []
    previous_state = ((rows[index - 1].get("action_result") or {}).get("state") or {})
    if not isinstance(previous_state, dict) or previous_state.get("screen") != "BUNDLE_SELECTION":
        return []
    return _compact_bundles(previous_state.get("bundles"))


def _compact_bundles(bundles: Any) -> list[dict[str, Any]]:
    if not isinstance(bundles, list):
        return []
    compact: list[dict[str, Any]] = []
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        cards: list[dict[str, Any]] = []
        for card in bundle.get("cards") or []:
            if not isinstance(card, dict):
                continue
            cards.append(
                {
                    "index": card.get("index"),
                    "card_id": card.get("card_id"),
                    "name": card.get("name"),
                    "card_type": card.get("card_type"),
                    "rarity": card.get("rarity"),
                    "energy_cost": card.get("energy_cost"),
                    "resolved_rules_text": card.get("resolved_rules_text"),
                }
            )
        compact.append({"index": bundle.get("index"), "cards": cards})
    return compact


def _bundle_cards_text(bundle: dict[str, Any]) -> str:
    pieces: list[str] = []
    for card in bundle.get("cards") or []:
        if not isinstance(card, dict):
            continue
        cost = card.get("energy_cost")
        name = card.get("name") or card.get("card_id") or "unknown"
        text = card.get("resolved_rules_text") or ""
        pieces.append(f"{name} [{cost}费] {text}".strip())
    return "；".join(pieces)


def _compact_route_groups(groups: list[Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        compact.append(
            {
                "next_node_id": group.get("next_node_id"),
                "next_legal_action_id": group.get("next_legal_action_id"),
                "next_node_type": group.get("next_node_type"),
                "route_count": group.get("route_count"),
                "count_ranges": group.get("count_ranges"),
                "key_features": group.get("key_features"),
                "representative_sequences": [
                    route.get("remaining_sequence")
                    for route in group.get("representative_routes") or []
                    if isinstance(route, dict)
                ][:2],
            }
        )
    return compact


def _range_text(group: dict[str, Any], key: str) -> str:
    ranges = group.get("count_ranges") if isinstance(group.get("count_ranges"), dict) else {}
    value = ranges.get(key) if isinstance(ranges.get(key), dict) else {}
    if value.get("min") == value.get("max"):
        return str(value.get("min", "?"))
    return f"{value.get('min', '?')}-{value.get('max', '?')}"


def _token_totals(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, int] = defaultdict(int)
    by_agent: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for decision in decisions:
        llm = decision.get("llm") if isinstance(decision.get("llm"), dict) else {}
        usage = llm.get("usage") if isinstance(llm.get("usage"), dict) else {}
        agent = str(decision.get("agent") or "unknown")
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
                by_agent[agent][key] += value
    return {**dict(totals), "by_agent": {agent: dict(values) for agent, values in by_agent.items()}}


def _infer_run_id(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str | None:
    candidates: list[Any] = [summary.get("run_id")]
    for row in rows:
        candidates.append(row.get("run_id"))
        state = ((row.get("action_result") or {}).get("state") or {})
        if isinstance(state, dict):
            candidates.append(state.get("run_id"))
        raw_state = (((row.get("raw") or {}).get("data") or {}).get("state") or {})
        if isinstance(raw_state, dict):
            candidates.append(raw_state.get("run_id"))
    for value in candidates:
        if isinstance(value, str) and value and value != "run_unknown":
            return value
    return None


def _infer_seed(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str | None:
    for key in ("seed", "run_seed"):
        value = summary.get(key)
        if isinstance(value, str) and value:
            return value
    for row in rows:
        action = row.get("action_request") if isinstance(row.get("action_request"), dict) else {}
        seed = action.get("seed") or ((action.get("payload") or {}).get("seed") if isinstance(action.get("payload"), dict) else None)
        if isinstance(seed, str) and seed:
            return seed
        state = ((row.get("action_result") or {}).get("state") or {})
        seed = _seed_from_state(state)
        if seed:
            return seed
        raw_state = (((row.get("raw") or {}).get("data") or {}).get("state") or {})
        seed = _seed_from_state(raw_state)
        if seed:
            return seed
    run_id = _infer_run_id(rows, summary)
    return run_id


def _seed_from_state(state: Any) -> str | None:
    if not isinstance(state, dict):
        return None
    character_select = state.get("character_select") if isinstance(state.get("character_select"), dict) else {}
    seed = character_select.get("seed")
    if isinstance(seed, str) and seed:
        return seed
    run_id = state.get("run_id")
    if isinstance(run_id, str) and run_id and run_id != "run_unknown":
        return run_id
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize an STS2 agent run directory for humans.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", type=Path, help="Write summary to this file instead of stdout.")
    args = parser.parse_args(argv)

    summary = summarize_run_dir(args.run_dir)
    content = (
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else render_markdown(summary)
    )
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
