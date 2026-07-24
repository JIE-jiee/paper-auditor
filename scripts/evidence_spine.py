"""Build and adjudicate a shared evidence spine for manuscript audits.

The module is intentionally dependency-free.  It reuses the manuscript loaders in
``audit_manuscript.py`` so that evidence anchors follow the same source ordering and
location model as the deterministic audit.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from audit_manuscript import (
    CALLOUT_RE,
    AuditError,
    SourceUnit,
    _crossref_kind,
    _is_explicitly_planned_target,
    _load_sources,
)
from manuscript_map import ManuscriptMapError, validate_manuscript_map
from verify_standards import authorize_standard_source_map


SCHEMA_VERSION = "0.1.0"
VALID_MODES = {"draft", "fast", "deep", "targeted"}
VALID_PASS_STATUSES = {
    "completed",
    "not_applicable",
    "insufficient_evidence",
    "failed",
    "not_run",
}
CAPABILITY_STATUSES = {"available", "partial", "missing"}
VALID_DRAFT_PLANNED_CHECKS = {
    "crossref-callout-planned-target",
    "latex-reference-planned-label",
}
SEMANTIC_REVIEW_ASSESSMENTS = {
    "satisfied",
    "unresolved",
    "contradicted",
    "not_yet_written",
    "not_applicable",
}
UNRESOLVED_SEMANTIC_ASSESSMENTS = (
    SEMANTIC_REVIEW_ASSESSMENTS - {"satisfied"}
)
LATEX_REFERENCE_RE = re.compile(
    r"\\(?:ref|eqref|autoref|pageref|nameref|cref|Cref)\*?\s*\{([^{}]+)\}"
)
SEVERITY_ORDER = {"Blocker": 0, "Major": 1, "Minor": 2, "Info": 3}
VALID_FINDING_STATUSES = {
    "confirmed",
    "likely",
    "needs-review",
    "unable-to-verify",
    "contested",
}
DEFAULT_STANDARDS_REGISTRY = Path(__file__).resolve().parent.parent / "references" / "standards-registry.json"

PASS_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "deterministic_text",
        "label": "缩写、术语、格式与交叉引用确定性检查",
        "required_modes": ("draft", "fast", "deep"),
        "semantic": False,
        "allow_not_applicable": False,
    },
    {
        "id": "language_tense",
        "label": "语言与时态语义审查",
        "required_modes": ("draft", "fast", "deep"),
        "semantic": True,
        "allow_not_applicable": False,
    },
    {
        "id": "abbreviation_terminology",
        "label": "缩写、术语与符号语义一致性审查",
        "required_modes": ("draft", "deep"),
        "semantic": True,
        "allow_not_applicable": False,
    },
    {
        "id": "quantitative",
        "label": "公式、单位、符号与数值一致性审查",
        "required_modes": ("draft", "deep"),
        "semantic": False,
        "allow_not_applicable": True,
    },
    {
        "id": "claim_logic",
        "label": "全文逻辑、研究范围与观点一致性审查",
        "required_modes": ("draft", "deep"),
        "semantic": True,
        "allow_not_applicable": False,
    },
    {
        "id": "citation_integrity",
        "label": "引文—参考文献完整性与书目真实性核验",
        "required_modes": ("deep",),
        "semantic": False,
        "allow_not_applicable": True,
    },
    {
        "id": "claim_support",
        "label": "论文主张—被引来源支持性核验",
        "required_modes": ("deep",),
        "semantic": True,
        "allow_not_applicable": True,
    },
    {
        "id": "engineering_standards",
        "label": "工程标准版本、条款、公式与适用性核验",
        "required_modes": ("deep",),
        "semantic": True,
        "allow_not_applicable": True,
    },
    {
        "id": "visual",
        "label": "图表、公式排版与渲染结果审查",
        "required_modes": ("deep",),
        "semantic": True,
        "allow_not_applicable": True,
    },
)
PASS_SPEC_BY_ID = {item["id"]: item for item in PASS_SPECS}

CAPABILITIES = (
    "manuscript_text",
    "editable_source",
    "rendered_pages",
    "reference_metadata",
    "cited_full_text",
    "standard_text",
    "figure_table_data",
)

ADDITIONAL_ARTIFACT_ROLES = {
    "bibliography",
    "appendix",
    "figure",
    "table_data",
    "profile",
    "terminology",
    "quantity_profile",
    "standards_registry",
    "cited_source",
    "cited_source_map",
    "standard_source",
    "supplement",
}

STANDARD_METADATA_CHECKS = {
    "standard-version-missing",
    "standard-edition-review",
    "standard-edition-inconsistent",
}

SEMANTIC_HIGH_SEVERITY_PASSES = {
    "language_tense",
    "abbreviation_terminology",
    "claim_logic",
    "claim_support",
    "engineering_standards",
    "visual",
}


class EvidenceSpineError(RuntimeError):
    """Raised when an evidence-spine contract is invalid or unsafe to use."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stable_id(prefix: str, *pieces: Any) -> str:
    material = "\0".join(str(piece) for piece in pieces)
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=8).hexdigest().upper()
    return f"{prefix}-{digest}"


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def load_json_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path).resolve(strict=True)
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceSpineError(f"无法读取 {label}：{source}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceSpineError(f"{label} 根节点必须是 JSON 对象：{source}")
    return data


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


def _assert_safe_write_targets(
    outputs: Iterable[str | Path], protected_inputs: Iterable[str | Path]
) -> None:
    protected = [
        Path(value).resolve(strict=False)
        for value in protected_inputs
        if str(value).strip()
    ]
    normalized_outputs = [Path(value).resolve(strict=False) for value in outputs]
    for index, output in enumerate(normalized_outputs):
        for other in normalized_outputs[index + 1 :]:
            if _paths_alias(output, other):
                raise EvidenceSpineError(f"输出路径彼此冲突：{output} 与 {other}")
        for target in (output, _temporary_output_path(output)):
            for protected_path in protected:
                if _paths_alias(target, protected_path):
                    raise EvidenceSpineError(
                        f"拒绝写入受保护输入或依赖路径：{target}"
                    )


def atomic_write(path: Path, text: str, *, force: bool = False) -> None:
    path = path.resolve(strict=False)
    if path.exists() and not force:
        raise EvidenceSpineError(f"拒绝覆盖已有输出：{path}；确认后使用 --force。")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_output_path(path)
    if temporary.exists() and not force:
        raise EvidenceSpineError(f"拒绝覆盖已有临时输出：{temporary}；确认后使用 --force。")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _stable_manifest_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": manifest.get("schema_version"),
        "paper_id": manifest.get("paper_id"),
        "root_input_sha256": manifest.get("root_input_sha256"),
        "root_source_id": manifest.get("root_source_id"),
        "artifacts": [
            {
                **{
                    key: item.get(key)
                    for key in (
                        "source_id",
                        "role",
                        "source",
                        "format",
                        "sha256",
                        "byte_count",
                    )
                },
                "identity": item.get("identity"),
                "authorization": item.get("authorization"),
            }
            for item in manifest.get("artifacts", [])
        ],
    }


def manifest_fingerprint(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(_stable_manifest_projection(manifest)))


def _stable_ledger_projection(ledger: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ledger.get("schema_version"),
        "paper_id": ledger.get("paper_id"),
        "input_fingerprint": ledger.get("input_fingerprint"),
        "text_mode": ledger.get("text_mode"),
        "dependencies": ledger.get("dependencies", []),
        "sources": ledger.get("sources", []),
        "evidence": ledger.get("evidence", []),
    }


def ledger_fingerprint(ledger: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(_stable_ledger_projection(ledger)))


def _stable_coverage_projection(coverage: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": coverage.get("schema_version"),
        "paper_id": coverage.get("paper_id"),
        "mode": coverage.get("mode"),
        "input_fingerprint": coverage.get("input_fingerprint"),
        "ledger_fingerprint": coverage.get("ledger_fingerprint"),
        "evidence_capabilities": coverage.get("evidence_capabilities", {}),
        "passes": coverage.get("passes", []),
    }


def coverage_fingerprint(coverage: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(_stable_coverage_projection(coverage)))


def _source_role_record(
    path: Path,
    *,
    source: str,
    role: str,
    format_name: str,
) -> dict[str, Any]:
    digest = sha256_file(path)
    return {
        "source_id": stable_id("SRC", role, source.casefold(), digest),
        "role": role,
        "source": source.replace("\\", "/"),
        "path": str(path.resolve()),
        "format": format_name,
        "sha256": digest,
        "byte_count": path.stat().st_size,
    }


def _evidence_tags(text: str, section: str) -> list[str]:
    tags: set[str] = set()
    if re.search(r"\d", text):
        tags.add("quantity")
    if re.search(
        r"\b(?:higher|lower|greater|smaller|increase[ds]?|decrease[ds]?|reduce[ds]?|"
        r"outperform(?:s|ed)?|compared with|relative to)\b",
        text,
        re.IGNORECASE,
    ):
        tags.add("comparison")
    if re.search(
        r"\b(?:cause[ds]?|lead[ds]? to|result(?:s|ed)? in|because of|due to|therefore)\b",
        text,
        re.IGNORECASE,
    ):
        tags.add("causal")
    if re.search(r"\b(?:all|always|never|generally|universally|regardless of)\b", text, re.IGNORECASE):
        tags.add("scope")
    if re.search(
        r"\\cite\w*\{|\[[0-9,;\-\s]+\]|\([A-Z][A-Za-z'\-]+(?: et al\.)?,?\s+\d{4}[a-z]?\)",
        text,
    ):
        tags.add("citation_context")
    if re.search(r"\b(?:Figs?\.?|Figures?|Tables?|Eqs?\.?|Equations?)\s*[~:]?\s*(?:\\ref\{)?\d", text, re.IGNORECASE):
        tags.add("callout")
    if re.search(r"\b(?:ASCE|ACI|AISC|Eurocode|EN\s*199\d|GB(?:/T)?|JGJ)\b", text, re.IGNORECASE):
        tags.add("standard")
    if re.search(
        r"\b(?:was|were|is|are)\s+(?:tested|analy[sz]ed|developed|calibrated|validated|measured)\b",
        text,
        re.IGNORECASE,
    ):
        tags.add("method_or_performance")
    if section:
        tags.add(f"section:{normalize_text(section).replace(' ', '_')[:48]}")
    return sorted(tags)


def _ledger_record(
    unit: SourceUnit,
    source_record: Mapping[str, Any],
    line: int,
    text: str,
    location: Mapping[str, Any],
    *,
    text_mode: str,
) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text).strip()
    text_digest = sha256_bytes(normalized.encode("utf-8"))
    evidence_id = stable_id(
        "EVD",
        source_record["source_id"],
        source_record["sha256"],
        line,
        location.get("paragraph", ""),
        location.get("page", ""),
        text_digest,
    )
    record: dict[str, Any] = {
        "evidence_id": evidence_id,
        "kind": "manuscript_span",
        "source_id": source_record["source_id"],
        "locator": dict(location),
        "text_sha256": text_digest,
        "tags": _evidence_tags(normalized, str(location.get("section", ""))),
        "extractor": unit.format,
        "extraction_confidence": "medium" if unit.format == "pdf" else "high",
    }
    if text_mode == "excerpt":
        record["quote"] = normalized[:1200]
        record["truncated"] = len(normalized) > 1200
    return record


