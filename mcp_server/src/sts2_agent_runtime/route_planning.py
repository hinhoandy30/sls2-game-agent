from __future__ import annotations

from collections import Counter
from typing import Any

DEFAULT_ROUTE_LIMIT = 128
DEFAULT_REPRESENTATIVE_ROUTES_PER_GROUP = 3


def build_route_planning_payload(
    raw_state: dict[str, Any],
    legal_actions: list[dict[str, Any]],
    *,
    route_limit: int = DEFAULT_ROUTE_LIMIT,
    include_route_candidates: bool = True,
    representative_routes_per_group: int = DEFAULT_REPRESENTATIVE_ROUTES_PER_GROUP,
) -> dict[str, Any] | None:
    map_payload = raw_state.get("map")
    if not isinstance(map_payload, dict):
        return None

    available_nodes = [node for node in map_payload.get("available_nodes") or [] if isinstance(node, dict)]
    if not available_nodes:
        return None

    nodes = [_normalize_graph_node(node) for node in map_payload.get("nodes") or [] if isinstance(node, dict)]
    graph = {node["node_id"]: node for node in nodes if node.get("node_id")}
    current_node_id = _coord_payload_to_node_id(map_payload.get("current_node"))
    available_node_ids = [_option_node_id(node) for node in available_nodes]
    visited_prefix = _visited_prefix(nodes, current_node_id)
    action_ids_by_node = _legal_action_ids_by_node(legal_actions)

    routes: list[list[dict[str, Any]]] = []
    for available_node, next_node_id in zip(available_nodes, available_node_ids, strict=False):
        if not next_node_id:
            continue
        start_node = graph.get(next_node_id) or _option_as_graph_node(available_node)
        _dfs_routes(start_node, graph, [start_node], routes, route_limit)
        if len(routes) >= route_limit:
            break

    route_candidates = []
    for index, path in enumerate(routes[:route_limit]):
        next_node = path[0]
        next_node_id = str(next_node["node_id"])
        route_candidates.append(
            _summarize_route(
                path,
                index=index,
                current_node_id=current_node_id,
                next_legal_action_id=action_ids_by_node.get(next_node_id),
                visited_prefix=visited_prefix,
            )
        )

    payload = {
        "schema_version": "route-planning.v1",
        "map_generation_count": map_payload.get("map_generation_count"),
        "current_node_id": current_node_id,
        "available_node_ids": [node_id for node_id in available_node_ids if node_id],
        "route_count": len(routes),
        "routes_omitted": max(0, len(routes) - len(route_candidates)),
        "counting_rule": "remaining_sequence and remaining_counts include only future nodes from the next move to the boss/leaf.",
        "visited_prefix": visited_prefix,
        "route_groups": _summarize_route_groups(route_candidates, representative_routes_per_group),
    }
    if include_route_candidates:
        payload["route_candidates"] = route_candidates
    return payload


def _normalize_graph_node(node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or _row_col_to_node_id(node.get("row"), node.get("col")) or "")
    child_ids = [
        str(child_id)
        for child_id in node.get("child_node_ids") or []
        if child_id is not None and str(child_id)
    ]
    if not child_ids:
        child_ids = [
            node_id
            for child in node.get("children") or []
            if (node_id := _coord_payload_to_node_id(child))
        ]

    return {
        "node_id": node_id,
        "row": node.get("row"),
        "col": node.get("col"),
        "node_type": str(node.get("node_type") or "Unknown"),
        "state": node.get("state"),
        "visited": bool(node.get("visited")),
        "is_current": bool(node.get("is_current")),
        "is_boss": bool(node.get("is_boss")),
        "is_second_boss": bool(node.get("is_second_boss")),
        "children": child_ids,
    }


def _option_as_graph_node(option: dict[str, Any]) -> dict[str, Any]:
    node_id = _option_node_id(option) or "unknown"
    return {
        "node_id": node_id,
        "row": option.get("row"),
        "col": option.get("col"),
        "node_type": str(option.get("node_type") or "Unknown"),
        "state": option.get("state"),
        "visited": False,
        "is_current": False,
        "is_boss": False,
        "is_second_boss": False,
        "children": [],
    }


