#!/usr/bin/env python3
"""Prepare and validate evidence-led citation claim-support assessments.

The deterministic ``prepare`` stage extracts cited claims, maps references to
user-provided local full text (or explicitly authorised open-access URLs), and
ranks short evidence candidates.  It does not decide whether a source supports
a claim.  A human or reviewing agent records that decision separately, and the
``finalize`` stage validates every decision before producing the final JSON and
Markdown report.

The manuscript and local source documents are read-only.  Network downloads are
disabled unless ``--allow-open-access-download`` is supplied explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import audit_manuscript as audit
import verify_references as references


PREPARE_SCHEMA_VERSION = "0.1.0"
FINAL_SCHEMA_VERSION = "0.1.0"
DEFAULT_TOP_K = 5
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30
SUPPORTED_SOURCE_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}
VERDICTS = {
    "supports",
    "partially_supports",
    "does_not_support",
    "unable_to_verify",
}
DIMENSION_VALUES = {
    "match",
    "partial",
    "mismatch",
    "contradiction",
    "unclear",
    "not_applicable",
}
SEVERITIES = {"Blocker", "Major", "Minor", "Info"}

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "just", "may", "me", "might", "more", "most", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs",
    "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "will", "with", "would", "you", "your", "et", "al", "fig", "figure",
    "table", "eq", "equation", "study", "paper", "research",
}

PRIORITY_PATTERNS = {
    "quantity": re.compile(
        r"(?<!\w)[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*(?:%|mm|cm|m|kN|N|MPa|GPa|Pa|Hz|rad)(?!\w)",
        re.I,
    ),
    "causal": re.compile(
        r"\b(?:cause[sd]?|caused by|lead(?:s|ing)? to|result(?:s|ed)? in|due to|"
        r"responsible for|govern(?:s|ed)?|determin(?:e|es|ed))\b",
        re.I,
    ),
    "comparison": re.compile(
        r"\b(?:increase[sd]?|decrease[sd]?|reduce[sd]?|improve[sd]?|higher|lower|"
        r"greater|smaller|outperform(?:s|ed)?|significant(?:ly)?|superior|inferior)\b",
        re.I,
    ),
    "scope": re.compile(
        r"\b(?:all|always|never|generally|widely|universally|eliminate[sd]?|ensure[sd]?)\b",
        re.I,
    ),
    "novelty": re.compile(
        r"\b(?:first|novel|newly|few studies|little attention|has not been|remain(?:s)? unknown)\b",
        re.I,
    ),
    "authority": re.compile(
        r"\b(?:according to|defined as|required?|recommend(?:s|ed)?|shall|must|standard|code)\b",
        re.I,
    ),
}

CITE_RE = re.compile(
    r"\\(?P<command>[A-Za-z]*cite[A-Za-z]*)\*?"
    r"(?:\s*\[[^\]]*\]){0,2}\s*\{(?P<keys>[^{}]+)\}"
)
NUMERIC_CITATION_RE = re.compile(
    r"\[(?P<body>\s*\d+(?:\s*[-–—]\s*\d+)?"
    r"(?:\s*[,;]\s*\d+(?:\s*[-–—]\s*\d+)?)*\s*)\]"
)
NARRATIVE_AUTHOR_YEAR_RE = re.compile(
    r"\b(?P<surname>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+)"
    r"(?:\s+et\s+al\.)?\s*\((?P<year>(?:18|19|20)\d{2})[a-z]?\)"
)
PAREN_AUTHOR_YEAR_RE = re.compile(r"\((?P<body>[^()]{1,240}\b(?:18|19|20)\d{2}[a-z]?[^()]*)\)")
QUANTITY_RE = re.compile(
    r"(?<![\w.])(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>%|GPa|MPa|kPa|Pa|kN|N|mm|cm|m|Hz|rad)(?!\w)",
    re.I,
)


class ClaimSupportError(RuntimeError):
    """Fatal input, validation, extraction, or output error."""


@dataclass(frozen=True)
class SourceMapEntry:
    citation_key: str = ""
    doi: str = ""
    path: Path | None = None
    url: str = ""
    access: str = "user-provided"


@dataclass
class SourceDocument:
    path: Path
    origin: str
    access: str
    url: str
    sha256: str
    detected_doi: str
    extraction_quality: str
    extracted_characters: int
    passages: list[dict[str, Any]]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _safe_quote(value: str, limit: int = 900) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _atomic_write_text(path: Path, text: str, *, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        if force:
            os.replace(temporary_name, path)
        else:
            try:
                os.link(temporary_name, path)
            except FileExistsError as exc:
                raise ClaimSupportError(f"输出文件已存在，未覆盖：{path}") from exc
            os.unlink(temporary_name)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            os.unlink(temporary_name)
            return
        os.unlink(temporary_name)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _check_output_targets(
    targets: Iterable[Path], protected: Iterable[Path], *, force: bool
) -> None:
    protected_resolved = {path.resolve(strict=False) for path in protected}
    existing: list[Path] = []
    for target in targets:
        resolved = target.resolve(strict=False)
        if resolved in protected_resolved:
            raise ClaimSupportError(f"输出路径与输入源冲突：{target}")
        if target.is_symlink():
            raise ClaimSupportError(f"拒绝写出到符号链接：{target}")
        if target.exists():
            existing.append(target)
    if existing and not force:
        raise ClaimSupportError(
            "输出文件已存在，未覆盖：" + "；".join(str(path) for path in existing)
        )


def _clean_latex_prose(value: str) -> str:
    value = re.sub(r"(?m)(?<!\\)%.*$", " ", value)
    value = value.replace(r"\%", "%").replace(r"\&", "&").replace(r"\_", "_").replace(r"\#", "#")
    value = re.sub(r"\\(?:begin|end)\{[^{}]+\}", " ", value)
    value = re.sub(r"\\(?:section|subsection|subsubsection|paragraph)\*?\{([^{}]*)\}", r"\1. ", value)
    for _ in range(3):
        updated = re.sub(
            r"\\(?:textit|textbf|emph|mathrm|textrm|textnormal|mbox)\{([^{}]*)\}",
            r"\1",
            value,
        )
        if updated == value:
            break
        value = updated
    value = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", value)
    value = value.replace("~", " ").replace("{", "").replace("}", "")
    value = value.replace("$", "")
    return re.sub(r"\s+", " ", value).strip()


def _sentence_list(value: str) -> list[str]:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return []
    return [
        piece.strip()
        for piece in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", value)
        if piece.strip()
    ]


def _context_for_span(text: str, start: int, end: int, format_name: str) -> tuple[str, str, str]:
    left = max(text.rfind("\n\n", 0, start), text.rfind("\r\n\r\n", 0, start))
    left = 0 if left < 0 else left + 2
    right_candidates = [position for position in (text.find("\n\n", end), text.find("\r\n\r\n", end)) if position >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    if right - left > 4000:
        left = max(left, start - 1800)
        right = min(right, end + 1800)
    paragraph = text[left:start] + " ⟦CITATION⟧ " + text[end:right]
    raw_quote = text[max(left, start - 250) : min(right, end + 250)]
    cleaned = _clean_latex_prose(paragraph) if format_name == "tex" else re.sub(r"\s+", " ", paragraph).strip()
    sentences = _sentence_list(cleaned)
    marker_index = next((index for index, sentence in enumerate(sentences) if "⟦CITATION⟧" in sentence), 0)
    sentence = sentences[marker_index] if sentences else cleaned
    if ";" in sentence:
        clauses = [clause.strip() for clause in sentence.split(";") if clause.strip()]
        sentence = next((clause for clause in clauses if "⟦CITATION⟧" in clause), sentence)
    claim = re.sub(r"\s*⟦CITATION⟧\s*", " ", sentence).strip(" ,;:")
    context_start = max(0, marker_index - 1)
    context_end = min(len(sentences), marker_index + 2)
    context = " ".join(sentences[context_start:context_end]) if sentences else cleaned
    return _safe_quote(claim, 700), _safe_quote(context, 1500), _safe_quote(raw_quote, 600)


def _priority_reasons(claim: str) -> list[str]:
    return [name for name, pattern in PRIORITY_PATTERNS.items() if pattern.search(claim)]


def _stable_claim_id(location: Mapping[str, Any], keys: Sequence[str], claim: str) -> str:
    material = "\0".join(
        [
            str(location.get("source", "")).casefold(),
            str(location.get("line", "")),
            str(location.get("paragraph", "")),
            str(location.get("page", "")),
            ",".join(key.casefold() for key in keys),
            references.normalize_text(claim),
        ]
    )
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=5).hexdigest().upper()
    return f"CLM-{digest}"


def _parse_numeric_body(body: str) -> list[int]:
    numbers: list[int] = []
    for piece in re.split(r"\s*[,;]\s*", body.strip()):
        range_match = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", piece)
        if range_match:
            first, last = int(range_match.group(1)), int(range_match.group(2))
            if 0 <= last - first <= 50:
                numbers.extend(range(first, last + 1))
        elif piece.isdigit():
            numbers.append(int(piece))
    return numbers


def _surname_from_metadata(author: str) -> str:
    return references.surname(author)


def _author_year_lookup(reference_entries: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[str]]:
    lookup: dict[tuple[str, str], list[str]] = {}
    for item in reference_entries:
        metadata = item.get("metadata", {})
        authors = metadata.get("authors", [])
        year = str(metadata.get("year", ""))
        key = str(metadata.get("key", ""))
        if not key or not year or not authors:
            continue
        surname = _surname_from_metadata(str(authors[0]))
        if surname:
            lookup.setdefault((surname, year), []).append(key)
    return lookup


def _extract_plain_author_year_keys(
    text: str, lookup: Mapping[tuple[str, str], list[str]]
) -> list[tuple[re.Match[str], list[str], float, str]]:
    found: list[tuple[re.Match[str], list[str], float, str]] = []
    for match in NARRATIVE_AUTHOR_YEAR_RE.finditer(text):
        candidates = lookup.get((references.normalize_text(match.group("surname")).replace(" ", ""), match.group("year")), [])
        if len(candidates) == 1:
            found.append((match, list(candidates), 0.90, "author-year-unique"))
    for match in PAREN_AUTHOR_YEAR_RE.finditer(text):
        keys: list[str] = []
        ambiguous = False
        for segment in re.split(r"\s*;\s*", match.group("body")):
            year_match = re.search(r"\b((?:18|19|20)\d{2})[a-z]?\b", segment)
            surname_match = re.search(r"\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+)(?:\s+et\s+al\.)?", segment)
            if not year_match or not surname_match:
                continue
            lookup_key = (
                references.normalize_text(surname_match.group(1)).replace(" ", ""),
                year_match.group(1),
            )
            candidates = lookup.get(lookup_key, [])
            if len(candidates) == 1:
                keys.extend(candidates)
            elif candidates:
                ambiguous = True
        if keys and not ambiguous:
            found.append((match, list(dict.fromkeys(keys)), 0.85, "author-year-unique"))
    return found


def extract_citation_occurrences(
    units: Sequence[audit.SourceUnit], reference_entries: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    lookup = _author_year_lookup(reference_entries)
    ordered_keys = [str(item.get("metadata", {}).get("key", "")) for item in reference_entries]
    for unit in units:
        if unit.format == "tex":
            for match in CITE_RE.finditer(unit.structure):
                if match.group("command").casefold() == "nocite":
                    continue
                keys = [key.strip() for key in match.group("keys").split(",") if key.strip() and key.strip() != "*"]
                if not keys:
                    continue
                block = unit.block_at_offset(match.start())
                if block.is_reference_section:
                    continue
                claim, context, raw_quote = _context_for_span(
                    unit.raw, match.start(), match.end(), unit.format
                )
                location = block.location()
                occurrences.append(
                    {
                        "id": _stable_claim_id(location, keys, claim),
                        "claim": claim,
                        "context": context,
                        "raw_quote": raw_quote,
                        "location": location,
                        "citation": {
                            "token": unit.raw[match.start() : match.end()],
                            "keys": keys,
                            "mapping_method": "latex-key",
                            "mapping_confidence": 0.99,
                        },
                        "priority_reasons": _priority_reasons(claim),
                    }
                )
            continue

        for block in unit.blocks:
            if block.is_reference_section or not block.raw.strip():
                continue
            claimed_spans: list[tuple[int, int]] = []
            for match in NUMERIC_CITATION_RE.finditer(block.raw):
                keys = [ordered_keys[index - 1] for index in _parse_numeric_body(match.group("body")) if 0 < index <= len(ordered_keys) and ordered_keys[index - 1]]
                if not keys:
                    continue
                claim, context, raw_quote = _context_for_span(
                    block.raw, match.start(), match.end(), unit.format
                )
                location = block.location()
                occurrences.append(
                    {
                        "id": _stable_claim_id(location, keys, claim),
                        "claim": claim,
                        "context": context,
                        "raw_quote": raw_quote,
                        "location": location,
                        "citation": {
                            "token": match.group(0),
                            "keys": keys,
                            "mapping_method": "numeric-reference-order",
                            "mapping_confidence": 0.92,
                        },
                        "priority_reasons": _priority_reasons(claim),
                    }
                )
                claimed_spans.append(match.span())
            for match, keys, confidence, method in _extract_plain_author_year_keys(block.raw, lookup):
                if any(match.start() < stop and start < match.end() for start, stop in claimed_spans):
                    continue
                claim, context, raw_quote = _context_for_span(
                    block.raw, match.start(), match.end(), unit.format
                )
                location = block.location()
                occurrences.append(
                    {
                        "id": _stable_claim_id(location, keys, claim),
                        "claim": claim,
                        "context": context,
                        "raw_quote": raw_quote,
                        "location": location,
                        "citation": {
                            "token": match.group(0),
                            "keys": keys,
                            "mapping_method": method,
                            "mapping_confidence": confidence,
                        },
                        "priority_reasons": _priority_reasons(claim),
                    }
                )
    unique: dict[str, dict[str, Any]] = {}
    for item in occurrences:
        unique.setdefault(item["id"], item)
    return list(unique.values())


def _reference_entry_from_metadata(metadata: Mapping[str, Any], status: str = "not_checked") -> dict[str, Any]:
    return {
        "metadata": {
            "key": str(metadata.get("key", "")),
            "doi": references.normalize_doi(str(metadata.get("doi", ""))),
            "title": str(metadata.get("title", "")),
            "authors": [str(value) for value in metadata.get("authors", [])],
            "year": str(metadata.get("year", "")),
            "container": str(metadata.get("container", "")),
            "location": dict(metadata.get("location", {})),
        },
        "metadata_status": status,
    }


def load_reference_entries(
    manuscript: Path, references_json: Path | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[Path]]:
    diagnostics: list[dict[str, Any]] = []
    protected: set[Path] = set()
    if references_json is not None:
        resolved = references_json.resolve(strict=True)
        protected.add(resolved)
        try:
            data = json.loads(resolved.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ClaimSupportError(f"无法读取 references.json：{resolved}: {exc}") from exc
        entries = []
        for item in data.get("entries", []):
            metadata = item.get("input_metadata", {})
            entries.append(_reference_entry_from_metadata(metadata, str(item.get("status", "not_checked"))))
        return entries, list(data.get("extraction_diagnostics", [])), protected

    try:
        extracted, extraction_diagnostics = references.extract_entries_with_diagnostics(manuscript)
    except (OSError, ValueError) as exc:
        raise ClaimSupportError(f"无法提取参考文献：{exc}") from exc
    diagnostics.extend(extraction_diagnostics)
    entries = [_reference_entry_from_metadata(references.entry_to_dict(entry)) for entry in extracted]
    return entries, diagnostics, protected


def load_source_map(path: Path | None) -> tuple[list[SourceMapEntry], set[Path]]:
    if path is None:
        return [], set()
    resolved = path.resolve(strict=True)
    try:
        data = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimSupportError(f"无法读取 source-map：{resolved}: {exc}") from exc
    if not isinstance(data, Mapping) or not isinstance(data.get("sources", []), list):
        raise ClaimSupportError("source-map 根节点必须包含 sources 数组。")
    entries: list[SourceMapEntry] = []
    for index, raw in enumerate(data.get("sources", []), 1):
        if not isinstance(raw, Mapping):
            raise ClaimSupportError(f"source-map 第 {index} 项必须是对象。")
        citation_key = str(raw.get("citation_key", "")).strip()
        doi = references.normalize_doi(str(raw.get("doi", "")))
        raw_path = str(raw.get("path", "")).strip()
        url = str(raw.get("url", "")).strip()
        if not citation_key and not doi:
            raise ClaimSupportError(f"source-map 第 {index} 项必须提供 citation_key 或 DOI。")
        if bool(raw_path) == bool(url):
            raise ClaimSupportError(f"source-map 第 {index} 项必须且只能提供 path 或 url。")
        local_path = None
        if raw_path:
            candidate = Path(raw_path)
            local_path = candidate if candidate.is_absolute() else resolved.parent / candidate
            local_path = local_path.resolve(strict=False)
            if local_path.suffix.casefold() not in SUPPORTED_SOURCE_SUFFIXES:
                raise ClaimSupportError(f"source-map 第 {index} 项格式不支持：{local_path.suffix}")
        if url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ClaimSupportError(f"source-map 第 {index} 项 URL 必须是 http/https。")
        entries.append(
            SourceMapEntry(
                citation_key=citation_key,
                doi=doi,
                path=local_path,
                url=url,
                access=str(raw.get("access", "user-provided") or "user-provided"),
            )
        )
    return entries, {resolved}


def _download_open_source(url: str, cache_dir: Path) -> Path:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "paper-auditor/0.1 (explicit open-access download)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            parsed = urllib.parse.urlparse(final_url)
            if parsed.scheme not in {"http", "https"}:
                raise ClaimSupportError("开放全文下载重定向到非 HTTP(S) 地址，已拒绝。")
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].lower()
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ClaimSupportError(f"开放全文下载失败：{exc}") from exc
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ClaimSupportError(f"开放全文超过 {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MiB 限制。")
    suffix = Path(urllib.parse.urlparse(final_url).path).suffix.casefold()
    if data.startswith(b"%PDF"):
        suffix = ".pdf"
    elif data.startswith(b"PK") and "wordprocessingml" in content_type:
        suffix = ".docx"
    elif content_type in {"text/plain", "text/markdown", "text/x-markdown"}:
        suffix = ".md" if "markdown" in content_type else ".txt"
    if suffix not in SUPPORTED_SOURCE_SUFFIXES:
        raise ClaimSupportError(
            f"开放全文响应不是受支持的 PDF/TXT/MD/DOCX：{content_type or suffix or 'unknown'}"
        )
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    target = cache_dir / f"oa-{digest}{suffix}"
    if not target.exists():
        _atomic_write_bytes(target, data)
    return target.resolve(strict=True)


def _iter_text_passages(text: str, *, page: int | None = None) -> Iterable[dict[str, Any]]:
    line_cursor = 1
    paragraph_number = 0
    groups = re.split(r"\n\s*\n+", text)
    if len(groups) == 1:
        groups = [line for line in text.splitlines() if line.strip()]
    for group in groups:
        paragraph_number += 1
        start_line = line_cursor
        line_cursor += group.count("\n") + 1
        compact = re.sub(r"\s+", " ", group).strip()
        if len(compact) < 35:
            continue
        sentences = _sentence_list(compact)
        if not sentences:
            continue
        windows: list[str] = []
        current: list[str] = []
        for sentence in sentences:
            if current and len(" ".join(current + [sentence])) > 1200:
                windows.append(" ".join(current))
                current = current[-1:]
            current.append(sentence)
        if current:
            windows.append(" ".join(current))
        for window_index, window in enumerate(windows, 1):
            location: dict[str, Any] = {
                "paragraph": paragraph_number,
                "line": start_line,
            }
            if page is not None:
                location["page"] = page
            yield {
                "text": _safe_quote(window, 1200),
                "location": location,
                "window": window_index,
            }


def extract_source_document(path: Path, *, origin: str, access: str, url: str = "") -> SourceDocument:
    resolved = path.resolve(strict=True)
    suffix = resolved.suffix.casefold()
    if suffix == ".pdf":
        raw = references.read_pdf_text(resolved)
        passages = [
            passage
            for page_number, page in enumerate(raw.split("\f"), 1)
            for passage in _iter_text_passages(page, page=page_number)
        ]
    elif suffix == ".docx":
        raw = references.read_docx_text(resolved)
        passages = list(_iter_text_passages(raw))
    elif suffix in {".txt", ".md"}:
        raw = references.read_text(resolved)
        passages = list(_iter_text_passages(raw))
    else:
        raise ClaimSupportError(f"不支持的全文格式：{suffix}")
    compact_characters = len(re.sub(r"\s+", "", raw))
    replacement_ratio = raw.count("�") / max(1, len(raw))
    if compact_characters >= 2000 and replacement_ratio < 0.005:
        quality = "good"
    elif compact_characters >= 300 and replacement_ratio < 0.02:
        quality = "limited"
    else:
        quality = "poor"
    return SourceDocument(
        path=resolved,
        origin=origin,
        access=access,
        url=url,
        sha256=sha256_file(resolved),
        detected_doi=references.first_doi(raw[:100000]),
        extraction_quality=quality,
        extracted_characters=compact_characters,
        passages=passages,
    )


def _tokenize(value: str) -> list[str]:
    normalized = references.normalize_text(value)
    return [
        token
        for token in normalized.split()
        if len(token) > 1 and token not in STOPWORDS and not re.fullmatch(r"(?:18|19|20)\d{2}", token)
    ]


def _extract_quantities(value: str) -> list[tuple[float, str, str]]:
    conversions = {
        "m": ("length", 1.0), "cm": ("length", 0.01), "mm": ("length", 0.001),
        "n": ("force", 1.0), "kn": ("force", 1000.0),
        "pa": ("stress", 1.0), "kpa": ("stress", 1000.0),
        "mpa": ("stress", 1_000_000.0), "gpa": ("stress", 1_000_000_000.0),
        "%": ("percent", 1.0), "hz": ("frequency", 1.0), "rad": ("angle", 1.0),
    }
    found: list[tuple[float, str, str]] = []
    for match in QUANTITY_RE.finditer(value):
        unit = match.group("unit").casefold()
        dimension, multiplier = conversions[unit]
        found.append((float(match.group("value")) * multiplier, dimension, match.group(0)))
    return found


def _quantity_match(claim: str, passage: str) -> tuple[float, list[str]]:
    claim_quantities = _extract_quantities(claim)
    if not claim_quantities:
        return 0.0, []
    passage_quantities = _extract_quantities(passage)
    matched: list[str] = []
    for claim_value, claim_dimension, raw in claim_quantities:
        for passage_value, passage_dimension, _ in passage_quantities:
            tolerance = max(abs(claim_value), 1.0) * 1e-6
            if claim_dimension == passage_dimension and abs(claim_value - passage_value) <= tolerance:
                matched.append(raw)
                break
    return len(matched) / len(claim_quantities), matched


def rank_evidence(claim: str, passages: Sequence[Mapping[str, Any]], top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query_tokens = _tokenize(claim)
    query_counts = Counter(query_tokens)
    passage_tokens = [_tokenize(str(passage.get("text", ""))) for passage in passages]
    document_frequency: Counter[str] = Counter()
    for tokens in passage_tokens:
        document_frequency.update(set(tokens))
    lengths = [len(tokens) for tokens in passage_tokens]
    average_length = sum(lengths) / max(1, len(lengths))
    raw_scores: list[float] = []
    coverages: list[float] = []
    quantity_scores: list[tuple[float, list[str]]] = []
    total = max(1, len(passages))
    for tokens, passage in zip(passage_tokens, passages):
        counts = Counter(tokens)
        bm25 = 0.0
        for token, query_frequency in query_counts.items():
            frequency = counts.get(token, 0)
            if not frequency:
                continue
            doc_frequency = document_frequency.get(token, 0)
            idf = math.log(1.0 + (total - doc_frequency + 0.5) / (doc_frequency + 0.5))
            denominator = frequency + 1.5 * (1.0 - 0.75 + 0.75 * len(tokens) / max(1.0, average_length))
            bm25 += idf * frequency * 2.5 / denominator * query_frequency
        raw_scores.append(bm25)
        query_set = set(query_tokens)
        coverages.append(len(query_set & set(tokens)) / max(1, len(query_set)))
        quantity_scores.append(_quantity_match(claim, str(passage.get("text", ""))))
    maximum_bm25 = max(raw_scores, default=0.0)
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, passage in enumerate(passages):
        bm25_normalized = raw_scores[index] / maximum_bm25 if maximum_bm25 else 0.0
        quantity_score, quantity_matches = quantity_scores[index]
        score = 0.65 * bm25_normalized + 0.20 * coverages[index] + 0.15 * quantity_score
        reasons: list[str] = []
        if bm25_normalized >= 0.50:
            reasons.append("bm25-related")
        if coverages[index] >= 0.45:
            reasons.append("technical-term-overlap")
        if quantity_matches:
            reasons.append("same-quantity-or-unit-conversion")
        candidate = {
            "quote": _safe_quote(str(passage.get("text", "")), 900),
            "location": dict(passage.get("location", {})),
            "retrieval_score": round(score, 4),
            "score_components": {
                "bm25": round(bm25_normalized, 4),
                "term_coverage": round(coverages[index], 4),
                "quantity_match": round(quantity_score, 4),
            },
            "match_reasons": reasons,
        }
        ranked.append((score, index, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()
    for _, _, candidate in ranked:
        normalized_quote = references.normalize_text(candidate["quote"])
        if not normalized_quote or normalized_quote in seen_quotes:
            continue
        seen_quotes.add(normalized_quote)
        candidate["rank"] = len(selected) + 1
        selected.append(candidate)
        if len(selected) >= top_k:
            break
    return selected, {
        "algorithm": "local-bm25-term-quantity-v1",
        "passage_count": len(passages),
        "query_terms": sorted(set(query_tokens)),
        "candidate_count": len(selected),
        "top_score": selected[0]["retrieval_score"] if selected else 0.0,
        "absence_is_not_non_support": True,
    }


def _source_doc_to_access(document: SourceDocument) -> dict[str, Any]:
    return {
        "status": "fulltext",
        "type": document.access,
        "path": str(document.path),
        "origin": document.origin,
        "url": document.url,
        "sha256": document.sha256,
        "detected_doi": document.detected_doi,
        "extraction_quality": document.extraction_quality,
        "extracted_characters": document.extracted_characters,
    }


def _automatic_match_score(metadata: Mapping[str, Any], document: SourceDocument) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    doi = references.normalize_doi(str(metadata.get("doi", "")))
    if doi and document.detected_doi:
        if doi == document.detected_doi:
            return 1.0, ["doi-exact"]
        return -1.0, ["doi-conflict"]
    key = _normalized_identifier(str(metadata.get("key", "")))
    stem = _normalized_identifier(document.path.stem)
    if key and key in stem:
        score = max(score, 0.96)
        reasons.append("citation-key-in-filename")
    title_tokens = set(_tokenize(str(metadata.get("title", ""))))
    sample_tokens = set(
        _tokenize(" ".join(passage["text"] for passage in document.passages[:8]))
    )
    if title_tokens:
        coverage = len(title_tokens & sample_tokens) / len(title_tokens)
        if coverage >= 0.65:
            score = max(score, 0.78 + 0.20 * coverage)
            reasons.append(f"title-token-coverage:{coverage:.2f}")
    authors = metadata.get("authors", [])
    year = str(metadata.get("year", ""))
    if authors and year:
        surname = _normalized_identifier(_surname_from_metadata(str(authors[0])))
        if surname and surname in stem and year in stem:
            score = max(score, 0.88)
            reasons.append("first-author-year-in-filename")
    return round(score, 4), reasons


def _find_map_entry(
    metadata: Mapping[str, Any], source_map: Sequence[SourceMapEntry]
) -> SourceMapEntry | None:
    key = str(metadata.get("key", "")).casefold()
    doi = references.normalize_doi(str(metadata.get("doi", "")))
    key_matches = [entry for entry in source_map if entry.citation_key.casefold() == key and key]
    if len(key_matches) > 1:
        raise ClaimSupportError(f"source-map 对引用键 {metadata.get('key')} 定义了多个来源。")
    if key_matches:
        return key_matches[0]
    doi_matches = [entry for entry in source_map if entry.doi and entry.doi == doi]
    if len(doi_matches) > 1:
        raise ClaimSupportError(f"source-map 对 DOI {doi} 定义了多个来源。")
    return doi_matches[0] if doi_matches else None


def _map_reference_source(
    metadata: Mapping[str, Any],
    source_map: Sequence[SourceMapEntry],
    documents: Mapping[Path, SourceDocument],
    *,
    allow_download: bool,
    cache_dir: Path,
    document_cache: dict[Path, SourceDocument],
    diagnostics: list[dict[str, Any]],
) -> tuple[dict[str, Any], SourceDocument | None]:
    mapped = _find_map_entry(metadata, source_map)
    if mapped:
        if mapped.url and not allow_download:
            return {
                "status": "unavailable",
                "method": "explicit-open-access-url",
                "reason": "open_access_download_not_authorized",
                "url": mapped.url,
            }, None
        source_path = mapped.path
        if mapped.url:
            try:
                source_path = _download_open_source(mapped.url, cache_dir)
            except ClaimSupportError as exc:
                return {
                    "status": "unavailable",
                    "method": "explicit-open-access-url",
                    "reason": "open_access_download_failed",
                    "url": mapped.url,
                    "detail": str(exc),
                }, None
        assert source_path is not None
        if not source_path.is_file():
            return {
                "status": "unavailable",
                "method": "explicit-source-map",
                "reason": "mapped_file_not_found",
                "path": str(source_path),
            }, None
        try:
            document = document_cache.get(source_path.resolve())
            if document is None:
                document = extract_source_document(
                    source_path,
                    origin="source-map",
                    access=mapped.access,
                    url=mapped.url,
                )
                document_cache[source_path.resolve()] = document
        except (OSError, ValueError, ClaimSupportError) as exc:
            return {
                "status": "unavailable",
                "method": "explicit-source-map",
                "reason": "fulltext_extraction_failed",
                "path": str(source_path),
                "detail": str(exc),
            }, None
        expected_doi = references.normalize_doi(str(metadata.get("doi", "")))
        if expected_doi and document.detected_doi and expected_doi != document.detected_doi:
            return {
                "status": "conflict",
                "method": "explicit-source-map",
                "reason": "source_doi_conflict",
                "expected_doi": expected_doi,
                "detected_doi": document.detected_doi,
                "path": str(source_path),
            }, None
        return {
            "status": "matched",
            "method": "explicit-source-map",
            "score": 1.0,
            "reasons": ["explicit-user-mapping"],
        }, document

    ranked: list[tuple[float, Path, SourceDocument, list[str]]] = []
    for path, document in documents.items():
        score, reasons = _automatic_match_score(metadata, document)
        if score >= 0:
            ranked.append((score, path, document, reasons))
        elif "doi-conflict" in reasons:
            diagnostics.append(
                {
                    "level": "info",
                    "code": "candidate-doi-conflict",
                    "citation_key": metadata.get("key", ""),
                    "source": str(path),
                    "message": "候选全文 DOI 与参考文献 DOI 不同，未自动绑定。",
                }
            )
    ranked.sort(key=lambda item: (-item[0], str(item[1]).casefold()))
    if not ranked or ranked[0][0] < 0.85:
        return {
            "status": "unavailable",
            "method": "automatic-local-match",
            "reason": "no_confident_local_source_match",
            "best_score": ranked[0][0] if ranked else 0.0,
        }, None
    best = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if best[0] - runner_up < 0.08:
        return {
            "status": "ambiguous",
            "method": "automatic-local-match",
            "reason": "candidate_separation_insufficient",
            "candidates": [
                {"path": str(path), "score": score, "reasons": reasons}
                for score, path, _, reasons in ranked[:3]
            ],
        }, None
    return {
        "status": "matched",
        "method": "automatic-local-match",
        "score": best[0],
        "runner_up_score": runner_up,
        "reasons": best[3],
    }, best[2]


def _parse_line_range(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+):(\d+)", value.strip())
    if not match or int(match.group(1)) > int(match.group(2)):
        raise ClaimSupportError("--line-range 必须是起始行:结束行，例如 80:130。")
    return int(match.group(1)), int(match.group(2))


def _filter_occurrences(
    occurrences: Sequence[dict[str, Any]],
    *,
    scope: str,
    sections: Sequence[str],
    citation_keys: Sequence[str],
    line_range: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    section_filters = [value.casefold() for value in sections]
    key_filters = {value.casefold() for value in citation_keys}
    selected: list[dict[str, Any]] = []
    for occurrence in occurrences:
        if scope == "priority" and not occurrence.get("priority_reasons"):
            continue
        section = str(occurrence.get("location", {}).get("section", "")).casefold()
        if section_filters and not any(value in section for value in section_filters):
            continue
        keys = {str(key).casefold() for key in occurrence.get("citation", {}).get("keys", [])}
        if key_filters and not keys.intersection(key_filters):
            continue
        if line_range:
            line = int(occurrence.get("location", {}).get("line", 0) or 0)
            if not line_range[0] <= line <= line_range[1]:
                continue
        selected.append(occurrence)
    return selected


def prepare_claim_evidence(
    manuscript: str | Path,
    output_dir: str | Path,
    *,
    references_json: str | Path | None = None,
    sources_dir: str | Path | None = None,
    source_map: str | Path | None = None,
    scope: str = "priority",
    sections: Sequence[str] = (),
    citation_keys: Sequence[str] = (),
    line_range: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    allow_open_access_download: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    manuscript_path = Path(manuscript).resolve(strict=True)
    review_dir = Path(output_dir).resolve(strict=False)
    json_path = review_dir / "claim-evidence.json"
    report_path = review_dir / "claim-evidence.md"
    references_path = Path(references_json) if references_json else None
    source_map_path = Path(source_map) if source_map else None
    source_directory = Path(sources_dir).resolve(strict=True) if sources_dir else None
    if source_directory and not source_directory.is_dir():
        raise ClaimSupportError(f"--sources-dir 不是目录：{source_directory}")
    protected = {manuscript_path}
    if references_path:
        protected.add(references_path.resolve(strict=True))
    if source_map_path:
        protected.add(source_map_path.resolve(strict=True))
    _check_output_targets((json_path, report_path), protected, force=force)

    diagnostics: list[dict[str, Any]] = []
    try:
        units = audit._load_sources(manuscript_path, diagnostics)
    except (audit.AuditError, OSError) as exc:
        raise ClaimSupportError(f"无法读取稿件：{exc}") from exc
    reference_entries, reference_diagnostics, reference_protected = load_reference_entries(
        manuscript_path, references_path
    )
    diagnostics.extend(reference_diagnostics)
    protected.update(reference_protected)
    map_entries, map_protected = load_source_map(source_map_path)
    protected.update(map_protected)

    occurrences = extract_citation_occurrences(units, reference_entries)
    occurrences = _filter_occurrences(
        occurrences,
        scope=scope,
        sections=sections,
        citation_keys=citation_keys,
        line_range=_parse_line_range(line_range),
    )
    metadata_by_key = {
        str(item.get("metadata", {}).get("key", "")): item for item in reference_entries
    }

    local_paths: set[Path] = set()
    if source_directory:
        local_paths.update(
            path.resolve()
            for path in source_directory.rglob("*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
        )
    local_paths.update(
        entry.path.resolve()
        for entry in map_entries
        if entry.path is not None and entry.path.is_file()
    )
    documents: dict[Path, SourceDocument] = {}
    for path in sorted(local_paths, key=lambda value: str(value).casefold()):
        try:
            documents[path] = extract_source_document(
                path, origin="sources-dir", access="user-provided"
            )
            protected.add(path)
        except (OSError, ValueError, ClaimSupportError) as exc:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "fulltext-extraction-failed",
                    "source": str(path),
                    "message": str(exc),
                }
            )

    document_cache = dict(documents)
    cache_dir = review_dir / "fulltext-cache"
    prepared_claims: list[dict[str, Any]] = []
    for occurrence in occurrences:
        reference_results: list[dict[str, Any]] = []
        for key in occurrence["citation"]["keys"]:
            reference_item = metadata_by_key.get(key)
            if reference_item is None:
                reference_results.append(
                    {
                        "citation_key": key,
                        "metadata_status": "missing_from_reference_inventory",
                        "metadata": {},
                        "source_match": {
                            "status": "unavailable",
                            "reason": "citation_key_not_in_reference_inventory",
                        },
                        "source_access": {"status": "unavailable"},
                        "evidence_candidates": [],
                        "retrieval": {
                            "algorithm": "not_run",
                            "candidate_count": 0,
                            "absence_is_not_non_support": True,
                        },
                        "assessment_status": "pending",
                    }
                )
                continue
            metadata = reference_item["metadata"]
            source_match, document = _map_reference_source(
                metadata,
                map_entries,
                documents,
                allow_download=allow_open_access_download,
                cache_dir=cache_dir,
                document_cache=document_cache,
                diagnostics=diagnostics,
            )
            if document is not None:
                protected.add(document.path)
                candidates, retrieval = rank_evidence(
                    occurrence["claim"], document.passages, max(1, min(top_k, 20))
                )
                source_access = _source_doc_to_access(document)
            else:
                candidates = []
                retrieval = {
                    "algorithm": "not_run",
                    "passage_count": 0,
                    "candidate_count": 0,
                    "top_score": 0.0,
                    "absence_is_not_non_support": True,
                    "reason": source_match.get("reason", source_match.get("status", "unavailable")),
                }
                source_access = {
                    "status": "unavailable",
                    "reason": source_match.get("reason", source_match.get("status", "unavailable")),
                }
            reference_results.append(
                {
                    "citation_key": key,
                    "doi": metadata.get("doi", ""),
                    "title": metadata.get("title", ""),
                    "metadata_status": reference_item.get("metadata_status", "not_checked"),
                    "metadata": metadata,
                    "source_match": source_match,
                    "source_access": source_access,
                    "evidence_candidates": candidates,
                    "retrieval": retrieval,
                    "assessment_status": "pending",
                }
            )
        prepared_claims.append({**occurrence, "references": reference_results})

    data = {
        "schema_version": PREPARE_SCHEMA_VERSION,
        "stage": "prepared",
        "generated_at": utc_now(),
        "input": {
            "path": str(manuscript_path),
            "sha256": sha256_file(manuscript_path),
            "reference_count": len(reference_entries),
            "citation_occurrence_count": len(occurrences),
        },
        "selection": {
            "scope": scope,
            "sections": list(sections),
            "citation_keys": list(citation_keys),
            "line_range": line_range or "",
            "top_k": max(1, min(top_k, 20)),
        },
        "privacy": {
            "manuscript_text_uploaded": False,
            "claim_text_uploaded": False,
            "automatic_fulltext_download": False,
            "explicit_open_access_download_authorized": bool(allow_open_access_download),
        },
        "claims": prepared_claims,
        "diagnostics": diagnostics,
        "limitations": [
            "证据候选只是本地检索结果，不是支持性结论。",
            "检索未命中不能证明来源不支持主张；应判为无法核验或继续阅读全文。",
            "PDF 文本提取可能丢失公式、表格结构和阅读顺序。",
            "每个引用来源必须单独判定；不得用引用簇的平均结果代替逐篇核验。",
        ],
    }
    _check_output_targets((json_path, report_path), protected, force=force)
    _atomic_write_text(
        json_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", force=force
    )
    _atomic_write_text(report_path, render_evidence_report(data), force=force)
    return data


def _format_location(location: Mapping[str, Any]) -> str:
    parts = [str(location.get("source", ""))]
    if location.get("page"):
        parts.append(f"第 {location['page']} 页")
    elif location.get("paragraph"):
        parts.append(f"第 {location['paragraph']} 段")
    elif location.get("line"):
        parts.append(f"第 {location['line']} 行")
    if location.get("section"):
        parts.append(str(location["section"]))
    return " · ".join(part for part in parts if part)


def render_evidence_report(data: Mapping[str, Any]) -> str:
    lines = [
        "# 引文主张证据候选",
        "",
        f"- 生成时间：`{data.get('generated_at', '')}`",
        f"- 稿件：`{data.get('input', {}).get('path', '')}`",
        f"- 待核验主张：{len(data.get('claims', []))}",
        "",
        "> 本文件只展示透明可复核的候选证据，不代表来源已经支持或不支持主张。检索未命中不得判为“不支持”。",
        "",
    ]
    if not data.get("claims"):
        lines.extend(["未提取到满足当前筛选条件的引用主张。", ""])
    for claim in data.get("claims", []):
        lines.extend(
            [
                f"## {claim.get('id', '')}",
                "",
                f"- 主张：{claim.get('claim', '')}",
                f"- 稿件位置：{_format_location(claim.get('location', {}))}",
                f"- 引用：`{', '.join(claim.get('citation', {}).get('keys', []))}`",
                f"- 优先原因：`{', '.join(claim.get('priority_reasons', [])) or '常规引用'}`",
                "",
            ]
        )
        for source in claim.get("references", []):
            lines.extend(
                [
                    f"### {source.get('citation_key', '')}",
                    "",
                    f"- 题名：{source.get('title', '') or '未提取'}",
                    f"- 来源匹配：`{source.get('source_match', {}).get('status', '')}` / "
                    f"`{source.get('source_match', {}).get('method', '')}`",
                    f"- 全文状态：`{source.get('source_access', {}).get('status', '')}`",
                    f"- 提取质量：`{source.get('source_access', {}).get('extraction_quality', '不可用')}`",
                    "",
                ]
            )
            candidates = source.get("evidence_candidates", [])
            if not candidates:
                lines.extend(["无候选证据；必须记为无法核验或人工阅读全文。", ""])
            for candidate in candidates:
                lines.extend(
                    [
                        f"- 候选 {candidate.get('rank')} · score={candidate.get('retrieval_score')}",
                        f"  - 位置：{_format_location(candidate.get('location', {}))}",
                        f"  - 原文：{candidate.get('quote', '')}",
                        f"  - 命中原因：`{', '.join(candidate.get('match_reasons', [])) or '弱文本相关'}`",
                    ]
                )
            lines.append("")
    return "\n".join(lines)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimSupportError(f"无法读取 {label}：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClaimSupportError(f"{label} 根节点必须是 JSON 对象。")
    return value


def _decision_key(value: Mapping[str, Any]) -> tuple[str, str]:
    return str(value.get("claim_id", "")), str(value.get("citation_key", ""))


def validate_decisions(
    evidence: Mapping[str, Any], decisions: Mapping[str, Any]
) -> dict[tuple[str, str], dict[str, Any]]:
    if evidence.get("schema_version") != PREPARE_SCHEMA_VERSION or evidence.get("stage") != "prepared":
        raise ClaimSupportError("claim-evidence.json 不是兼容的 prepared 数据。")
    raw_decisions = decisions.get("decisions")
    if not isinstance(raw_decisions, list):
        raise ClaimSupportError("claim-decisions.json 必须包含 decisions 数组。")
    expected: dict[tuple[str, str], Mapping[str, Any]] = {}
    for claim in evidence.get("claims", []):
        for source in claim.get("references", []):
            expected[(str(claim.get("id", "")), str(source.get("citation_key", "")))] = source
    validated: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(raw_decisions, 1):
        if not isinstance(raw, Mapping):
            raise ClaimSupportError(f"第 {index} 个 decision 必须是对象。")
        pair = _decision_key(raw)
        if not all(pair):
            raise ClaimSupportError(f"第 {index} 个 decision 缺少 claim_id 或 citation_key。")
        if pair not in expected:
            raise ClaimSupportError(f"decision 指向不存在的主张/文献：{pair[0]} / {pair[1]}")
        if pair in validated:
            raise ClaimSupportError(f"decision 重复：{pair[0]} / {pair[1]}")
        verdict = str(raw.get("verdict", ""))
        if verdict not in VERDICTS:
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的 verdict 无效：{verdict}")
        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的 confidence 必须在 0 到 1 之间。")
        rationale = str(raw.get("rationale", "")).strip()
        if len(rationale) < 8:
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 必须给出可复核的 rationale。")
        ranks = raw.get("evidence_ranks", [])
        if not isinstance(ranks, list) or any(not isinstance(rank, int) or isinstance(rank, bool) for rank in ranks):
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的 evidence_ranks 必须是整数数组。")
        available_ranks = {
            int(item.get("rank")) for item in expected[pair].get("evidence_candidates", [])
        }
        if any(rank not in available_ranks for rank in ranks):
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 引用了不存在的证据候选。")
        dimensions = raw.get("dimension_matches", {})
        if not isinstance(dimensions, Mapping) or any(
            str(value) not in DIMENSION_VALUES for value in dimensions.values()
        ):
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的 dimension_matches 含无效值。")
        source_access = expected[pair].get("source_access", {})
        if verdict != "unable_to_verify":
            minimum = 0.70 if verdict == "partially_supports" else 0.80
            if float(confidence) < minimum:
                raise ClaimSupportError(
                    f"{pair[0]} / {pair[1]} 低于 {minimum:.2f}；应改为 unable_to_verify。"
                )
            if source_access.get("status") != "fulltext" or source_access.get("extraction_quality") == "poor":
                raise ClaimSupportError(f"{pair[0]} / {pair[1]} 没有足够全文证据，只能 unable_to_verify。")
            if not ranks:
                raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的结论必须选择至少一个证据候选。")
        values = {str(value) for value in dimensions.values()}
        if verdict == "supports":
            if not dimensions or values - {"match", "not_applicable"}:
                raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的 supports 与维度判断不一致。")
        elif verdict == "partially_supports":
            if not values.intersection({"partial", "mismatch", "unclear"}):
                raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的部分支持必须说明受限维度。")
        elif verdict == "does_not_support":
            if not values.intersection({"mismatch", "contradiction"}):
                raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的不支持必须说明冲突维度。")
        severity = str(raw.get("severity", "")).strip()
        if severity and severity not in SEVERITIES:
            raise ClaimSupportError(f"{pair[0]} / {pair[1]} 的 severity 无效。")
        validated[pair] = {
            **dict(raw),
            "confidence": round(float(confidence), 2),
            "rationale": rationale,
            "evidence_ranks": list(dict.fromkeys(ranks)),
            "dimension_matches": dict(dimensions),
        }
    missing = sorted(set(expected) - set(validated))
    if missing:
        sample = "；".join(f"{claim}/{key}" for claim, key in missing[:5])
        raise ClaimSupportError(f"缺少 {len(missing)} 条决策：{sample}")
    return validated


def _overall_verdict(verdicts: Sequence[str]) -> str:
    if not verdicts:
        return "unable_to_verify"
    if "does_not_support" in verdicts:
        return "does_not_support"
    if "partially_supports" in verdicts:
        return "partially_supports"
    if all(verdict == "supports" for verdict in verdicts):
        return "supports"
    return "unable_to_verify"


def _finding_id(claim_id: str, citation_key: str, verdict: str) -> str:
    material = f"{claim_id}\0{citation_key.casefold()}\0{verdict}"
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=5).hexdigest().upper()
    return f"CITE-{digest}"


def finalize_claim_support(
    evidence_path: str | Path,
    decisions_path: str | Path,
    output_dir: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    evidence_file = Path(evidence_path).resolve(strict=True)
    decisions_file = Path(decisions_path).resolve(strict=True)
    review_dir = Path(output_dir).resolve(strict=False)
    json_path = review_dir / "claim-support.json"
    report_path = review_dir / "claim-support-report.md"
    _check_output_targets(
        (json_path, report_path), (evidence_file, decisions_file), force=force
    )
    evidence = _load_json_object(evidence_file, "claim-evidence.json")
    decisions = _load_json_object(decisions_file, "claim-decisions.json")
    validated = validate_decisions(evidence, decisions)

    finalized_claims: list[dict[str, Any]] = []
    formal_findings: list[dict[str, Any]] = []
    pair_counts: Counter[str] = Counter()
    overall_counts: Counter[str] = Counter()
    for claim in evidence.get("claims", []):
        finalized_sources: list[dict[str, Any]] = []
        source_verdicts: list[str] = []
        for source in claim.get("references", []):
            pair = (str(claim.get("id", "")), str(source.get("citation_key", "")))
            decision = validated[pair]
            candidate_by_rank = {
                int(candidate["rank"]): candidate
                for candidate in source.get("evidence_candidates", [])
            }
            selected_evidence = [candidate_by_rank[rank] for rank in decision["evidence_ranks"]]
            verdict = str(decision["verdict"])
            pair_counts[verdict] += 1
            source_verdicts.append(verdict)
            finalized = {
                **source,
                "assessment_status": "assessed",
                "verdict": verdict,
                "confidence": decision["confidence"],
                "rationale": decision["rationale"],
                "dimension_matches": decision["dimension_matches"],
                "selected_evidence": selected_evidence,
                "suggested_revision": str(decision.get("suggested_revision", "")),
                "severity": str(decision.get("severity", "")),
                "reviewer": str(decision.get("reviewer", "human-or-agent")),
            }
            finalized_sources.append(finalized)
            if verdict == "does_not_support" or (
                verdict == "partially_supports" and decision["confidence"] >= 0.80
            ):
                severity = finalized["severity"] or (
                    "Major" if verdict == "does_not_support" else "Minor"
                )
                formal_findings.append(
                    {
                        "id": _finding_id(pair[0], pair[1], verdict),
                        "category": "citation-support",
                        "check_id": "citation-does-not-support-claim"
                        if verdict == "does_not_support"
                        else "citation-partially-supports-claim",
                        "severity": severity,
                        "confidence": decision["confidence"],
                        "status": "confirmed" if decision["confidence"] >= 0.90 else "likely",
                        "location": claim.get("location", {}),
                        "quote": claim.get("claim", ""),
                        "verdict": verdict,
                        "citation_key": pair[1],
                        "dimension_matches": decision["dimension_matches"],
                        "observation": decision["rationale"],
                        "evidence": selected_evidence,
                        "evidence_source": {
                            "citation_key": pair[1],
                            "sha256": source.get("source_access", {}).get("sha256", ""),
                            "basename": Path(
                                str(source.get("source_access", {}).get("path", ""))
                            ).name,
                            "detected_doi": source.get("source_access", {}).get(
                                "detected_doi", ""
                            ),
                        },
                        "suggested_fix": str(decision.get("suggested_revision", "")),
                        "auto_fixable": False,
                    }
                )
        overall = _overall_verdict(source_verdicts)
        overall_counts[overall] += 1
        finalized_claims.append(
            {**claim, "references": finalized_sources, "overall_verdict": overall}
        )

    data = {
        "schema_version": FINAL_SCHEMA_VERSION,
        "stage": "finalized",
        "generated_at": utc_now(),
        "input": evidence.get("input", {}),
        "evidence_packet": {
            "path": str(evidence_file),
            "sha256": sha256_file(evidence_file),
        },
        "decision_file": {
            "path": str(decisions_file),
            "sha256": sha256_file(decisions_file),
        },
        "summary": {
            "claim_count": len(finalized_claims),
            "reference_assessment_count": sum(pair_counts.values()),
            "by_reference_verdict": {verdict: pair_counts.get(verdict, 0) for verdict in sorted(VERDICTS)},
            "by_claim_verdict": {verdict: overall_counts.get(verdict, 0) for verdict in sorted(VERDICTS)},
            "formal_finding_count": len(formal_findings),
        },
        "claims": finalized_claims,
        "formal_findings": formal_findings,
        "decision_boundaries": {
            "supports": "全文直接证据与主张的实质维度一致。",
            "partially_supports": "至少一个核心命题有证据，但范围、条件、强度或并列命题不完整。",
            "does_not_support": "全文证据显示直接矛盾或明确对象/条件/结果错位；检索未命中本身不算。",
            "unable_to_verify": "全文、映射、提取或证据不足，无法达到其他结论的门槛。",
        },
    }
    _atomic_write_text(
        json_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", force=force
    )
    _atomic_write_text(report_path, render_final_report(data), force=force)
    return data


def render_final_report(data: Mapping[str, Any]) -> str:
    summary = data.get("summary", {})
    labels = {
        "supports": "支持",
        "partially_supports": "部分支持",
        "does_not_support": "不支持",
        "unable_to_verify": "无法核验",
    }
    lines = [
        "# 引文主张支持性核验报告",
        "",
        f"- 生成时间：`{data.get('generated_at', '')}`",
        f"- 主张数：{summary.get('claim_count', 0)}",
        f"- 文献逐项判断数：{summary.get('reference_assessment_count', 0)}",
        f"- 正式发现：{summary.get('formal_finding_count', 0)}",
        "",
        "## 结果汇总",
        "",
    ]
    for verdict in ("does_not_support", "partially_supports", "unable_to_verify", "supports"):
        lines.append(
            f"- {labels[verdict]}：{summary.get('by_reference_verdict', {}).get(verdict, 0)}"
        )
    lines.extend(["", "## 主张与证据", ""])
    for claim in data.get("claims", []):
        overall = str(claim.get("overall_verdict", "unable_to_verify"))
        lines.extend(
            [
                f"### {claim.get('id', '')} · {labels.get(overall, overall)}",
                "",
                f"- 主张：{claim.get('claim', '')}",
                f"- 稿件位置：{_format_location(claim.get('location', {}))}",
                "",
            ]
        )
        for source in claim.get("references", []):
            verdict = str(source.get("verdict", "unable_to_verify"))
            lines.extend(
                [
                    f"#### `{source.get('citation_key', '')}` · {labels.get(verdict, verdict)} · "
                    f"confidence={source.get('confidence', 0):.2f}",
                    "",
                    f"- 题名：{source.get('title', '') or '未提取'}",
                    f"- 理由：{source.get('rationale', '')}",
                    f"- 维度：`{json.dumps(source.get('dimension_matches', {}), ensure_ascii=False)}`",
                ]
            )
            if source.get("suggested_revision"):
                lines.append(f"- 建议改写：{source.get('suggested_revision')}")
            if source.get("selected_evidence"):
                lines.append("- 采用证据：")
                for evidence in source["selected_evidence"]:
                    lines.extend(
                        [
                            f"  - {_format_location(evidence.get('location', {}))} · score={evidence.get('retrieval_score')}",
                            f"    - {evidence.get('quote', '')}",
                        ]
                    )
            else:
                lines.append("- 采用证据：无；当前结论为无法核验。")
            lines.append("")
    lines.extend(
        [
            "## 判定边界",
            "",
            "- “不支持”必须有直接矛盾或明确错位证据；检索未命中不能作为依据。",
            "- 只有摘要、全文不可读、引用映射不唯一或判断置信度不足时，应写为“无法核验”。",
            "- 多篇文献逐篇判断；本报告不以平均分掩盖单篇误引。",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="准备并验证论文主张—引用—来源原文的支持性证据链。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="提取引用主张并生成本地证据候选")
    prepare.add_argument("manuscript", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--references-json", type=Path)
    prepare.add_argument("--sources-dir", type=Path)
    prepare.add_argument("--source-map", type=Path)
    prepare.add_argument("--scope", choices=("priority", "all"), default="priority")
    prepare.add_argument("--section", action="append", default=[])
    prepare.add_argument("--citation-key", action="append", default=[])
    prepare.add_argument("--line-range", help="起始行:结束行，例如 80:130")
    prepare.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    prepare.add_argument("--allow-open-access-download", action="store_true")
    prepare.add_argument("--force", action="store_true")

    finalize = subparsers.add_parser("finalize", help="验证人工/代理决策并生成最终报告")
    finalize.add_argument("evidence", type=Path, help="prepare 生成的 claim-evidence.json")
    finalize.add_argument("decisions", type=Path, help="人工/代理填写的 claim-decisions.json")
    finalize.add_argument("--output-dir", type=Path, required=True)
    finalize.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            data = prepare_claim_evidence(
                args.manuscript,
                args.output_dir,
                references_json=args.references_json,
                sources_dir=args.sources_dir,
                source_map=args.source_map,
                scope=args.scope,
                sections=args.section,
                citation_keys=args.citation_key,
                line_range=args.line_range,
                top_k=max(1, min(args.top_k, 20)),
                allow_open_access_download=args.allow_open_access_download,
                force=args.force,
            )
            print(f"已准备 {len(data['claims'])} 条引用主张。")
            print(Path(args.output_dir).resolve() / "claim-evidence.json")
            print("下一步：逐条填写 claim-decisions.json，再运行 finalize。")
        else:
            data = finalize_claim_support(
                args.evidence, args.decisions, args.output_dir, force=args.force
            )
            print(f"已核验 {data['summary']['reference_assessment_count']} 个主张—文献对。")
            print(Path(args.output_dir).resolve() / "claim-support-report.md")
    except (ClaimSupportError, OSError, ValueError) as exc:
        print(f"claim-support: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