def _initial_capabilities(units: Sequence[SourceUnit], rendered: Sequence[Path], diagnostics: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    formats = {unit.format for unit in units}
    extraction_warnings = any(item.get("level") == "warning" for item in diagnostics)
    has_text = any(unit.raw.strip() for unit in units)
    capabilities = {name: "missing" for name in CAPABILITIES}
    if has_text:
        capabilities["manuscript_text"] = "partial" if extraction_warnings else "available"
    if formats & {"tex", "docx", "md", "txt"}:
        capabilities["editable_source"] = "available"
    if "pdf" in formats or rendered:
        capabilities["rendered_pages"] = "available"
    return capabilities


def _bind_cited_source_maps(artifacts: list[dict[str, Any]]) -> None:
    cited_sources = [
        item for item in artifacts if item.get("role") == "cited_source"
    ]
    source_maps = [
        item for item in artifacts if item.get("role") == "cited_source_map"
    ]
    by_path = {
        Path(str(item.get("path", ""))).resolve(strict=True): item
        for item in cited_sources
    }
    key_bindings: dict[str, Path] = {}
    for source_path, artifact in by_path.items():
        identity = artifact.get("identity", {})
        citation_keys = (
            identity.get("citation_keys", [])
            if isinstance(identity, Mapping)
            else []
        )
        for citation_key in citation_keys:
            normalized_key = _identity_key(citation_key)
            if not normalized_key:
                continue
            previous = key_bindings.get(normalized_key)
            if previous is not None and previous != source_path:
                raise EvidenceSpineError(
                    f"同一引用键不能绑定到多个 cited_source：{citation_key}"
                )
            key_bindings[normalized_key] = source_path
    if not source_maps:
        return

    for source_map in source_maps:
        map_path = Path(str(source_map.get("path", ""))).resolve(strict=True)
        try:
            data = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceSpineError(f"无法读取 cited source-map：{map_path}: {exc}") from exc
        rows = data.get("sources") if isinstance(data, Mapping) else None
        if not isinstance(rows, list):
            raise EvidenceSpineError(
                f"cited source-map 必须包含 sources 数组：{map_path}"
            )
        for index, raw in enumerate(rows, 1):
            if not isinstance(raw, Mapping):
                raise EvidenceSpineError(
                    f"cited source-map 第 {index} 项必须是对象：{map_path}"
                )
            citation_key = str(raw.get("citation_key", "")).strip()
            path_text = str(raw.get("path", "")).strip()
            if not citation_key or not path_text:
                continue
            try:
                target = (map_path.parent / path_text).resolve(strict=True)
            except OSError as exc:
                raise EvidenceSpineError(
                    f"cited source-map 的本地路径不可读：{citation_key} -> {path_text}"
                ) from exc
            artifact = by_path.get(target)
            if artifact is None:
                raise EvidenceSpineError(
                    "cited source-map 的本地路径必须同时声明为 cited_source："
                    f"{citation_key} -> {target}"
                )
            normalized_key = _identity_key(citation_key)
            previous = key_bindings.get(normalized_key)
            if previous is not None and previous != target:
                raise EvidenceSpineError(
                    f"cited source-map 将同一引用键绑定到多个来源：{citation_key}"
                )
            key_bindings[normalized_key] = target
            identity = artifact.setdefault("identity", {})
            existing = [str(value) for value in identity.get("citation_keys", [])]
            identity["citation_keys"] = sorted(
                {value for value in [*existing, citation_key] if value.strip()},
                key=str.casefold,
            )


def _validate_cited_source_identities(
    artifacts: Sequence[Mapping[str, Any]],
) -> list[str]:
    if not any(item.get("role") == "cited_source" for item in artifacts):
        return []
    reconstructed = copy.deepcopy([dict(item) for item in artifacts])
    for item in reconstructed:
        if item.get("role") != "cited_source":
            continue
        path = Path(str(item.get("path", "")))
        item["identity"] = {
            "basename": path.name,
            "citation_keys": [path.stem],
        }
    try:
        _bind_cited_source_maps(reconstructed)
    except (EvidenceSpineError, OSError) as exc:
        return [f"cited_source_identity_invalid:{exc}"]
    expected = {
        str(item.get("source_id", "")): item.get("identity")
        for item in reconstructed
        if item.get("role") == "cited_source"
    }
    return [
        f"cited_source_identity_mismatch:{item.get('source', '')}"
        for item in artifacts
        if item.get("role") == "cited_source"
        and canonical_json(item.get("identity"))
        != canonical_json(expected.get(str(item.get("source_id", ""))))
    ]


def prepare_evidence_spine(
    manuscript: str | Path,
    output_dir: str | Path,
    *,
    mode: str = "deep",
    required_passes: Sequence[str] = (),
    rendered_artifacts: Sequence[str | Path] = (),
    additional_artifacts: Sequence[tuple[str, str | Path]] = (),
    text_mode: str = "excerpt",
    standards_source_map: str | Path | None = None,
    standards_registry: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if mode not in VALID_MODES:
        raise EvidenceSpineError(f"未知审核模式：{mode}")
    if text_mode not in {"excerpt", "hash-only"}:
        raise EvidenceSpineError("text_mode 只能是 excerpt 或 hash-only")
    unknown_passes = sorted(set(required_passes) - set(PASS_SPEC_BY_ID))
    if unknown_passes:
        raise EvidenceSpineError(f"未知 pass：{', '.join(unknown_passes)}")
    if mode == "targeted" and not required_passes:
        raise EvidenceSpineError("targeted 模式至少需要一个 --required-pass")

    input_path = Path(manuscript).resolve(strict=True)
    diagnostics: list[dict[str, Any]] = []
    try:
        units = _load_sources(input_path, diagnostics)
    except (AuditError, OSError) as exc:
        raise EvidenceSpineError(str(exc)) from exc

    root = input_path.parent
    artifacts: list[dict[str, Any]] = []
    root_source_id = ""
    source_records: dict[str, dict[str, Any]] = {}
    for unit in units:
        record = _source_role_record(
            unit.path,
            source=unit.source,
            role="manuscript_source",
            format_name=unit.format,
        )
        artifacts.append(record)
        source_records[unit.source.casefold().replace("\\", "/")] = record
        if unit.path.resolve() == input_path:
            root_source_id = record["source_id"]

    rendered_paths: list[Path] = []
    for item in rendered_artifacts:
        rendered = Path(item).resolve(strict=True)
        if not rendered.is_file():
            raise EvidenceSpineError(f"渲染文件不存在：{rendered}")
        rendered_paths.append(rendered)
        try:
            source = rendered.relative_to(root).as_posix()
        except ValueError:
            source = rendered.name
        artifacts.append(
            _source_role_record(
                rendered,
                source=source,
                role="rendered_manuscript",
                format_name=rendered.suffix.casefold().lstrip(".") or "binary",
            )
        )

    if standards_source_map is not None and any(
        role == "standards_registry" for role, _ in additional_artifacts
    ):
        raise EvidenceSpineError(
            "使用 --standards-source-map 时请通过 --standards-registry 指定注册表，不要重复声明 artifact。"
        )
    seen_additional: set[tuple[str, Path]] = set()
    for role, artifact_value in additional_artifacts:
        if role == "standard_source":
            raise EvidenceSpineError(
                "拒绝裸 standard_source；请使用 --standards-source-map 通过权利与许可门禁。"
            )
        if role not in ADDITIONAL_ARTIFACT_ROLES:
            raise EvidenceSpineError(f"未知附加 artifact role：{role}")
        artifact_path = Path(artifact_value).resolve(strict=True)
        if not artifact_path.is_file():
            raise EvidenceSpineError(f"附加审核依赖不存在：{artifact_path}")
        key = (role, artifact_path)
        if key in seen_additional:
            raise EvidenceSpineError(f"重复附加审核依赖：{role}={artifact_path}")
        seen_additional.add(key)
        try:
            source = artifact_path.relative_to(root).as_posix()
        except ValueError:
            source = artifact_path.name
        record = _source_role_record(
            artifact_path,
            source=source,
            role=role,
            format_name=artifact_path.suffix.casefold().lstrip(".") or "binary",
        )
        if role == "cited_source":
            record["identity"] = {
                "basename": artifact_path.name,
                "citation_keys": [artifact_path.stem],
            }
        artifacts.append(record)

    _bind_cited_source_maps(artifacts)

    if standards_source_map is not None:
        source_map_path = Path(standards_source_map).resolve(strict=True)
        registry_path = Path(standards_registry or DEFAULT_STANDARDS_REGISTRY).resolve(strict=True)
        try:
            authorization_records = authorize_standard_source_map(
                source_map_path, registry_path
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise EvidenceSpineError(f"标准 source-map 无法授权：{exc}") from exc
        blocked = [
            item for item in authorization_records if item.get("gate_status") != "allowed"
        ]
        if blocked:
            statuses = ", ".join(
                f"{item.get('designation', '')}={item.get('gate_status', '')}"
                for item in blocked
            )
            raise EvidenceSpineError(
                f"标准全文权利门禁未通过；未读取或哈希标准正文：{statuses}"
            )
        for role, path in (
            ("standard_source_map", source_map_path),
            ("standards_registry", registry_path),
        ):
            try:
                source = path.relative_to(root).as_posix()
            except ValueError:
                source = path.name
            record = _source_role_record(
                path,
                source=source,
                role=role,
                format_name=path.suffix.casefold().lstrip(".") or "binary",
            )
            artifacts.append(record)
        source_map_digest = sha256_file(source_map_path)
        registry_digest = sha256_file(registry_path)
        for item in authorization_records:
            source_path = Path(str(item["resolved_path"]))
            source_label = f"standard-sources/{item['canonical_designation']}/{source_path.name}"
            record = _source_role_record(
                source_path,
                source=source_label,
                role="standard_source",
                format_name=source_path.suffix.casefold().lstrip(".") or "binary",
            )
            record["authorization"] = {
                key: item.get(key)
                for key in (
                    "designation",
                    "canonical_designation",
                    "family",
                    "processing_mode",
                    "rights_attested",
                    "permission_reference_provided",
                    "permission_reference_sha256",
                    "fulltext_processing_policy",
                    "gate_status",
                    "source_map_entry_sha256",
                )
            }
            record["authorization"]["source_map_sha256"] = source_map_digest
            record["authorization"]["standards_registry_sha256"] = registry_digest
            artifacts.append(record)
    elif standards_registry is not None:
        raise EvidenceSpineError("--standards-registry 只能与 --standards-source-map 一起使用")

    artifacts.sort(key=lambda item: (item["role"], item["source"].casefold(), item["sha256"]))
    root_digest = sha256_file(input_path)
    paper_id = stable_id("PAPER", input_path.name.casefold(), root_digest)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "paper_id": paper_id,
        "root_input": str(input_path),
        "root_input_sha256": root_digest,
        "root_source_id": root_source_id,
        "artifacts": artifacts,
        "diagnostics": diagnostics,
    }
    manifest["input_fingerprint"] = manifest_fingerprint(manifest)

    evidence: list[dict[str, Any]] = []
    for unit in units:
        source_key = unit.source.casefold().replace("\\", "/")
        source_record = source_records[source_key]
        for block in unit.blocks:
            if not block.raw.strip():
                continue
            evidence.append(
                _ledger_record(
                    unit,
                    source_record,
                    block.line,
                    block.raw,
                    block.location(),
                    text_mode=text_mode,
                )
            )
    evidence.sort(
        key=lambda item: (
            str(item["locator"].get("source", "")).casefold(),
            int(item["locator"].get("line", 0) or 0),
            item["evidence_id"],
        )
    )
    ledger: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "paper_id": paper_id,
        "input_fingerprint": manifest["input_fingerprint"],
        "text_mode": text_mode,
        "dependencies": [
            {
                "source_id": item["source_id"],
                "role": item["role"],
                "source": item["source"],
                "format": item["format"],
                "sha256": item["sha256"],
                "path": item["path"],
            }
            for item in artifacts
        ],
        "sources": [
            {
                "source_id": item["source_id"],
                "source": item["source"],
                "format": item["format"],
                "sha256": item["sha256"],
            }
            for item in artifacts
            if item["role"] == "manuscript_source"
        ],
        "evidence": evidence,
        "summary": {
            "evidence_count": len(evidence),
            "tag_counts": dict(
                sorted(Counter(tag for item in evidence for tag in item.get("tags", [])).items())
            ),
        },
        "privacy": {
            "contains_manuscript_excerpts": text_mode == "excerpt",
            "sharing_warning": "Evidence ledgers may contain unpublished manuscript excerpts; keep the review directory private.",
        },
    }
    ledger["ledger_fingerprint"] = ledger_fingerprint(ledger)

    required = set(required_passes)
    if mode != "targeted":
        required.update(
            spec["id"] for spec in PASS_SPECS if mode in spec["required_modes"]
        )
    coverage: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "updated_at": utc_now(),
        "paper_id": paper_id,
        "mode": mode,
        "input_fingerprint": manifest["input_fingerprint"],
        "ledger_fingerprint": ledger["ledger_fingerprint"],
        "evidence_capabilities": _initial_capabilities(units, rendered_paths, diagnostics),
        "passes": [
            {
                "pass_id": spec["id"],
                "label": spec["label"],
                "required": spec["id"] in required,
                "semantic": spec["semantic"],
                "status": "not_run",
                "rationale": "",
                "ledger_binding": "none",
                "result": None,
                "reviewer": "",
                "recorded_at": None,
            }
            for spec in PASS_SPECS
        ],
    }
    roles = {item["role"] for item in artifacts}
    if "table_data" in roles:
        coverage["evidence_capabilities"]["figure_table_data"] = "available"
    if "cited_source" in roles:
        coverage["evidence_capabilities"]["cited_full_text"] = "partial"
    if "standard_source" in roles:
        coverage["evidence_capabilities"]["standard_text"] = "partial"
    coverage["coverage_fingerprint"] = coverage_fingerprint(coverage)

    review_dir = Path(output_dir).resolve(strict=False)
    outputs = {
        "manifest": review_dir / "artifact-manifest.json",
        "ledger": review_dir / "evidence-ledger.json",
        "coverage": review_dir / "coverage.json",
    }
    _assert_safe_write_targets(
        outputs.values(),
        [item.get("path", "") for item in artifacts],
    )
    for path in outputs.values():
        if path.exists() and not force:
            raise EvidenceSpineError(f"拒绝覆盖已有输出：{path}；确认后使用 --force。")
    for key, payload in (
        ("manifest", manifest),
        ("ledger", ledger),
        ("coverage", coverage),
    ):
        atomic_write(
            outputs[key],
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            force=force,
        )
    return {"manifest": manifest, "ledger": ledger, "coverage": coverage, "paths": outputs}


def _validate_contract_pair(coverage: Mapping[str, Any], ledger: Mapping[str, Any]) -> None:
    if coverage.get("schema_version") != SCHEMA_VERSION or ledger.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceSpineError("coverage 或 ledger 的 schema_version 不兼容")
    if coverage.get("paper_id") != ledger.get("paper_id"):
        raise EvidenceSpineError("coverage 与 ledger 的 paper_id 不一致")
    if coverage.get("input_fingerprint") != ledger.get("input_fingerprint"):
        raise EvidenceSpineError("coverage 与 ledger 的输入指纹不一致")
    expected_ledger = ledger_fingerprint(ledger)
    if ledger.get("ledger_fingerprint") != expected_ledger:
        raise EvidenceSpineError("evidence-ledger.json 指纹无效或内容已被修改")
    if coverage.get("ledger_fingerprint") != expected_ledger:
        raise EvidenceSpineError("coverage 引用的 ledger 指纹与当前 ledger 不一致")
    if not isinstance(ledger.get("sources"), list) or not isinstance(ledger.get("evidence"), list):
        raise EvidenceSpineError("ledger 的 sources 与 evidence 必须是数组")
    if not isinstance(ledger.get("dependencies"), list):
        raise EvidenceSpineError("ledger 缺少完整 dependencies 清单")

    mode = str(coverage.get("mode", ""))
    if mode not in VALID_MODES:
        raise EvidenceSpineError(f"coverage 模式无效：{mode}")
    passes = coverage.get("passes")
    if not isinstance(passes, list):
        raise EvidenceSpineError("coverage passes 必须是数组")
    records: dict[str, Mapping[str, Any]] = {}
    for item in passes:
        if not isinstance(item, Mapping):
            raise EvidenceSpineError("coverage pass 必须是对象")
        pass_id = str(item.get("pass_id", ""))
        if pass_id not in PASS_SPEC_BY_ID:
            raise EvidenceSpineError(f"coverage 含未知 pass：{pass_id}")
        if pass_id in records:
            raise EvidenceSpineError(f"coverage 含重复 pass：{pass_id}")
        spec = PASS_SPEC_BY_ID[pass_id]
        if item.get("label") != spec["label"] or item.get("semantic") is not spec["semantic"]:
            raise EvidenceSpineError(f"coverage pass 规格被修改：{pass_id}")
        if item.get("status") not in VALID_PASS_STATUSES:
            raise EvidenceSpineError(f"coverage pass 状态无效：{pass_id}")
        if (
            item.get("status") == "not_applicable"
            and not spec["allow_not_applicable"]
        ):
            raise EvidenceSpineError(f"pass {pass_id} 始终适用，不能标记为 not_applicable")
        records[pass_id] = item
    missing = sorted(set(PASS_SPEC_BY_ID) - set(records))
    if missing:
        raise EvidenceSpineError(f"coverage 缺少 pass：{', '.join(missing)}")
    for spec in PASS_SPECS:
        if mode in spec["required_modes"] and not records[spec["id"]].get("required"):
            raise EvidenceSpineError(f"coverage 取消了 {mode} 模式必需 pass：{spec['id']}")
    if mode == "targeted" and not any(bool(item.get("required")) for item in passes):
        raise EvidenceSpineError("targeted coverage 至少需要一个必需 pass")
    capabilities = coverage.get("evidence_capabilities")
    if not isinstance(capabilities, Mapping):
        raise EvidenceSpineError("coverage evidence_capabilities 必须是对象")
    if set(capabilities) != set(CAPABILITIES):
        raise EvidenceSpineError("coverage evidence_capabilities 字段不完整")
    if any(value not in CAPABILITY_STATUSES for value in capabilities.values()):
        raise EvidenceSpineError("coverage 含非法证据能力状态")
    expected_coverage = coverage_fingerprint(coverage)
    if coverage.get("coverage_fingerprint") != expected_coverage:
        raise EvidenceSpineError("coverage.json 指纹无效或内容已被直接修改")