def _dfs_routes(
    node: dict[str, Any],
    graph: dict[str, dict[str, Any]],
    path: list[dict[str, Any]],
    routes: list[list[dict[str, Any]]],
    route_limit: int,
) -> None:
    if len(routes) >= route_limit:
        return
    child_ids = [child_id for child_id in node.get("children") or [] if child_id in graph]
    if node.get("is_boss") or node.get("is_second_boss") or not child_ids:
        routes.append(path)
        return
    for child_id in sorted(child_ids, key=_node_id_sort_key):
        if any(existing.get("node_id") == child_id for existing in path):
            continue
        child = graph[child_id]
        _dfs_routes(child, graph, [*path, child], routes, route_limit)


def _summarize_route(
    path: list[dict[str, Any]],
    *,
    index: int,
    current_node_id: str | None,
    next_legal_action_id: str | None,
    visited_prefix: list[dict[str, Any]],
) -> dict[str, Any]:
    sequence = [str(node.get("node_type") or "Unknown") for node in path]
    counts = Counter(_count_key(node_type) for node_type in sequence)
    remaining_path = [
        {
            "node_id": node.get("node_id"),
            "row": node.get("row"),
            "col": node.get("col"),
            "node_type": node.get("node_type"),
        }
        for node in path
    ]

    prefix_ids = [str(node["node_id"]) for node in visited_prefix if node.get("node_id")]
    remaining_ids = [str(node["node_id"]) for node in path if node.get("node_id")]
    return {
        "route_id": f"route_{index:04d}_from_{current_node_id or 'unknown'}",
        "origin_route_key": "->".join([*prefix_ids, *remaining_ids]),
        "next_node_id": remaining_ids[0] if remaining_ids else None,
        "next_legal_action_id": next_legal_action_id,
        "remaining_sequence": sequence,
        "remaining_path": remaining_path,
        "remaining_counts": {
            "monster": counts["monster"],
            "elite": counts["elite"],
            "event": counts["event"],
            "shop": counts["shop"],
            "rest": counts["rest"],
            "treasure": counts["treasure"],
            "boss": counts["boss"],
            "unknown": counts["unknown"],
        },
        "features": {
            "first_elite_in_steps": _first_index(sequence, "elite"),
            "rest_before_first_elite": _type_before(sequence, "rest", "elite"),
            "shop_before_first_elite": _type_before(sequence, "shop", "elite"),
            "max_consecutive_monsters": _max_consecutive(sequence, {"monster"}),
        },
    }


