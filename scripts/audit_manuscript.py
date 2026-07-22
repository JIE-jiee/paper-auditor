#!/usr/bin/env python3
"""Deterministic, read-only manuscript checks for the paper-auditor skill.

The script intentionally limits itself to findings that can be anchored in the
source.  Parser limitations and extraction uncertainty are emitted separately
as diagnostics, never as manuscript defects.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree


SCHEMA_VERSION = "0.1.0"
PDFTEXT_TIMEOUT_SECONDS = 60
SEVERITY_ORDER = {"Blocker": 0, "Major": 1, "Minor": 2, "Info": 3}
PREFIXES = {
    "abbreviation": "ABBR",
    "terminology": "TERM",
    "spelling": "LANG",
    "unit": "UNIT",
    "cross-reference": "XREF",
    "latex": "TEX",
    "bibliography": "BIB",
}

SECTION_NAMES = {
    "abstract": "Abstract",
    "keywords": "Keywords",
    "introduction": "Introduction",
    "background": "Background",
    "methods": "Methods",
    "methodology": "Methodology",
    "materials and methods": "Materials and Methods",
    "results": "Results",
    "discussion": "Discussion",
    "results and discussion": "Results and Discussion",
    "conclusions": "Conclusions",
    "conclusion": "Conclusion",
    "acknowledgments": "Acknowledgments",
    "acknowledgements": "Acknowledgements",
    "data availability": "Data Availability",
    "reference": "References",
    "references": "References",
    "bibliography": "Bibliography",
    "literature cited": "Literature Cited",
    "works cited": "Works Cited",
}

REFERENCE_SECTIONS = {
    "reference",
    "references",
    "bibliography",
    "literature cited",
    "works cited",
}

ABBREVIATION_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+)*)(?![A-Za-z0-9])"
)
ALL_CAPS_STOPWORDS = {
    "ABSTRACT",
    "INTRODUCTION",
    "BACKGROUND",
    "METHODS",
    "METHODOLOGY",
    "RESULTS",
    "DISCUSSION",
    "CONCLUSIONS",
    "CONCLUSION",
    "REFERENCES",
    "ACKNOWLEDGMENTS",
    "ACKNOWLEDGEMENTS",
    "APPENDIX",
    "TABLE",
    "FIGURE",
}
INITIAL_STOPWORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}

UK_TO_US = {
    "behaviour": "behavior",
    "behaviours": "behaviors",
    "behavioural": "behavioral",
    "modelling": "modeling",
    "modelled": "modeled",
    "centre": "center",
    "centres": "centers",
    "fibre": "fiber",
    "fibres": "fibers",
    "colour": "color",
    "colours": "colors",
    "analyse": "analyze",
    "analysed": "analyzed",
    "analysing": "analyzing",
    "optimisation": "optimization",
    "normalisation": "normalization",
}

CANONICAL_UNITS = {
    "gpa": "GPa",
    "mpa": "MPa",
    "kpa": "kPa",
    "pa": "Pa",
    "kn": "kN",
    "mn": "MN",
    "n": "N",
    "hz": "Hz",
    "mm": "mm",
    "cm": "cm",
    "km": "km",
    "kg": "kg",
    "ms": "ms",
    "rad": "rad",
    "°c": "°C",
    "m": "m",
    "s": "s",
    "g": "g",
}
CASE_SAFE_UNITS = {"gpa", "mpa", "kpa", "kn", "mn", "hz", "°c"}
UNIT_RE = re.compile(
    r"(?<![\w.])(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?P<space>\s*)(?P<unit>GPa|MPa|kPa|Pa|kN|MN|Hz|mm|cm|km|kg|ms|rad|°C|N|m|s|g)"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)

CAPTION_RE = re.compile(
    r"^\s*(?P<label>Figs?\.?|Figures?|Tables?|Eqs?\.?|Equations?)\s*"
    r"\(?(?P<identifier>[A-Z]?\d+(?:\.\d+)*[A-Za-z]?)\)?\s*"
    r"(?P<separator>[.:]|[-–—])\s+",
    re.IGNORECASE,
)
CALLOUT_RE = re.compile(
    r"\b(?P<label>Figs?\.?|Figures?|Tables?|Eqs?\.?|Equations?)\s*"
    r"\(?(?P<identifier>[A-Z]?\d+(?:\.\d+)*[A-Za-z]?)\)?",
    re.IGNORECASE,
)


class AuditError(RuntimeError):
    """Fatal input or configuration problem."""


@dataclass
class SourceUnit:
    path: Path
    source: str
    format: str
    raw: str
    structure: str
    masked: str
    heading_lines: dict[int, str] = field(default_factory=dict)
    page_by_line: dict[int, int] = field(default_factory=dict)
    paragraph_by_line: dict[int, int] = field(default_factory=dict)
    blocks: list["Block"] = field(default_factory=list)
    line_starts: list[int] = field(default_factory=list)

    def prepare_offsets(self) -> None:
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer(r"\n", self.raw))

    def block_at_offset(self, offset: int) -> "Block":
        if not self.blocks:
            return Block(self, 1, "", "", "Front matter", "body")
        line = bisect.bisect_right(self.line_starts, max(0, offset))
        line = min(max(line, 1), len(self.blocks))
        return self.blocks[line - 1]


@dataclass(frozen=True)
class Block:
    unit: SourceUnit
    line: int
    raw: str
    scan: str
    section: str
    scope: str

    @property
    def is_reference_section(self) -> bool:
        normalized = re.sub(r"\s+", " ", self.section).strip().casefold().rstrip(":")
        return normalized in REFERENCE_SECTIONS or normalized.startswith("references ")

    def location(self) -> dict[str, Any]:
        location: dict[str, Any] = {
            "source": self.unit.source,
            "line": self.line,
            "section": self.section,
            "scope": self.scope,
        }
        if self.line in self.unit.page_by_line:
            location["page"] = self.unit.page_by_line[self.line]
        if self.line in self.unit.paragraph_by_line:
            location["paragraph"] = self.unit.paragraph_by_line[self.line]
        return location


def _diagnostic(
    diagnostics: list[dict[str, Any]],
    level: str,
    code: str,
    source: str,
    message: str,
) -> None:
    diagnostics.append({"level": level, "code": code, "source": source, "message": message})


def _read_text(path: Path, diagnostics: list[dict[str, Any]], source: str) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = data.decode(encoding)
            if encoding == "cp1252":
                _diagnostic(
                    diagnostics,
                    "warning",
                    "encoding-fallback",
                    source,
                    "文件不是 UTF-8；已使用 cp1252 解码，字符判断需复核。",
                )
            return text
        except UnicodeDecodeError:
            continue
    _diagnostic(
        diagnostics,
        "warning",
        "encoding-replacement",
        source,
        "无法可靠识别编码；已替换不可解码字符，相关位置需复核。",
    )
    return data.decode("utf-8", errors="replace")


def _mask_ranges(text: str, ranges: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in ranges:
        for index in range(max(0, start), min(len(chars), end)):
            if chars[index] not in "\r\n":
                chars[index] = " "
    return "".join(chars)


def _latex_exclusion_ranges(text: str) -> list[tuple[int, int]]:
    """Locate comments and literal code while preserving source coordinates."""

    ranges: list[tuple[int, int]] = []
    line_start = 0
    for line in text.splitlines(keepends=True):
        for offset, char in enumerate(line):
            if char != "%":
                continue
            slash_count = 0
            cursor = offset - 1
            while cursor >= 0 and line[cursor] == "\\":
                slash_count += 1
                cursor -= 1
            if slash_count % 2 == 0:
                ranges.append((line_start + offset, line_start + len(line)))
                break
        line_start += len(line)

    without_comments = _mask_ranges(text, ranges)
    verb_re = re.compile(r"\\verb\*?(?P<delimiter>[^\sA-Za-z])")
    for match in verb_re.finditer(without_comments):
        delimiter = match.group("delimiter")
        line_end = without_comments.find("\n", match.end())
        if line_end == -1:
            line_end = len(without_comments)
        close = without_comments.find(delimiter, match.end(), line_end)
        ranges.append((match.start(), close + 1 if close != -1 else line_end))

    without_comments_or_verb = _mask_ranges(text, ranges)
    begin_re = re.compile(r"\\begin\{(?P<environment>verbatim\*?|lstlisting|minted)\}")
    cursor = 0
    while True:
        begin = begin_re.search(without_comments_or_verb, cursor)
        if not begin:
            break
        environment = begin.group("environment")
        end_re = re.compile(rf"\\end\{{{re.escape(environment)}\}}")
        end = end_re.search(without_comments_or_verb, begin.end())
        stop = end.end() if end else len(text)
        ranges.append((begin.start(), stop))
        cursor = max(stop, begin.end())
    return ranges


def _tex_structure_view(text: str) -> str:
    """Mask non-structural LaTeX, retaining real include/ref/cite/label commands."""

    return _mask_ranges(text, _latex_exclusion_ranges(text))


def _mask_tex(text: str, structure: str | None = None) -> str:
    structure = structure if structure is not None else _tex_structure_view(text)
    ranges: list[tuple[int, int]] = []
    for pattern in (
        re.compile(r"(?<!\\)\$(?!\$).*?(?<!\\)\$"),
        re.compile(r"\\\(.*?\\\)", re.DOTALL),
        re.compile(r"\\\[.*?\\\]", re.DOTALL),
        re.compile(
            r"\\begin\{(?P<mathenv>equation\*?|align\*?|displaymath)\}"
            r".*?\\end\{(?P=mathenv)\}",
            re.DOTALL,
        ),
        re.compile(
            r"\\(?:label|(?:[A-Za-z]*cite[A-Za-z]*|cite)|(?:auto|page|name|eq|c|C)?ref|url|path|includegraphics)"
            r"\*?(?:\s*\[[^\]]*\]){0,2}\s*\{[^{}]*\}"
        ),
    ):
        ranges.extend(match.span() for match in pattern.finditer(structure))

    masked = _mask_ranges(structure, ranges)
    masked = re.sub(r"\\[A-Za-z@]+\*?", lambda m: " " * len(m.group(0)), masked)
    masked = masked.translate(str.maketrans({"{": " ", "}": " ", "~": " "}))
    return masked


def _markdown_prose_view(text: str) -> str:
    """Mask fenced/inline code and HTML comments without moving any position."""

    ranges: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = text.find("<!--", cursor)
        if start == -1:
            break
        close = text.find("-->", start + 4)
        stop = close + 3 if close != -1 else len(text)
        ranges.append((start, stop))
        cursor = stop

    without_comments = _mask_ranges(text, ranges)
    fence_start: tuple[str, int, int] | None = None
    offset = 0
    for line in without_comments.splitlines(keepends=True):
        line_without_break = line.rstrip("\r\n")
        if fence_start is None:
            opening = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", line_without_break)
            if opening:
                token = opening.group(1)
                fence_start = (token[0], len(token), offset)
        else:
            character, minimum_length, start = fence_start
            closing = re.match(
                rf"^[ ]{{0,3}}{re.escape(character)}{{{minimum_length},}}[ \t]*$",
                line_without_break,
            )
            if closing:
                ranges.append((start, offset + len(line)))
                fence_start = None
        offset += len(line)
    if fence_start is not None:
        ranges.append((fence_start[2], len(text)))

    excluded = _mask_ranges(text, ranges)
    inline_ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(excluded):
        if excluded[index] != "`":
            index += 1
            continue
        run_end = index + 1
        while run_end < len(excluded) and excluded[run_end] == "`":
            run_end += 1
        delimiter = excluded[index:run_end]
        search = run_end
        close = -1
        while True:
            candidate = excluded.find(delimiter, search)
            if candidate == -1:
                break
            before_ok = candidate == 0 or excluded[candidate - 1] != "`"
            after = candidate + len(delimiter)
            after_ok = after == len(excluded) or excluded[after] != "`"
            if before_ok and after_ok:
                close = candidate
                break
            search = candidate + 1
        if close == -1:
            index = run_end
            continue
        inline_ranges.append((index, close + len(delimiter)))
        index = close + len(delimiter)
    return _mask_ranges(excluded, inline_ranges)


def _docx_text(path: Path) -> tuple[str, dict[int, str], dict[int, int]]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise AuditError(f"无法读取 DOCX 主文档：{path}: {exc}") from exc

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise AuditError(f"DOCX XML 损坏：{path}: {exc}") from exc

    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines: list[str] = []
    heading_lines: dict[int, str] = {}
    paragraph_by_line: dict[int, int] = {}
    paragraph_number = 0
    for paragraph in root.iter(f"{w}p"):
        paragraph_number += 1
        pieces: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{w}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{w}tab":
                pieces.append("\t")
            elif node.tag == f"{w}br":
                pieces.append(" ")
        value = "".join(pieces)
        if not value.strip():
            continue
        lines.append(value)
        line_number = len(lines)
        paragraph_by_line[line_number] = paragraph_number
        style = paragraph.find(f"{w}pPr/{w}pStyle")
        style_name = style.get(f"{w}val", "") if style is not None else ""
        if style_name.casefold().startswith("heading") or style_name.casefold() in {
            "title",
            "subtitle",
        }:
            heading_lines[line_number] = value.strip()
    return "\n".join(lines), heading_lines, paragraph_by_line


def _pdf_text(
    path: Path, diagnostics: list[dict[str, Any]], source: str
) -> tuple[str, dict[int, int]]:
    executable = shutil.which("pdftotext")
    if not executable:
        _diagnostic(
            diagnostics,
            "warning",
            "pdf-extractor-unavailable",
            source,
            "未找到 pdftotext；未对 PDF 文本执行确定性检查。",
        )
        return "", {}
    try:
        completed = subprocess.run(
            [executable, "-layout", str(path), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=PDFTEXT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        _diagnostic(
            diagnostics,
            "error",
            "pdf-extraction-timeout",
            source,
            f"pdftotext 超过 {PDFTEXT_TIMEOUT_SECONDS} 秒未完成；已停止提取。",
        )
        return "", {}
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        _diagnostic(
            diagnostics,
            "error",
            "pdf-extraction-failed",
            source,
            f"pdftotext 提取失败：{message or '未知错误'}",
        )
        return "", {}
    decoded = completed.stdout.decode("utf-8", errors="replace")
    lines: list[str] = []
    pages: dict[int, int] = {}
    for page_number, page in enumerate(decoded.split("\f"), 1):
        for line in page.splitlines():
            lines.append(line)
            pages[len(lines)] = page_number
    _diagnostic(
        diagnostics,
        "info",
        "pdf-text-extracted",
        source,
        "PDF 检查基于 pdftotext 提取结果；版面、公式与图中文字仍需视觉复核。",
    )
    return "\n".join(lines), pages


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _recognize_heading(raw: str) -> str | None:
    stripped = raw.strip()
    markdown = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", stripped)
    if markdown:
        return markdown.group(1).strip()
    tex = re.search(r"\\(?:sub)*section\*?\{([^{}]+)\}", raw)
    if tex:
        return tex.group(1).strip()
    candidate = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)])\s+", "", stripped)
    normalized = re.sub(r"\s+", " ", candidate).casefold().rstrip(":")
    if len(candidate) <= 60 and normalized in SECTION_NAMES:
        return SECTION_NAMES[normalized]
    return None


def _build_blocks(unit: SourceUnit) -> None:
    raw_lines = unit.raw.splitlines()
    structure_lines = unit.structure.splitlines()
    masked_lines = unit.masked.splitlines()
    if len(structure_lines) < len(raw_lines):
        structure_lines.extend([""] * (len(raw_lines) - len(structure_lines)))
    if len(masked_lines) < len(raw_lines):
        masked_lines.extend([""] * (len(raw_lines) - len(masked_lines)))
    current_section = "Front matter"
    abstract_environment = False
    bibliography_environment = False
    blocks: list[Block] = []
    for line_number, raw in enumerate(raw_lines, 1):
        structure_line = structure_lines[line_number - 1]
        if unit.format == "tex" and re.search(r"\\begin\{abstract\}", structure_line):
            abstract_environment = True
            current_section = "Abstract"
        if unit.format == "tex" and re.search(r"\\begin\{thebibliography\}", structure_line):
            bibliography_environment = True
            current_section = "Bibliography"
        heading = unit.heading_lines.get(line_number) or _recognize_heading(structure_line)
        if heading:
            current_section = heading
        section_key = re.sub(r"\s+", " ", current_section).casefold()
        scope = "abstract" if abstract_environment or section_key == "abstract" else "body"
        blocks.append(
            Block(
                unit=unit,
                line=line_number,
                raw=raw,
                scan=masked_lines[line_number - 1] if line_number <= len(masked_lines) else "",
                section=current_section,
                scope=scope,
            )
        )
        if unit.format == "tex" and re.search(r"\\end\{abstract\}", structure_line):
            abstract_environment = False
            current_section = "Front matter"
        if unit.format == "tex" and bibliography_environment and re.search(
            r"\\end\{thebibliography\}", structure_line
        ):
            bibliography_environment = False
            current_section = "Front matter"
    unit.blocks = blocks
    unit.prepare_offsets()


def _make_unit(
    path: Path,
    source: str,
    format_name: str,
    raw: str,
    *,
    heading_lines: dict[int, str] | None = None,
    page_by_line: dict[int, int] | None = None,
    paragraph_by_line: dict[int, int] | None = None,
) -> SourceUnit:
    if format_name == "tex":
        structure = _tex_structure_view(raw)
        masked = _mask_tex(raw, structure)
    elif format_name == "md":
        structure = _markdown_prose_view(raw)
        masked = structure
    else:
        structure = raw
        masked = raw
    unit = SourceUnit(
        path=path,
        source=source,
        format=format_name,
        raw=raw,
        structure=structure,
        masked=masked,
        heading_lines=heading_lines or {},
        page_by_line=page_by_line or {},
        paragraph_by_line=paragraph_by_line or {},
    )
    _build_blocks(unit)
    return unit


def _load_sources(input_path: Path, diagnostics: list[dict[str, Any]]) -> list[SourceUnit]:
    if not input_path.is_file():
        raise AuditError(f"稿件不存在或不是文件：{input_path}")
    root = input_path.resolve().parent
    suffix = input_path.suffix.casefold()
    if suffix == ".tex":
        units: list[SourceUnit] = []
        visited: set[Path] = set()

        def visit(path: Path) -> None:
            resolved = path.resolve()
            if resolved in visited:
                return
            visited.add(resolved)
            source = _display_path(resolved, root)
            if not resolved.is_file():
                _diagnostic(
                    diagnostics,
                    "warning",
                    "tex-include-missing",
                    source,
                    "LaTeX include/input 指向的文件不存在；相关检查可能不完整。",
                )
                return
            raw = _read_text(resolved, diagnostics, source)
            unit = _make_unit(resolved, source, "tex", raw)
            units.append(unit)
            for match in re.finditer(
                r"\\(?:input|include)\s*\{([^{}]+)\}", unit.structure
            ):
                relative = match.group(1).strip()
                child = resolved.parent / relative
                if not child.suffix:
                    child = child.with_suffix(".tex")
                visit(child)

        visit(input_path)
        if len(units) > 1:
            _diagnostic(
                diagnostics,
                "info",
                "tex-multifile-order-approximate",
                input_path.name,
                "多文件 LaTeX 的首次出现顺序按文件遍历近似；跨文件缩写首次定义需复核。",
            )
        return units

    source = input_path.name
    if suffix in {".txt", ".md"}:
        raw = _read_text(input_path, diagnostics, source)
        return [_make_unit(input_path, source, suffix[1:], raw)]
    if suffix == ".docx":
        raw, headings, paragraphs = _docx_text(input_path)
        return [
            _make_unit(
                input_path,
                source,
                "docx",
                raw,
                heading_lines=headings,
                paragraph_by_line=paragraphs,
            )
        ]
    if suffix == ".pdf":
        raw, pages = _pdf_text(input_path, diagnostics, source)
        return [_make_unit(input_path, source, "pdf", raw, page_by_line=pages)]
    raise AuditError("仅支持 .txt、.md、.tex、.docx，以及安装 pdftotext 时的 .pdf。")


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"无法读取个人配置：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"个人配置根节点必须是 JSON 对象：{path}")
    return value


def _load_terms(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    except OSError as exc:
        raise AuditError(f"无法读取术语表：{path}: {exc}") from exc
    required = {"preferred", "aliases", "forbidden", "abbreviation", "case_sensitive", "notes"}
    if not rows and path.stat().st_size:
        raise AuditError(f"术语表没有可解析的数据行：{path}")
    if rows and not required.issubset(rows[0]):
        raise AuditError(f"术语表缺少列：{', '.join(sorted(required - set(rows[0])))}")
    for row in rows:
        row["alias_list"] = [item.strip() for item in row["aliases"].split("|") if item.strip()]
        row["forbidden_list"] = [item.strip() for item in row["forbidden"].split("|") if item.strip()]
        row["case_sensitive_bool"] = row["case_sensitive"].strip().casefold() == "true"
    return rows


def _short_quote(text: str, start: int | None = None, end: int | None = None) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if start is not None and end is not None and len(compact) > 180:
        center = min(max((start + end) // 2, 0), len(compact))
        left = max(0, center - 75)
        right = min(len(compact), center + 75)
        compact = compact[left:right]
    return compact[:180]


def _normalize_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _phrase_pattern(value: str) -> re.Pattern[str]:
    escaped = re.escape(value)
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def _crossref_kind(label: str) -> str:
    folded = label.casefold()
    if folded.startswith("fig"):
        return "figure"
    if folded.startswith("table"):
        return "table"
    return "equation"


class Auditor:
    def __init__(
        self,
        input_path: Path,
        units: list[SourceUnit],
        profile: dict[str, Any],
        terms: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        self.input_path = input_path
        self.units = units
        self.profile = profile
        self.terms = terms
        self.diagnostics = diagnostics
        self.findings: list[dict[str, Any]] = []
        self.finding_ids: set[str] = set()
        self.inventory: dict[str, Any] = {}
        self.extra_source_paths: set[Path] = set()
        overrides = profile.get("severity_overrides", {})
        if not isinstance(overrides, dict):
            raise AuditError("profile.severity_overrides 必须是 check_id 到严重程度的对象。")
        invalid_overrides = {
            check_id: value
            for check_id, value in overrides.items()
            if not isinstance(check_id, str) or value not in SEVERITY_ORDER
        }
        if invalid_overrides:
            details = ", ".join(
                f"{check_id!r}={value!r}"
                for check_id, value in sorted(
                    invalid_overrides.items(), key=lambda item: str(item[0])
                )
            )
            allowed = ", ".join(SEVERITY_ORDER)
            raise AuditError(
                f"profile.severity_overrides 含非法值：{details}；允许值：{allowed}。"
            )
        self.severity_overrides: dict[str, str] = dict(overrides)
        self.known_expansions: dict[str, list[str]] = defaultdict(list)
        self.configured_abbreviations: set[str] = set()
        for row in terms:
            abbreviation = row["abbreviation"].strip()
            if abbreviation:
                token = abbreviation.split(maxsplit=1)[0]
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:[-/][A-Za-z0-9]+)*", token):
                    self.configured_abbreviations.add(token)
                    self.known_expansions[token].append(row["preferred"])
                    self.known_expansions[token].extend(row["alias_list"])

    def add_finding(
        self,
        *,
        category: str,
        check_id: str,
        severity: str,
        confidence: float,
        status: str,
        block: Block,
        observation: str,
        expected: str,
        reason: str,
        suggested_fix: str,
        auto_fixable: bool,
        key: str,
        quote: str | None = None,
        evidence_source: str = "manuscript",
    ) -> None:
        if confidence < 0.60:
            return
        severity = self.severity_overrides.get(check_id, severity)
        if severity not in SEVERITY_ORDER:
            raise AuditError(f"检查 {check_id} 的严重程度无效：{severity!r}")
        location = block.location()
        stable_material = "\0".join(
            [
                check_id,
                location["source"].casefold(),
                str(location.get("line", "")),
                str(location.get("paragraph", "")),
                str(location.get("page", "")),
                _normalize_phrase(key),
            ]
        )
        digest = hashlib.blake2s(stable_material.encode("utf-8"), digest_size=5).hexdigest().upper()
        identifier = f"{PREFIXES[category]}-{digest}"
        if identifier in self.finding_ids:
            return
        self.finding_ids.add(identifier)
        self.findings.append(
            {
                "id": identifier,
                "category": category,
                "check_id": check_id,
                "severity": severity,
                "confidence": round(confidence, 2),
                "status": status,
                "location": location,
                "quote": quote if quote is not None else _short_quote(block.raw),
                "observation": observation,
                "expected": expected,
                "reason": reason,
                "evidence": [{"class": "A", "source": evidence_source}],
                "suggested_fix": suggested_fix,
                "auto_fixable": auto_fixable,
            }
        )

    @property
    def blocks(self) -> list[Block]:
        return [block for unit in self.units for block in unit.blocks]

    def run(self) -> dict[str, Any]:
        self.check_abbreviations()
        self.check_terminology()
        self.check_spelling()
        self.check_units()
        self.check_plain_cross_references()
        self.check_latex()
        self.findings.sort(
            key=lambda finding: (
                SEVERITY_ORDER[finding["severity"]],
                finding["location"]["source"].casefold(),
                finding["location"].get("line", 0),
                finding["check_id"],
                finding["id"],
            )
        )
        manifests = []
        for unit in self.units:
            if unit.path.is_file():
                manifests.append(
                    {
                        "source": unit.source,
                        "sha256": hashlib.sha256(unit.path.read_bytes()).hexdigest(),
                    }
                )
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "input": str(self.input_path.resolve()),
            "sources": manifests,
            "summary": {
                "finding_count": len(self.findings),
                "by_severity": dict(
                    sorted(Counter(item["severity"] for item in self.findings).items())
                ),
                "diagnostic_count": len(self.diagnostics),
            },
            "findings": self.findings,
            "diagnostics": sorted(
                self.diagnostics,
                key=lambda item: (item["level"], item["source"].casefold(), item["code"]),
            ),
            "inventories": self.inventory,
        }

    def _candidate_abbreviations(self, block: Block) -> list[re.Match[str]]:
        if block.is_reference_section:
            return []
        matches: list[re.Match[str]] = []
        seen_spans: set[tuple[int, int]] = set()
        whitelist = set(self.profile.get("abbreviations", {}).get("whitelist", []))
        for match in ABBREVIATION_RE.finditer(block.scan):
            abbreviation = match.group(1)
            if abbreviation in whitelist or abbreviation in ALL_CAPS_STOPWORDS:
                continue
            if len(abbreviation) > 18:
                continue
            letters = [char for char in abbreviation if char.isalpha()]
            if sum(char.isupper() for char in letters) < 2:
                continue
            matches.append(match)
            seen_spans.add(match.span())
        for abbreviation in sorted(self.configured_abbreviations, key=lambda value: (-len(value), value)):
            if abbreviation in whitelist:
                continue
            pattern = re.compile(
                rf"(?<![A-Za-z0-9])({re.escape(abbreviation)})(?![A-Za-z0-9])"
            )
            for match in pattern.finditer(block.scan):
                if match.span() not in seen_spans:
                    matches.append(match)
                    seen_spans.add(match.span())
        return sorted(matches, key=lambda match: (match.start(), match.end()))

    def _initials_match(self, expansion: str, abbreviation: str) -> bool:
        target = "".join(char for char in abbreviation.upper() if char.isalpha())
        parts = re.findall(r"[A-Za-z]+", expansion)
        if not parts or not target:
            return False
        full = "".join(part[0].upper() for part in parts)
        reduced = "".join(
            part[0].upper() for part in parts if part.casefold() not in INITIAL_STOPWORDS
        )
        return target in {full, reduced}

    def _definition_for(self, block: Block, match: re.Match[str]) -> str | None:
        preceding_lines: list[str] = []
        cursor_index = block.line - 2
        inspected = 0
        structure_lines = block.unit.structure.splitlines()
        while cursor_index >= 0 and len(preceding_lines) < 2 and inspected < 4:
            previous = block.unit.blocks[cursor_index]
            inspected += 1
            if (
                previous.scope != block.scope
                or previous.section != block.section
                or previous.is_reference_section
            ):
                break
            if not previous.raw.strip():
                break
            structure_line = (
                structure_lines[previous.line - 1]
                if previous.line <= len(structure_lines)
                else previous.raw
            )
            if _recognize_heading(structure_line):
                break
            if previous.scan.strip():
                preceding_lines.append(previous.scan)
            cursor_index -= 1
        preceding_lines.reverse()
        prefix_context = "\n".join(preceding_lines)
        if prefix_context:
            text = f"{prefix_context}\n{block.scan}"
            position_shift = len(prefix_context) + 1
        else:
            text = block.scan
            position_shift = 0

        abbreviation = match.group(1)
        match_start = match.start() + position_shift
        match_end = match.end() + position_shift
        cursor = match_start - 1
        while cursor >= 0 and text[cursor].isspace():
            cursor -= 1
        if cursor >= 0 and text[cursor] == "(":
            prefix = text[max(0, cursor - 300) : cursor]
            boundary = max(prefix.rfind(mark) for mark in ".;:!?=")
            phrase = prefix[boundary + 1 :]
            spans = list(re.finditer(r"[A-Za-z][A-Za-z'’-]*(?:-[A-Za-z'’-]+)*", phrase))
            for count in range(1, min(12, len(spans)) + 1):
                start = spans[-count].start()
                candidate = re.sub(r"\s+", " ", phrase[start : spans[-1].end()]).strip()
                if self._initials_match(candidate, abbreviation):
                    return candidate
            normalized_phrase = _normalize_phrase(phrase)
            for known in self.known_expansions.get(abbreviation, []):
                if normalized_phrase.endswith(_normalize_phrase(known)):
                    return known

        cursor = match_end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "(":
            close = text.find(")", cursor + 1, min(len(text), cursor + 180))
            if close != -1:
                candidate = re.sub(r"\s+", " ", text[cursor + 1 : close]).strip()
                if self._initials_match(candidate, abbreviation):
                    return candidate
                known_values = {
                    _normalize_phrase(value) for value in self.known_expansions.get(abbreviation, [])
                }
                if _normalize_phrase(candidate) in known_values:
                    return candidate
        return None

    def check_abbreviations(self) -> None:
        occurrences: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        inventory: dict[str, dict[str, Any]] = {}
        abbreviation_config = self.profile.get("abbreviations", {})
        separate_scopes = bool(
            abbreviation_config.get("require_definition_in_abstract_and_main_text", True)
        )
        for block in self.blocks:
            for match in self._candidate_abbreviations(block):
                abbreviation = match.group(1)
                expansion = self._definition_for(block, match)
                occurrence = {
                    "block": block,
                    "start": match.start(),
                    "expansion": expansion,
                }
                ledger_scope = block.scope if separate_scopes else "document"
                occurrences[(abbreviation, ledger_scope)].append(occurrence)
                item = inventory.setdefault(
                    abbreviation,
                    {"abstract_uses": 0, "body_uses": 0, "definitions": []},
                )
                item[f"{block.scope}_uses"] += 1
                if expansion and expansion not in item["definitions"]:
                    item["definitions"].append(expansion)

        minimum = int(abbreviation_config.get("minimum_uses_after_definition", 2))
        for (abbreviation, scope), items in sorted(occurrences.items()):
            first = items[0]
            scope_label = {
                "abstract": "摘要",
                "body": "正文",
                "document": "全文",
            }[scope]
            if separate_scopes:
                definition_reason = (
                    "个人配置要求摘要与正文分别定义缩写；摘要中的定义不能替代正文首次定义。"
                )
            else:
                definition_reason = "个人配置仅要求在全文首次出现时定义缩写。"
            if not first["expansion"]:
                self.add_finding(
                    category="abbreviation",
                    check_id="abbreviation-first-use",
                    severity="Minor",
                    confidence=0.98,
                    status="confirmed",
                    block=first["block"],
                    observation=f"缩写 {abbreviation} 在{scope_label}首次出现时未定义。",
                    expected=f"在{scope_label}首次出现时给出全称并定义 {abbreviation}。",
                    reason=definition_reason,
                    suggested_fix=f"在此处写出全称，随后以括号定义 {abbreviation}。",
                    auto_fixable=False,
                    key=f"{abbreviation}|{scope}|first-use",
                )

            definitions = [item for item in items if item["expansion"]]
            normalized_definitions: dict[str, dict[str, Any]] = {}
            for definition in definitions:
                normalized = _normalize_phrase(definition["expansion"])
                if normalized not in normalized_definitions:
                    normalized_definitions[normalized] = definition
            if len(normalized_definitions) > 1:
                second = list(normalized_definitions.values())[1]
                expansions = sorted({item["expansion"] for item in normalized_definitions.values()})
                self.add_finding(
                    category="abbreviation",
                    check_id="abbreviation-multiple-expansions",
                    severity="Major",
                    confidence=0.96,
                    status="confirmed",
                    block=second["block"],
                    observation=f"缩写 {abbreviation} 对应多个全称：{'；'.join(expansions)}。",
                    expected=f"同一{scope_label}缩写账本内，一个缩写应保持一个明确全称。",
                    reason="多个全称会使技术对象或方法的指代不确定。",
                    suggested_fix="确认预期含义并统一全称；若确为不同概念，请使用不同缩写。",
                    auto_fixable=False,
                    key=f"{abbreviation}|{scope}|multiple-expansions",
                )

            if definitions:
                first_definition_index = items.index(definitions[0])
                uses_after = sum(
                    1 for item in items[first_definition_index + 1 :] if not item["expansion"]
                )
                if uses_after < minimum:
                    self.add_finding(
                        category="abbreviation",
                        check_id="abbreviation-low-use",
                        severity="Info",
                        confidence=0.98,
                        status="confirmed",
                        block=definitions[0]["block"],
                        observation=f"{abbreviation} 定义后仅使用 {uses_after} 次，低于配置阈值 {minimum} 次。",
                        expected="仅在能明显减少重复且会持续使用时引入缩写。",
                        reason="低频缩写增加读者记忆负担。",
                        suggested_fix="考虑删除缩写并保留全称；若期刊或领域惯例要求，可保留。",
                        auto_fixable=False,
                        key=f"{abbreviation}|{scope}|low-use",
                    )
        self.inventory["abbreviations"] = dict(sorted(inventory.items()))

    def check_terminology(self) -> None:
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        caution_tokens = (
            "may differ",
            "not always",
            "confirm",
            "distinction",
            "semantic",
            "only when",
            "sentence role",
            "journal",
            "product names",
            "both occur",
            "do not replace",
            "technically intended",
        )
        for row in self.terms:
            preferred = row["preferred"].strip()
            notes = row["notes"].strip()
            flags = 0 if row["case_sensitive_bool"] else re.IGNORECASE
            for block in self.blocks:
                if block.is_reference_section:
                    continue
                preferred_matches = list(_phrase_pattern(preferred).finditer(block.scan))
                counts[preferred][preferred] += len(preferred_matches)
                claimed_spans = [match.span() for match in preferred_matches]
                for forbidden in row["forbidden_list"]:
                    pattern = re.compile(_phrase_pattern(forbidden).pattern, flags)
                    for match in pattern.finditer(block.scan):
                        claimed_spans.append(match.span())
                        counts[preferred][forbidden] += 1
                        self.add_finding(
                            category="terminology",
                            check_id="terminology-forbidden",
                            severity="Major" if "self-resetting" in forbidden.casefold() else "Minor",
                            confidence=0.98,
                            status="confirmed",
                            block=block,
                            quote=_short_quote(block.raw, match.start(), match.end()),
                            observation=f"使用了个人术语表标记的禁用表达“{match.group(0)}”。",
                            expected=f"默认使用“{preferred}”，并确认技术含义。",
                            reason=notes or "该表达可能造成术语含义或写法不一致。",
                            suggested_fix=f"核对语义后改为“{preferred}”。",
                            auto_fixable=False,
                            key=f"{preferred}|forbidden|{forbidden}|{match.start()}",
                            evidence_source="personal terminology profile",
                        )
                for alias in sorted(
                    row["alias_list"], key=lambda value: (-len(value), value.casefold())
                ):
                    pattern = re.compile(_phrase_pattern(alias).pattern, flags)
                    needs_review = any(token in notes.casefold() for token in caution_tokens)
                    for match in pattern.finditer(block.scan):
                        if any(
                            match.start() < claimed_end and claimed_start < match.end()
                            for claimed_start, claimed_end in claimed_spans
                        ):
                            continue
                        claimed_spans.append(match.span())
                        counts[preferred][alias] += 1
                        self.add_finding(
                            category="terminology",
                            check_id="terminology-variant",
                            severity="Info" if needs_review else "Minor",
                            confidence=0.72 if needs_review else 0.96,
                            status="needs-review" if needs_review else "confirmed",
                            block=block,
                            quote=_short_quote(block.raw, match.start(), match.end()),
                            observation=f"发现术语变体“{match.group(0)}”；个人默认写法为“{preferred}”。",
                            expected=f"确认该处是否与“{preferred}”指同一概念，并保持全文一致。",
                            reason=notes or "同一技术概念应使用一致的术语和连字符形式。",
                            suggested_fix=(
                                f"确认语义相同后改为“{preferred}”。"
                                if not needs_review
                                else "先确认技术对象和句法作用，再决定是否统一；不要机械替换。"
                            ),
                            auto_fixable=not needs_review,
                            key=f"{preferred}|alias|{alias}|{match.start()}",
                            evidence_source="personal terminology profile",
                        )
        self.inventory["terminology"] = {
            preferred: dict(sorted(variants.items()))
            for preferred, variants in sorted(counts.items())
            if sum(variants.values())
        }

    def check_spelling(self) -> None:
        if self.profile.get("style", {}).get("english_variant", "en-US") != "en-US":
            self.inventory["spelling_variants"] = {}
            return
        counts: Counter[str] = Counter()
        for block in self.blocks:
            if block.is_reference_section:
                continue
            for british, american in UK_TO_US.items():
                pattern = re.compile(rf"\b{re.escape(british)}\b", re.IGNORECASE)
                for match in pattern.finditer(block.scan):
                    counts[match.group(0)] += 1
                    self.add_finding(
                        category="spelling",
                        check_id="english-variant",
                        severity="Minor",
                        confidence=0.99,
                        status="confirmed",
                        block=block,
                        quote=_short_quote(block.raw, match.start(), match.end()),
                        observation=f"发现英式拼写“{match.group(0)}”，与 en-US 配置不一致。",
                        expected=f"使用美式拼写“{american}”。",
                        reason="同一稿件应保持英语变体一致。",
                        suggested_fix=f"改为“{american}”。",
                        auto_fixable=True,
                        key=f"{british}|{match.start()}",
                        evidence_source="personal style profile",
                    )
        self.inventory["spelling_variants"] = dict(sorted(counts.items()))

    def check_units(self) -> None:
        space_required = bool(
            self.profile.get("style", {}).get("space_between_number_and_si_unit", True)
        )
        counts: Counter[str] = Counter()
        for block in self.blocks:
            if block.is_reference_section:
                continue
            for match in UNIT_RE.finditer(block.scan):
                raw_unit = match.group("unit")
                canonical = CANONICAL_UNITS.get(raw_unit.casefold())
                if not canonical:
                    continue
                counts[canonical] += 1
                if space_required and match.group("space") == "":
                    self.add_finding(
                        category="unit",
                        check_id="unit-spacing",
                        severity="Minor",
                        confidence=0.99,
                        status="confirmed",
                        block=block,
                        quote=_short_quote(block.raw, match.start(), match.end()),
                        observation=f"数值与单位“{match.group(0)}”之间缺少空格。",
                        expected=f"写作“{match.group('number')} {canonical}”。",
                        reason="个人样式配置要求数值与 SI 单位之间留空格。",
                        suggested_fix="在数值与单位之间插入一个普通空格或期刊允许的不可断行空格。",
                        auto_fixable=True,
                        key=f"space|{match.group(0)}|{match.start()}",
                        evidence_source="personal style profile",
                    )
                if raw_unit.casefold() in CASE_SAFE_UNITS and raw_unit != canonical:
                    self.add_finding(
                        category="unit",
                        check_id="unit-case",
                        severity="Minor",
                        confidence=0.99,
                        status="confirmed",
                        block=block,
                        quote=_short_quote(block.raw, match.start(), match.end()),
                        observation=f"单位大小写“{raw_unit}”不符合配置中的标准形式。",
                        expected=f"使用“{canonical}”。",
                        reason="SI 前缀和单位符号区分大小写。",
                        suggested_fix=f"将“{raw_unit}”改为“{canonical}”。",
                        auto_fixable=True,
                        key=f"case|{raw_unit}|{match.start()}",
                        evidence_source="personal style profile",
                    )
            if not self.profile.get("style", {}).get("space_before_percent", False):
                for match in re.finditer(r"(?<!\w)(\d+(?:\.\d+)?)\s+%", block.scan):
                    self.add_finding(
                        category="unit",
                        check_id="percent-spacing",
                        severity="Minor",
                        confidence=0.99,
                        status="confirmed",
                        block=block,
                        quote=_short_quote(block.raw, match.start(), match.end()),
                        observation="百分号前存在空格，与个人样式配置不一致。",
                        expected=f"写作“{match.group(1)}%”。",
                        reason="个人样式配置不在数值与百分号之间留空格。",
                        suggested_fix="删除百分号前的空格。",
                        auto_fixable=True,
                        key=f"percent|{match.start()}",
                        evidence_source="personal style profile",
                    )
        self.inventory["units"] = dict(sorted(counts.items()))

    def check_plain_cross_references(self) -> None:
        declarations: dict[tuple[str, str], list[Block]] = defaultdict(list)
        callouts: dict[tuple[str, str], list[Block]] = defaultdict(list)
        for block in self.blocks:
            if block.is_reference_section:
                continue
            if block.unit.format == "tex":
                if self.profile.get("checks", {}).get(
                    "hardcoded_latex_cross_references", True
                ):
                    for match in re.finditer(
                        r"\b(?:Fig(?:ure)?\.?|Table|Eq(?:uation)?\.?)\s*\(?\d+(?:\.\d+)*[A-Za-z]?\)?",
                        block.scan,
                        re.IGNORECASE,
                    ):
                        self.add_finding(
                            category="cross-reference",
                            check_id="latex-hardcoded-cross-reference",
                            severity="Minor",
                            confidence=0.92,
                            status="confirmed",
                            block=block,
                            quote=_short_quote(block.raw, match.start(), match.end()),
                            observation=f"LaTeX 正文中存在硬编码交叉引用“{match.group(0)}”。",
                            expected="使用 \\ref、\\eqref 或 cleveref 类命令生成编号。",
                            reason="硬编码编号在增删图表或公式后容易失配。",
                            suggested_fix="为目标添加稳定 \\label，并用相应引用命令替换数字。",
                            auto_fixable=False,
                            key=f"hardcoded|{match.group(0)}|{match.start()}",
                        )
                continue
            caption_match = CAPTION_RE.match(block.scan)
            caption_span: tuple[int, int] | None = None
            if caption_match:
                key = (
                    _crossref_kind(caption_match.group("label")),
                    caption_match.group("identifier").casefold(),
                )
                declarations[key].append(block)
                caption_span = caption_match.span()
            for match in CALLOUT_RE.finditer(block.scan):
                if caption_span and match.start() >= caption_span[0] and match.end() <= caption_span[1]:
                    continue
                key = (
                    _crossref_kind(match.group("label")),
                    match.group("identifier").casefold(),
                )
                callouts[key].append(block)

        for key, blocks in sorted(declarations.items()):
            kind, identifier = key
            for duplicate in blocks[1:]:
                self.add_finding(
                    category="cross-reference",
                    check_id="crossref-duplicate-target",
                    severity="Major",
                    confidence=0.97,
                    status="confirmed",
                    block=duplicate,
                    observation=f"检测到重复的 {kind} 编号 {identifier}。",
                    expected="每个图、表或公式编号应唯一。",
                    reason="重复编号会使正文引用无法唯一定位。",
                    suggested_fix="更正编号并同步全部引用。",
                    auto_fixable=False,
                    key=f"duplicate|{kind}|{identifier}",
                )
            if key not in callouts:
                block = blocks[0]
                confidence = 0.68 if block.unit.format in {"docx", "pdf"} else 0.91
                self.add_finding(
                    category="cross-reference",
                    check_id="crossref-target-not-called",
                    severity="Minor",
                    confidence=confidence,
                    status="needs-review" if confidence < 0.8 else "confirmed",
                    block=block,
                    observation=f"{kind} {identifier} 有题注，但未检测到正文引用。",
                    expected="每个图、表或编号公式应在正文中被明确引用。",
                    reason="未引用的目标可能是遗漏、冗余，或抽取未保留域代码。",
                    suggested_fix="在首次讨论处加入引用；若 Word/PDF 使用自动域，请在渲染稿中复核。",
                    auto_fixable=False,
                    key=f"unused|{kind}|{identifier}",
                )

        declared_kinds = {kind for kind, _ in declarations}
        for key, blocks in sorted(callouts.items()):
            if key in declarations:
                continue
            kind, identifier = key
            block = blocks[0]
            confidence = 0.87 if kind in declared_kinds and block.unit.format not in {"docx", "pdf"} else 0.68
            if block.unit.format == "pdf":
                confidence = 0.62
            self.add_finding(
                category="cross-reference",
                check_id="crossref-callout-missing-target",
                severity="Minor",
                confidence=confidence,
                status="likely" if confidence >= 0.8 else "needs-review",
                block=block,
                observation=f"正文引用了 {kind} {identifier}，但未检测到对应题注或编号目标。",
                expected="正文引用应能对应到唯一的图、表或公式目标。",
                reason="目标可能缺失、编号错误，或未被当前文本提取器识别。",
                suggested_fix="核对目标编号；对 Word/PDF 稿件同时检查渲染页面和域代码。",
                auto_fixable=False,
                key=f"missing|{kind}|{identifier}",
            )
        self.inventory["cross_references"] = {
            "declared": [f"{kind}:{identifier}" for kind, identifier in sorted(declarations)],
            "called": [f"{kind}:{identifier}" for kind, identifier in sorted(callouts)],
        }

    def _bib_paths(self, tex_units: list[SourceUnit]) -> list[Path]:
        paths: list[Path] = []
        for unit in tex_units:
            for match in re.finditer(r"\\bibliography\s*\{([^{}]+)\}", unit.structure):
                for item in match.group(1).split(","):
                    path = unit.path.parent / item.strip()
                    if not path.suffix:
                        path = path.with_suffix(".bib")
                    paths.append(path)
            for match in re.finditer(
                r"\\addbibresource(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}", unit.structure
            ):
                paths.append(unit.path.parent / match.group(1).strip())
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            resolved = path.resolve()
            if resolved not in seen:
                unique.append(resolved)
                seen.add(resolved)
        return unique

    def check_latex(self) -> None:
        tex_units = [unit for unit in self.units if unit.format == "tex"]
        if not tex_units:
            self.inventory["latex"] = {"applicable": False}
            return
        labels: dict[str, list[Block]] = defaultdict(list)
        references: list[tuple[str, Block]] = []
        citations: list[tuple[str, Block]] = []
        nocitations: list[tuple[str, Block]] = []
        nocite_star = False
        external_documents = False
        for unit in tex_units:
            for match in re.finditer(r"\\label\s*\{([^{}]+)\}", unit.structure):
                key = match.group(1).strip()
                if key:
                    labels[key].append(unit.block_at_offset(match.start()))
            for match in re.finditer(
                r"\\(?:ref|eqref|autoref|pageref|nameref|cref|Cref)\*?\s*\{([^{}]+)\}",
                unit.structure,
            ):
                block = unit.block_at_offset(match.start())
                references.extend(
                    (key.strip(), block) for key in match.group(1).split(",") if key.strip()
                )
            cite_re = re.compile(
                r"\\(?P<command>[A-Za-z]*cite[A-Za-z]*)\*?"
                r"(?:\s*\[[^\]]*\]){0,2}\s*\{(?P<keys>[^{}]+)\}"
            )
            for match in cite_re.finditer(unit.structure):
                command = match.group("command").casefold()
                keys = [key.strip() for key in match.group("keys").split(",") if key.strip()]
                block = unit.block_at_offset(match.start())
                if command == "nocite":
                    if "*" in keys:
                        nocite_star = True
                    nocitations.extend((key, block) for key in keys if key != "*")
                else:
                    citations.extend((key, block) for key in keys)
            if re.search(r"\\externaldocument(?:\s*\[[^\]]*\])?\s*\{", unit.structure):
                external_documents = True

        for key, blocks in sorted(labels.items()):
            for duplicate in blocks[1:]:
                self.add_finding(
                    category="latex",
                    check_id="latex-duplicate-label",
                    severity="Major",
                    confidence=0.99,
                    status="confirmed",
                    block=duplicate,
                    observation=f"LaTeX 标签“{key}”被重复定义。",
                    expected="每个 \\label 键在项目中应唯一。",
                    reason="重复标签会使交叉引用解析到错误或不确定的目标。",
                    suggested_fix="为重复目标分配唯一标签并更新引用。",
                    auto_fixable=False,
                    key=f"duplicate-label|{key}",
                )

        referenced_label_keys = {key for key, _ in references}
        for key, block in references:
            if key in labels:
                continue
            confidence = 0.72 if external_documents else 0.99
            self.add_finding(
                category="latex",
                check_id="latex-reference-missing-label",
                severity="Major" if not external_documents else "Info",
                confidence=confidence,
                status="confirmed" if not external_documents else "needs-review",
                block=block,
                observation=f"引用键“{key}”没有在已读取的 LaTeX 源文件中定义。",
                expected="每个交叉引用键应对应唯一 \\label；外部文档引用除外。",
                reason=(
                    "项目使用了 \\externaldocument，当前键可能来自外部辅助文件。"
                    if external_documents
                    else "未定义标签通常会在编译稿中显示为未解析引用。"
                ),
                suggested_fix="检查拼写、include 文件和外部文档配置，再补充或更正标签。",
                auto_fixable=False,
                key=f"missing-label|{key}",
            )

        if self.profile.get("checks", {}).get("unused_latex_labels", True):
            for key, blocks in sorted(labels.items()):
                if key not in referenced_label_keys:
                    self.add_finding(
                        category="latex",
                        check_id="latex-unused-label",
                        severity="Info",
                        confidence=0.92,
                        status="likely",
                        block=blocks[0],
                        observation=f"标签“{key}”未被已识别的引用命令使用。",
                        expected="删除无用标签，或确认它是否由未识别的宏/外部文件调用。",
                        reason="无用标签可能是残留内容；自定义宏可能造成假阳性。",
                        suggested_fix="搜索自定义引用宏后再决定是否删除。",
                        auto_fixable=False,
                        key=f"unused-label|{key}",
                    )

        bib_paths = self._bib_paths(tex_units)
        if not bib_paths and citations:
            candidates = sorted(self.input_path.resolve().parent.glob("*.bib"))
            if len(candidates) == 1:
                bib_paths = candidates
                _diagnostic(
                    self.diagnostics,
                    "info",
                    "bibliography-auto-discovered",
                    candidates[0].name,
                    "未找到显式 bibliography 命令；已使用目录中唯一的 .bib 文件。",
                )
            elif len(candidates) > 1:
                _diagnostic(
                    self.diagnostics,
                    "warning",
                    "bibliography-ambiguous",
                    self.input_path.name,
                    "存在多个 .bib 文件且未能确定实际使用者；未执行 BibTeX 键完整性判断。",
                )

        bib_entries: dict[str, list[Block]] = defaultdict(list)
        for bib_path in bib_paths:
            source = _display_path(bib_path, self.input_path.resolve().parent)
            if not bib_path.is_file():
                _diagnostic(
                    self.diagnostics,
                    "warning",
                    "bibliography-file-missing",
                    source,
                    "LaTeX 指定的参考文献数据库不存在；未将其键判为稿件缺陷。",
                )
                continue
            self.extra_source_paths.add(bib_path)
            raw = _read_text(bib_path, self.diagnostics, source)
            bib_unit = _make_unit(bib_path, source, "bib", raw)
            entry_re = re.compile(
                r"@(?!(?:string|preamble|comment)\b)[A-Za-z]+\s*[({]\s*([^,\s]+)\s*,",
                re.IGNORECASE,
            )
            for match in entry_re.finditer(raw):
                bib_entries[match.group(1).strip()].append(bib_unit.block_at_offset(match.start()))

        for key, blocks in sorted(bib_entries.items()):
            for duplicate in blocks[1:]:
                self.add_finding(
                    category="bibliography",
                    check_id="bibtex-duplicate-key",
                    severity="Major",
                    confidence=0.99,
                    status="confirmed",
                    block=duplicate,
                    observation=f"BibTeX 键“{key}”重复。",
                    expected="每个 BibTeX 条目键应唯一。",
                    reason="重复键会导致引用解析不确定或覆盖。",
                    suggested_fix="为条目分配唯一键并更新对应引用。",
                    auto_fixable=False,
                    key=f"duplicate-bib|{key}",
                )

        all_used = citations + nocitations
        if citations and not bib_entries and not bib_paths:
            _diagnostic(
                self.diagnostics,
                "warning",
                "bibliography-not-found",
                self.input_path.name,
                "检测到引用命令，但未定位到可核对的 .bib 数据库。",
            )
        if bib_entries:
            for key, block in all_used:
                if key not in bib_entries:
                    self.add_finding(
                        category="bibliography",
                        check_id="latex-citation-missing-bib-key",
                        severity="Major",
                        confidence=0.99,
                        status="confirmed",
                        block=block,
                        observation=f"引用键“{key}”不在已读取的 BibTeX 数据库中。",
                        expected="每个 \\cite/\\nocite 键都应对应唯一 BibTeX 条目。",
                        reason="缺失键会在编译时产生未解析引用。",
                        suggested_fix="更正引用键，或向实际使用的 .bib 文件添加准确条目。",
                        auto_fixable=False,
                        key=f"missing-bib|{key}",
                    )
            if self.profile.get("checks", {}).get("unused_bibliography_entries", True) and not nocite_star:
                used_keys = {key for key, _ in all_used}
                for key, blocks in sorted(bib_entries.items()):
                    if key not in used_keys:
                        self.add_finding(
                            category="bibliography",
                            check_id="bibtex-unused-entry",
                            severity="Info",
                            confidence=0.99,
                            status="confirmed",
                            block=blocks[0],
                            observation=f"BibTeX 条目“{key}”未被稿件引用。",
                            expected="提交数据库宜只保留实际引用条目，除非工作流有意保留共享库。",
                            reason="未用条目可能是残留，但共享 .bib 库中也可能是有意存在。",
                            suggested_fix="确认该 .bib 是否为共享库；若不是，可移除未用条目。",
                            auto_fixable=False,
                            key=f"unused-bib|{key}",
                        )

        self.inventory["latex"] = {
            "applicable": True,
            "labels": len(labels),
            "references": len(references),
            "citation_keys": len(citations),
            "bib_entries": len(bib_entries),
            "bib_files": [str(path) for path in bib_paths],
            "external_documents": external_documents,
        }


def _atomic_write(path: Path, text: str, *, force: bool = False) -> None:
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
                raise AuditError(f"输出文件已存在，未覆盖：{path}") from exc
            os.unlink(temporary_name)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _format_location(location: dict[str, Any]) -> str:
    parts = [location["source"]]
    if "page" in location:
        parts.append(f"第 {location['page']} 页")
    if "paragraph" in location:
        parts.append(f"第 {location['paragraph']} 段")
    else:
        parts.append(f"第 {location.get('line', '?')} 行")
    if location.get("section"):
        parts.append(str(location["section"]))
    return " · ".join(parts)


def render_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# 论文确定性审核报告",
        "",
        f"- 输入：`{result['input']}`",
        f"- 正式发现：{summary['finding_count']} 条",
        f"- 解析诊断：{summary['diagnostic_count']} 条",
        "- 范围：缩写、术语、英语变体、单位、交叉引用、LaTeX/BibTeX 一致性",
        "",
        "> 本报告是确定性初筛，不替代全文逻辑、论证、图形视觉与文献真实性的深度审核。",
        "",
        "## 按严重程度汇总",
        "",
    ]
    for severity in ("Blocker", "Major", "Minor", "Info"):
        lines.append(f"- {severity}: {summary['by_severity'].get(severity, 0)}")
    lines.extend(["", "## 正式发现", ""])
    if not result["findings"]:
        lines.extend(["未发现满足报告阈值的确定性问题。", ""])
    for finding in result["findings"]:
        lines.extend(
            [
                f"### {finding['id']} · {finding['severity']} · {finding['observation']}",
                "",
                f"- 检查：`{finding['check_id']}`",
                f"- 状态 / 置信度：`{finding['status']}` / {finding['confidence']:.2f}",
                f"- 位置：{_format_location(finding['location'])}",
                f"- 原文：“{finding['quote']}”",
                f"- 预期：{finding['expected']}",
                f"- 原因：{finding['reason']}",
                f"- 建议：{finding['suggested_fix']}",
                f"- 可安全自动修复：{'是' if finding['auto_fixable'] else '否'}",
                "",
            ]
        )
    lines.extend(["## 解析与覆盖诊断", ""])
    if not result["diagnostics"]:
        lines.extend(["无。", ""])
    else:
        for diagnostic in result["diagnostics"]:
            lines.append(
                f"- `{diagnostic['level']}` / `{diagnostic['code']}` / "
                f"{diagnostic['source']}：{diagnostic['message']}"
            )
        lines.append("")
    lines.extend(
        [
            "## 清单摘要",
            "",
            f"- 缩写种类：{len(result['inventories'].get('abbreviations', {}))}",
            f"- 检出的术语族：{len(result['inventories'].get('terminology', {}))}",
            f"- 单位种类：{len(result['inventories'].get('units', {}))}",
            "- 完整机器可读清单见 `findings.json`。",
            "",
        ]
    )
    return "\n".join(lines)


def run_audit(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    profile_path: str | Path | None = None,
    terms_path: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    manuscript = Path(input_path).resolve()
    review_dir = Path(output_dir).resolve()
    outputs = [review_dir / "findings.json", review_dir / "review-report.md"]
    if review_dir.exists() and not review_dir.is_dir():
        raise AuditError(f"输出位置不是目录：{review_dir}")
    if not force:
        existing_outputs = [output for output in outputs if output.exists()]
        if existing_outputs:
            joined = "；".join(str(output) for output in existing_outputs)
            raise AuditError(f"输出文件已存在，未覆盖：{joined}。如需替换，请显式使用 force=True。")

    script_root = Path(__file__).resolve().parent.parent
    profile_file = (
        Path(profile_path).resolve()
        if profile_path
        else script_root / "references" / "personal-profile.json"
    )
    terms_file = (
        Path(terms_path).resolve()
        if terms_path
        else script_root / "references" / "terminology.tsv"
    )
    diagnostics: list[dict[str, Any]] = []
    profile = _load_profile(profile_file)
    terms = _load_terms(terms_file)
    units = _load_sources(manuscript, diagnostics)
    auditor = Auditor(manuscript, units, profile, terms, diagnostics)
    result = auditor.run()
    protected = {unit.path.resolve() for unit in units} | {
        path.resolve() for path in auditor.extra_source_paths
    }
    for output in outputs:
        if output.resolve() in protected:
            raise AuditError(f"输出路径会覆盖稿件或参考文献源文件：{output}")
    _atomic_write(
        outputs[0],
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        force=force,
    )
    _atomic_write(outputs[1], render_report(result), force=force)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以只读方式执行论文确定性审校并输出 findings.json 与 review-report.md。"
    )
    parser.add_argument("manuscript", help=".txt/.md/.tex/.docx，或可由 pdftotext 读取的 .pdf")
    parser.add_argument(
        "--output-dir",
        help="独立审核输出目录；默认位于稿件旁的 <stem>-review",
    )
    parser.add_argument("--profile", help="覆盖默认 personal-profile.json")
    parser.add_argument("--terms", help="覆盖默认 terminology.tsv")
    parser.add_argument(
        "--force",
        action="store_true",
        help="显式允许覆盖输出目录中已有的 findings.json/review-report.md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manuscript = Path(args.manuscript)
    output_dir = Path(args.output_dir) if args.output_dir else manuscript.with_name(
        f"{manuscript.stem}-review"
    )
    try:
        result = run_audit(
            manuscript,
            output_dir,
            profile_path=args.profile,
            terms_path=args.terms,
            force=args.force,
        )
    except (AuditError, OSError) as exc:
        print(f"paper-auditor: {exc}", file=sys.stderr)
        return 2
    print(f"审核完成：{len(result['findings'])} 条正式发现")
    print(Path(output_dir).resolve() / "review-report.md")
    print(Path(output_dir).resolve() / "findings.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
