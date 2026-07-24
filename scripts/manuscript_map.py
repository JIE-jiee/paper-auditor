"""Validate a reviewer-authored manuscript traceability map.

This module is intentionally offline and dependency-free.  It validates a JSON
contract and, optionally, binds declared ``evidence_ids`` to an evidence-spine
ledger.  It never reads manuscript prose, guesses section roles, or decides
whether a scientific claim is true.  Those remain semantic-review tasks.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "0.1.0"
ARTIFACT_TYPE = "manuscript_map"
VALIDATION_ARTIFACT_TYPE = "manuscript_map_validation"
VALID_COMPLETION_MODES = {"draft", "complete"}
VALID_LEDGER_TEXT_MODES = {"excerpt", "hash-only"}

NODE_ROLES = {
    "title",
    "central_message",
    "research_context",
    "gap",
    "research_question",
    "objective",
    "hypothesis",
    "method",
    "result",
    "interpretation",
    "figure_table",
    "discussion",
    "limitation",
    "conclusion",
    "abstract_claim",
    "citation_claim",
}
NODE_ROLE_ALIASES = {"visual": "figure_table"}
ENTRY_ROLES = ("research_question", "objective", "hypothesis")
REQUIRED_COMPLETE_ROLES = ("gap", "method", "result", "interpretation", "conclusion")
CRITICAL_ROLES = (*REQUIRED_COMPLETE_ROLES, *ENTRY_ROLES)

NODE_STATUSES = {
    "planned",
    "not_yet_written",
    "drafted",
    "verified",
    "needs_review",
    "not_applicable",
}
EDGE_STATUSES = {
    "planned",
    "not_yet_written",
    "mapped",
    "verified",
    "needs_review",
    "not_applicable",
}
ACTIVE_NODE_STATUSES = {"drafted", "verified", "needs_review"}
ACTIVE_EDGE_STATUSES = {"mapped", "verified", "needs_review"}
UNFINISHED_STATUSES = {"planned", "not_yet_written", "not_applicable"}

RELATIONS = {
    "frames",
    "motivates",
    "addressed_by",
    "produces",
    "evidences",
    "interpreted_by",
    "supports",
    "bounds",
    "summarizes",
    "grounded_in",
    "aligns_with",
    "depends_on",
    "contradicts",
}

# Only relations with a stable directional meaning are constrained here.
# Generic relations remain available for reviewer-authored, paper-specific maps.
RELATION_ROLE_RULES: dict[str, set[tuple[str, str]]] = {
    "frames": {
        ("title", "central_message"),
        ("title", "objective"),
        ("title", "result"),
        ("central_message", "objective"),
        ("central_message", "result"),
        ("central_message", "conclusion"),
    },
    "motivates": {
        ("research_context", "gap"),
        ("citation_claim", "gap"),
        ("gap", "research_question"),
        ("gap", "objective"),
        ("gap", "hypothesis"),
        ("research_question", "objective"),
    },
    "addressed_by": {
        ("research_question", "method"),
        ("objective", "method"),
        ("hypothesis", "method"),
    },
    "produces": {("method", "result")},
    "evidences": {
        ("figure_table", "result"),
        ("figure_table", "discussion"),
        ("figure_table", "conclusion"),
        ("result", "abstract_claim"),
    },
    "interpreted_by": {("result", "interpretation"), ("result", "discussion")},
    "bounds": {
        ("limitation", "discussion"),
        ("limitation", "conclusion"),
        ("limitation", "central_message"),
        ("limitation", "abstract_claim"),
    },
}

CORE_TRANSITIONS: tuple[tuple[set[str], set[str], set[str]], ...] = (
    ({"gap"}, set(ENTRY_ROLES), {"motivates"}),
    (set(ENTRY_ROLES), {"method"}, {"addressed_by"}),
    ({"method"}, {"result"}, {"produces"}),
    ({"result"}, {"interpretation"}, {"interpreted_by"}),
    ({"interpretation"}, {"conclusion"}, {"supports"}),
)

ROOT_REQUIRED = {"schema_version", "artifact_type", "manuscript_map"}
ROOT_ALLOWED = set(ROOT_REQUIRED)
MAP_REQUIRED = {"map_id", "manuscript_stage", "card", "nodes", "edges"}
MAP_ALLOWED = set(MAP_REQUIRED)
CARD_REQUIRED = {
    "target_journal",
    "article_type",
    "research_question",
    "central_message",
    "scope_boundaries",
}
CARD_ALLOWED = set(CARD_REQUIRED)
NODE_REQUIRED = {
    "id",
    "role",
    "label",
    "status",
    "summary",
    "section",
    "evidence_ids",
}
NODE_ALLOWED = set(NODE_REQUIRED)
EDGE_REQUIRED = {
    "id",
    "from",
    "to",
    "relation",
    "status",
    "rationale",
    "evidence_ids",
}
EDGE_ALLOWED = set(EDGE_REQUIRED)

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
EVIDENCE_ID_PATTERN = re.compile(r"^EVD-[A-F0-9]{16}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class ManuscriptMapError(RuntimeError):
    """Raised for unsafe I/O or an unusable command input."""


def manuscript_map_template(stage: str = "draft") -> dict[str, Any]:
    """Return a new, deterministic blank manuscript-map template."""

    if stage not in VALID_COMPLETION_MODES:
        raise ManuscriptMapError(f"未知稿件阶段：{stage}")
    node_status = "planned" if stage == "draft" else "not_yet_written"
    edge_status = "planned" if stage == "draft" else "not_yet_written"
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "manuscript_map": {
            "map_id": "MAP-001",
            "manuscript_stage": stage,
            "card": {
                "target_journal": "",
                "article_type": "",
                "research_question": "",
                "central_message": "",
                "scope_boundaries": [],
            },
            "nodes": [
                {
                    "id": "GAP-001",
                    "role": "gap",
                    "label": "Research gap",
                    "status": node_status,
                    "summary": "",
                    "section": "Introduction",
                    "evidence_ids": [],
                },
                {
                    "id": "OBJ-001",
                    "role": "objective",
                    "label": "Study objective",
                    "status": node_status,
                    "summary": "",
                    "section": "Introduction",
                    "evidence_ids": [],
                },
                {
                    "id": "MTH-001",
                    "role": "method",
                    "label": "Method or study design",
                    "status": node_status,
                    "summary": "",
                    "section": "Methods",
                    "evidence_ids": [],
                },
                {
                    "id": "RES-001",
                    "role": "result",
                    "label": "Principal result",
                    "status": node_status,
                    "summary": "",
                    "section": "Results",
                    "evidence_ids": [],
                },
                {
                    "id": "INT-001",
                    "role": "interpretation",
                    "label": "Bounded interpretation",
                    "status": node_status,
                    "summary": "",
                    "section": "Discussion",
                    "evidence_ids": [],
                },
                {
                    "id": "CON-001",
                    "role": "conclusion",
                    "label": "Bounded conclusion",
                    "status": node_status,
                    "summary": "",
                    "section": "Conclusions",
                    "evidence_ids": [],
                },
            ],
            "edges": [
                {
                    "id": "EDGE-001",
                    "from": "GAP-001",
                    "to": "OBJ-001",
                    "relation": "motivates",
                    "status": edge_status,
                    "rationale": "",
                    "evidence_ids": [],
                },
                {
                    "id": "EDGE-002",
                    "from": "OBJ-001",
                    "to": "MTH-001",
                    "relation": "addressed_by",
                    "status": edge_status,
                    "rationale": "",
                    "evidence_ids": [],
                },
                {
                    "id": "EDGE-003",
                    "from": "MTH-001",
                    "to": "RES-001",
                    "relation": "produces",
                    "status": edge_status,
                    "rationale": "",
                    "evidence_ids": [],
                },
                {
                    "id": "EDGE-004",
                    "from": "RES-001",
                    "to": "INT-001",
                    "relation": "interpreted_by",
                    "status": edge_status,
                    "rationale": "",
                    "evidence_ids": [],
                },
                {
                    "id": "EDGE-005",
                    "from": "INT-001",
                    "to": "CON-001",
                    "relation": "supports",
                    "status": edge_status,
                    "rationale": "",
                    "evidence_ids": [],
                },
            ],
        },
    }


def _issue(
    destination: list[dict[str, str]],
    code: str,
    path: str,
    message: str,
) -> None:
    destination.append({"code": code, "path": path, "message": message})


def _check_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    path: str,
    errors: list[dict[str, str]],
) -> None:
    for key in sorted(required - set(value)):
        _issue(errors, "missing_field", f"{path}.{key}", "缺少必需字段。")
    for key in sorted(set(value) - allowed):
        _issue(errors, "unknown_field", f"{path}.{key}", "严格合约不接受该字段。")


def _check_string(
    value: Any,
    *,
    path: str,
    errors: list[dict[str, str]],
    allow_empty: bool,
) -> str | None:
    if not isinstance(value, str):
        _issue(errors, "invalid_type", path, "该字段必须是字符串。")
        return None
    if not allow_empty and not value.strip():
        _issue(errors, "empty_string", path, "该字段不能为空。")
        return None
    return value


def _validate_evidence_ids(
    value: Any,
    *,
    path: str,
    errors: list[dict[str, str]],
    references: list[tuple[str, str]],
) -> list[str]:
    if not isinstance(value, list):
        _issue(errors, "invalid_type", path, "evidence_ids 必须是数组。")
        return []
    accepted: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str) or not EVIDENCE_ID_PATTERN.fullmatch(item):
            _issue(
                errors,
                "invalid_evidence_id",
                item_path,
                "证据 ID 必须使用 EVD- 加 16 位大写十六进制字符。",
            )
            continue
        if item in seen:
            _issue(
                errors,
                "duplicate_evidence_id",
                item_path,
                "同一节点或边不能重复列出相同 evidence_id。",
            )
            continue
        seen.add(item)
        accepted.append(item)
        references.append((item, item_path))
    return accepted


def ledger_fingerprint(ledger: Mapping[str, Any]) -> str:
    """Recompute the evidence-spine fingerprint from its stable projection."""

    projection = {
        "schema_version": ledger.get("schema_version"),
        "paper_id": ledger.get("paper_id"),
        "input_fingerprint": ledger.get("input_fingerprint"),
        "text_mode": ledger.get("text_mode"),
        "dependencies": ledger.get("dependencies", []),
        "sources": ledger.get("sources", []),
        "evidence": ledger.get("evidence", []),
    }
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _ledger_index(
    ledger: Mapping[str, Any],
    errors: list[dict[str, str]],
) -> tuple[set[str], str | None, str | None]:
    if ledger.get("schema_version") != SCHEMA_VERSION:
        _issue(
            errors,
            "invalid_ledger_schema_version",
            "$ledger.schema_version",
            f"evidence ledger schema_version 必须为 {SCHEMA_VERSION}。",
        )
    paper_id = ledger.get("paper_id")
    if not isinstance(paper_id, str) or not paper_id.strip():
        _issue(
            errors,
            "invalid_ledger_paper_id",
            "$ledger.paper_id",
            "evidence ledger paper_id 必须是非空字符串。",
        )
    input_fingerprint = ledger.get("input_fingerprint")
    if (
        not isinstance(input_fingerprint, str)
        or not SHA256_PATTERN.fullmatch(input_fingerprint)
    ):
        _issue(
            errors,
            "invalid_ledger_input_fingerprint",
            "$ledger.input_fingerprint",
            "ledger input_fingerprint 必须是 64 位小写十六进制 SHA-256。",
        )
        input_fingerprint = None
    text_mode = ledger.get("text_mode")
    if not isinstance(text_mode, str) or text_mode not in VALID_LEDGER_TEXT_MODES:
        _issue(
            errors,
            "invalid_ledger_text_mode",
            "$ledger.text_mode",
            "ledger text_mode 只能是 excerpt 或 hash-only。",
        )

    evidence = ledger.get("evidence")
    if not isinstance(evidence, list):
        _issue(
            errors,
            "invalid_ledger",
            "$ledger.evidence",
            "evidence ledger 必须包含 evidence 数组。",
        )
        return set(), None, None
    identifiers: set[str] = set()
    for index, item in enumerate(evidence):
        path = f"$ledger.evidence[{index}]"
        if not isinstance(item, Mapping):
            _issue(errors, "invalid_ledger_entry", path, "ledger evidence 项必须是对象。")
            continue
        identifier = item.get("evidence_id")
        if not isinstance(identifier, str) or not EVIDENCE_ID_PATTERN.fullmatch(identifier):
            _issue(
                errors,
                "invalid_ledger_evidence_id",
                f"{path}.evidence_id",
                "ledger evidence_id 格式无效。",
            )
            continue
        if identifier in identifiers:
            _issue(
                errors,
                "duplicate_ledger_evidence_id",
                f"{path}.evidence_id",
                "ledger 含重复 evidence_id。",
            )
            continue
        identifiers.add(identifier)
    fingerprint = ledger.get("ledger_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        _issue(
            errors,
            "missing_ledger_fingerprint",
            "$ledger.ledger_fingerprint",
            "提供的 evidence ledger 缺少 ledger_fingerprint。",
        )
        fingerprint = None
    elif fingerprint != ledger_fingerprint(ledger):
        _issue(
            errors,
            "stale_ledger_fingerprint",
            "$ledger.ledger_fingerprint",
            "ledger_fingerprint 与当前 dependencies、sources 或 evidence 稳定投影不一致。",
        )
        fingerprint = None
    return identifiers, fingerprint, input_fingerprint


def _node_role(node: Mapping[str, Any]) -> str:
    raw_role = node.get("role")
    if not isinstance(raw_role, str):
        return ""
    return NODE_ROLE_ALIASES.get(raw_role, raw_role)


def _declared_evidence_ids(item: Mapping[str, Any]) -> list[str]:
    raw_ids = item.get("evidence_ids")
    if not isinstance(raw_ids, list):
        return []
    return [
        value
        for value in raw_ids
        if isinstance(value, str) and EVIDENCE_ID_PATTERN.fullmatch(value)
    ]


def _evidence_is_ready(
    item: Mapping[str, Any],
    *,
    ledger_ids: set[str] | None,
    ledger_binding_valid: bool,
) -> bool:
    identifiers = _declared_evidence_ids(item)
    if not identifiers:
        return False
    return ledger_ids is None or (
        ledger_binding_valid and all(value in ledger_ids for value in identifiers)
    )


def _node_is_active(node: Mapping[str, Any]) -> bool:
    return node.get("status") in ACTIVE_NODE_STATUSES


def _edge_is_active(
    edge: Mapping[str, Any], node_by_id: Mapping[str, Mapping[str, Any]]
) -> bool:
    source = node_by_id.get(str(edge.get("from", "")))
    target = node_by_id.get(str(edge.get("to", "")))
    return (
        edge.get("status") in ACTIVE_EDGE_STATUSES
        and source is not None
        and target is not None
        and _node_is_active(source)
        and _node_is_active(target)
    )


def _node_is_complete_ready(
    node: Mapping[str, Any],
    *,
    ledger_ids: set[str] | None,
    ledger_binding_valid: bool,
) -> bool:
    return node.get("status") == "verified" and _evidence_is_ready(
        node,
        ledger_ids=ledger_ids,
        ledger_binding_valid=ledger_binding_valid,
    )


def _edge_is_complete_ready(
    edge: Mapping[str, Any],
    node_by_id: Mapping[str, Mapping[str, Any]],
    *,
    ledger_ids: set[str] | None,
    ledger_binding_valid: bool,
) -> bool:
    source = node_by_id.get(str(edge.get("from", "")))
    target = node_by_id.get(str(edge.get("to", "")))
    return (
        edge.get("status") == "verified"
        and source is not None
        and target is not None
        and _node_is_complete_ready(
            source,
            ledger_ids=ledger_ids,
            ledger_binding_valid=ledger_binding_valid,
        )
        and _node_is_complete_ready(
            target,
            ledger_ids=ledger_ids,
            ledger_binding_valid=ledger_binding_valid,
        )
        and _evidence_is_ready(
            edge,
            ledger_ids=ledger_ids,
            ledger_binding_valid=ledger_binding_valid,
        )
    )


def _core_chain_complete(
    node_by_id: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    require_verified: bool = False,
    ledger_ids: set[str] | None = None,
    ledger_binding_valid: bool = True,
) -> bool:
    current = {
        identifier
        for identifier, node in node_by_id.items()
        if _node_role(node) == "gap"
        and (
            _node_is_complete_ready(
                node,
                ledger_ids=ledger_ids,
                ledger_binding_valid=ledger_binding_valid,
            )
            if require_verified
            else _node_is_active(node)
        )
    }
    if not current:
        return False
    for source_roles, target_roles, allowed_relations in CORE_TRANSITIONS:
        next_nodes: set[str] = set()
        for edge in edges:
            edge_ready = (
                _edge_is_complete_ready(
                    edge,
                    node_by_id,
                    ledger_ids=ledger_ids,
                    ledger_binding_valid=ledger_binding_valid,
                )
                if require_verified
                else _edge_is_active(edge, node_by_id)
            )
            if not edge_ready:
                continue
            source_id = str(edge.get("from", ""))
            target_id = str(edge.get("to", ""))
            source = node_by_id.get(source_id, {})
            target = node_by_id.get(target_id, {})
            if (
                source_id in current
                and _node_role(source) in source_roles
                and _node_role(target) in target_roles
                and edge.get("relation") in allowed_relations
            ):
                next_nodes.add(target_id)
        if not next_nodes:
            return False
        current = next_nodes
    return True


def _display_node(node: Mapping[str, Any] | None, fallback: str) -> str:
    if not node:
        return fallback
    label = str(node.get("label", "")).strip()
    role = _node_role(node)
    identifier = str(node.get("id", fallback))
    return f"{identifier} · {role}" + (f" · {label}" if label else "")


def validate_manuscript_map(
    payload: Mapping[str, Any],
    *,
    ledger: Mapping[str, Any] | None = None,
    completion: str | None = None,
) -> dict[str, Any]:
    """Validate a map without mutating it or performing semantic review.

    ``completion`` may be ``draft`` or ``complete``.  When omitted, the value
    declared by ``manuscript_map.manuscript_stage`` is used.  Supplying a ledger
    additionally validates every declared evidence ID against that ledger.
    """

    if completion is not None and completion not in VALID_COMPLETION_MODES:
        raise ManuscriptMapError(f"未知完成模式：{completion}")
    if not isinstance(payload, Mapping):
        raise ManuscriptMapError("manuscript-map JSON 根节点必须是对象。")
    if ledger is not None and not isinstance(ledger, Mapping):
        raise ManuscriptMapError("evidence ledger JSON 根节点必须是对象。")

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    contract_gaps: list[dict[str, str]] = []
    references: list[tuple[str, str]] = []
    _check_keys(
        payload,
        required=ROOT_REQUIRED,
        allowed=ROOT_ALLOWED,
        path="$",
        errors=errors,
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        _issue(
            errors,
            "incompatible_schema_version",
            "$.schema_version",
            f"schema_version 必须为 {SCHEMA_VERSION}。",
        )
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        _issue(
            errors,
            "invalid_artifact_type",
            "$.artifact_type",
            f"artifact_type 必须为 {ARTIFACT_TYPE}。",
        )

    map_value = payload.get("manuscript_map")
    preserved_map = copy.deepcopy(map_value)
    if not isinstance(map_value, Mapping):
        _issue(
            errors,
            "invalid_type",
            "$.manuscript_map",
            "manuscript_map 必须是对象。",
        )
        map_value = {}
    _check_keys(
        map_value,
        required=MAP_REQUIRED,
        allowed=MAP_ALLOWED,
        path="$.manuscript_map",
        errors=errors,
    )

    map_id = _check_string(
        map_value.get("map_id"),
        path="$.manuscript_map.map_id",
        errors=errors,
        allow_empty=False,
    )
    if map_id is not None and not IDENTIFIER_PATTERN.fullmatch(map_id):
        _issue(
            errors,
            "invalid_identifier",
            "$.manuscript_map.map_id",
            "map_id 必须以字母开头，且只包含字母、数字、点、冒号、下划线或连字符。",
        )

    declared_stage = map_value.get("manuscript_stage")
    if declared_stage not in VALID_COMPLETION_MODES:
        _issue(
            errors,
            "invalid_manuscript_stage",
            "$.manuscript_map.manuscript_stage",
            "manuscript_stage 只能是 draft 或 complete。",
        )
    completion_mode = completion or (
        declared_stage if declared_stage in VALID_COMPLETION_MODES else "draft"
    )

    card = map_value.get("card")
    if not isinstance(card, Mapping):
        _issue(errors, "invalid_type", "$.manuscript_map.card", "card 必须是对象。")
        card = {}
    _check_keys(
        card,
        required=CARD_REQUIRED,
        allowed=CARD_ALLOWED,
        path="$.manuscript_map.card",
        errors=errors,
    )
    for field in ("target_journal", "article_type", "research_question", "central_message"):
        _check_string(
            card.get(field),
            path=f"$.manuscript_map.card.{field}",
            errors=errors,
            allow_empty=True,
        )
    boundaries = card.get("scope_boundaries")
    if not isinstance(boundaries, list):
        _issue(
            errors,
            "invalid_type",
            "$.manuscript_map.card.scope_boundaries",
            "scope_boundaries 必须是字符串数组。",
        )
    else:
        seen_boundaries: set[str] = set()
        for index, boundary in enumerate(boundaries):
            path = f"$.manuscript_map.card.scope_boundaries[{index}]"
            value = _check_string(
                boundary, path=path, errors=errors, allow_empty=False
            )
            if value is None:
                continue
            normalized = value.strip().casefold()
            if normalized in seen_boundaries:
                _issue(errors, "duplicate_scope_boundary", path, "研究范围边界重复。")
            seen_boundaries.add(normalized)

    nodes_value = map_value.get("nodes")
    if not isinstance(nodes_value, list):
        _issue(
            errors,
            "invalid_type",
            "$.manuscript_map.nodes",
            "nodes 必须是数组。",
        )
        nodes_value = []
    if not nodes_value:
        _issue(
            errors,
            "empty_nodes",
            "$.manuscript_map.nodes",
            "论文地图至少需要一个节点。",
        )

    node_by_id: dict[str, Mapping[str, Any]] = {}
    parsed_nodes: list[Mapping[str, Any]] = []
    for index, raw_node in enumerate(nodes_value):
        path = f"$.manuscript_map.nodes[{index}]"
        if not isinstance(raw_node, Mapping):
            _issue(errors, "invalid_node", path, "节点必须是对象。")
            continue
        _check_keys(
            raw_node,
            required=NODE_REQUIRED,
            allowed=NODE_ALLOWED,
            path=path,
            errors=errors,
        )
        identifier = _check_string(
            raw_node.get("id"),
            path=f"{path}.id",
            errors=errors,
            allow_empty=False,
        )
        if identifier is not None:
            if not IDENTIFIER_PATTERN.fullmatch(identifier):
                _issue(
                    errors,
                    "invalid_identifier",
                    f"{path}.id",
                    "节点 ID 格式无效。",
                )
            elif identifier in node_by_id:
                _issue(
                    errors,
                    "duplicate_node_id",
                    f"{path}.id",
                    f"节点 ID {identifier} 重复。",
                )
            else:
                node_by_id[identifier] = raw_node
        role = raw_node.get("role")
        normalized_role = _node_role(raw_node)
        if role in NODE_ROLE_ALIASES:
            _issue(
                warnings,
                "normalized_node_role",
                f"{path}.role",
                f"节点角色 {role} 按规范角色 {normalized_role} 校验；原始地图保持不变。",
            )
        elif normalized_role not in NODE_ROLES:
            _issue(
                errors,
                "invalid_node_role",
                f"{path}.role",
                f"未知节点角色：{role}",
            )
        status = raw_node.get("status")
        if status not in NODE_STATUSES:
            _issue(
                errors,
                "invalid_node_status",
                f"{path}.status",
                f"未知节点状态：{status}",
            )
        for field, allow_empty in (
            ("label", False),
            ("summary", True),
            ("section", True),
        ):
            _check_string(
                raw_node.get(field),
                path=f"{path}.{field}",
                errors=errors,
                allow_empty=allow_empty,
            )
        evidence_ids = _validate_evidence_ids(
            raw_node.get("evidence_ids"),
            path=f"{path}.evidence_ids",
            errors=errors,
            references=references,
        )
        if status == "verified" and not evidence_ids:
            _issue(
                contract_gaps,
                "verified_node_without_evidence",
                f"{path}.evidence_ids",
                "状态为 verified 的节点至少需要一个 evidence_id。",
            )
        parsed_nodes.append(raw_node)

    edges_value = map_value.get("edges")
    if not isinstance(edges_value, list):
        _issue(
            errors,
            "invalid_type",
            "$.manuscript_map.edges",
            "edges 必须是数组。",
        )
        edges_value = []

    parsed_edges: list[Mapping[str, Any]] = []
    edge_ids: set[str] = set()
    for index, raw_edge in enumerate(edges_value):
        path = f"$.manuscript_map.edges[{index}]"
        if not isinstance(raw_edge, Mapping):
            _issue(errors, "invalid_edge", path, "边必须是对象。")
            continue
        _check_keys(
            raw_edge,
            required=EDGE_REQUIRED,
            allowed=EDGE_ALLOWED,
            path=path,
            errors=errors,
        )
        identifier = _check_string(
            raw_edge.get("id"),
            path=f"{path}.id",
            errors=errors,
            allow_empty=False,
        )
        if identifier is not None:
            if not IDENTIFIER_PATTERN.fullmatch(identifier):
                _issue(errors, "invalid_identifier", f"{path}.id", "边 ID 格式无效。")
            elif identifier in edge_ids:
                _issue(
                    errors,
                    "duplicate_edge_id",
                    f"{path}.id",
                    f"边 ID {identifier} 重复。",
                )
            elif identifier in node_by_id:
                _issue(
                    errors,
                    "duplicate_global_id",
                    f"{path}.id",
                    f"边 ID {identifier} 与节点 ID 冲突。",
                )
            else:
                edge_ids.add(identifier)
        source_id = _check_string(
            raw_edge.get("from"),
            path=f"{path}.from",
            errors=errors,
            allow_empty=False,
        )
        target_id = _check_string(
            raw_edge.get("to"),
            path=f"{path}.to",
            errors=errors,
            allow_empty=False,
        )
        if source_id is not None and source_id not in node_by_id:
            _issue(
                errors,
                "dangling_edge_source",
                f"{path}.from",
                f"边引用了不存在的节点 {source_id}。",
            )
        if target_id is not None and target_id not in node_by_id:
            _issue(
                errors,
                "dangling_edge_target",
                f"{path}.to",
                f"边引用了不存在的节点 {target_id}。",
            )
        if source_id is not None and source_id == target_id:
            _issue(errors, "self_loop", path, "论文追踪边不能连接节点自身。")
        relation = raw_edge.get("relation")
        if relation not in RELATIONS:
            _issue(
                errors,
                "invalid_relation",
                f"{path}.relation",
                f"未知关系：{relation}",
            )
        status = raw_edge.get("status")
        if status not in EDGE_STATUSES:
            _issue(
                errors,
                "invalid_edge_status",
                f"{path}.status",
                f"未知边状态：{status}",
            )
        _check_string(
            raw_edge.get("rationale"),
            path=f"{path}.rationale",
            errors=errors,
            allow_empty=True,
        )
        evidence_ids = _validate_evidence_ids(
            raw_edge.get("evidence_ids"),
            path=f"{path}.evidence_ids",
            errors=errors,
            references=references,
        )
        if status == "verified" and not evidence_ids:
            _issue(
                contract_gaps,
                "verified_edge_without_evidence",
                f"{path}.evidence_ids",
                "状态为 verified 的边至少需要一个 evidence_id。",
            )
        if (
            relation in RELATION_ROLE_RULES
            and source_id in node_by_id
            and target_id in node_by_id
        ):
            role_pair = (
                _node_role(node_by_id[source_id]),
                _node_role(node_by_id[target_id]),
            )
            if role_pair not in RELATION_ROLE_RULES[relation]:
                _issue(
                    errors,
                    "relation_role_mismatch",
                    f"{path}.relation",
                    f"关系 {relation} 不允许连接 {role_pair[0]} → {role_pair[1]}。",
                )
        parsed_edges.append(raw_edge)

    active_edges = [
        edge for edge in parsed_edges if _edge_is_active(edge, node_by_id)
    ]
    incident: set[str] = {
        str(edge.get(key, "")) for edge in active_edges for key in ("from", "to")
    }
    for index, node in enumerate(parsed_nodes):
        role = _node_role(node)
        if role not in CRITICAL_ROLES:
            continue
        identifier = str(node.get("id", ""))
        status = node.get("status")
        path = f"$.manuscript_map.nodes[{index}]"
        if (
            completion_mode == "complete"
            and role in CRITICAL_ROLES
            and status in UNFINISHED_STATUSES
        ):
            _issue(
                contract_gaps,
                "unfinished_critical_node",
                f"{path}.status",
                f"完整稿中的关键节点 {identifier or role} 不能保持 {status}。",
            )
        if (
            completion_mode == "complete"
            and _node_is_active(node)
            and not node.get("evidence_ids")
        ):
            _issue(
                contract_gaps,
                "critical_node_without_evidence",
                f"{path}.evidence_ids",
                f"完整稿关键节点 {identifier or role} 必须映射到稿件证据。",
            )
        if _node_is_active(node) and identifier not in incident:
            destination = contract_gaps if completion_mode == "complete" else warnings
            _issue(
                destination,
                "unmapped_critical_node",
                path,
                f"关键节点 {identifier or role} 尚未连接到有效追踪边。",
            )
        if completion_mode == "complete" and status == "needs_review":
            _issue(
                contract_gaps,
                "critical_node_needs_review",
                f"{path}.status",
                f"完整稿关键节点 {identifier or role} 仍为 needs_review，不能算已验证。",
            )
        elif completion_mode == "complete" and status == "drafted":
            _issue(
                contract_gaps,
                "unverified_complete_core_node",
                f"{path}.status",
                f"完整稿关键节点 {identifier or role} 必须为 verified。",
            )

    active_role_ids: dict[str, set[str]] = {
        role: {
            identifier
            for identifier, node in node_by_id.items()
            if _node_role(node) == role and _node_is_active(node)
        }
        for role in CRITICAL_ROLES
    }
    if completion_mode == "complete":
        for role in REQUIRED_COMPLETE_ROLES:
            if not active_role_ids[role]:
                _issue(
                    contract_gaps,
                    "missing_active_critical_role",
                    "$.manuscript_map.nodes",
                    f"完整稿缺少处于 drafted、verified 或 needs_review 状态的 {role} 节点。",
                )
        if not any(active_role_ids[role] for role in ENTRY_ROLES):
            _issue(
                contract_gaps,
                "missing_active_entry_role",
                "$.manuscript_map.nodes",
                "完整稿至少需要一个 active 的 research_question、objective 或 hypothesis 入口节点。",
            )
        if not str(card.get("central_message", "")).strip():
            _issue(
                warnings,
                "central_message_empty",
                "$.manuscript_map.card.central_message",
                "完整稿的中心信息仍为空。",
            )

    ledger_ids: set[str] = set()
    ledger_fingerprint: str | None = None
    ledger_input_fingerprint: str | None = None
    verified_references: set[str] = set()
    if ledger is not None:
        ledger_ids, ledger_fingerprint, ledger_input_fingerprint = _ledger_index(
            ledger, errors
        )
        for identifier, path in references:
            if identifier not in ledger_ids:
                _issue(
                    errors,
                    "unknown_evidence_id",
                    path,
                    f"{identifier} 不存在于提供的 evidence ledger。",
                )
            else:
                verified_references.add(identifier)
    elif references:
        _issue(
            warnings,
            "evidence_ids_not_checked",
            "$.manuscript_map",
            "未提供 --ledger；evidence_ids 仅通过格式检查，未核验其真实存在。",
        )

    ledger_integrity_valid = not any(
        item["code"].startswith(
            (
                "invalid_ledger",
                "duplicate_ledger",
                "missing_ledger",
                "stale_ledger",
            )
        )
        for item in errors
    )
    binding_ids = ledger_ids if ledger is not None else None
    closure_binding_ids = ledger_ids if ledger is not None else set()
    closure_ledger_valid = ledger is not None and ledger_integrity_valid
    if completion_mode == "complete" and ledger is None:
        _issue(
            contract_gaps,
            "ledger_required_for_argument_closure",
            "$.manuscript_map",
            "未提供 evidence ledger；结构可校验，但论证不能标记为 closed。",
        )

    if completion_mode == "complete":
        for index, edge in enumerate(parsed_edges):
            source = node_by_id.get(str(edge.get("from", "")), {})
            target = node_by_id.get(str(edge.get("to", "")), {})
            source_role = _node_role(source)
            target_role = _node_role(target)
            relation = edge.get("relation")
            is_core_transition = any(
                source_role in source_roles
                and target_role in target_roles
                and relation in allowed_relations
                for source_roles, target_roles, allowed_relations in CORE_TRANSITIONS
            )
            if not is_core_transition:
                continue
            path = f"$.manuscript_map.edges[{index}]"
            edge_status = edge.get("status")
            if edge_status == "needs_review":
                _issue(
                    contract_gaps,
                    "core_edge_needs_review",
                    f"{path}.status",
                    f"核心追踪边 {edge.get('id', '')} 仍为 needs_review，不能算已验证。",
                )
            elif edge_status != "verified":
                _issue(
                    contract_gaps,
                    "unverified_complete_core_edge",
                    f"{path}.status",
                    f"完整稿核心追踪边 {edge.get('id', '')} 必须为 verified。",
                )
            if not _declared_evidence_ids(edge):
                _issue(
                    contract_gaps,
                    "core_edge_without_evidence",
                    f"{path}.evidence_ids",
                    f"完整稿核心追踪边 {edge.get('id', '')} 必须映射到稿件证据。",
                )

        ready_nodes = {
            identifier: node
            for identifier, node in node_by_id.items()
            if _node_role(node) in CRITICAL_ROLES
            and _node_is_complete_ready(
                node,
                ledger_ids=binding_ids,
                ledger_binding_valid=ledger_integrity_valid,
            )
        }
        relationship_edges = [
            edge
            for edge in parsed_edges
            if edge.get("status") == "verified"
            and _evidence_is_ready(
                edge,
                ledger_ids=binding_ids,
                ledger_binding_valid=ledger_integrity_valid,
            )
            and _edge_is_active(edge, node_by_id)
        ]
        ready_role_ids = {
            role: {
                identifier
                for identifier, node in ready_nodes.items()
                if _node_role(node) == role
            }
            for role in CRITICAL_ROLES
        }
        for role in REQUIRED_COMPLETE_ROLES:
            if not ready_role_ids[role]:
                _issue(
                    contract_gaps,
                    "missing_verified_core_role",
                    "$.manuscript_map.nodes",
                    f"完整稿缺少具有有效证据绑定的 verified {role} 节点。",
                )
        if not any(ready_role_ids[role] for role in ENTRY_ROLES):
            _issue(
                contract_gaps,
                "missing_verified_entry_role",
                "$.manuscript_map.nodes",
                "完整稿至少需要一个具有有效证据绑定的 verified research_question、objective 或 hypothesis 入口。",
            )

        for index, node in enumerate(parsed_nodes):
            identifier = str(node.get("id", ""))
            role = _node_role(node)
            if role not in CRITICAL_ROLES or not _node_is_active(node):
                continue
            incoming = [
                edge
                for edge in relationship_edges
                if str(edge.get("to", "")) == identifier
            ]
            outgoing = [
                edge
                for edge in relationship_edges
                if str(edge.get("from", "")) == identifier
            ]
            checks: list[tuple[bool, str, str]] = []
            if role == "gap":
                checks.append(
                    (
                        any(
                            edge.get("relation") == "motivates"
                            and _node_role(
                                node_by_id.get(str(edge.get("to", "")), {})
                            )
                            in ENTRY_ROLES
                            for edge in outgoing
                        ),
                        "gap_without_entry",
                        "gap 必须通过 verified motivates 边连接到问题/目标入口。",
                    )
                )
            elif role in ENTRY_ROLES:
                checks.extend(
                    [
                        (
                            any(
                                edge.get("relation") == "motivates"
                                and _node_role(
                                    node_by_id.get(str(edge.get("from", "")), {})
                                )
                                == "gap"
                                for edge in incoming
                            ),
                            "entry_without_gap",
                            f"{role} 入口必须由 verified gap → entry 边引出。",
                        ),
                        (
                            any(
                                edge.get("relation") == "addressed_by"
                                and _node_role(
                                    node_by_id.get(str(edge.get("to", "")), {})
                                )
                                == "method"
                                for edge in outgoing
                            ),
                            "entry_without_method",
                            f"{role} 入口必须通过 verified addressed_by 边映射到 method。",
                        ),
                    ]
                )
            elif role == "method":
                checks.extend(
                    [
                        (
                            any(
                                edge.get("relation") == "addressed_by"
                                and _node_role(
                                    node_by_id.get(str(edge.get("from", "")), {})
                                )
                                in ENTRY_ROLES
                                for edge in incoming
                            ),
                            "method_without_entry",
                            "每个 method 必须由 verified 问题/目标入口映射。",
                        ),
                        (
                            any(
                                edge.get("relation") == "produces"
                                and _node_role(
                                    node_by_id.get(str(edge.get("to", "")), {})
                                )
                                == "result"
                                for edge in outgoing
                            ),
                            "method_without_result",
                            "每个 method 必须通过 verified produces 边连接到 result。",
                        ),
                    ]
                )
            elif role == "result":
                checks.extend(
                    [
                        (
                            any(
                                edge.get("relation") == "produces"
                                and _node_role(
                                    node_by_id.get(str(edge.get("from", "")), {})
                                )
                                == "method"
                                for edge in incoming
                            ),
                            "result_without_method",
                            "每个 result 必须具有 verified method → produces 入边。",
                        ),
                        (
                            any(
                                edge.get("relation") == "interpreted_by"
                                and _node_role(
                                    node_by_id.get(str(edge.get("to", "")), {})
                                )
                                == "interpretation"
                                for edge in outgoing
                            ),
                            "result_without_interpretation",
                            "每个 result 必须通过 verified interpreted_by 边连接到 interpretation。",
                        ),
                    ]
                )
            elif role == "interpretation":
                checks.extend(
                    [
                        (
                            any(
                                edge.get("relation") == "interpreted_by"
                                and _node_role(
                                    node_by_id.get(str(edge.get("from", "")), {})
                                )
                                == "result"
                                for edge in incoming
                            ),
                            "interpretation_without_result",
                            "每个 interpretation 必须具有 verified result → interpreted_by 入边。",
                        ),
                        (
                            any(
                                edge.get("relation") == "supports"
                                and _node_role(
                                    node_by_id.get(str(edge.get("to", "")), {})
                                )
                                == "conclusion"
                                for edge in outgoing
                            ),
                            "interpretation_without_conclusion",
                            "每个 interpretation 必须通过 verified supports 边连接到 conclusion。",
                        ),
                    ]
                )
            elif role == "conclusion":
                checks.append(
                    (
                        any(
                            edge.get("relation") == "supports"
                            and _node_role(
                                node_by_id.get(str(edge.get("from", "")), {})
                            )
                            == "interpretation"
                            for edge in incoming
                        ),
                        "conclusion_without_interpretation",
                        "每个 conclusion 必须具有 verified interpretation → supports 入边。",
                    )
                )
            for passed, code, message in checks:
                if not passed:
                    _issue(
                        contract_gaps,
                        code,
                        f"$.manuscript_map.nodes[{index}]",
                        message,
                    )

    chain_complete = _core_chain_complete(
        node_by_id,
        parsed_edges,
        require_verified=completion_mode == "complete",
        ledger_ids=closure_binding_ids,
        ledger_binding_valid=closure_ledger_valid,
    )
    if completion_mode == "complete" and not chain_complete:
        _issue(
            contract_gaps,
            "complete_core_chain_missing",
            "$.manuscript_map.edges",
            "完整稿必须具有 gap → "
            "(research_question | objective | hypothesis) → method → result → "
            "interpretation → conclusion 的连续 verified 证据链。",
        )

    traceability_rows: list[dict[str, Any]] = []
    for edge in parsed_edges:
        source_id = str(edge.get("from", ""))
        target_id = str(edge.get("to", ""))
        evidence_ids = edge.get("evidence_ids")
        evidence_ids = evidence_ids if isinstance(evidence_ids, list) else []
        valid_ids = [
            item
            for item in evidence_ids
            if isinstance(item, str) and EVIDENCE_ID_PATTERN.fullmatch(item)
        ]
        if ledger is None:
            binding = "not_checked" if valid_ids else "none"
        elif valid_ids and all(item in ledger_ids for item in valid_ids):
            binding = "verified"
        elif valid_ids:
            binding = "invalid"
        else:
            binding = "none"
        traceability_rows.append(
            {
                "edge_id": str(edge.get("id", "")),
                "from_id": source_id,
                "from_role": _node_role(node_by_id.get(source_id, {})),
                "from_label": str(node_by_id.get(source_id, {}).get("label", "")),
                "relation": str(edge.get("relation", "")),
                "to_id": target_id,
                "to_role": _node_role(node_by_id.get(target_id, {})),
                "to_label": str(node_by_id.get(target_id, {}).get("label", "")),
                "status": str(edge.get("status", "")),
                "evidence_count": len(valid_ids),
                "evidence_binding": binding,
            }
        )

    status = "valid" if not errors else "invalid"
    argument_status = (
        "closed"
        if completion_mode == "complete"
        and chain_complete
        and not contract_gaps
        and not errors
        else "unresolved"
    )
    ledger_binding_status = (
        "not_provided"
        if ledger is None
        else (
            "verified"
            if not any(
                item["code"].startswith(
                    ("invalid_ledger", "duplicate_ledger", "missing_ledger", "stale_ledger")
                )
                or item["code"] == "unknown_evidence_id"
                for item in errors
            )
            else "invalid"
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": VALIDATION_ARTIFACT_TYPE,
        "validation_scope": (
            "structure_and_evidence_binding" if ledger is not None else "structure_only"
        ),
        "semantic_audit_status": "not_performed_by_validator",
        "status": status,
        "argument_status": argument_status,
        "completion_mode": completion_mode,
        "provenance": {
            "ledger_fingerprint": ledger_fingerprint,
            "input_fingerprint": ledger_input_fingerprint,
        },
        "summary": {
            "error_count": len(errors),
            "contract_gap_count": len(contract_gaps),
            "warning_count": len(warnings),
            "node_count": len(parsed_nodes),
            "edge_count": len(parsed_edges),
            "active_edge_count": len(active_edges),
            "core_chain_complete": chain_complete,
            "evidence_reference_count": len(references),
            "unique_evidence_reference_count": len({item for item, _ in references}),
            "verified_evidence_reference_count": len(verified_references),
            "ledger_binding_status": ledger_binding_status,
            "semantic_findings_evaluated": 0,
            "semantic_audit_completed": False,
        },
        "errors": errors,
        "contract_gaps": contract_gaps,
        "warnings": warnings,
        "traceability_rows": traceability_rows,
        "manuscript_map": preserved_map,
    }


def _escape_markdown(value: Any) -> str:
    return str(value or "").replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render_traceability_markdown(validation: Mapping[str, Any]) -> str:
    """Render a concise, deterministic traceability table."""

    summary = validation.get("summary", {})
    summary = summary if isinstance(summary, Mapping) else {}
    lines = [
        "# Manuscript traceability map",
        "",
        f"- Contract validation: `{validation.get('status', '')}`",
        f"- Argument status: `{validation.get('argument_status', '')}`",
        f"- Completion mode: `{validation.get('completion_mode', '')}`",
        f"- Validation scope: `{validation.get('validation_scope', '')}`",
        "- Semantic audit: `not performed by this validator`",
        f"- Core chain complete: `{str(bool(summary.get('core_chain_complete'))).lower()}`",
        (
            "- Errors / contract gaps / warnings: "
            f"{summary.get('error_count', 0)} / "
            f"{summary.get('contract_gap_count', 0)} / "
            f"{summary.get('warning_count', 0)}"
        ),
        "",
    ]
    if validation.get("validation_scope") == "structure_only":
        lines.extend(
            [
                "> Evidence IDs were not checked against an evidence ledger. A valid contract is not a completed semantic audit.",
                "",
            ]
        )
    lines.extend(
        [
            "| From | Relation | To | Status | Evidence |",
            "|---|---|---|---|---|",
        ]
    )
    rows = validation.get("traceability_rows")
    rows = rows if isinstance(rows, list) else []
    if not rows:
        lines.append("| — | — | — | — | — |")
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        source = " · ".join(
            item
            for item in (
                str(row.get("from_id", "")),
                str(row.get("from_role", "")),
                str(row.get("from_label", "")),
            )
            if item
        )
        target = " · ".join(
            item
            for item in (
                str(row.get("to_id", "")),
                str(row.get("to_role", "")),
                str(row.get("to_label", "")),
            )
            if item
        )
        evidence = f"{row.get('evidence_count', 0)} · {row.get('evidence_binding', '')}"
        lines.append(
            "| "
            + " | ".join(
                _escape_markdown(item)
                for item in (
                    source,
                    row.get("relation", ""),
                    target,
                    row.get("status", ""),
                    evidence,
                )
            )
            + " |"
        )
    for heading, key in (
        ("Validation errors", "errors"),
        ("Argument closure gaps", "contract_gaps"),
        ("Warnings", "warnings"),
    ):
        values = validation.get(key)
        values = values if isinstance(values, list) else []
        lines.extend(["", f"## {heading}", ""])
        if not values:
            lines.append("None.")
        for item in values:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                f"- `{_escape_markdown(item.get('code', ''))}` at "
                f"`{_escape_markdown(item.get('path', ''))}`: "
                f"{_escape_markdown(item.get('message', ''))}"
            )
    lines.append("")
    return "\n".join(lines)


def _temporary_output_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp").resolve(strict=False)


def _paths_alias(left: str | Path, right: str | Path) -> bool:
    left_path = Path(left).resolve(strict=False)
    right_path = Path(right).resolve(strict=False)
    if left_path == right_path:
        return True
    try:
        return left_path.exists() and right_path.exists() and left_path.samefile(right_path)
    except OSError:
        return False


def _ledger_declared_paths(
    ledger: Mapping[str, Any], ledger_source: Path
) -> list[Path]:
    """Resolve dependency paths declared by a ledger for write protection."""

    base = ledger_source.parent
    declared: list[Path] = []

    def add_path(value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = base / candidate
        declared.append(candidate.resolve(strict=False))

    add_path(ledger.get("root_input"))
    for field in ("dependencies", "artifacts", "sources"):
        values = ledger.get(field)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, Mapping):
                add_path(item.get("path"))

    unique: list[Path] = []
    for candidate in declared:
        if not any(_paths_alias(candidate, existing) for existing in unique):
            unique.append(candidate)
    return unique


def _assert_safe_write_targets(
    outputs: Iterable[str | Path], protected_inputs: Iterable[str | Path]
) -> None:
    protected = [
        Path(value).resolve(strict=False)
        for value in protected_inputs
        if str(value).strip()
    ]
    raw_outputs = [Path(value) for value in outputs]
    normalized_outputs = [value.resolve(strict=False) for value in raw_outputs]
    for index, (raw_output, output) in enumerate(
        zip(raw_outputs, normalized_outputs)
    ):
        if raw_output.is_symlink():
            raise ManuscriptMapError(f"拒绝写入符号链接输出：{raw_output}")
        raw_temporary = raw_output.with_name(f".{raw_output.name}.tmp")
        if raw_temporary.is_symlink():
            raise ManuscriptMapError(f"拒绝写入符号链接临时输出：{raw_temporary}")
        temporary = raw_temporary.resolve(strict=False)
        for other in normalized_outputs[index + 1 :]:
            if _paths_alias(output, other):
                raise ManuscriptMapError(f"输出路径彼此冲突：{output} 与 {other}")
        for target in (output, temporary):
            for protected_path in protected:
                if _paths_alias(target, protected_path):
                    raise ManuscriptMapError(
                        f"拒绝写入输入、ledger 或其声明依赖的路径别名：{target}"
                    )


def _preflight_outputs(paths: Sequence[Path], *, force: bool) -> None:
    for path in paths:
        if path.exists() and not force:
            raise ManuscriptMapError(f"拒绝覆盖已有输出：{path}；确认后使用 --force。")
        temporary = _temporary_output_path(path)
        if temporary.exists() and not force:
            raise ManuscriptMapError(
                f"拒绝覆盖已有临时输出：{temporary}；确认后使用 --force。"
            )


def _atomic_write(path: Path, text: str, *, force: bool) -> None:
    path = path.resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_output_path(path)
    if temporary.is_symlink():
        raise ManuscriptMapError(f"拒绝写入符号链接临时输出：{temporary}")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_template(
    output_path: str | Path,
    *,
    stage: str = "draft",
    force: bool = False,
) -> Path:
    """Write a blank template, refusing implicit overwrite."""

    output = Path(output_path).resolve(strict=False)
    _assert_safe_write_targets([output], [])
    _preflight_outputs([output], force=force)
    payload = manuscript_map_template(stage)
    _atomic_write(
        output,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        force=force,
    )
    return output


def validate_to_files(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    ledger_path: str | Path | None = None,
    completion: str | None = None,
    force: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    """Validate an input file and write JSON plus Markdown projections."""

    source = Path(input_path).resolve(strict=True)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManuscriptMapError(f"无法读取 manuscript map：{source}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ManuscriptMapError("manuscript-map JSON 根节点必须是对象。")

    ledger: Mapping[str, Any] | None = None
    ledger_source: Path | None = None
    if ledger_path is not None:
        ledger_source = Path(ledger_path).resolve(strict=True)
        try:
            raw_ledger = json.loads(ledger_source.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManuscriptMapError(
                f"无法读取 evidence ledger：{ledger_source}: {exc}"
            ) from exc
        if not isinstance(raw_ledger, Mapping):
            raise ManuscriptMapError("evidence ledger JSON 根节点必须是对象。")
        ledger = raw_ledger

    validation = validate_manuscript_map(
        payload, ledger=ledger, completion=completion
    )
    output_root = Path(output_dir).resolve(strict=False)
    json_path = output_root / "manuscript-map-validation.json"
    markdown_path = output_root / "manuscript-map-traceability.md"
    protected: list[Path] = [source]
    if ledger_source is not None:
        protected.append(ledger_source)
        protected.extend(_ledger_declared_paths(ledger or {}, ledger_source))
    _assert_safe_write_targets([json_path, markdown_path], protected)
    _preflight_outputs([json_path, markdown_path], force=force)
    _atomic_write(
        json_path,
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        force=force,
    )
    _atomic_write(
        markdown_path,
        render_traceability_markdown(validation),
        force=force,
    )
    return validation, json_path, markdown_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "生成或校验由语义审核者填写的论文主线图；本工具不从关键词推断论文逻辑。"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="生成空白论文主线卡/地图")
    initialize.add_argument("output")
    initialize.add_argument(
        "--stage", choices=sorted(VALID_COMPLETION_MODES), default="draft"
    )
    initialize.add_argument("--force", action="store_true")

    validate = subparsers.add_parser(
        "validate",
        help="严格校验地图结构并生成 JSON 与 Markdown 追踪表",
        description=(
            "校验 reviewer-authored 地图的结构和证据绑定。"
            "正式审核必须提供 --ledger；省略时仅进行 structure_only 校验。"
        ),
    )
    validate.add_argument("input")
    validate.add_argument("--output-dir", required=True)
    validate.add_argument(
        "--ledger",
        help="evidence-ledger.json 路径；正式审核必须提供，省略则不核验证据真实性",
    )
    validate.add_argument(
        "--completion",
        choices=sorted(VALID_COMPLETION_MODES),
        help="覆盖地图声明的 manuscript_stage，仅用于本次校验",
    )
    validate.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            path = write_template(args.output, stage=args.stage, force=args.force)
            print(path)
            return 0
        result, json_path, markdown_path = validate_to_files(
            args.input,
            args.output_dir,
            ledger_path=args.ledger,
            completion=args.completion,
            force=args.force,
        )
        if result["status"] == "valid":
            if result["validation_scope"] == "structure_only":
                print("valid (structure_only; evidence not verified)")
                print(f"argument {result.get('argument_status', 'unresolved')}")
            else:
                print(
                    f"valid (contract; argument {result.get('argument_status', 'unresolved')})"
                )
        else:
            errors = result.get("errors", [])
            print(f"invalid (error_count={len(errors)})")
            for item in errors[:5]:
                print(
                    f"- {item.get('code', '')} @ {item.get('path', '')}"
                )
        print(json_path)
        print(markdown_path)
        return 0 if result["status"] == "valid" else 1
    except (ManuscriptMapError, OSError, ValueError) as exc:
        print(f"manuscript-map: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