def _summarize_route_groups(route_candidates: list[dict[str, Any]], representative_limit: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for candidate in route_candidates:
        next_node_id = str(candidate.get("next_node_id") or "unknown")
        groups.setdefault(next_node_id, []).append(candidate)

    route_groups = []
    for next_node_id in sorted(groups, key=_node_id_sort_key):
        candidates = groups[next_node_id]
        first = candidates[0]
        route_groups.append(
            {
                "next_node_id": next_node_id,
                "next_legal_action_id": first.get("next_legal_action_id"),
                "next_node_type": (first.get("remaining_path") or [{}])[0].get("node_type"),
                "route_count": len(candidates),
                "count_ranges": _count_ranges(candidates),
                "key_features": _group_features(candidates),
                "representative_routes": _representative_routes(candidates, representative_limit),
            }
        )
    return route_groups


def _count_ranges(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ranges: dict[str, dict[str, Any]] = {}
    for key in ("monster", "elite", "rest", "shop", "event", "treasure", "boss"):
        values = [
            int((candidate.get("remaining_counts") or {}).get(key) or 0)
            for candidate in candidates
        ]
        ranges[key] = {
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "values": sorted(set(values)),
        }
    return ranges


def _group_features(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    first_elite_steps = [
        int((candidate.get("features") or {}).get("first_elite_in_steps"))
        for candidate in candidates
        if isinstance((candidate.get("features") or {}).get("first_elite_in_steps"), int)
    ]
    rest_before = [bool((candidate.get("features") or {}).get("rest_before_first_elite")) for candidate in candidates]
    shop_before = [bool((candidate.get("features") or {}).get("shop_before_first_elite")) for candidate in candidates]
    max_monsters = [
        int((candidate.get("features") or {}).get("max_consecutive_monsters") or 0)
        for candidate in candidates
    ]
    return {
        "first_elite_in_steps_range": _range_or_none(first_elite_steps),
        "has_elite_free_route": any(((candidate.get("remaining_counts") or {}).get("elite") or 0) == 0 for candidate in candidates),
        "rest_before_first_elite_any": any(rest_before),
        "rest_before_first_elite_all": all(rest_before) if rest_before else False,
        "shop_before_first_elite_any": any(shop_before),
        "shop_before_first_elite_all": all(shop_before) if shop_before else False,
        "max_consecutive_monsters_range": _range_or_none(max_monsters),
    }


def _representative_routes(candidates: list[dict[str, Any]], representative_limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_signatures: set[tuple[Any, ...]] = set()
    for candidate in sorted(candidates, key=_representative_sort_key):
        signature = (
            tuple((candidate.get("remaining_counts") or {}).get(key) for key in ("elite", "rest", "shop", "monster", "event")),
            tuple(candidate.get("remaining_sequence") or []),
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        selected.append(
            {
                "route_id": candidate.get("route_id"),
                "remaining_sequence": candidate.get("remaining_sequence"),
                "remaining_counts": candidate.get("remaining_counts"),
                "features": candidate.get("features"),
            }
        )
        if len(selected) >= representative_limit:
            break
    return selected


def _representative_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, int, str]:
    counts = candidate.get("remaining_counts") or {}
    features = candidate.get("features") or {}
    return (
        int(counts.get("elite") or 0),
        -int(counts.get("rest") or 0),
        -int(counts.get("shop") or 0),
        int(features.get("max_consecutive_monsters") or 0),
        str(candidate.get("route_id") or ""),
    )


def _range_or_none(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    return {"min": min(values), "max": max(values)}


def _visited_prefix(nodes: list[dict[str, Any]], current_node_id: str | None) -> list[dict[str, Any]]:
    visited = [
        {
            "node_id": node.get("node_id"),
            "row": node.get("row"),
            "col": node.get("col"),
            "node_type": node.get("node_type"),
        }
        for node in nodes
        if node.get("visited") and node.get("node_id") != current_node_id
    ]
    return sorted(visited, key=lambda node: (node.get("row") if isinstance(node.get("row"), int) else 999, node.get("col") if isinstance(node.get("col"), int) else 999))


def _legal_action_ids_by_node(legal_actions: list[dict[str, Any]]) -> dict[str, str]:
    by_node: dict[str, str] = {}
    for action in legal_actions:
        if action.get("action") != "choose_map_node" or not action.get("id"):
            continue
        node_id = str(action.get("node_id") or _row_col_to_node_id(action.get("row"), action.get("col")) or "")
        if node_id:
            by_node[node_id] = str(action["id"])
    return by_node


def _option_node_id(option: dict[str, Any]) -> str | None:
    return str(option.get("node_id") or _row_col_to_node_id(option.get("row"), option.get("col")) or "") or None


def _coord_payload_to_node_id(coord: Any) -> str | None:
    if not isinstance(coord, dict):
        return None
    return _row_col_to_node_id(coord.get("row"), coord.get("col"))


def _row_col_to_node_id(row: Any, col: Any) -> str | None:
    if isinstance(row, int) and isinstance(col, int):
        return f"{row}:{col}"
    return None


def _node_id_sort_key(node_id: str) -> tuple[int, int, str]:
    try:
        row, col = node_id.split(":", 1)
        return int(row), int(col), node_id
    except ValueError:
        return 999, 999, node_id


def _count_key(node_type: str) -> str:
    normalized = node_type.lower()
    if "elite" in normalized:
        return "elite"
    if "monster" in normalized:
        return "monster"
    if "event" in normalized or "unknown" in normalized or normalized == "?":
        return "event"
    if "shop" in normalized or "merchant" in normalized:
        return "shop"
    if "rest" in normalized or "campfire" in normalized:
        return "rest"
    if "treasure" in normalized or "chest" in normalized:
        return "treasure"
    if "boss" in normalized or "ancient" in normalized:
        return "boss"
    return "unknown"


def _first_index(sequence: list[str], node_type: str) -> int | None:
    for index, item in enumerate(sequence, start=1):
        if _count_key(item) == node_type:
            return index
    return None


def _type_before(sequence: list[str], before: str, target: str) -> bool:
    target_index = _first_index(sequence, target)
    before_index = _first_index(sequence, before)
    return target_index is not None and before_index is not None and before_index < target_index


def _max_consecutive(sequence: list[str], target_types: set[str]) -> int:
    best = 0
    current = 0
    for node_type in sequence:
        if _count_key(node_type) in target_types:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best