def _result_dependency_candidates(ledger: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = ledger.get("dependencies", [])
    return [item for item in values if isinstance(item, Mapping)]


def _match_result_source(source: str, digest: str, dependencies: Sequence[Mapping[str, Any]]) -> bool:
    normalized = _source_key(source)
    if source:
        exact = [
            item
            for item in dependencies
            if normalized
            in {
                _source_key(item.get("source")),
                _source_key(item.get("path")),
            }
        ]
        if exact:
            return any(str(item.get("sha256", "")) == digest for item in exact)
        basename = Path(source).name.casefold()
        by_basename = [
            item
            for item in dependencies
            if basename
            in {
                Path(str(item.get("source", ""))).name.casefold(),
                Path(str(item.get("path", ""))).name.casefold(),
            }
        ]
        return len(by_basename) == 1 and str(
            by_basename[0].get("sha256", "")
        ) == digest
    digest_matches = [
        item for item in dependencies if str(item.get("sha256", "")) == digest
    ]
    return len(digest_matches) == 1


def _validate_result_sources(result: Mapping[str, Any], ledger: Mapping[str, Any]) -> tuple[list[str], bool]:
    warnings: list[str] = []
    dependencies = _result_dependency_candidates(ledger)
    matched = False
    result_sources = result.get("sources")
    if isinstance(result_sources, list):
        for item in result_sources:
            if not isinstance(item, Mapping):
                raise EvidenceSpineError("pass 结果 sources 每项必须是对象")
            source = str(item.get("source", item.get("path", "")))
            digest = str(item.get("sha256", ""))
            if digest:
                if not _match_result_source(source, digest, dependencies):
                    raise EvidenceSpineError(f"pass 结果中的来源不是当前 manifest：{source or digest}")
                matched = True
    elif result_sources is not None:
        raise EvidenceSpineError("pass 结果 sources 必须是数组")
    input_record = result.get("input")
    if isinstance(input_record, Mapping) and input_record.get("sha256"):
        source = str(input_record.get("path", input_record.get("source", "")))
        digest = str(input_record.get("sha256", ""))
        if not _match_result_source(source, digest, dependencies):
            raise EvidenceSpineError(f"pass 结果 input 不是当前 manifest：{source or digest}")
        matched = True
    if not matched:
        warnings.append("result_without_source_manifest")
    return warnings, matched


def _validate_result_envelope_shape(
    result: Mapping[str, Any],
    *,
    pass_id: str,
    status: str,
) -> str:
    schema_version = result.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise EvidenceSpineError(
            "completed/not_applicable result.schema_version 必须是原生非空字符串"
        )
    declared_pass = result.get("pass_id")
    if not isinstance(declared_pass, str) or not declared_pass.strip():
        raise EvidenceSpineError(
            "completed/not_applicable result.pass_id 必须是原生非空字符串"
        )
    if declared_pass.strip() != pass_id:
        raise EvidenceSpineError(
            f"pass result 声明为 {declared_pass.strip()}，不能记录为 {pass_id}"
        )

    collection_fields = (
        "findings",
        "formal_findings",
        "planned_items",
        "diagnostics",
        "claims",
        "entries",
        "mentions",
        "review_tasks",
        "review_candidates",
        "values",
        "symbols",
    )
    for key in collection_fields:
        if key in result and not isinstance(result.get(key), list):
            raise EvidenceSpineError(f"pass result.{key} 必须是数组")
    for key in ("inventory", "inventories"):
        if key in result and not isinstance(result.get(key), Mapping):
            raise EvidenceSpineError(f"pass result.{key} 必须是对象")

    summary_value = result.get("summary")
    if "summary" in result and not isinstance(summary_value, Mapping):
        raise EvidenceSpineError("pass result.summary 必须是对象")
    summary = summary_value if isinstance(summary_value, Mapping) else {}
    if (
        "review_completed" in summary
        and summary.get("review_completed") is not True
    ):
        raise EvidenceSpineError(
            "completed result 的 summary.review_completed 若存在，必须为布尔值 true"
        )

    count_fields = {
        "finding_count": "findings",
        "formal_finding_count": "formal_findings",
        "planned_item_count": "planned_items",
        "diagnostic_count": "diagnostics",
        "claim_count": "claims",
        "mention_count": "mentions",
        "clause_review_task_count": "review_tasks",
        "review_candidate_count": "review_candidates",
        "value_count": "values",
        "symbol_count": "symbols",
    }
    for count_key, collection_key in count_fields.items():
        if count_key not in summary:
            continue
        count = summary.get(count_key)
        values = result.get(collection_key)
        if isinstance(count, bool) or not isinstance(count, int):
            raise EvidenceSpineError(
                f"pass result.summary.{count_key} 必须是整数"
            )
        if not isinstance(values, list) or count != len(values):
            raise EvidenceSpineError(
                f"pass result.summary.{count_key} 与 {collection_key} 数量不一致"
            )

    if pass_id == "citation_integrity" and status == "completed":
        entries = result.get("entries")
        input_record = result.get("input")
        entry_count = (
            input_record.get("entry_count")
            if isinstance(input_record, Mapping)
            else None
        )
        if (
            not isinstance(entries, list)
            or isinstance(entry_count, bool)
            or not isinstance(entry_count, int)
            or entry_count != len(entries)
        ):
            raise EvidenceSpineError(
                "citation_integrity result 的 input.entry_count 必须与 entries 一致"
            )
    return schema_version.strip()


def _validate_not_applicable_inventory(result: Mapping[str, Any]) -> dict[str, Any]:
    inventory = result.get("inventory")
    if not isinstance(inventory, Mapping):
        raise EvidenceSpineError("not_applicable result 必须包含 inventory 对象")
    scope_value = inventory.get("scope")
    scope = scope_value.strip() if isinstance(scope_value, str) else ""
    count = inventory.get("item_count")
    items = inventory.get("items")
    if not scope:
        raise EvidenceSpineError("not_applicable inventory.scope 必须是原生非空字符串")
    if isinstance(count, bool) or not isinstance(count, int) or count != 0:
        raise EvidenceSpineError("not_applicable inventory.item_count 必须为整数 0")
    if not isinstance(items, list) or items:
        raise EvidenceSpineError("not_applicable inventory.items 必须是空数组")
    return {"scope": scope, "item_count": 0, "items": []}


def _has_completed_result_evidence(
    result: Mapping[str, Any],
    pass_id: str,
) -> bool:
    finding_lists = [
        result.get(key)
        for key in ("findings", "formal_findings")
        if key in result
    ]
    if any(isinstance(items, list) and items for items in finding_lists):
        return True
    if pass_id == "claim_logic":
        return (
            result.get("semantic_audit_status") == "completed"
            and isinstance(result.get("semantic_review"), Mapping)
        )
    summary = result.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    if PASS_SPEC_BY_ID[pass_id]["semantic"]:
        return summary.get("review_completed") is True
    if summary.get("review_completed") is True:
        return True
    if pass_id in {"deterministic_text", "quantitative"}:
        return (
            isinstance(result.get("findings"), list)
            and "finding_count" in summary
        )
    if pass_id == "citation_integrity":
        return isinstance(result.get("entries"), list)
    return False

def _validate_embedded_manuscript_map(
    result: Mapping[str, Any],
    ledger: Mapping[str, Any],
    *,
    completion: str | None,
    required: bool,
) -> dict[str, Any] | None:
    if result.get("artifact_type") == "manuscript_map_validation" or result.get(
        "semantic_audit_status"
    ) == "not_performed_by_validator":
        raise EvidenceSpineError(
            "论文主线结构校验器的原始输出不能作为 claim_logic 语义审核结果"
        )
    if required and result.get("pass_id") != "claim_logic":
        raise EvidenceSpineError(
            "draft/deep 的 claim_logic result 必须声明 pass_id=claim_logic"
        )
    if required and result.get("semantic_audit_status") != "completed":
        raise EvidenceSpineError(
            "draft/deep 的 claim_logic 必须声明 semantic_audit_status=completed"
        )
    embedded = result.get("manuscript_map_validation")
    if embedded is None:
        if required:
            raise EvidenceSpineError(
                "draft/deep 的 claim_logic completed result 必须包含 manuscript_map_validation"
            )
        return None
    if not isinstance(embedded, Mapping):
        raise EvidenceSpineError("manuscript_map_validation 必须是对象")
    if result.get("semantic_audit_status") != "completed":
        raise EvidenceSpineError(
            "论文主线结构校验不能冒充语义审核；claim_logic 必须声明 semantic_audit_status=completed"
        )
    if embedded.get("artifact_type") != "manuscript_map_validation":
        raise EvidenceSpineError("嵌入的论文主线产物类型无效")
    if embedded.get("status") != "valid":
        raise EvidenceSpineError("不能记录未通过结构校验的论文主线")
    if embedded.get("validation_scope") != "structure_and_evidence_binding":
        raise EvidenceSpineError("论文主线必须针对当前 evidence ledger 完成证据绑定")
    embedded_provenance = (
        embedded.get("provenance", {})
        if isinstance(embedded.get("provenance"), Mapping)
        else {}
    )
    if embedded_provenance.get("ledger_fingerprint") != ledger.get(
        "ledger_fingerprint"
    ):
        raise EvidenceSpineError("论文主线使用了不同或过期的 ledger 指纹")
    if embedded_provenance.get("input_fingerprint") != ledger.get(
        "input_fingerprint"
    ):
        raise EvidenceSpineError("论文主线使用了不同或过期的输入指纹")

    payload = {
        "schema_version": embedded.get("schema_version"),
        "artifact_type": "manuscript_map",
        "manuscript_map": copy.deepcopy(embedded.get("manuscript_map")),
    }
    try:
        revalidated = validate_manuscript_map(
            payload,
            ledger=ledger,
            completion=completion,
        )
    except ManuscriptMapError as exc:
        raise EvidenceSpineError(f"论文主线无法重新校验：{exc}") from exc
    if revalidated.get("status") != "valid":
        codes = ", ".join(
            str(item.get("code", "invalid"))
            for item in revalidated.get("errors", [])
            if isinstance(item, Mapping)
        )
        raise EvidenceSpineError(f"论文主线重新校验失败：{codes or 'invalid'}")
    return revalidated


def _required_semantic_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceSpineError(f"{label} 必须是非空字符串")
    return value.strip()


def _validate_semantic_review_items(
    values: Any,
    *,
    id_field: str,
    expected_ids: set[str],
    label: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(values, list):
        raise EvidenceSpineError(f"semantic_review.{label} 必须是数组")
    reviewed: list[dict[str, Any]] = []
    assessments: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            raise EvidenceSpineError(
                f"semantic_review.{label}[{index}] 必须是对象"
            )
        identifier = _required_semantic_string(
            item.get(id_field),
            f"semantic_review.{label}[{index}].{id_field}",
        )
        if identifier in seen:
            raise EvidenceSpineError(
                f"semantic_review.{label} 的 {id_field} 必须唯一且非空"
            )
        assessment = _required_semantic_string(
            item.get("assessment"),
            f"semantic_review.{label}[{index}].assessment",
        )
        if assessment not in SEMANTIC_REVIEW_ASSESSMENTS:
            allowed = ", ".join(sorted(SEMANTIC_REVIEW_ASSESSMENTS))
            raise EvidenceSpineError(
                f"semantic_review.{label}[{index}].assessment 无效；允许：{allowed}"
            )
        _required_semantic_string(
            item.get("rationale"),
            f"semantic_review.{label}[{index}].rationale",
        )
        seen.add(identifier)
        assessments.append(assessment)
        reviewed.append(copy.deepcopy(dict(item)))

    missing = sorted(expected_ids - seen)
    extra = sorted(seen - expected_ids)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"缺少 {', '.join(missing)}")
        if extra:
            details.append(f"额外 {', '.join(extra)}")
        raise EvidenceSpineError(
            f"semantic_review.{label} 未精确覆盖论文主线：{'；'.join(details)}"
        )
    return reviewed, assessments


def _validate_claim_logic_semantic_review(
    result: Mapping[str, Any],
    map_validation: Mapping[str, Any] | None,
    ledger: Mapping[str, Any],
    *,
    reviewer: str,
) -> dict[str, Any]:
    reviewer = _required_semantic_string(reviewer, "claim_logic reviewer")
    if result.get("semantic_audit_status") != "completed":
        raise EvidenceSpineError(
            "claim_logic 必须声明 semantic_audit_status=completed"
        )
    review = result.get("semantic_review")
    if not isinstance(review, Mapping):
        raise EvidenceSpineError("claim_logic 必须包含 semantic_review 对象")
    scope = _required_semantic_string(review.get("scope"), "semantic_review.scope")
    reviewed_by = _required_semantic_string(
        review.get("reviewed_by"), "semantic_review.reviewed_by"
    )
    if reviewed_by != reviewer:
        raise EvidenceSpineError(
            "semantic_review.reviewed_by 必须与 coverage reviewer 完全一致"
        )
    if review.get("ledger_fingerprint") != ledger.get("ledger_fingerprint"):
        raise EvidenceSpineError("semantic_review 使用了不同或过期的 ledger 指纹")
    if review.get("input_fingerprint") != ledger.get("input_fingerprint"):
        raise EvidenceSpineError("semantic_review 使用了不同或过期的输入指纹")

    map_value = (
        map_validation.get("manuscript_map", {})
        if isinstance(map_validation, Mapping)
        else {}
    )
    nodes = map_value.get("nodes", []) if isinstance(map_value, Mapping) else []
    edges = map_value.get("edges", []) if isinstance(map_value, Mapping) else []
    expected_node_ids = {
        str(item.get("id", ""))
        for item in nodes
        if isinstance(item, Mapping) and str(item.get("id", "")).strip()
    }
    expected_edge_ids = {
        str(item.get("id", ""))
        for item in edges
        if isinstance(item, Mapping) and str(item.get("id", "")).strip()
    }
    node_reviews, node_assessments = _validate_semantic_review_items(
        review.get("node_reviews"),
        id_field="node_id",
        expected_ids=expected_node_ids,
        label="node_reviews",
    )
    edge_reviews, edge_assessments = _validate_semantic_review_items(
        review.get("edge_reviews"),
        id_field="edge_id",
        expected_ids=expected_edge_ids,
        label="edge_reviews",
    )

    gaps = (
        map_validation.get("contract_gaps", [])
        if isinstance(map_validation, Mapping)
        else []
    )
    gaps = gaps if isinstance(gaps, list) else []
    gap_reviews_value = review.get("contract_gap_reviews")
    if not isinstance(gap_reviews_value, list):
        raise EvidenceSpineError(
            "semantic_review.contract_gap_reviews 必须是数组"
        )
    gap_reviews: list[dict[str, Any]] = []
    seen_gap_indices: set[int] = set()
    for position, item in enumerate(gap_reviews_value):
        if not isinstance(item, Mapping):
            raise EvidenceSpineError(
                f"semantic_review.contract_gap_reviews[{position}] 必须是对象"
            )
        gap_index = item.get("gap_index")
        if (
            isinstance(gap_index, bool)
            or not isinstance(gap_index, int)
            or gap_index < 0
            or gap_index >= len(gaps)
            or gap_index in seen_gap_indices
        ):
            raise EvidenceSpineError(
                "semantic_review.contract_gap_reviews.gap_index 必须唯一并对应现有 gap"
            )
        gap = gaps[gap_index]
        gap = gap if isinstance(gap, Mapping) else {}
        if (
            item.get("gap_code") != gap.get("code")
            or item.get("gap_path") != gap.get("path")
        ):
            raise EvidenceSpineError(
                f"semantic_review.contract_gap_reviews[{position}] 未绑定对应 contract gap"
            )
        assessment = _required_semantic_string(
            item.get("assessment"),
            f"semantic_review.contract_gap_reviews[{position}].assessment",
        )
        if assessment not in UNRESOLVED_SEMANTIC_ASSESSMENTS:
            raise EvidenceSpineError(
                "contract gap 的 assessment 必须明确为 unresolved、contradicted、"
                "not_yet_written 或 not_applicable"
            )
        _required_semantic_string(
            item.get("rationale"),
            f"semantic_review.contract_gap_reviews[{position}].rationale",
        )
        seen_gap_indices.add(gap_index)
        gap_reviews.append(copy.deepcopy(dict(item)))
    if seen_gap_indices != set(range(len(gaps))):
        raise EvidenceSpineError(
            "semantic_review.contract_gap_reviews 必须逐项覆盖全部 contract_gaps"
        )

    assessments = node_assessments + edge_assessments
    has_unresolved = any(
        value in UNRESOLVED_SEMANTIC_ASSESSMENTS for value in assessments
    ) or bool(gap_reviews)
    if (
        isinstance(map_validation, Mapping)
        and map_validation.get("argument_status") != "closed"
        and expected_node_ids | expected_edge_ids
        and not has_unresolved
    ):
        raise EvidenceSpineError(
            "argument_status 未闭环时，semantic_review 不能把全部节点和边标为 satisfied"
        )
    return {
        "scope": scope,
        "reviewed_by": reviewed_by,
        "input_fingerprint": ledger.get("input_fingerprint"),
        "ledger_fingerprint": ledger.get("ledger_fingerprint"),
        "node_reviews": node_reviews,
        "edge_reviews": edge_reviews,
        "contract_gap_reviews": gap_reviews,
        "has_unresolved_assessment": has_unresolved,
    }


def _validate_claim_logic_work_items(
    result: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    embedded = result.get("manuscript_map_validation")
    map_value = (
        embedded.get("manuscript_map", {})
        if isinstance(embedded, Mapping)
        else {}
    )
    nodes = map_value.get("nodes", []) if isinstance(map_value, Mapping) else []
    known_node_ids = {
        str(item.get("id", ""))
        for item in nodes
        if isinstance(item, Mapping) and str(item.get("id", "")).strip()
    }

    questions_value = result.get("questions_for_author", [])
    if not isinstance(questions_value, list):
        raise EvidenceSpineError("questions_for_author 必须是数组")
    questions: list[dict[str, Any]] = []
    question_ids: set[str] = set()
    for index, item in enumerate(questions_value):
        if not isinstance(item, Mapping):
            raise EvidenceSpineError(f"questions_for_author[{index}] 必须是对象")
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in question_ids:
            raise EvidenceSpineError("给作者的问题必须具有唯一且非空的 id")
        for field in ("question", "why_it_matters", "needed_evidence_or_decision"):
            if not str(item.get(field, "")).strip():
                raise EvidenceSpineError(f"{identifier} 缺少 {field}")
        node_ids = item.get("node_ids")
        if not isinstance(node_ids, list) or not node_ids:
            raise EvidenceSpineError(f"{identifier}.node_ids 必须是非空数组")
        if any(not isinstance(value, str) or not value.strip() for value in node_ids):
            raise EvidenceSpineError(f"{identifier}.node_ids 含无效节点 ID")
        unknown = sorted(set(node_ids) - known_node_ids)
        if unknown:
            raise EvidenceSpineError(
                f"{identifier} 引用了未知论文主线节点：{', '.join(unknown)}"
            )
        question_ids.add(identifier)
        questions.append(copy.deepcopy(dict(item)))

    tasks_value = result.get("next_writing_tasks", [])
    if not isinstance(tasks_value, list):
        raise EvidenceSpineError("next_writing_tasks 必须是数组")
    tasks: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    for index, item in enumerate(tasks_value):
        if not isinstance(item, Mapping):
            raise EvidenceSpineError(f"next_writing_tasks[{index}] 必须是对象")
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in seen_task_ids:
            raise EvidenceSpineError("下一步任务必须具有唯一且非空的 id")
        for field in ("task", "why_now", "completion_evidence"):
            if not str(item.get(field, "")).strip():
                raise EvidenceSpineError(f"{identifier} 缺少 {field}")
        depends_on = item.get("depends_on")
        if not isinstance(depends_on, list) or any(
            not isinstance(value, str) or not value.strip() for value in depends_on
        ):
            raise EvidenceSpineError(f"{identifier}.depends_on 必须是任务 ID 数组")
        unknown_dependencies = sorted(set(depends_on) - seen_task_ids)
        if unknown_dependencies:
            raise EvidenceSpineError(
                f"{identifier} 依赖尚未出现的任务：{', '.join(unknown_dependencies)}"
            )
        seen_task_ids.add(identifier)
        tasks.append(copy.deepcopy(dict(item)))
    return questions, tasks


def _planned_target_occurrence_matches(
    *,
    check_id: str,
    quote: str,
    target_kind: str,
    target_identifier: str,
) -> bool:
    if check_id == "crossref-callout-planned-target":
        if target_kind not in {"figure", "table", "equation"}:
            return False
        for match in CALLOUT_RE.finditer(quote):
            if (
                _crossref_kind(match.group("label")) == target_kind
                and match.group("identifier").casefold()
                == target_identifier.casefold()
                and _is_explicitly_planned_target(
                    quote, match.start(), match.end()
                )
            ):
                return True
        return False
    if check_id == "latex-reference-planned-label":
        if target_kind != "latex-label":
            return False
        for match in LATEX_REFERENCE_RE.finditer(quote):
            keys = [
                key.strip()
                for key in match.group(1).split(",")
                if key.strip()
            ]
            if (
                target_identifier in keys
                and _is_explicitly_planned_target(
                    quote, match.start(), match.end()
                )
            ):
                return True
        return False
    return False


def _validate_draft_planned_items(
    result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    values = result.get("planned_items", [])
    if not isinstance(values, list):
        raise EvidenceSpineError("planned_items 必须是数组")
    if values and result.get("manuscript_stage") != "draft":
        raise EvidenceSpineError(
            "planned_items 只能来自 manuscript_stage=draft 的确定性审核"
        )
    planned: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            raise EvidenceSpineError(f"planned_items[{index}] 必须是对象")
        identifier = str(item.get("id", "")).strip()
        if not identifier.startswith("PLAN-") or identifier in identifiers:
            raise EvidenceSpineError("planned_items 必须具有唯一的 PLAN-* id")
        check_id = str(item.get("check_id", "")).strip()
        if check_id not in VALID_DRAFT_PLANNED_CHECKS:
            raise EvidenceSpineError(
                f"{identifier} 使用了不允许的 planned check_id：{check_id}"
            )
        if item.get("status") != "planned":
            raise EvidenceSpineError(f"{identifier}.status 必须为 planned")
        location = item.get("location")
        if not isinstance(location, Mapping) or not str(
            location.get("source", "")
        ).strip():
            raise EvidenceSpineError(f"{identifier}.location 必须含 source")
        if not any(
            isinstance(location.get(field), int) and location.get(field) >= 0
            for field in ("line", "paragraph", "page")
        ):
            raise EvidenceSpineError(
                f"{identifier}.location 必须含 line、paragraph 或 page"
            )
        if not str(item.get("quote", "")).strip():
            raise EvidenceSpineError(f"{identifier}.quote 不能为空")
        target = item.get("target")
        if not isinstance(target, Mapping) or not str(
            target.get("kind", "")
        ).strip() or not str(target.get("identifier", "")).strip():
            raise EvidenceSpineError(
                f"{identifier}.target 必须含 kind 与 identifier"
            )
        quote = str(item.get("quote", ""))
        target_kind = str(target.get("kind", "")).strip()
        target_identifier = str(target.get("identifier", "")).strip()
        if not _planned_target_occurrence_matches(
            check_id=check_id,
            quote=quote,
            target_kind=target_kind,
            target_identifier=target_identifier,
        ):
            raise EvidenceSpineError(
                f"{identifier} 的 quote 不含与 check_id/target 匹配的明确计划 occurrence"
            )
        if not str(item.get("next_step", "")).strip():
            raise EvidenceSpineError(f"{identifier}.next_step 不能为空")
        identifiers.add(identifier)
        planned.append(copy.deepcopy(dict(item)))
    return planned


def _parse_capability_updates(values: Sequence[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise EvidenceSpineError("--capability 必须使用 name=available|partial|missing")
        name, status = (part.strip() for part in value.split("=", 1))
        if name not in CAPABILITIES:
            raise EvidenceSpineError(f"未知证据能力：{name}")
        if status not in CAPABILITY_STATUSES:
            raise EvidenceSpineError(f"证据能力状态无效：{status}")
        updates[name] = status
    return updates


def _validate_pass_result_payload(
    result: Mapping[str, Any],
    ledger: Mapping[str, Any],
    *,
    pass_id: str,
    status: str,
    mode: str,
    reviewer: Any,
    attest_ledger_read: bool,
) -> dict[str, Any]:
    schema_version = _validate_result_envelope_shape(
        result,
        pass_id=pass_id,
        status=status,
    )
    warnings, source_bound = _validate_result_sources(result, ledger)
    provenance = (
        result.get("provenance", {})
        if isinstance(result.get("provenance"), Mapping)
        else {}
    )
    native_fingerprint = provenance.get("ledger_fingerprint")
    if (
        provenance.get("input_fingerprint")
        and provenance.get("input_fingerprint") != ledger.get("input_fingerprint")
    ):
        raise EvidenceSpineError("pass result 使用了不同或过期的输入指纹")
    reviewer_text = reviewer.strip() if isinstance(reviewer, str) else ""
    if native_fingerprint:
        if native_fingerprint != ledger["ledger_fingerprint"]:
            raise EvidenceSpineError("pass result 使用了不同或过期的 ledger 指纹")
        binding = "native"
    elif PASS_SPEC_BY_ID[pass_id]["semantic"]:
        if not attest_ledger_read or not reviewer_text:
            raise EvidenceSpineError(
                "语义 pass 缺少原生 ledger 指纹；必须提供 --attest-ledger-read 和 --reviewer"
            )
        if not source_bound:
            raise EvidenceSpineError("语义 pass 的人工绑定仍需当前输入哈希")
        binding = "reviewer_attested"
    else:
        if not source_bound:
            raise EvidenceSpineError("非语义 pass 必须提供当前输入哈希或原生 ledger 指纹")
        binding = "paired_after_run"

    if status == "completed" and pass_id == "claim_logic":
        map_completion = (
            "draft"
            if mode == "draft"
            else "complete" if mode == "deep" else None
        )
        map_validation = _validate_embedded_manuscript_map(
            result,
            ledger,
            completion=map_completion,
            required=mode in {"draft", "deep"},
        )
        _validate_claim_logic_semantic_review(
            result,
            map_validation,
            ledger,
            reviewer=reviewer,
        )
        _validate_claim_logic_work_items(result)
    if status == "completed" and pass_id == "deterministic_text":
        planned_items = _validate_draft_planned_items(result)
        if planned_items and mode != "draft":
            raise EvidenceSpineError(
                "draft planned_items 不能记录到非 draft evidence spine"
            )

    inventory: dict[str, Any] | None = None
    if status == "not_applicable":
        inventory = _validate_not_applicable_inventory(result)
    elif not _has_completed_result_evidence(result, pass_id):
        raise EvidenceSpineError(
            "completed result 缺少与 pass 匹配的可核验执行证据，不能证明审核已完成"
        )
    findings = result.get("findings", result.get("formal_findings", []))
    return {
        "schema_version": schema_version,
        "finding_count": len(findings) if isinstance(findings, list) else None,
        "planned_item_count": (
            len(result.get("planned_items", []))
            if isinstance(result.get("planned_items"), list)
            else None
        ),
        "binding": binding,
        "warnings": warnings,
        "inventory": inventory,
    }


def record_pass(
    coverage_path: str | Path,
    ledger_path: str | Path,
    output_path: str | Path,
    *,
    pass_id: str,
    status: str,
    result_path: str | Path | None = None,
    rationale: str = "",
    reviewer: str = "",
    attest_ledger_read: bool = False,
    capability_updates: Mapping[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if pass_id not in PASS_SPEC_BY_ID:
        raise EvidenceSpineError(f"未知 pass：{pass_id}")
    if status not in VALID_PASS_STATUSES - {"not_run"}:
        raise EvidenceSpineError("record-pass 不能写入该状态")
    if (
        status == "not_applicable"
        and not PASS_SPEC_BY_ID[pass_id]["allow_not_applicable"]
    ):
        raise EvidenceSpineError(f"pass {pass_id} 始终适用，不能标记为 not_applicable")
    coverage = load_json_object(coverage_path, "coverage.json")
    ledger = load_json_object(ledger_path, "evidence-ledger.json")
    _validate_contract_pair(coverage, ledger)
    updated = copy.deepcopy(coverage)
    pass_record = next(
        (item for item in updated.get("passes", []) if item.get("pass_id") == pass_id),
        None,
    )
    if pass_record is None:
        raise EvidenceSpineError(f"coverage 缺少 pass：{pass_id}")

    if status != "completed" and not rationale.strip():
        raise EvidenceSpineError(f"状态 {status} 必须提供 --rationale")
    if status in {"completed", "not_applicable"} and result_path is None:
        raise EvidenceSpineError(f"{status} pass 必须提供 --result 作为执行或清点证据")

    result_file: Path | None = None
    result_record: dict[str, Any] | None = None
    binding = "none"
    if status in {"completed", "not_applicable"}:
        result_file = Path(result_path or "").resolve(strict=True)
        result = load_json_object(result_file, "pass result")
        declared_pass = str(result.get("pass_id", "")).strip()
        if declared_pass and declared_pass != pass_id:
            raise EvidenceSpineError(
                f"pass result 声明为 {declared_pass}，不能记录为 {pass_id}"
            )
        warnings, source_bound = _validate_result_sources(result, ledger)
        provenance = (
            result.get("provenance", {})
            if isinstance(result.get("provenance"), Mapping)
            else {}
        )
        native_fingerprint = provenance.get("ledger_fingerprint")
        if provenance.get("input_fingerprint") and provenance.get("input_fingerprint") != ledger.get("input_fingerprint"):
            raise EvidenceSpineError("pass result 使用了不同或过期的输入指纹")
        if native_fingerprint:
            if native_fingerprint != ledger["ledger_fingerprint"]:
                raise EvidenceSpineError("pass result 使用了不同或过期的 ledger 指纹")
            binding = "native"
        elif PASS_SPEC_BY_ID[pass_id]["semantic"]:
            if not attest_ledger_read or not reviewer.strip():
                raise EvidenceSpineError(
                    "语义 pass 缺少原生 ledger 指纹；必须提供 --attest-ledger-read 和 --reviewer"
                )
            if not source_bound:
                raise EvidenceSpineError("语义 pass 的人工绑定仍需当前输入哈希")
            binding = "reviewer_attested"
        else:
            if not source_bound:
                raise EvidenceSpineError("非语义 pass 必须提供当前输入哈希或原生 ledger 指纹")
            binding = "paired_after_run"
        if status == "completed" and pass_id == "claim_logic":
            map_completion = (
                "draft"
                if coverage.get("mode") == "draft"
                else "complete" if coverage.get("mode") == "deep" else None
            )
            map_validation = _validate_embedded_manuscript_map(
                result,
                ledger,
                completion=map_completion,
                required=coverage.get("mode") in {"draft", "deep"},
            )
            _validate_claim_logic_semantic_review(
                result,
                map_validation,
                ledger,
                reviewer=reviewer,
            )
            _validate_claim_logic_work_items(result)
        if status == "completed" and pass_id == "deterministic_text":
            planned_items = _validate_draft_planned_items(result)
            if planned_items and coverage.get("mode") != "draft":
                raise EvidenceSpineError(
                    "draft planned_items 不能记录到非 draft evidence spine"
                )
        inventory: dict[str, Any] | None = None
        if status == "not_applicable":
            inventory = _validate_not_applicable_inventory(result)
        elif not _has_completed_result_evidence(result, pass_id):
            raise EvidenceSpineError(
                "completed result 缺少与 pass 匹配的可核验执行证据，不能证明审核已完成"
            )
        validated_result = _validate_pass_result_payload(
            result,
            ledger,
            pass_id=pass_id,
            status=status,
            mode=str(coverage.get("mode", "")),
            reviewer=reviewer,
            attest_ledger_read=attest_ledger_read,
        )
        binding = str(validated_result["binding"])

        findings = result.get("findings", result.get("formal_findings", []))
        result_record = {
            "path": str(result_file),
            "sha256": sha256_file(result_file),
            "schema_version": validated_result["schema_version"],
            "finding_count": validated_result["finding_count"],
            "ledger_fingerprint": ledger["ledger_fingerprint"],
            "planned_item_count": validated_result["planned_item_count"],
            "binding": binding,
            "warnings": validated_result["warnings"],
            "inventory": validated_result["inventory"],
        }

    pass_record.update(
        {
            "status": status,
            "rationale": rationale.strip(),
            "ledger_binding": binding,
            "result": result_record,
            "reviewer": reviewer.strip(),
            "recorded_at": utc_now(),
        }
    )
    for name, capability_status in (capability_updates or {}).items():
        if name not in CAPABILITIES or capability_status not in CAPABILITY_STATUSES:
            raise EvidenceSpineError(f"非法证据能力更新：{name}={capability_status}")
        updated["evidence_capabilities"][name] = capability_status
    updated["updated_at"] = utc_now()
    updated["coverage_fingerprint"] = coverage_fingerprint(updated)
    protected_paths: list[str | Path] = [coverage_path, ledger_path]
    protected_paths.extend(
        str(item.get("path", ""))
        for item in ledger.get("dependencies", [])
        if isinstance(item, Mapping) and str(item.get("path", "")).strip()
    )
    if result_file is not None:
        protected_paths.append(result_file)
    _assert_safe_write_targets([output_path], protected_paths)
    atomic_write(
        Path(output_path),
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
        force=force,
    )
    return updated


def _validate_manifest(manifest: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceSpineError("artifact-manifest.json schema_version 不兼容")
    if manifest.get("input_fingerprint") != manifest_fingerprint(manifest):
        raise EvidenceSpineError("artifact-manifest.json 指纹无效或内容已被修改")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise EvidenceSpineError("artifact-manifest.json artifacts 必须是数组")
    if any(not isinstance(item, Mapping) for item in artifacts):
        raise EvidenceSpineError("artifact-manifest.json artifact 必须是对象")
    source_ids = [str(item.get("source_id", "")) for item in artifacts]
    if any(not value for value in source_ids) or len(source_ids) != len(set(source_ids)):
        raise EvidenceSpineError("artifact-manifest.json source_id 缺失或重复")

    root_path = Path(str(manifest.get("root_input", "")))
    root_source_id = str(manifest.get("root_source_id", ""))
    root_artifact = next(
        (item for item in artifacts if item.get("source_id") == root_source_id), None
    )
    if root_artifact is None or root_artifact.get("role") != "manuscript_source":
        problems.append("root_source_binding_missing")
    else:
        artifact_root = Path(str(root_artifact.get("path", "")))
        if root_path.resolve(strict=False) != artifact_root.resolve(strict=False):
            problems.append("root_input_path_mismatch")
    if not root_path.is_file():
        problems.append("missing_root_input")
    elif sha256_file(root_path) != manifest.get("root_input_sha256"):
        problems.append("stale_root_input")

    standard_sources = [item for item in artifacts if item.get("role") == "standard_source"]
    ordinary = [item for item in artifacts if item.get("role") != "standard_source"]
    current_paths: set[str] = set()
    for artifact in ordinary:
        path_text = artifact.get("path")
        if not path_text:
            problems.append(f"missing_path:{artifact.get('source', '')}")
            continue
        path = Path(str(path_text))
        if not path.is_file():
            problems.append(f"missing_artifact:{artifact.get('source', '')}")
            continue
        if sha256_file(path) != artifact.get("sha256"):
            problems.append(f"stale_artifact:{artifact.get('source', '')}")
            continue
        current_paths.add(str(path.resolve()))

    problems.extend(_validate_cited_source_identities(artifacts))

    if standard_sources:
        source_maps = [item for item in artifacts if item.get("role") == "standard_source_map"]
        registries = [item for item in artifacts if item.get("role") == "standards_registry"]
        if len(source_maps) != 1 or len(registries) != 1:
            problems.append("standard_authorization_dependencies_missing")
            return problems
        source_map = source_maps[0]
        registry = registries[0]
        if str(Path(str(source_map.get("path", ""))).resolve(strict=False)) not in current_paths or str(Path(str(registry.get("path", ""))).resolve(strict=False)) not in current_paths:
            problems.append("standard_authorization_dependencies_stale")
            return problems
        try:
            authorized = authorize_standard_source_map(
                Path(str(source_map["path"])), Path(str(registry["path"]))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            problems.append(f"standard_authorization_invalid:{exc}")
            return problems
        allowed_by_path = {
            str(Path(str(item["resolved_path"])).resolve()): item
            for item in authorized
            if item.get("gate_status") == "allowed"
        }
        map_digest = str(source_map.get("sha256", ""))
        registry_digest = str(registry.get("sha256", ""))
        for artifact in standard_sources:
            path = Path(str(artifact.get("path", "")))
            expected = allowed_by_path.get(str(path.resolve(strict=False)))
            if expected is None:
                problems.append(f"standard_source_not_authorized:{artifact.get('source', '')}")
                continue
            expected_authorization = {
                key: expected.get(key)
                for key in (
                    "designation",
                    "canonical_designation",
                    "family",
                    "processing_mode",
                    "rights_attested",
                    "permission_reference_provided",
                    "permission_reference_sha256",
                    "fulltext_processing_policy",
                    "gate_status",
                    "source_map_entry_sha256",
                )
            }
            expected_authorization["source_map_sha256"] = map_digest
            expected_authorization["standards_registry_sha256"] = registry_digest
            if canonical_json(artifact.get("authorization")) != canonical_json(expected_authorization):
                problems.append(f"standard_authorization_mismatch:{artifact.get('source', '')}")
                continue
            if not path.is_file():
                problems.append(f"missing_artifact:{artifact.get('source', '')}")
            elif sha256_file(path) != artifact.get("sha256"):
                problems.append(f"stale_artifact:{artifact.get('source', '')}")
    return problems


def _load_units_for_validation(manifest: Mapping[str, Any]) -> tuple[list[SourceUnit], list[str]]:
    diagnostics: list[dict[str, Any]] = []
    try:
        units = _load_sources(Path(str(manifest["root_input"])), diagnostics)
    except (AuditError, OSError, KeyError) as exc:
        return [], [f"anchor_source_unavailable:{exc}"]
    problems = [
        f"anchor_extraction_warning:{item.get('source', '')}:{item.get('code', '')}"
        for item in diagnostics
        if item.get("level") == "warning"
    ]
    return units, problems


def _source_key(value: Any) -> str:
    return str(value or "").replace("\\", "/").casefold()


def _match_unit(units: Sequence[SourceUnit], source: str) -> SourceUnit | None:
    requested = _source_key(source)
    exact = [unit for unit in units if _source_key(unit.source) == requested]
    if len(exact) == 1:
        return exact[0]
    basename = Path(source).name.casefold()
    by_name = [unit for unit in units if Path(unit.source).name.casefold() == basename]
    return by_name[0] if len(by_name) == 1 else None


def _candidate_blocks(unit: SourceUnit, location: Mapping[str, Any]) -> list[Any]:
    line = location.get("line")
    if isinstance(line, int) and line > 0:
        start = max(0, line - 4)
        end = min(len(unit.blocks), line + 3)
        return unit.blocks[start:end]
    paragraph = location.get("paragraph")
    if isinstance(paragraph, int):
        return [
            block
            for block in unit.blocks
            if block.location().get("paragraph") == paragraph
        ]
    page = location.get("page")
    if isinstance(page, int):
        return [block for block in unit.blocks if block.location().get("page") == page]
    return []


def _locator_evidence_ids(
    units: Sequence[SourceUnit],
    evidence_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    location: Mapping[str, Any],
) -> tuple[bool, list[str], str]:
    source = str(location.get("source", ""))
    source_path = Path(source)
    if source_path.is_absolute() or ".." in source_path.parts:
        return False, [], "unsafe_source_locator"
    unit = _match_unit(units, source)
    if unit is None:
        return False, [], "source_not_found_or_ambiguous"
    blocks = _candidate_blocks(unit, location)
    if not blocks:
        return False, [], "locator_not_resolved"
    line_numbers = {block.line for block in blocks}
    source_records = evidence_by_source.get(_source_key(unit.source), [])
    identifiers = [
        str(item.get("evidence_id"))
        for item in source_records
        if item.get("locator", {}).get("line") in line_numbers
    ]
    if not identifiers:
        return False, [], "no_ledger_evidence_for_locator"
    return True, sorted(set(identifiers)), "verified"


def _anchor_finding(
    finding: Mapping[str, Any],
    units: Sequence[SourceUnit],
    evidence_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[bool, list[str], str]:
    location = finding.get("location")
    if not isinstance(location, Mapping):
        return False, [], "missing_location"
    source = str(location.get("source", ""))
    source_path = Path(source)
    if source_path.is_absolute() or ".." in source_path.parts:
        return False, [], "unsafe_source_locator"
    unit = _match_unit(units, source)
    if unit is None:
        return False, [], "source_not_found_or_ambiguous"
    quote = normalize_text(finding.get("quote"))
    if not quote:
        return False, [], "missing_quote"
    blocks = _candidate_blocks(unit, location)
    if not blocks:
        return False, [], "locator_not_resolved"
    window = normalize_text("\n".join(block.raw for block in blocks))
    if quote not in window and window not in quote:
        return False, [], "quote_not_found_near_locator"

    line_numbers = {block.line for block in blocks}
    source_records = evidence_by_source.get(_source_key(unit.source), [])
    evidence_ids = [
        str(item.get("evidence_id"))
        for item in source_records
        if item.get("locator", {}).get("line") in line_numbers
    ]
    existing = finding.get("evidence_ids")
    if isinstance(existing, list) and existing:
        known = {str(item.get("evidence_id")) for item in source_records}
        requested = [str(item) for item in existing]
        if not all(item in known for item in requested):
            return False, [], "unknown_evidence_id"
        if not all(item in set(evidence_ids) for item in requested):
            return False, [], "evidence_id_outside_locator"
        evidence_ids = requested
    if not evidence_ids:
        return False, [], "no_ledger_evidence_for_locator"

    for related in finding.get("related_locations", []):
        if not isinstance(related, Mapping):
            return False, [], "invalid_related_location"
        resolved, related_ids, reason = _locator_evidence_ids(
            units, evidence_by_source, related
        )
        if not resolved:
            return False, [], f"related_{reason}"
        evidence_ids.extend(related_ids)
    return True, sorted(set(evidence_ids)), "verified"


def _anchor_draft_planned_item(
    item: Mapping[str, Any],
    units: Sequence[SourceUnit],
    evidence_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[bool, list[str], str]:
    """Anchor a planned quote in one direction: quote must come from source."""
    location = item.get("location")
    if not isinstance(location, Mapping):
        return False, [], "missing_location"
    source = str(location.get("source", ""))
    source_path = Path(source)
    if source_path.is_absolute() or ".." in source_path.parts:
        return False, [], "unsafe_source_locator"
    unit = _match_unit(units, source)
    if unit is None:
        return False, [], "source_not_found_or_ambiguous"
    quote = normalize_text(item.get("quote"))
    if not quote:
        return False, [], "missing_quote"
    blocks = _candidate_blocks(unit, location)
    if not blocks:
        return False, [], "locator_not_resolved"
    source_window = normalize_text("\n".join(block.raw for block in blocks))
    if quote not in source_window:
        return False, [], "planned_quote_not_found_near_locator"
    return _anchor_finding(item, units, evidence_by_source)


def _required_capabilities(finding: Mapping[str, Any], pass_id: str) -> list[str]:
    category = str(finding.get("category", "")).casefold()
    check_id = str(finding.get("check_id", "")).casefold()
    required = {"manuscript_text"}
    if pass_id == "claim_support" or category == "citation-support":
        required.add("cited_full_text")
    if pass_id == "citation_integrity" or category == "citation-integrity":
        required.add("reference_metadata")
    if (
        pass_id == "visual"
        or category in {"visual", "figure", "table", "figure-table", "graphics"}
        or "figure-peak" in check_id
    ):
        required.add("rendered_pages")
    if pass_id == "engineering_standards" and check_id not in STANDARD_METADATA_CHECKS:
        required.add("standard_text")
    declared = finding.get("required_capabilities")
    if isinstance(declared, list):
        required.update(str(item) for item in declared if str(item))
    return sorted(required)


def _capabilities_satisfied(required: Sequence[str], available: Mapping[str, Any]) -> tuple[bool, list[str]]:
    missing = [
        item
        for item in required
        if available.get(item) not in {"available"}
    ]
    return not missing, missing


def _semantic_controls(
    finding: Mapping[str, Any],
    pass_id: str,
    *,
    ledger_digest: str,
    proposer: str,
) -> tuple[bool, str]:
    severity = str(finding.get("severity", ""))
    if finding.get("evidence_mode") == "deterministic":
        check_id = str(finding.get("check_id", "")).casefold()
        if pass_id == "engineering_standards" and check_id in STANDARD_METADATA_CHECKS:
            return True, "not_required"
        if severity in {"Blocker", "Major"} and pass_id in SEMANTIC_HIGH_SEVERITY_PASSES:
            return False, "untrusted_deterministic_override"
    if severity not in {"Blocker", "Major"} or pass_id not in SEMANTIC_HIGH_SEVERITY_PASSES:
        return True, "not_required"
    alternatives = finding.get("alternative_explanations")
    if not isinstance(alternatives, list) or not alternatives:
        return False, "missing_alternative_explanations"
    for item in alternatives:
        if not isinstance(item, Mapping):
            return False, "invalid_alternative_explanation"
        if not str(item.get("explanation", "")).strip():
            return False, "invalid_alternative_explanation"
        if item.get("status") not in {"ruled_out", "plausible", "not_checked"}:
            return False, "invalid_alternative_explanation_status"
        if item.get("status") == "not_checked":
            return False, "alternative_explanation_not_checked"
    recheck = finding.get("independent_recheck")
    if not isinstance(recheck, Mapping):
        return False, "missing_independent_recheck"
    if recheck.get("status") not in {"confirmed", "contested"}:
        return False, "independent_recheck_not_completed"
    if not str(recheck.get("reviewer", "")).strip() or not str(recheck.get("rationale", "")).strip():
        return False, "incomplete_independent_recheck"
    if proposer and str(recheck.get("reviewer", "")).strip().casefold() == proposer.strip().casefold():
        return False, "rechecker_not_independent"
    if recheck.get("ledger_fingerprint") != ledger_digest:
        return False, "recheck_ledger_mismatch"
    plausible = any(item.get("status") == "plausible" for item in alternatives)
    return True, "contested" if recheck.get("status") == "contested" or plausible else "verified"


def _adapt_finding(finding: dict[str, Any], pass_id: str) -> dict[str, Any]:
    """Normalize known producer differences without inventing factual evidence."""

    if pass_id == "claim_support":
        finding.setdefault(
            "expected",
            "Each cited source should support the nearby manuscript claim at the stated scope, conditions, and strength.",
        )
        finding.setdefault(
            "reason",
            "The source-by-source support decision identified a scope, condition, result, or contradiction mismatch.",
        )
        finding.setdefault(
            "required_capabilities", ["manuscript_text", "cited_full_text"]
        )
    return finding


def _result_findings(result: Mapping[str, Any], pass_id: str) -> list[dict[str, Any]]:
    values = result.get("findings")
    if not isinstance(values, list):
        values = result.get("formal_findings")
    if not isinstance(values, list):
        return []
    return [
        _adapt_finding(copy.deepcopy(item), pass_id)
        for item in values
        if isinstance(item, Mapping)
    ]




def _result_manual_candidates(
    result: Mapping[str, Any], pass_id: str
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if pass_id == "claim_support":
        for claim in result.get("claims", []):
            if not isinstance(claim, Mapping):
                continue
            for reference in claim.get("references", []):
                if not isinstance(reference, Mapping) or reference.get("verdict") != "unable_to_verify":
                    continue
                citation_key = str(reference.get("citation_key", ""))
                rationale = str(reference.get("rationale", "")).strip() or "The cited source could not be verified from available evidence."
                candidates.append(
                    {
                        "id": stable_id("MANUAL", claim.get("id", ""), citation_key, "unable_to_verify"),
                        "claim_id": claim.get("id", ""),
                        "citation_key": citation_key,
                        "priority": bool(claim.get("priority")),
                        "category": "citation-support-gap",
                        "check_id": "claim-support-unable-to-verify",
                        "severity": "Info",
                        "confidence": 0.0,
                        "status": "unable-to-verify",
                        "location": copy.deepcopy(claim.get("location", {})),
                        "quote": str(claim.get("claim", "")),
                        "observation": rationale,
                        "expected": "Priority citation-dependent claims should be checked against the cited source text.",
                        "reason": "unable_to_verify",
                        "evidence": copy.deepcopy(reference.get("selected_evidence", [])),
                        "suggested_fix": "Provide a lawful source copy or narrow the claim until support can be verified.",
                        "auto_fixable": False,
                        "_manual_reason": "claim_support_unable_to_verify",
                    }
                )
    elif pass_id == "engineering_standards":
        for task in result.get("review_tasks", []):
            if not isinstance(task, Mapping) or task.get("assessment") == "assessed":
                continue
            evidence_status = str(task.get("evidence_status", "not_assessed"))
            candidates.append(
                {
                    "id": str(task.get("id", "")) or stable_id("MANUAL", task),
                    "standard": task.get("standard", ""),
                    "reference_identifier": task.get("reference_identifier", ""),
                    "category": "standard-evidence-gap",
                    "check_id": "standard-review-not-assessed",
                    "severity": "Info",
                    "confidence": 0.0,
                    "status": "unable-to-verify",
                    "location": copy.deepcopy(task.get("manuscript_location", {})),
                    "quote": str(task.get("manuscript_context", "")),
                    "observation": f"The standard review task remains unresolved: {evidence_status}.",
                    "expected": "Clause, formula, provision, and applicability checks require the exact authorized edition.",
                    "reason": evidence_status,
                    "evidence": copy.deepcopy(task.get("source_evidence", [])),
                    "suggested_fix": "Supply authorized exact-edition evidence and complete the recorded standard review task.",
                    "auto_fixable": False,
                    "_manual_reason": f"standard_review_unresolved:{evidence_status}",
                }
            )
    elif pass_id == "quantitative":
        for candidate in result.get("review_candidates", []):
            if not isinstance(candidate, Mapping):
                continue
            candidates.append(
                {
                    "id": str(candidate.get("id", "")) or stable_id("MANUAL", candidate),
                    "category": "quantitative-review-candidate",
                    "check_id": str(candidate.get("type", "quantitative-review")),
                    "severity": "Info",
                    "confidence": 0.0,
                    "status": "needs-review",
                    "location": copy.deepcopy(candidate.get("location", {})),
                    "related_locations": copy.deepcopy(candidate.get("related_locations", [])),
                    "quote": str(candidate.get("quote", "")),
                    "observation": str(candidate.get("reason", "")),
                    "expected": str(candidate.get("required_evidence", "Additional quantitative evidence is required.")),
                    "reason": "quantitative_candidate_not_adjudicated",
                    "evidence": [],
                    "suggested_fix": str(candidate.get("required_evidence", "Complete the indicated manual check.")),
                    "auto_fixable": False,
                    "_manual_reason": "quantitative_review_candidate",
                }
            )
    return candidates
def _finding_schema_problems(finding: Mapping[str, Any]) -> list[str]:
    required = (
        "category",
        "check_id",
        "severity",
        "confidence",
        "status",
        "location",
        "quote",
        "observation",
        "expected",
        "reason",
        "evidence",
        "suggested_fix",
        "auto_fixable",
    )
    problems = [f"missing_field:{field}" for field in required if field not in finding]
    for field in (
        "category",
        "check_id",
        "status",
        "quote",
        "observation",
        "expected",
        "reason",
        "suggested_fix",
    ):
        if field in finding and not str(finding.get(field, "")).strip():
            problems.append(f"empty_field:{field}")
    if "location" in finding and not isinstance(finding.get("location"), Mapping):
        problems.append("invalid_field:location")
    if "evidence" in finding and not isinstance(finding.get("evidence"), list):
        problems.append("invalid_field:evidence")
    if "auto_fixable" in finding and not isinstance(finding.get("auto_fixable"), bool):
        problems.append("invalid_field:auto_fixable")
    if finding.get("status") not in VALID_FINDING_STATUSES:
        problems.append("invalid_status")
    category = str(finding.get("category", "")).casefold()
    if category == "citation-support":
        if finding.get("verdict") not in {"partially_supports", "does_not_support"}:
            problems.append("invalid_claim_support_verdict")
        if not str(finding.get("citation_key", "")).strip():
            problems.append("missing_citation_key")
        if not isinstance(finding.get("dimension_matches"), Mapping):
            problems.append("missing_dimension_matches")
        if not isinstance(finding.get("evidence"), list) or not finding.get("evidence"):
            problems.append("missing_direct_external_evidence")
    return problems


def _direct_evidence_role(finding: Mapping[str, Any], pass_id: str) -> str | None:
    check_id = str(finding.get("check_id", "")).casefold()
    if pass_id == "engineering_standards" and check_id not in STANDARD_METADATA_CHECKS:
        return "standard_source"
    if pass_id == "claim_support" or str(finding.get("category", "")).casefold() == "citation-support":
        return "cited_source"
    return None


def _pass_category_problem(finding: Mapping[str, Any], pass_id: str) -> str | None:
    category = str(finding.get("category", "")).strip().casefold()
    if not category:
        return None
    allowed: dict[str, set[str]] = {
        "claim_support": {"citation-support"},
        "engineering_standards": {
            "standard",
            "standards",
            "engineering-standard",
            "engineering-standards",
        },
        "visual": {"visual", "figure", "table", "figure-table", "graphics"},
    }
    if pass_id in allowed and category not in allowed[pass_id]:
        return f"incompatible_pass_category:{pass_id}:{category}"
    return None


def _identity_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _artifact_units(
    artifact: Mapping[str, Any], cache: dict[str, list[SourceUnit]]
) -> list[SourceUnit]:
    path_text = str(artifact.get("path", ""))
    if path_text in cache:
        return cache[path_text]
    diagnostics: list[dict[str, Any]] = []
    try:
        units = _load_sources(Path(path_text), diagnostics)
    except (AuditError, OSError):
        units = []
    cache[path_text] = units
    return units


def _artifact_matches_locator_source(artifact: Mapping[str, Any], source: str) -> bool:
    if not source:
        return False
    requested = _source_key(source)
    basename = Path(source).name.casefold()
    return requested == _source_key(artifact.get("source")) or basename in {
        Path(str(artifact.get("source", ""))).name.casefold(),
        Path(str(artifact.get("path", ""))).name.casefold(),
    }


def _select_direct_artifact(
    finding: Mapping[str, Any],
    item: Mapping[str, Any],
    role: str,
    artifacts: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str]:
    candidates = list(artifacts)
    evidence_source = finding.get("evidence_source")
    evidence_source = evidence_source if isinstance(evidence_source, Mapping) else {}
    digest = str(item.get("source_sha256", evidence_source.get("sha256", ""))).strip()
    if digest:
        candidates = [item for item in candidates if item.get("sha256") == digest]
        if not candidates:
            return None, "external_source_hash_not_declared"
    location = item.get("location") if isinstance(item.get("location"), Mapping) else {}
    source = str(location.get("source", evidence_source.get("basename", ""))).strip()
    if source:
        candidates = [item for item in candidates if _artifact_matches_locator_source(item, source)]
        if not candidates:
            return None, "external_locator_source_not_declared"
    if role == "cited_source":
        citation_key = str(finding.get("citation_key", "")).strip()
        item_key = str(item.get("citation_key", "")).strip()
        if item_key and citation_key and _identity_key(item_key) != _identity_key(citation_key):
            return None, "external_citation_key_mismatch"
        if citation_key:
            keyed = [
                artifact
                for artifact in candidates
                if _identity_key(citation_key)
                in {
                    _identity_key(key)
                    for key in artifact.get("identity", {}).get("citation_keys", [])
                }
            ]
            if not keyed:
                return None, "external_citation_key_not_declared"
            candidates = keyed
    else:
        designation = str(
            finding.get("standard_designation", finding.get("standard", ""))
        ).strip()
        if designation:
            keyed = [
                artifact
                for artifact in candidates
                if _identity_key(designation)
                in {
                    _identity_key(artifact.get("authorization", {}).get("designation", "")),
                    _identity_key(artifact.get("authorization", {}).get("canonical_designation", "")),
                }
            ]
            if not keyed:
                return None, "standard_designation_not_declared"
            candidates = keyed
    if len(candidates) == 1:
        return candidates[0], "verified"
    if not candidates:
        return None, "external_source_not_resolved"
    return None, "external_source_identity_ambiguous"


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _resolve_external_locator(
    artifact: Mapping[str, Any],
    item: Mapping[str, Any],
    quote: str,
    cache: dict[str, list[SourceUnit]],
) -> tuple[dict[str, Any] | None, str]:
    units = _artifact_units(artifact, cache)
    if not units:
        return None, "external_source_unreadable"
    location = dict(item.get("location", {})) if isinstance(item.get("location"), Mapping) else {}
    match_quote = normalize_text(quote.rstrip("….").strip())
    if not match_quote:
        return None, "missing_direct_external_evidence"
    line_requested = "line" in location
    page_requested = "page" in location
    paragraph_requested = "paragraph" in location
    line = _positive_int(location.get("line")) if line_requested else None
    page = _positive_int(location.get("page")) if page_requested else None
    paragraph = _positive_int(location.get("paragraph")) if paragraph_requested else None
    if (line_requested and line is None) or (page_requested and page is None) or (paragraph_requested and paragraph is None):
        return None, "external_locator_invalid"

    for unit in units:
        blocks = list(unit.blocks)
        if page_requested:
            blocks = [block for block in blocks if block.location().get("page") == page]
            if not blocks:
                continue
        if paragraph_requested and unit.paragraph_by_line:
            blocks = [block for block in blocks if block.location().get("paragraph") == paragraph]
            if not blocks:
                continue
        if line_requested:
            if page_requested:
                if line is None or line > len(blocks):
                    continue
                begin = max(0, line - 4)
                end = min(len(blocks), line + 3)
                blocks = blocks[begin:end]
            else:
                if line is None or line > len(unit.blocks):
                    continue
                begin = max(0, line - 4)
                end = min(len(unit.blocks), line + 3)
                blocks = unit.blocks[begin:end]
        if not blocks:
            continue
        window = normalize_text("\n".join(block.raw for block in blocks))
        if match_quote not in window and window not in match_quote:
            continue
        canonical: dict[str, Any] = {"source": artifact.get("source", "")}
        if line_requested:
            canonical["line"] = line
        else:
            matching = next(
                (block for block in blocks if normalize_text(block.raw) and normalize_text(block.raw) in match_quote),
                blocks[0],
            )
            canonical["line"] = matching.line
        if page_requested:
            canonical["page"] = page
        if paragraph_requested:
            canonical["paragraph"] = paragraph
        return canonical, "verified"
    return None, "external_quote_not_found_near_locator"


def _register_direct_evidence(
    finding: Mapping[str, Any],
    pass_id: str,
    manifest: Mapping[str, Any],
    cache: dict[str, list[SourceUnit]],
) -> tuple[list[dict[str, Any]], list[str]]:
    role = _direct_evidence_role(finding, pass_id)
    if role is None:
        return [], []
    artifacts = [item for item in manifest.get("artifacts", []) if item.get("role") == role]
    if not artifacts:
        return [], [f"missing_direct_artifact:{role}"]
    evidence_items = [
        item
        for item in finding.get("evidence", [])
        if isinstance(item, Mapping) and str(item.get("quote", item.get("text", ""))).strip()
    ]
    if not evidence_items:
        return [], ["missing_direct_external_evidence"]

    records: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, item in enumerate(evidence_items, 1):
        quote = re.sub(r"\s+", " ", str(item.get("quote", item.get("text", "")))).strip()
        artifact, identity_status = _select_direct_artifact(finding, item, role, artifacts)
        if artifact is None:
            problems.append(f"{identity_status}:{index}")
            continue
        locator, locator_status = _resolve_external_locator(artifact, item, quote, cache)
        if locator is None:
            problems.append(f"{locator_status}:{index}")
            continue
        quote_digest = sha256_bytes(quote.encode("utf-8"))
        identifier = stable_id(
            "EVD",
            artifact.get("source_id", ""),
            artifact.get("sha256", ""),
            canonical_json(locator).decode("utf-8"),
            quote_digest,
        )
        records.append(
            {
                "evidence_id": identifier,
                "kind": "external_source_span" if role == "cited_source" else "standard_span",
                "source_id": artifact.get("source_id", ""),
                "locator": locator,
                "quote": quote[:1200],
                "truncated": len(quote) > 1200,
                "text_sha256": quote_digest,
                "evidence_class": item.get("class", "B"),
                "extractor": artifact.get("format", "unknown"),
                "extraction_confidence": "medium" if artifact.get("format") == "pdf" else "high",
                "producer_pass": pass_id,
            }
        )
    return records, problems


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _finding_sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    location = item.get("location", {}) if isinstance(item.get("location"), Mapping) else {}
    return (
        SEVERITY_ORDER.get(str(item.get("severity", "Info")), 4),
        _source_key(location.get("source")),
        _safe_int(location.get("line", 0)),
        str(item.get("check_id", "")),
        str(item.get("id", "")),
    )


def _format_location(location: Mapping[str, Any]) -> str:
    pieces = [str(location.get("source", "unknown"))]
    for label, key in (("页", "page"), ("段", "paragraph"), ("行", "line")):
        if location.get(key) not in (None, ""):
            pieces.append(f"{label}{location[key]}")
    if location.get("section"):
        pieces.append(str(location["section"]))
    return " / ".join(pieces)

def _markdown_cell(value: Any) -> str:
    text = str(value if value not in (None, "") else "unknown")
    return text.replace("|", r"\|").replace("\r", " ").replace("\n", " ")



def render_report(data: Mapping[str, Any]) -> str:
    summary = data.get("summary", {})
    mode = str(data.get("mode", data.get("coverage", {}).get("mode", "")))
    report_title = "# 论文写作导航报告" if mode == "draft" else "# 论文审核裁决报告"
    lines = [
        "# 论文审核裁决报告",
        "",
        f"- 审核状态：`{data.get('review_status', '')}`",
        f"- 投稿准备度：`{data.get('submission_readiness', '')}`",
        f"- 正式发现：{summary.get('formal_finding_count', 0)}",
        f"- 人工确认项：{summary.get('manual_check_count', 0)}",
        f"- 草稿计划项：{summary.get('draft_planned_item_count', 0)}",
        f"- 报告指纹：`{data.get('report_fingerprint', '')}`",
        "",
    ]
    lines[0] = report_title
    lines.insert(2, f"- 工作模式：`{mode}`")
    if data.get("review_status") != "complete":
        lines.extend(
            [
                "> 本次审核未覆盖全部必要项目，不能把“未发现问题”解释为稿件无问题。",
                "",
            ]
        )
    lines.extend(["## 覆盖情况", ""])
    for item in data.get("coverage", {}).get("passes", []):
        marker = "必需" if item.get("required") else "可选"
        rationale = f"；{item.get('rationale')}" if item.get("rationale") else ""
        lines.append(
            f"- `{item.get('pass_id')}`（{marker}）：`{item.get('status')}`{rationale}"
        )
    map_validation = data.get("manuscript_map_validation")
    planned_items = data.get("draft_planned_items", [])
    planned_items = planned_items if isinstance(planned_items, list) else []
    if planned_items:
        lines.extend(
            [
                "",
                "## 草稿计划项（尚未完成，不是缺陷）",
                "",
            ]
        )
        for item in planned_items:
            if not isinstance(item, Mapping):
                continue
            target = item.get("target", {})
            target = target if isinstance(target, Mapping) else {}
            lines.extend(
                [
                    f"### {item.get('id', '')} · "
                    f"{target.get('kind', '')} {target.get('identifier', '')}",
                    "",
                    f"- 位置：{_format_location(item.get('location', {}))}",
                    f"- 当前文字：{item.get('quote', '')}",
                    f"- 下一步：{item.get('next_step', '')}",
                    "",
                ]
            )
    if isinstance(map_validation, Mapping):
        map_value = map_validation.get("manuscript_map", {})
        map_value = map_value if isinstance(map_value, Mapping) else {}
        card = map_value.get("card", {})
        card = card if isinstance(card, Mapping) else {}
        boundaries = card.get("scope_boundaries", [])
        boundaries = boundaries if isinstance(boundaries, list) else []
        lines.extend(
            [
                "",
                "## 论文主线卡",
                "",
                f"- 地图契约状态：`{map_validation.get('status', '')}`",
                f"- 论证闭环状态：`{map_validation.get('argument_status', '')}`",
                "",
                "| 项目 | 当前记录 |",
                "|---|---|",
            ]
        )
        for label, value in (
            ("目标期刊", card.get("target_journal")),
            ("文章类型", card.get("article_type")),
            ("研究问题", card.get("research_question")),
            ("中心信息", card.get("central_message")),
            ("范围边界", "；".join(str(item) for item in boundaries)),
        ):
            lines.append(f"| {label} | {_markdown_cell(value)} |")
        lines.extend(
            [
                "",
                "## 主线追踪",
                "",
                "| 起点 | 关系 | 终点 | 状态 | 证据绑定 |",
                "|---|---|---|---|---|",
            ]
        )
        rows = map_validation.get("traceability_rows", [])
        rows = rows if isinstance(rows, list) else []
        if not rows:
            lines.append("| — | — | — | — | — |")
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            source = " · ".join(
                str(row.get(key, ""))
                for key in ("from_id", "from_role", "from_label")
                if str(row.get(key, "")).strip()
            )
            target = " · ".join(
                str(row.get(key, ""))
                for key in ("to_id", "to_role", "to_label")
                if str(row.get(key, "")).strip()
            )
            lines.append(
                "| "
                + " | ".join(
                    _markdown_cell(value)
                    for value in (
                        source,
                        row.get("relation"),
                        target,
                        row.get("status"),
                        row.get("evidence_binding"),
                    )
                )
                + " |"
            )
        valid_rows = [row for row in rows if isinstance(row, Mapping)]
        satisfied = [
            row
            for row in valid_rows
            if row.get("status") == "verified"
            and row.get("evidence_binding") == "verified"
        ]
        unresolved = [row for row in valid_rows if row not in satisfied]
        lines.extend(["", "### 已满足的功能连接", ""])
        if not satisfied:
            lines.append("当前尚无同时完成状态确认与证据绑定的连接。")
        for row in satisfied:
            lines.append(
                f"- `{row.get('edge_id', '')}`：{row.get('from_id', '')} "
                f"—{row.get('relation', '')}→ {row.get('to_id', '')}"
            )
        lines.extend(["", "### 尚未解决的功能连接", ""])
        if not unresolved:
            lines.append("无。")
        for row in unresolved:
            lines.append(
                f"- `{row.get('edge_id', '')}`：{row.get('from_id', '')} "
                f"—{row.get('relation', '')}→ {row.get('to_id', '')}；"
                f"状态 `{row.get('status', '')}`，证据绑定 "
                f"`{row.get('evidence_binding', '')}`"
            )
        gaps = map_validation.get("contract_gaps", [])
        gaps = gaps if isinstance(gaps, list) else []
        lines.extend(["", "### 论证契约缺口", ""])
        if not gaps:
            lines.append("无。")
        for item in gaps:
            if not isinstance(item, Mapping):
                continue
            lines.extend(
                [
                    f"- `{item.get('code', '')}`",
                    f"  - 路径：`{item.get('path', '')}`",
                    f"  - 说明：{item.get('message', '')}",
                ]
            )
    findings = data.get("findings", [])
    lines.extend(["", "## 正式发现", ""])
    if not findings:
        lines.append("在当前已完成且证据充分的审核范围内，没有形成正式发现。")
    for item in findings:
        lines.extend(
            [
                f"### {item.get('severity', 'Info')} · {item.get('id', '')}",
                "",
                f"- 位置：{_format_location(item.get('location', {}))}",
                f"- 置信度：{item.get('confidence', '')}",
                f"- 原文：{item.get('quote', '')}",
                f"- 问题：{item.get('observation', '')}",
                f"- 建议：{item.get('suggested_fix', '')}",
                f"- 证据 ID：{', '.join(item.get('evidence_ids', []))}",
                "",
            ]
        )
    lines.extend(["## 人工确认项", ""])
    manual = data.get("manual_checks", [])
    if not manual:
        lines.append("无。")
    for item in manual:
        reasons = ", ".join(item.get("adjudication", {}).get("reasons", []))
        lines.extend(
            [
                f"- `{item.get('id', 'UNIDENTIFIED')}`（建议影响等级：{item.get('severity', 'Info')}）：{reasons}",
                f"  - 位置：{_format_location(item.get('location', {}))}",
                f"  - 原文：{item.get('quote', '')}",
            ]
        )
    questions = data.get("questions_for_author", [])
    questions = questions if isinstance(questions, list) else []
    if isinstance(map_validation, Mapping) or questions:
        lines.extend(["", "## 给作者的问题", ""])
        if not questions:
            lines.append("无。")
        for item in questions:
            if not isinstance(item, Mapping):
                continue
            nodes = ", ".join(str(value) for value in item.get("node_ids", []))
            lines.extend(
                [
                    f"### {item.get('id', '')} · {item.get('question', '')}",
                    "",
                    f"- 相关主线节点：{nodes}",
                    f"- 为什么重要：{item.get('why_it_matters', '')}",
                    f"- 需要补充：{item.get('needed_evidence_or_decision', '')}",
                    "",
                ]
            )
    tasks = data.get("next_writing_tasks", [])
    tasks = tasks if isinstance(tasks, list) else []
    if isinstance(map_validation, Mapping) or tasks:
        lines.extend(["## 下一步写作/证据任务", ""])
        if not tasks:
            lines.append("无。")
        for index, item in enumerate(tasks, start=1):
            if not isinstance(item, Mapping):
                continue
            dependencies = ", ".join(
                str(value) for value in item.get("depends_on", [])
            ) or "无"
            lines.extend(
                [
                    f"{index}. **{item.get('id', '')}**：{item.get('task', '')}",
                    f"   - 为什么现在做：{item.get('why_now', '')}",
                    f"   - 完成证据：{item.get('completion_evidence', '')}",
                    f"   - 前置任务：{dependencies}",
                ]
            )
    lines.extend(["", "## 诊断", ""])
    diagnostics = data.get("diagnostics", [])
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("无。")
    lines.append("")
    return "\n".join(lines)


def adjudicate_report(
    manifest_path: str | Path,
    ledger_path: str | Path,
    coverage_path: str | Path,
    output_dir: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    manifest = load_json_object(manifest_path, "artifact-manifest.json")
    ledger = load_json_object(ledger_path, "evidence-ledger.json")
    coverage = load_json_object(coverage_path, "coverage.json")
    _validate_contract_pair(coverage, ledger)
    if manifest.get("paper_id") != ledger.get("paper_id"):
        raise EvidenceSpineError("manifest 与 ledger 的 paper_id 不一致")
    if manifest.get("input_fingerprint") != ledger.get("input_fingerprint"):
        raise EvidenceSpineError("manifest 与 ledger 的输入指纹不一致")

    diagnostics = _validate_manifest(manifest)
    units, anchor_diagnostics = _load_units_for_validation(manifest)
    diagnostics.extend(anchor_diagnostics)
    stale_input = any(
        item.startswith(
            ("missing_artifact:", "stale_artifact:", "missing_root_input", "stale_root_input", "root_input_", "root_source_", "cited_source_identity_", "standard_authorization_")
        )
        for item in diagnostics
    )
    trusted_capabilities = _trusted_capabilities(coverage, manifest)

    evidence_ids = {str(item.get("evidence_id")) for item in ledger.get("evidence", [])}
    if len(evidence_ids) != len(ledger.get("evidence", [])):
        raise EvidenceSpineError("evidence-ledger.json 含重复 evidence_id")
    evidence_by_source: dict[str, list[Mapping[str, Any]]] = {}
    for item in ledger.get("evidence", []):
        locator = item.get("locator", {}) if isinstance(item.get("locator"), Mapping) else {}
        evidence_by_source.setdefault(_source_key(locator.get("source")), []).append(item)

    formal: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    manuscript_map_validation: dict[str, Any] | None = None
    claim_logic_semantic_review: dict[str, Any] | None = None
    questions_for_author: list[dict[str, Any]] = []
    next_writing_tasks: list[dict[str, Any]] = []
    draft_planned_items: list[dict[str, Any]] = []
    external_evidence_by_id: dict[str, dict[str, Any]] = {}
    artifact_text_cache: dict[str, list[SourceUnit]] = {}
    seen: dict[str, bytes] = {}
    incomplete_required = False
    contested = False

    for pass_record in coverage.get("passes", []):
        if not isinstance(pass_record, Mapping):
            continue
        pass_id = str(pass_record.get("pass_id", ""))
        status = str(pass_record.get("status", "not_run"))
        required = bool(pass_record.get("required"))
        if required and status not in {"completed", "not_applicable"}:
            incomplete_required = True
        if status not in {"completed", "not_applicable"}:
            continue
        result_record = pass_record.get("result")
        if not isinstance(result_record, Mapping):
            diagnostics.append(f"completed_pass_without_result:{pass_id}")
            if required:
                incomplete_required = True
            continue
        result_path = Path(str(result_record.get("path", "")))
        if not result_path.is_file():
            diagnostics.append(f"missing_pass_result:{pass_id}")
            if required:
                incomplete_required = True
            continue
        if sha256_file(result_path) != result_record.get("sha256"):
            diagnostics.append(f"stale_pass_result:{pass_id}")
            if required:
                incomplete_required = True
            continue
        if result_record.get("ledger_fingerprint") != ledger["ledger_fingerprint"]:
            diagnostics.append(f"stale_pass_ledger:{pass_id}")
            if required:
                incomplete_required = True
            continue
        try:
            result = load_json_object(result_path, f"{pass_id} result")
            validated_result = _validate_pass_result_payload(
                result,
                ledger,
                pass_id=pass_id,
                status=status,
                mode=str(coverage.get("mode", "")),
                reviewer=pass_record.get("reviewer", ""),
                attest_ledger_read=(
                    result_record.get("binding") == "reviewer_attested"
                ),
            )
            recorded_metadata = {
                key: result_record.get(key)
                for key in (
                    "schema_version",
                    "finding_count",
                    "planned_item_count",
                    "binding",
                    "warnings",
                    "inventory",
                )
            }
            if canonical_json(recorded_metadata) != canonical_json(validated_result):
                raise EvidenceSpineError("coverage result metadata 与当前 pass result 不一致")
            if pass_record.get("ledger_binding") != validated_result.get("binding"):
                raise EvidenceSpineError("coverage ledger_binding 与 pass result 不一致")
        except (EvidenceSpineError, OSError, json.JSONDecodeError) as exc:
            diagnostics.append(f"invalid_pass_result_contract:{pass_id}:{exc}")
            if required:
                incomplete_required = True
            continue
        if status == "not_applicable":
            continue
        if pass_id == "deterministic_text":
            try:
                planned_items = _validate_draft_planned_items(result)
                if planned_items and coverage.get("mode") != "draft":
                    raise EvidenceSpineError(
                        "draft planned_items 出现在非 draft evidence spine"
                    )
            except EvidenceSpineError as exc:
                diagnostics.append(f"invalid_draft_planned_items:{exc}")
                incomplete_required = True
                continue
            for planned_item in planned_items:
                anchored, attached_ids, anchor_status = _anchor_draft_planned_item(
                    planned_item,
                    units,
                    evidence_by_source,
                )
                if not anchored:
                    diagnostics.append(
                        "invalid_draft_planned_item_anchor:"
                        f"{planned_item.get('id', '')}:{anchor_status}"
                    )
                    incomplete_required = True
                    continue
                planned_item["origin_pass"] = pass_id
                planned_item["evidence_ids"] = attached_ids
                draft_planned_items.append(planned_item)
        if pass_id == "claim_logic":
            map_completion = (
                "draft"
                if coverage.get("mode") == "draft"
                else "complete" if coverage.get("mode") == "deep" else None
            )
            try:
                manuscript_map_validation = _validate_embedded_manuscript_map(
                    result,
                    ledger,
                    completion=map_completion,
                    required=coverage.get("mode") in {"draft", "deep"},
                )
                claim_logic_semantic_review = (
                    _validate_claim_logic_semantic_review(
                        result,
                        manuscript_map_validation,
                        ledger,
                        reviewer=str(pass_record.get("reviewer", "")),
                    )
                )
                questions_for_author, next_writing_tasks = (
                    _validate_claim_logic_work_items(result)
                )
            except EvidenceSpineError as exc:
                diagnostics.append(f"invalid_claim_logic_contract:{exc}")
                manuscript_map_validation = None
                claim_logic_semantic_review = None
                questions_for_author = []
                next_writing_tasks = []
                incomplete_required = True
                continue
        for candidate in _result_manual_candidates(result, pass_id):
            manual_reason = str(candidate.pop("_manual_reason", "unresolved_review_item"))
            anchored, attached_ids, anchor_status = _anchor_finding(
                candidate, units, evidence_by_source
            )
            reasons = [manual_reason]
            if not anchored:
                reasons.append(anchor_status)
            candidate["origin_pass"] = pass_id
            candidate["evidence_ids"] = attached_ids
            candidate["adjudication"] = {
                "outcome": "manual_check",
                "reasons": sorted(set(reasons)),
                "required_capabilities": _required_capabilities(candidate, pass_id),
                "severity_preserved_as_proposed_impact": candidate.get("severity", "Info"),
            }
            manual.append(candidate)
        for finding in _result_findings(result, pass_id):
            finding_id = str(finding.get("id", ""))
            if not finding_id:
                finding_id = stable_id(
                    "SEM",
                    pass_id,
                    finding.get("check_id", ""),
                    canonical_json(finding.get("location", {})).decode("utf-8"),
                    finding.get("quote", ""),
                )
                finding["id"] = finding_id
            fingerprint = canonical_json(finding)
            if finding_id in seen:
                if seen[finding_id] != fingerprint:
                    diagnostics.append(f"conflicting_duplicate_finding:{finding_id}")
                    clone = copy.deepcopy(finding)
                    clone["origin_pass"] = pass_id
                    clone["adjudication"] = {
                        "outcome": "manual_check",
                        "reasons": ["conflicting_duplicate_finding"],
                    }
                    manual.append(clone)
                continue
            seen[finding_id] = fingerprint
            finding["origin_pass"] = pass_id
            reasons: list[str] = _finding_schema_problems(finding)
            category_problem = _pass_category_problem(finding, pass_id)
            if category_problem:
                reasons.append(category_problem)
            anchored, attached_ids, anchor_status = _anchor_finding(
                finding, units, evidence_by_source
            )
            if not anchored:
                reasons.append(anchor_status)
            direct_records, direct_problems = _register_direct_evidence(
                finding, pass_id, manifest, artifact_text_cache
            )
            reasons.extend(direct_problems)
            for record in direct_records:
                identifier = str(record["evidence_id"])
                previous = external_evidence_by_id.get(identifier)
                if previous is not None and canonical_json(previous) != canonical_json(record):
                    reasons.append(f"conflicting_external_evidence:{identifier}")
                    continue
                external_evidence_by_id[identifier] = record
                attached_ids.append(identifier)
            attached_ids = sorted(set(attached_ids))
            required_capabilities = _required_capabilities(finding, pass_id)
            capabilities_ok, missing_capabilities = _capabilities_satisfied(
                required_capabilities,
                trusted_capabilities,
            )
            if not capabilities_ok:
                reasons.extend(f"missing_capability:{item}" for item in missing_capabilities)
            controls_ok, controls_status = _semantic_controls(
                finding,
                pass_id,
                ledger_digest=ledger["ledger_fingerprint"],
                proposer=str(pass_record.get("reviewer", "")),
            )
            if not controls_ok:
                reasons.append(controls_status)
            if stale_input:
                reasons.append("stale_input")
            confidence = finding.get("confidence")
            confidence_valid = (
                not isinstance(confidence, bool)
                and isinstance(confidence, (int, float))
                and math.isfinite(float(confidence))
                and 0 <= float(confidence) <= 1
            )
            confidence_value = float(confidence) if confidence_valid else 0.0
            if not confidence_valid:
                reasons.append("invalid_confidence")
            severity = str(finding.get("severity", ""))
            if severity not in SEVERITY_ORDER:
                reasons.append("invalid_severity")

            if reasons:
                finding["confidence"] = min(confidence_value, 0.59)
                finding["evidence_ids"] = attached_ids
                finding["adjudication"] = {
                    "outcome": "manual_check",
                    "reasons": sorted(set(reasons)),
                    "required_capabilities": required_capabilities,
                    "severity_preserved_as_proposed_impact": severity or "unknown",
                }
                manual.append(finding)
                continue
            finding["evidence_ids"] = attached_ids
            finding["adjudication"] = {
                "outcome": "accepted",
                "anchor_status": "verified",
                "required_capabilities": required_capabilities,
                "semantic_controls": controls_status,
            }
            if controls_status == "contested":
                contested = True
                finding["status"] = "contested"
            formal.append(finding)

    if stale_input:
        review_status = "stale"
    elif incomplete_required:
        review_status = "incomplete"
    else:
        review_status = "complete"

    formal.sort(key=_finding_sort_key)
    manual.sort(key=_finding_sort_key)
    draft_planned_items.sort(
        key=lambda item: (
            _source_key(item.get("location", {}).get("source", "")),
            item.get("location", {}).get("page", 0),
            item.get("location", {}).get("paragraph", 0),
            item.get("location", {}).get("line", 0),
            str(item.get("id", "")),
        )
    )
    has_revision_finding = any(
        item.get("severity") in {"Blocker", "Major", "Minor"}
        for item in formal
    )
    deep_argument_unresolved = (
        coverage.get("mode") == "deep"
        and isinstance(manuscript_map_validation, Mapping)
        and manuscript_map_validation.get("argument_status") != "closed"
    )
    semantic_assessment_unresolved = bool(
        isinstance(claim_logic_semantic_review, Mapping)
        and claim_logic_semantic_review.get("has_unresolved_assessment")
    )
    if review_status != "complete" or contested or manual:
        readiness = "manual_confirmation_required"
    elif has_revision_finding:
        readiness = "revision_required"
    elif coverage.get("mode") == "draft":
        readiness = "draft_in_progress"
    elif deep_argument_unresolved or semantic_assessment_unresolved:
        readiness = "manual_confirmation_required"
    else:
        readiness = "ready_given_evidence"

    external_evidence = sorted(
        external_evidence_by_id.values(),
        key=lambda item: (str(item.get("source_id", "")), str(item.get("evidence_id", ""))),
    )
    final_ledger = copy.deepcopy(ledger)
    final_ledger["generated_at"] = utc_now()
    final_ledger["base_ledger_fingerprint"] = ledger["ledger_fingerprint"]
    final_sources = list(final_ledger.get("sources", []))
    final_sources.extend(
        {
            "source_id": item["source_id"],
            "source": item["source"],
            "format": item["format"],
            "sha256": item["sha256"],
            "role": item["role"],
        }
        for item in manifest.get("artifacts", [])
        if item.get("role") in {"cited_source", "standard_source"}
    )
    final_ledger["sources"] = sorted(
        {str(item.get("source_id")): item for item in final_sources}.values(),
        key=lambda item: (str(item.get("role", "")), str(item.get("source", "")).casefold()),
    )
    final_ledger["evidence"] = list(ledger.get("evidence", [])) + external_evidence
    final_ledger["summary"] = {
        **dict(ledger.get("summary", {})),
        "evidence_count": len(final_ledger["evidence"]),
        "external_evidence_count": len(external_evidence),
    }
    final_ledger.pop("ledger_fingerprint", None)
    final_ledger["ledger_fingerprint"] = ledger_fingerprint(final_ledger)

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "paper_id": manifest["paper_id"],
        "input_fingerprint": manifest["input_fingerprint"],
        "ledger_fingerprint": ledger["ledger_fingerprint"],
        "final_ledger_fingerprint": final_ledger["ledger_fingerprint"],
        "coverage_fingerprint": coverage["coverage_fingerprint"],
        "mode": coverage["mode"],
        "review_status": review_status,
        "submission_readiness": readiness,
        "summary": {
            "formal_finding_count": len(formal),
            "manual_check_count": len(manual),
            "external_evidence_count": len(external_evidence),
            "question_for_author_count": len(questions_for_author),
            "draft_planned_item_count": len(draft_planned_items),
            "next_writing_task_count": len(next_writing_tasks),
            "manuscript_map_status": (
                manuscript_map_validation.get("status")
                if isinstance(manuscript_map_validation, Mapping)
                else None
            ),
            "manuscript_argument_status": (
                manuscript_map_validation.get("argument_status")
                if isinstance(manuscript_map_validation, Mapping)
                else None
            ),
            "manuscript_contract_gap_count": len(
                manuscript_map_validation.get("contract_gaps", [])
            ) if isinstance(manuscript_map_validation, Mapping) else 0,
            "claim_logic_unresolved_assessment": semantic_assessment_unresolved,
            "by_severity": dict(
                sorted(Counter(item.get("severity", "Info") for item in formal).items())
            ),
        },
        "coverage": coverage,
        "findings": formal,
        "manual_checks": manual,
        "manuscript_map_validation": manuscript_map_validation,
        "claim_logic_semantic_review": claim_logic_semantic_review,
        "draft_planned_items": draft_planned_items,
        "questions_for_author": questions_for_author,
        "next_writing_tasks": next_writing_tasks,
        "diagnostics": sorted(set(diagnostics)),
    }
    stable_report = {
        key: result[key]
        for key in (
            "paper_id",
            "input_fingerprint",
            "ledger_fingerprint",
            "final_ledger_fingerprint",
            "coverage_fingerprint",
            "mode",
            "review_status",
            "submission_readiness",
            "findings",
            "manual_checks",
            "diagnostics",
            "draft_planned_items",
            "manuscript_map_validation",
            "claim_logic_semantic_review",
            "questions_for_author",
            "next_writing_tasks",
        )
    }
    result["report_fingerprint"] = sha256_bytes(canonical_json(stable_report))

    output = Path(output_dir).resolve(strict=False)
    json_path = output / "findings.json"
    report_path = output / "review-report.md"
    final_ledger_path = output / "final-evidence-ledger.json"
    protected_paths: list[str | Path] = [manifest_path, ledger_path, coverage_path]
    protected_paths.append(str(manifest.get("root_input", "")))
    protected_paths.extend(
        str(item.get("path", ""))
        for item in manifest.get("artifacts", [])
        if isinstance(item, Mapping) and str(item.get("path", "")).strip()
    )
    protected_paths.extend(
        str(result_record.get("path", ""))
        for pass_record in coverage.get("passes", [])
        if isinstance(pass_record, Mapping)
        for result_record in [pass_record.get("result")]
        if isinstance(result_record, Mapping) and str(result_record.get("path", "")).strip()
    )
    _assert_safe_write_targets(
        [json_path, report_path, final_ledger_path], protected_paths
    )
    if not force:
        for path in (json_path, report_path, final_ledger_path):
            if path.exists():
                raise EvidenceSpineError(f"拒绝覆盖已有输出：{path}；确认后使用 --force。")
    atomic_write(
        final_ledger_path,
        json.dumps(final_ledger, ensure_ascii=False, indent=2) + "\n",
        force=force,
    )
    atomic_write(
        json_path,
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        force=force,
    )
    atomic_write(report_path, render_report(result), force=force)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="建立统一论文证据台账、覆盖记录并确定性裁决各审核 pass。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="生成 manifest、ledger 与 coverage 模板")
    prepare.add_argument("manuscript")
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--mode", choices=sorted(VALID_MODES), default="deep")
    prepare.add_argument("--required-pass", action="append", default=[])
    prepare.add_argument("--rendered-artifact", action="append", default=[])
    prepare.add_argument("--artifact", action="append", default=[], metavar="ROLE=PATH")
    prepare.add_argument("--text-mode", choices=("excerpt", "hash-only"), default="excerpt")
    prepare.add_argument("--standards-source-map")
    prepare.add_argument("--standards-registry")
    prepare.add_argument("--force", action="store_true")

    record = subparsers.add_parser("record-pass", help="把一个审核 pass 绑定到当前 ledger")
    record.add_argument("coverage")
    record.add_argument("ledger")
    record.add_argument("--output", required=True)
    record.add_argument("--pass-id", choices=sorted(PASS_SPEC_BY_ID), required=True)
    record.add_argument(
        "--status",
        choices=sorted(VALID_PASS_STATUSES - {"not_run"}),
        required=True,
    )
    record.add_argument("--result")
    record.add_argument("--rationale", default="")
    record.add_argument("--reviewer", default="")
    record.add_argument("--attest-ledger-read", action="store_true")
    record.add_argument("--capability", action="append", default=[])
    record.add_argument("--force", action="store_true")

    finalize = subparsers.add_parser("finalize", help="验证锚点、证据边界和覆盖状态并生成最终报告")
    finalize.add_argument("manifest")
    finalize.add_argument("ledger")
    finalize.add_argument("coverage")
    finalize.add_argument("--output-dir", required=True)
    finalize.add_argument("--force", action="store_true")
    return parser


def _parse_additional_artifacts(values: Sequence[str]) -> list[tuple[str, Path]]:
    parsed: list[tuple[str, Path]] = []
    for value in values:
        if "=" not in value:
            raise EvidenceSpineError("--artifact 必须使用 ROLE=PATH")
        role, path_text = (part.strip() for part in value.split("=", 1))
        if role not in ADDITIONAL_ARTIFACT_ROLES:
            raise EvidenceSpineError(f"未知附加 artifact role：{role}")
        if not path_text:
            raise EvidenceSpineError("--artifact 的路径不能为空")
        parsed.append((role, Path(path_text)))
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_evidence_spine(
                args.manuscript,
                args.output_dir,
                mode=args.mode,
                required_passes=args.required_pass,
                rendered_artifacts=args.rendered_artifact,
                additional_artifacts=_parse_additional_artifacts(args.artifact),
                text_mode=args.text_mode,
                standards_source_map=args.standards_source_map,
                standards_registry=args.standards_registry,
                force=args.force,
            )
            print(result["paths"]["manifest"])
            print(result["paths"]["ledger"])
            print(result["paths"]["coverage"])
            return 0
        if args.command == "record-pass":
            updated = record_pass(
                args.coverage,
                args.ledger,
                args.output,
                pass_id=args.pass_id,
                status=args.status,
                result_path=args.result,
                rationale=args.rationale,
                reviewer=args.reviewer,
                attest_ledger_read=args.attest_ledger_read,
                capability_updates=_parse_capability_updates(args.capability),
                force=args.force,
            )
            print(Path(args.output).resolve())
            print(updated["coverage_fingerprint"])
            return 0
        result = adjudicate_report(
            args.manifest,
            args.ledger,
            args.coverage,
            args.output_dir,
            force=args.force,
        )
        print(Path(args.output_dir).resolve() / "review-report.md")
        print(result["review_status"])
        return 0
    except (EvidenceSpineError, OSError, ValueError) as exc:
        print(f"evidence-spine: {exc}", file=sys.stderr)
        return 2


def _trusted_capabilities(
    coverage: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, str]:
    claimed = dict(coverage.get("evidence_capabilities", {}))
    artifacts = [item for item in manifest.get("artifacts", []) if isinstance(item, Mapping)]
    roles = {str(item.get("role", "")) for item in artifacts}
    manuscript_formats = {
        str(item.get("format", "")).casefold()
        for item in artifacts
        if item.get("role") == "manuscript_source"
    }
    if not (manuscript_formats & {"tex", "docx", "md", "txt"}):
        claimed["editable_source"] = "missing"
    if not artifacts or not manuscript_formats:
        claimed["manuscript_text"] = "missing"
    if "rendered_manuscript" not in roles and "pdf" not in manuscript_formats:
        claimed["rendered_pages"] = "missing"
    if "cited_source" not in roles:
        claimed["cited_full_text"] = "missing"
    authorized_standard = any(
        item.get("role") == "standard_source"
        and isinstance(item.get("authorization"), Mapping)
        and item.get("authorization", {}).get("gate_status") == "allowed"
        for item in artifacts
    )
    if not authorized_standard:
        claimed["standard_text"] = "missing"
    if "table_data" not in roles:
        claimed["figure_table_data"] = "missing"
    return {
        name: status if status in CAPABILITY_STATUSES else "missing"
        for name, status in claimed.items()
        if name in CAPABILITIES
    }


if __name__ == "__main__":
    raise SystemExit(main())
