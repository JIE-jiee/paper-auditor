#!/usr/bin/env python3
"""Build an evidence-led ledger for engineering-standard citations.

The verifier never guesses clause content. It checks designations and edition
consistency deterministically. Full-text search is allowed only after an
explicit rights attestation and, where required by the registry, a recorded
publisher-permission reference. It never uploads or copies a standard and never
modifies the manuscript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from audit_manuscript import AuditError, Block, _load_sources
from verify_references import read_docx_text, read_pdf_text, read_text


SCHEMA_VERSION = "0.2.0"
SUPPORTED_STANDARD_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}

STANDARD_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])(?:ASCE(?:\s*/\s*SEI)?|ASCE\s+SEI)\s*7(?:-\d{2})?(?![A-Za-z0-9-])", re.I),
    re.compile(r"(?<![A-Za-z0-9])ACI(?:\s+CODE)?[-\s]*318M?(?:-\d{2}(?:\(\d{2}\))?)?(?![A-Za-z0-9-])", re.I),
    re.compile(r"(?<![A-Za-z0-9])(?:ANSI\s*/\s*)?AISC\s*(?:360|341)(?:-\d{2})?(?![A-Za-z0-9-])", re.I),
    re.compile(r"(?<![A-Za-z0-9])EN\s*199[0-9](?:-\d+(?:-\d+)*)?(?::\d{4})?(?![A-Za-z0-9-])", re.I),
    re.compile(r"(?<![A-Za-z0-9])GB(?:\s*/\s*T)?\s*\d{4,6}(?:\.\d+)?(?:-\d{4})?(?![A-Za-z0-9-])", re.I),
    re.compile(r"(?<![A-Za-z0-9])JGJ(?:\s*/\s*T)?\s*\d+(?:-\d{4})?(?![A-Za-z0-9-])", re.I),
)

CLAUSE_PATTERNS = (
    ("clause", re.compile(r"\b(?:Section|Sec\.?|Clause|Cl\.?)\s*(?P<id>[A-Z]?\d+(?:\.\d+)+(?:\([A-Za-z0-9]+\))*)", re.I)),
    ("clause", re.compile(r"第\s*(?P<id>\d+(?:\.\d+)+)\s*条")),
    ("equation", re.compile(r"\b(?:Equation|Eq\.?)\s*\(?(?P<id>[A-Z]?\d+(?:[.\-]\d+)+(?:\([A-Za-z0-9]+\))*)\)?", re.I)),
    ("table", re.compile(r"\bTable\s*(?P<id>[A-Z]?\d+(?:[.\-]\d+)*)", re.I)),
    ("figure", re.compile(r"\b(?:Figure|Fig\.?)\s*(?P<id>[A-Z]?\d+(?:[.\-]\d+)*)", re.I)),
)


@dataclass
class StandardMention:
    raw: str
    canonical: str
    family: str
    edition: str
    block: Block
    start: int
    clauses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.edition)

    def location(self) -> dict[str, Any]:
        return self.block.location()


@dataclass(frozen=True)
class StandardSource:
    path: Path
    rights_attested: bool = False
    permission_reference: str = ""
    processing_mode: str = "local-deterministic"
    origin: str = "source-map"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _short(value: str, limit: int = 360) -> str:
    value = _space(value)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _stable_id(prefix: str, *parts: str) -> str:
    material = "\0".join(_space(str(part)).casefold() for part in parts)
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=5).hexdigest().upper()
    return f"{prefix}-{digest}"


def normalize_designation(raw: str) -> tuple[str, str, str]:
    """Return canonical designation, family, and explicit edition."""
    compact = _space(raw).upper().replace("–", "-").replace("—", "-")
    compact = re.sub(r"\s*/\s*", "/", compact)
    if compact.startswith("ASCE"):
        match = re.search(r"7(?:-(\d{2}))?", compact)
        edition = match.group(1) if match and match.group(1) else ""
        return (f"ASCE/SEI 7-{edition}" if edition else "ASCE/SEI 7", "ASCE/SEI 7", edition)
    if compact.startswith("ACI"):
        match = re.search(r"318M?(?:-(\d{2}(?:\(\d{2}\))?))?", compact)
        edition = match.group(1) if match and match.group(1) else ""
        return (f"ACI CODE-318-{edition}" if edition else "ACI 318", "ACI 318", edition)
    if "AISC" in compact:
        number_match = re.search(r"AISC\s*(360|341)", compact)
        number = number_match.group(1) if number_match else ""
        edition_match = re.search(rf"{number}-(\d{{2}})", compact) if number else None
        edition = edition_match.group(1) if edition_match else ""
        family = f"AISC {number}"
        canonical = f"ANSI/AISC {number}-{edition}" if edition else family
        return canonical, family, edition
    if compact.startswith("EN"):
        cleaned = re.sub(r"\s+", " ", compact)
        match = re.match(r"EN\s*(199[0-9](?:-\d+(?:-\d+)*)?)(?::(\d{4}))?", cleaned)
        part = match.group(1) if match else cleaned.replace("EN", "", 1).strip()
        edition = match.group(2) if match and match.group(2) else ""
        family = f"EN {part}"
        return (f"{family}:{edition}" if edition else family, family, edition)
    if compact.startswith("GB"):
        prefix = "GB/T" if "/T" in compact else "GB"
        match = re.search(r"(\d{4,6}(?:\.\d+)?)(?:-(\d{4}))?", compact)
        number = match.group(1) if match else ""
        edition = match.group(2) if match and match.group(2) else ""
        family = f"{prefix} {number}".strip()
        return (f"{family}-{edition}" if edition else family, family, edition)
    prefix = "JGJ/T" if "/T" in compact else "JGJ"
    match = re.search(r"(\d+)(?:-(\d{4}))?", compact)
    number = match.group(1) if match else ""
    edition = match.group(2) if match and match.group(2) else ""
    family = f"{prefix} {number}".strip()
    return (f"{family}-{edition}" if edition else family, family, edition)


def load_registry(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("standards", []), list):
        raise ValueError(f"标准注册表格式无效：{path}")
    return data


def _registry_by_family(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in registry.get("standards", []):
        if isinstance(item, dict) and item.get("family"):
            result[str(item["family"])] = item
    return result


def extract_mentions(units: Iterable[Any]) -> list[StandardMention]:
    mentions: list[StandardMention] = []
    for unit in units:
        for block in unit.blocks:
            structure = block.unit.structure.splitlines()
            searchable = structure[block.line - 1] if block.line <= len(structure) else block.raw
            for pattern in STANDARD_PATTERNS:
                for match in pattern.finditer(searchable):
                    raw = match.group(0)
                    canonical, family, edition = normalize_designation(raw)
                    mentions.append(StandardMention(raw, canonical, family, edition, block, match.start()))
    mentions.sort(key=lambda item: (item.block.unit.source.casefold(), item.block.line, item.start, item.canonical))
    return mentions


def _nearby_blocks(mention: StandardMention, radius: int = 2) -> list[Block]:
    blocks = mention.block.unit.blocks
    begin = max(0, mention.block.line - 1 - radius)
    end = min(len(blocks), mention.block.line + radius)
    return blocks[begin:end]


def attach_clause_mentions(mentions: list[StandardMention]) -> None:
    for mention in mentions:
        seen: set[tuple[str, str, int]] = set()
        for block in _nearby_blocks(mention):
            for kind, pattern in CLAUSE_PATTERNS:
                for match in pattern.finditer(block.raw):
                    identifier = match.group("id")
                    key = (kind, identifier.casefold(), block.line)
                    if key in seen:
                        continue
                    seen.add(key)
                    mention.clauses.append(
                        {
                            "kind": kind,
                            "identifier": identifier,
                            "token": match.group(0),
                            "location": block.location(),
                            "context": _short(block.raw),
                        }
                    )


def _source_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def load_source_map(path: Path | None) -> dict[str, StandardSource]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = data.get("sources", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        raise ValueError("标准 source-map 的 sources 必须是数组。")
    result: dict[str, StandardSource] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("designation") or not row.get("path"):
            raise ValueError("source-map 每项必须包含 designation 与 path。")
        candidate = (path.parent / str(row["path"])).resolve(strict=True)
        if candidate.suffix.casefold() not in SUPPORTED_STANDARD_SUFFIXES:
            raise ValueError(f"不支持的标准文本格式：{candidate}")
        result[_source_key(str(row["designation"]))] = StandardSource(
            path=candidate,
            rights_attested=row.get("rights_attested") is True,
            permission_reference=_space(str(row.get("permission_reference", ""))),
            processing_mode=_space(str(row.get("processing_mode", "local-deterministic"))),
            origin="source-map",
        )
    return result


def discover_standard_sources(directory: Path | None) -> list[Path]:
    if directory is None:
        return []
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError(f"标准文本目录不是文件夹：{directory}")
    return sorted(
        (path for path in directory.rglob("*") if path.is_file() and path.suffix.casefold() in SUPPORTED_STANDARD_SUFFIXES),
        key=lambda path: str(path).casefold(),
    )


def match_standard_source(
    mention: StandardMention,
    explicit: Mapping[str, StandardSource],
    candidates: Sequence[Path],
) -> tuple[StandardSource | None, str]:
    exact = explicit.get(_source_key(mention.canonical)) or explicit.get(_source_key(mention.raw))
    if exact:
        return exact, "explicit-map"
    keys = {_source_key(mention.canonical), _source_key(mention.family)}
    matches = [path for path in candidates if any(key and key in _source_key(path.stem) for key in keys)]
    if len(matches) == 1:
        return StandardSource(path=matches[0], origin="standards-dir"), "filename"
    if len(matches) > 1:
        return None, "ambiguous-filename"
    return None, "not-found"


def _fulltext_processing_policy(registry_item: Mapping[str, Any] | None) -> str:
    if not registry_item:
        return "rights-attestation-required"
    policy = str(registry_item.get("fulltext_processing_policy", "rights-attestation-required"))
    if policy not in {"permission-required", "rights-attestation-required"}:
        return "rights-attestation-required"
    return policy


def _source_gate_status(source: StandardSource, policy: str) -> str:
    if source.processing_mode != "local-deterministic":
        return "processing-mode-not-approved"
    if not source.rights_attested:
        return "rights-attestation-required"
    if policy == "permission-required" and not source.permission_reference:
        return "publisher-permission-required"
    return "allowed"


def authorize_standard_source_map(
    source_map_path: Path,
    registry_path: Path,
) -> list[dict[str, Any]]:
    """Validate source-map rights without opening any standard full text.

    The returned records are suitable for a manifest.  They deliberately retain
    only whether a permission reference was provided plus its digest, never the
    permission text itself.
    """

    source_map_path = source_map_path.resolve(strict=True)
    registry_path = registry_path.resolve(strict=True)
    data = json.loads(source_map_path.read_text(encoding="utf-8-sig"))
    rows = data.get("sources", []) if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        raise ValueError("标准 source-map 的 sources 必须是非空数组。")
    registry = load_registry(registry_path)
    registry_families = _registry_by_family(registry)
    records: list[dict[str, Any]] = []
    seen_designations: set[str] = set()
    seen_paths: set[Path] = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("designation") or not row.get("path"):
            raise ValueError("source-map 每项必须包含 designation 与 path。")
        designation = _space(str(row["designation"]))
        designation_key = _source_key(designation)
        if designation_key in seen_designations:
            raise ValueError(f"source-map 含重复标准代号：{designation}")
        seen_designations.add(designation_key)
        candidate = (source_map_path.parent / str(row["path"])).resolve(strict=True)
        if candidate.suffix.casefold() not in SUPPORTED_STANDARD_SUFFIXES:
            raise ValueError(f"不支持的标准文本格式：{candidate}")
        if candidate in seen_paths:
            raise ValueError(f"同一标准文件不能映射到多个代号：{candidate.name}")
        seen_paths.add(candidate)
        source = StandardSource(
            path=candidate,
            rights_attested=row.get("rights_attested") is True,
            permission_reference=_space(str(row.get("permission_reference", ""))),
            processing_mode=_space(str(row.get("processing_mode", "local-deterministic"))),
            origin="source-map",
        )
        canonical, family, _ = normalize_designation(designation)
        policy = _fulltext_processing_policy(registry_families.get(family))
        gate_status = _source_gate_status(source, policy)
        permission_digest = (
            hashlib.sha256(source.permission_reference.encode("utf-8")).hexdigest()
            if source.permission_reference
            else ""
        )
        entry_projection = {
            "designation": designation,
            "path": str(row["path"]),
            "processing_mode": source.processing_mode,
            "rights_attested": source.rights_attested,
            "permission_reference_sha256": permission_digest,
        }
        records.append(
            {
                **entry_projection,
                "canonical_designation": canonical,
                "family": family,
                "resolved_path": str(candidate),
                "fulltext_processing_policy": policy,
                "permission_reference_provided": bool(source.permission_reference),
                "gate_status": gate_status,
                "source_map_entry_sha256": hashlib.sha256(
                    json.dumps(entry_projection, ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest(),
            }
        )
    return records


def read_standard_source(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        return read_pdf_text(path)
    if suffix == ".docx":
        return read_docx_text(path)
    return read_text(path)


def find_identifier_evidence(text: str, identifier: str, limit: int = 3) -> list[dict[str, Any]]:
    escaped = re.escape(identifier)
    pattern = re.compile(rf"(?<![0-9A-Za-z]){escaped}(?![0-9A-Za-z])", re.I)
    evidence: list[dict[str, Any]] = []
    for page_number, page in enumerate(text.split("\f"), 1):
        lines = page.splitlines()
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            begin = max(0, index - 2)
            end = min(len(lines), index + 3)
            evidence.append(
                {
                    "page": page_number,
                    "line": index + 1,
                    "quote": _short(" ".join(lines[begin:end]), 800),
                }
            )
            if len(evidence) >= limit:
                return evidence
    return evidence


def _finding(
    check_id: str,
    severity: str,
    confidence: float,
    location: Mapping[str, Any],
    observation: str,
    expected: str,
    reason: str,
    suggestion: str,
    *,
    quote: str,
    related_locations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    identifier = _stable_id("STD", check_id, str(location.get("source", "")), str(location.get("line", "")), observation)
    item: dict[str, Any] = {
        "id": identifier,
        "category": "standard",
        "check_id": check_id,
        "severity": severity,
        "confidence": round(confidence, 2),
        "status": "needs-review",
        "location": dict(location),
        "quote": _short(quote, 220),
        "evidence_mode": "deterministic",
        "observation": observation,
        "expected": expected,
        "reason": reason,
        "evidence": [{"class": "A", "source": "manuscript"}],
        "suggested_fix": suggestion,
        "auto_fixable": False,
    }
    if related_locations:
        item["related_locations"] = [dict(value) for value in related_locations]
    return item


def build_ledger(
    manuscript: Path,
    registry_path: Path,
    *,
    standards_dir: Path | None = None,
    source_map_path: Path | None = None,
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    units = _load_sources(manuscript, diagnostics)
    registry = load_registry(registry_path)
    registry_families = _registry_by_family(registry)
    mentions = extract_mentions(units)
    attach_clause_mentions(mentions)
    explicit_sources = load_source_map(source_map_path)
    candidate_sources = discover_standard_sources(standards_dir)
    source_cache: dict[Path, tuple[str, str]] = {}
    findings: list[dict[str, Any]] = []
    review_tasks: list[dict[str, Any]] = []
    output_mentions: list[dict[str, Any]] = []

    by_family: dict[str, list[StandardMention]] = defaultdict(list)
    for mention in mentions:
        by_family[mention.family].append(mention)
        registry_item = registry_families.get(mention.family)
        current = str(registry_item.get("canonical_designation", "")) if registry_item else ""
        edition_status = "not-in-bundled-registry"
        if not mention.edition:
            edition_status = "missing"
            findings.append(
                _finding(
                    "standard-version-missing",
                    "Major",
                    0.98,
                    mention.location(),
                    f"标准“{mention.raw}”未写明版本/年份。",
                    "标准引用应给出完整代号、版本或年份，并说明适用的国家附录/修订（如适用）。",
                    "缺少版本会使条款、公式和适用范围无法复核。",
                    "补充研究实际采用的完整标准代号；不要仅按最新版本自动替换。",
                    quote=mention.raw,
                )
            )
        elif registry_item:
            if _source_key(mention.canonical) == _source_key(current):
                edition_status = "registry-current-publication"
            else:
                edition_status = "different-from-registry-current-publication"
                findings.append(
                    _finding(
                        "standard-edition-review",
                        "Info",
                        0.99,
                        mention.location(),
                        f"稿件使用“{mention.canonical}”，注册表所列当前出版物为“{current}”。",
                        "确认研究采用的版本与项目日期、管辖区、所依据建筑规范或比较目的相符。",
                        "较旧版本可能仍是合法的控制版本，不能仅凭出版时间判错。",
                        "在方法或标准说明中写明采用该版本的依据；必要时核对勘误、补遗和解释。",
                        quote=mention.raw,
                    )
                )

        standard_source, source_match = match_standard_source(mention, explicit_sources, candidate_sources)
        processing_policy = _fulltext_processing_policy(registry_item)
        source_info: dict[str, Any] = {
            "status": source_match,
            "processing_policy": processing_policy,
        }
        source_text = ""
        if standard_source:
            source_path = standard_source.path
            source_info.update(
                {
                    "match_method": source_match,
                    "basename": source_path.name,
                    "source_origin": standard_source.origin,
                    "processing_mode": standard_source.processing_mode,
                    "rights_attested": standard_source.rights_attested,
                    "permission_reference_provided": bool(standard_source.permission_reference),
                }
            )
            gate_status = _source_gate_status(standard_source, processing_policy)
            if gate_status != "allowed":
                source_info["status"] = gate_status
            else:
                try:
                    if source_path not in source_cache:
                        source_cache[source_path] = (
                            read_standard_source(source_path),
                            hashlib.sha256(source_path.read_bytes()).hexdigest(),
                        )
                    source_text, source_hash = source_cache[source_path]
                    source_info.update(
                        {
                            "status": "available",
                            "sha256": source_hash,
                        }
                    )
                except (OSError, ValueError) as exc:
                    source_info.update({"status": "unreadable", "error": str(exc)})

        clause_outputs: list[dict[str, Any]] = []
        for clause in mention.clauses:
            evidence = find_identifier_evidence(source_text, clause["identifier"]) if source_text else []
            if evidence:
                evidence_status = "located-candidates"
            elif source_info.get("status") == "available":
                evidence_status = "not-located-in-extracted-text"
            elif source_info.get("status") in {
                "rights-attestation-required",
                "publisher-permission-required",
                "processing-mode-not-approved",
            }:
                evidence_status = str(source_info["status"])
            else:
                evidence_status = "source-unavailable"
            clause_output = {**clause, "evidence_status": evidence_status, "source_evidence": evidence}
            clause_outputs.append(clause_output)
            review_tasks.append(
                {
                    "id": _stable_id("STD-TASK", mention.canonical, clause["kind"], clause["identifier"], str(clause["location"])),
                    "type": "standard-clause-review",
                    "standard": mention.canonical,
                    "reference_kind": clause["kind"],
                    "reference_identifier": clause["identifier"],
                    "manuscript_location": clause["location"],
                    "manuscript_context": clause["context"],
                    "evidence_status": evidence_status,
                    "source_evidence": evidence,
                    "required_checks": [
                        "exact edition and amendment",
                        "definition and symbol mapping",
                        "unit system and coefficients",
                        "limits, exceptions, and referenced clauses",
                        "structural system, material, hazard, method, and jurisdiction applicability",
                    ],
                    "assessment": "not_assessed",
                }
            )

        output_mentions.append(
            {
                "id": _stable_id("STD-M", mention.canonical, str(mention.location())),
                "raw": mention.raw,
                "canonical_designation": mention.canonical,
                "family": mention.family,
                "edition": mention.edition,
                "designation_complete": mention.complete,
                "edition_status": edition_status,
                "registry_current_publication": current,
                "registry_metadata": registry_item or {},
                "location": mention.location(),
                "context": _short(mention.block.raw),
                "source_access": source_info,
                "references": clause_outputs,
                "applicability_assessment": "not_assessed",
            }
        )

    for family, family_mentions in sorted(by_family.items()):
        editions = sorted({item.edition for item in family_mentions if item.edition})
        if len(editions) <= 1:
            continue
        first = family_mentions[0]
        findings.append(
            _finding(
                "standard-edition-inconsistent",
                "Major",
                0.96,
                first.location(),
                f"同一标准族“{family}”在稿件中出现多个版本：{', '.join(editions)}。",
                "除非论文明确进行版本比较，否则同一计算或试验依据应使用并说明一致的控制版本。",
                "跨版本的条款号、系数、公式和适用范围可能不同。",
                "确认这是历史比较还是无意混用；分别标明每一处版本及其用途。",
                quote=first.raw,
                related_locations=[item.location() for item in family_mentions[1:]],
            )
        )

    findings.sort(key=lambda item: (item["location"].get("source", "").casefold(), item["location"].get("line", 0), item["check_id"]))
    source_manifest = [
        {"source": unit.source, "sha256": hashlib.sha256(unit.path.read_bytes()).hexdigest()}
        for unit in units
        if unit.path.is_file()
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "input": {"path": str(manuscript), "sha256": hashlib.sha256(manuscript.read_bytes()).hexdigest()},
        "registry": {"path": str(registry_path), "checked_at": registry.get("checked_at", ""), "sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest()},
        "sources": source_manifest,
        "summary": {
            "mention_count": len(output_mentions),
            "families": dict(sorted(Counter(item["family"] for item in output_mentions).items())),
            "finding_count": len(findings),
            "clause_review_task_count": len(review_tasks),
        },
        "mentions": output_mentions,
        "findings": findings,
        "review_tasks": review_tasks,
        "diagnostics": diagnostics,
        "limitations": [
            "A newer publication is not automatically the governing edition for a study or jurisdiction.",
            "Clause text and formulas are never inferred from metadata or memory.",
            "A discoverable local file is not authorization to read standard full text.",
            "ASCE and ACI full-text processing remains blocked without a recorded publisher-permission reference.",
            "A clause not found in extracted text is unable-to-verify, not proof of an invalid citation.",
            "Applicability requires semantic review of scope, assumptions, exceptions, and governing rules.",
        ],
    }


def render_report(data: Mapping[str, Any]) -> str:
    summary = data.get("summary", {})
    lines = [
        "# 工程标准核验报告",
        "",
        f"- 生成时间：`{data.get('generated_at', '')}`",
        f"- 标准提及：{summary.get('mention_count', 0)}",
        f"- 版本/代号发现：{summary.get('finding_count', 0)}",
        f"- 条款/公式复核任务：{summary.get('clause_review_task_count', 0)}",
        "",
        "> 较新版本不自动等于本研究的控制版本。条款内容、公式和适用范围只有在获得准确版本的标准正文或直接官方证据后才能判定。",
        "",
        "## 版本与代号问题",
        "",
    ]
    findings = data.get("findings", [])
    if not findings:
        lines.append("未发现可确定定位的版本或代号问题。")
    for finding in findings:
        location = finding.get("location", {})
        lines.extend(
            [
                f"### {finding.get('id', '')} · {finding.get('severity', '')}",
                "",
                f"- 位置：`{location.get('source', '')}:{location.get('line', '')}`",
                f"- 观察：{finding.get('observation', '')}",
                f"- 原因：{finding.get('reason', '')}",
                f"- 建议：{finding.get('suggested_fix', '')}",
                "",
            ]
        )
    lines.extend(["## 标准台账", ""])
    for mention in data.get("mentions", []):
        location = mention.get("location", {})
        source_access = mention.get("source_access", {})
        lines.extend(
            [
                f"### {mention.get('canonical_designation', '')}",
                "",
                f"- 位置：`{location.get('source', '')}:{location.get('line', '')}`",
                f"- 版本状态：`{mention.get('edition_status', '')}`",
                f"- 注册表当前出版物：`{mention.get('registry_current_publication', '') or '未设置'}`",
                f"- 标准正文：`{source_access.get('status', '')}`",
                f"- 全文处理策略：`{source_access.get('processing_policy', '')}`",
                f"- 本地文件名：`{source_access.get('basename', '')}`",
                f"- 上下文：{mention.get('context', '')}",
            ]
        )
        for reference in mention.get("references", []):
            lines.append(
                f"- {reference.get('kind', '')} `{reference.get('identifier', '')}`：`{reference.get('evidence_status', '')}`"
            )
            for evidence in reference.get("source_evidence", [])[:2]:
                lines.append(f"  - 标准正文候选（p.{evidence.get('page', '')}）：{evidence.get('quote', '')}")
        lines.append("")
    lines.extend(
        [
            "## 使用边界",
            "",
            "- 对条款任务逐项核对准确版本、定义、单位、系数、限制、例外和引用链。",
            "- 未提供标准正文时，报告只验证代号和版本一致性，不声称条款正确或错误。",
            "- 仅发现本地标准文件不代表获得处理授权；必须通过 source-map 明示权利声明，ASCE/ACI 还需记录出版方许可依据。",
            "- 不把用户提供的标准正文复制到报告或 Skill，只保留短证据片段、位置和哈希。",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(data: Mapping[str, Any], output_dir: Path, *, force: bool = False) -> tuple[Path, Path]:
    output_dir = output_dir.resolve(strict=False)
    json_path = (output_dir / "standards.json").resolve(strict=False)
    report_path = (output_dir / "standards-report.md").resolve(strict=False)
    protected = {Path(str(data.get("input", {}).get("path", ""))).resolve(strict=False)}
    protected.update(Path(str(item.get("source", ""))).resolve(strict=False) for item in data.get("sources", []) if item.get("source"))
    for target in (json_path, report_path):
        if target in protected:
            raise ValueError(f"拒绝写出：输出路径与输入源相同：{target}")
        if target.is_symlink():
            raise ValueError(f"拒绝写出到符号链接目标：{target}")
    existing = [target for target in (json_path, report_path) if target.exists()]
    if existing and not force:
        raise FileExistsError("输出文件已存在，未覆盖；如确认替换，请使用 --force。")
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "w" if force else "x"
    with json_path.open(mode, encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    try:
        with report_path.open(mode, encoding="utf-8") as handle:
            handle.write(render_report(data))
    except Exception:
        if not force:
            json_path.unlink(missing_ok=True)
        raise
    return json_path, report_path


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="核验结构工程标准代号、版本与用户提供正文中的条款证据。")
    parser.add_argument("manuscript", type=Path, help=".tex、.docx、.pdf、.md 或 .txt 稿件")
    parser.add_argument("--output-dir", type=Path, required=True, help="新的核验输出目录")
    parser.add_argument("--registry", type=Path, default=root / "references" / "standards-registry.json", help="标准元数据注册表")
    parser.add_argument("--standards-dir", type=Path, help="只发现候选文件名；不构成全文处理授权")
    parser.add_argument("--source-map", type=Path, help="含本地路径、权利声明和许可依据的 JSON 显式映射")
    parser.add_argument("--force", action="store_true", help="覆盖旧报告；永不覆盖稿件或标准正文")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manuscript = args.manuscript.resolve(strict=True)
        registry = args.registry.resolve(strict=True)
        data = build_ledger(
            manuscript,
            registry,
            standards_dir=args.standards_dir,
            source_map_path=args.source_map.resolve(strict=True) if args.source_map else None,
        )
        json_path, report_path = write_outputs(data, args.output_dir, force=args.force)
    except (AuditError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"已写入：{json_path}")
    print(f"已写入：{report_path}")
    print("提示：较新出版物不自动等于控制版本；条款与适用范围须以准确版本正文复核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
