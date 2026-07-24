#!/usr/bin/env python3
"""Privacy-preserving bibliographic metadata verification.

Only DOI or minimum title/author/year metadata is sent to Crossref or DataCite.
The manuscript, citation context, and figures are never uploaded. Network I/O
is isolated behind an injectable transport, and ``--offline`` performs no I/O.
Outputs never overwrite an input source and existing reports require ``--force``.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from xml.etree import ElementTree


SCHEMA_VERSION = "0.3.0"
CROSSREF_BASE = "https://api.crossref.org"
DATACITE_BASE = "https://api.datacite.org"
PDF_TIMEOUT_SECONDS = 60
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+")
YEAR_RE = re.compile(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)")
REFERENCE_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(references|bibliography|参考文献)\s*$"
)

# Keep this vocabulary exactly aligned with references/citation-verification.md.
STATUS_EXPLANATIONS = {
    "verified": "权威注册元数据已找到，已提供字段未见实质冲突。",
    "verified_with_warnings": "权威注册元数据已找到，仅有非实质差异或信息不完整，建议人工确认。",
    "identifier_conflict": "标识符可解析或找到强候选，但题名、作者、年份或 DOI 存在实质冲突。",
    "ambiguous": "找到多个相近候选，现有元数据不足以唯一判断。",
    "not_found": "在本次查询的数据源中没有找到足够匹配；这不等于文献伪造。",
    "verification_unavailable": "离线、隐私设置、元数据不足、网络或服务问题阻止了核验；详见 reason。",
    "retracted_or_updated": "注册元数据表明该记录涉及撤稿、更正、撤回或其他更新关系。",
}
UPDATE_TERMS = (
    "retract",
    "withdraw",
    "remove",
    "correct",
    "update",
    "expression-of-concern",
    "expressionofconcern",
    "obsolete",
)


@dataclass
class BibliographicEntry:
    key: str = ""
    entry_type: str = ""
    doi: str = ""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    container: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publisher: str = ""
    url: str = ""
    source: str = ""
    line: int | None = None
    extraction: str = ""


@dataclass
class FetchResponse:
    status: int
    data: Any = None
    raw: bytes = b""
    url: str = ""


@dataclass
class QueryAttempt:
    source: str
    url: str
    queried_at: str
    http_status: int | None = None
    response_sha256: str = ""
    error: str = ""


class NetworkFailure(RuntimeError):
    """Raised when an endpoint cannot be reached or decoded."""


Transport = Callable[[str, Mapping[str, str], float], FetchResponse]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法解码文本文件：{path}")


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(ns + "p"):
        paragraphs.append("".join(node.text or "" for node in paragraph.iter(ns + "t")))
    return "\n".join(paragraphs)


def read_pdf_text(path: Path) -> str:
    """Extract PDF text to stdout with pdftotext; never create or alter a PDF file."""
    executable = shutil.which("pdftotext")
    if not executable:
        raise ValueError(
            "无法读取 PDF：未找到 pdftotext。请安装 Poppler，或先将 PDF 导出为 .txt。"
        )
    command = [executable, "-enc", "UTF-8", "-layout", str(path), "-"]
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": PDF_TIMEOUT_SECONDS,
        "check": False,
    }
    if sys.platform.startswith("win") and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(command, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"PDF 文本提取超过 {PDF_TIMEOUT_SECONDS} 秒，已终止；原 PDF 未修改。"
        ) from exc
    except OSError as exc:
        raise ValueError(f"无法启动 pdftotext：{exc}；原 PDF 未修改。") from exc
    if completed.returncode != 0:
        stderr = completed.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        detail = re.sub(r"\s+", " ", str(stderr or "")).strip()[:500]
        raise ValueError(
            f"pdftotext 提取失败（退出码 {completed.returncode}）"
            + (f"：{detail}" if detail else "")
            + "；原 PDF 未修改。"
        )
    stdout = completed.stdout
    if isinstance(stdout, str):
        return stdout
    return bytes(stdout or b"").decode("utf-8-sig", errors="replace")


def strip_unbalanced_trailing_doi_punctuation(value: str) -> str:
    value = value.strip().rstrip(".,;:?!\"'")
    pairs = (("(", ")"), ("[", "]"), ("{", "}"))
    changed = True
    while changed and value:
        changed = False
        for opening, closing in pairs:
            if value.endswith(closing) and value.count(closing) > value.count(opening):
                value = value[:-1].rstrip()
                changed = True
    return value


def normalize_doi(value: str) -> str:
    if not value:
        return ""
    value = html.unescape(urllib.parse.unquote(value)).strip()
    value = re.sub(r"(?i)^\s*(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)", "", value)
    match = DOI_RE.search(value)
    if not match:
        return ""
    return strip_unbalanced_trailing_doi_punctuation(match.group(0)).lower()


def first_doi(value: str) -> str:
    match = DOI_RE.search(value or "")
    return normalize_doi(match.group(0)) if match else ""


def clean_tex(value: str) -> str:
    value = value.replace("~", " ")
    value = re.sub(r"\\(?:url|doi)\s*\{([^{}]*)\}", r"\1", value, flags=re.I)
    value = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", value)
    value = value.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", value).strip(" \t\r\n,;\"'")


def unwrap_bib_value(value: str) -> str:
    pieces = [piece.strip() for piece in re.split(r"\s*#\s*", value.strip()) if piece.strip()]
    cleaned: list[str] = []
    for piece in pieces or [value.strip()]:
        while len(piece) >= 2 and (
            (piece[0] == "{" and piece[-1] == "}")
            or (piece[0] == '"' and piece[-1] == '"')
        ):
            piece = piece[1:-1].strip()
        cleaned.append(piece)
    return clean_tex("".join(cleaned))


def split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"' and depth == 0:
            quote = not quote
        elif not quote:
            if char == "{":
                depth += 1
            elif char == "}" and depth:
                depth -= 1
            elif char == delimiter and depth == 0:
                parts.append(value[start:index])
                start = index + 1
    parts.append(value[start:])
    return parts


def parse_bibtex(content: str, source: str) -> list[BibliographicEntry]:
    entries: list[BibliographicEntry] = []
    start_re = re.compile(r"@([A-Za-z]+)\s*([({])")
    position = 0
    while True:
        match = start_re.search(content, position)
        if not match:
            break
        entry_type = match.group(1).lower()
        opening = match.group(2)
        closing = "}" if opening == "{" else ")"
        depth, quote, escaped = 1, False, False
        index = match.end()
        while index < len(content) and depth:
            char = content[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"' and opening == "(":
                quote = not quote
            elif not quote:
                if char == opening:
                    depth += 1
                elif char == closing:
                    depth -= 1
            index += 1
        if depth:
            break
        body = content[match.end() : index - 1]
        position = index
        if entry_type in {"comment", "preamble", "string"}:
            continue
        pieces = split_top_level(body)
        key = pieces[0].strip() if pieces else ""
        fields: dict[str, str] = {}
        for piece in pieces[1:]:
            if "=" in piece:
                name, raw_value = piece.split("=", 1)
                fields[name.strip().lower()] = unwrap_bib_value(raw_value)
        doi = normalize_doi(fields.get("doi", "")) or first_doi(
            " ".join((fields.get("url", ""), fields.get("note", "")))
        )
        author_text = fields.get("author", "")
        authors = [clean_tex(author) for author in re.split(r"\s+and\s+", author_text, flags=re.I)]
        year_match = YEAR_RE.search(fields.get("year", ""))
        entries.append(
            BibliographicEntry(
                key=key,
                entry_type=entry_type,
                doi=doi,
                title=fields.get("title", ""),
                authors=[author for author in authors if author],
                year=year_match.group(1) if year_match else "",
                container=fields.get("journal", "") or fields.get("booktitle", ""),
                volume=fields.get("volume", ""),
                issue=fields.get("number", "") or fields.get("issue", ""),
                pages=fields.get("pages", ""),
                publisher=fields.get("publisher", ""),
                url=fields.get("url", ""),
                source=source,
                line=content.count("\n", 0, match.start()) + 1,
                extraction="bibtex",
            )
        )
    return entries


def infer_text_metadata(fragment: str, source: str, line: int, key: str = "") -> BibliographicEntry:
    plain = clean_tex(re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", fragment))
    doi = first_doi(plain)
    without_url = re.sub(r"(?i)https?://\S+|doi\s*:\s*\S+", " ", plain)
    year_match = YEAR_RE.search(without_url)
    year = year_match.group(1) if year_match else ""
    author_part = without_url[: year_match.start()] if year_match else ""
    author_part = author_part.strip(" .,(;:")[-400:]
    authors = [part.strip() for part in re.split(r"\s+and\s+|\s*;\s*", author_part, flags=re.I)]
    authors = [part for part in authors if 1 < len(part) < 160]
    title = ""
    quoted = re.search(r"[\"“]([^\"”]{12,350})[\"”]", without_url)
    if quoted:
        title = quoted.group(1).strip()
    elif year_match:
        tail = without_url[year_match.end() :].lstrip(" ).,;:")
        for candidate in (part.strip() for part in re.split(r"\.\s+", tail)):
            words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", candidate)
            if len(words) >= 4 and not candidate.lower().startswith(("http", "vol", "doi")):
                title = candidate[:500]
                break
    return BibliographicEntry(
        key=key,
        doi=doi,
        title=title,
        authors=authors,
        year=year,
        source=source,
        line=line,
        extraction="text-heuristic",
    )


def _reference_fragments(text: str, start_line: int) -> Iterable[tuple[str, int]]:
    lines = text.splitlines()
    current: list[str] = []
    current_line = start_line
    numbered = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+")

    def flush() -> tuple[str, int] | None:
        nonlocal current
        if not current:
            return None
        result = (" ".join(piece.strip() for piece in current), current_line)
        current = []
        return result

    for offset, line in enumerate(lines):
        line_no = start_line + offset
        if not line.strip():
            item = flush()
            if item:
                yield item
            continue
        if numbered.match(line) or (current and YEAR_RE.search(line) and YEAR_RE.search(" ".join(current))):
            item = flush()
            if item:
                yield item
            current_line = line_no
        elif not current:
            current_line = line_no
        current.append(line)
    item = flush()
    if item:
        yield item


def parse_text_references(content: str, source: str) -> list[BibliographicEntry]:
    entries: list[BibliographicEntry] = []
    seen_dois: set[str] = set()
    bib_env = re.search(
        r"(?is)\\begin\{thebibliography\}.*?\n(.*?)\\end\{thebibliography\}", content
    )
    if bib_env:
        body = bib_env.group(1)
        item_re = re.compile(r"(?is)\\bibitem(?:\[[^\]]*\])?\{([^{}]+)\}(.*?)(?=\\bibitem|\Z)")
        for item in item_re.finditer(body):
            absolute = bib_env.start(1) + item.start()
            entry = infer_text_metadata(
                item.group(2), source, content.count("\n", 0, absolute) + 1, item.group(1)
            )
            entries.append(entry)
            if entry.doi:
                seen_dois.add(entry.doi)
    heading = REFERENCE_HEADING_RE.search(content)
    if heading:
        tail = content[heading.end() :]
        start_line = content.count("\n", 0, heading.end()) + 1
        stop = re.search(
            r"(?im)^\s*(?:#{1,3}\s*)?(appendix|supplementary material|附录)\b.*$", tail
        )
        if stop:
            tail = tail[: stop.start()]
        for fragment, line in _reference_fragments(tail, start_line):
            if len(fragment) < 12 or not (YEAR_RE.search(fragment) or DOI_RE.search(fragment)):
                continue
            entry = infer_text_metadata(fragment, source, line)
            if entry.doi and entry.doi in seen_dois:
                continue
            entries.append(entry)
            if entry.doi:
                seen_dois.add(entry.doi)
    for line_no, line in enumerate(content.splitlines(), 1):
        for match in DOI_RE.finditer(line):
            doi = normalize_doi(match.group(0))
            if doi in seen_dois:
                continue
            entry = infer_text_metadata(line, source, line_no)
            entry.doi = doi
            entries.append(entry)
            seen_dois.add(doi)
    return entries


def strip_tex_comments_preserve_lines(content: str) -> str:
    cleaned: list[str] = []
    for line in content.splitlines(keepends=True):
        cut = len(line)
        for index, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                cut = index
                break
        suffix = "\n" if line.endswith("\n") else ""
        cleaned.append(line[:cut].rstrip("\r\n") + suffix)
    return "".join(cleaned)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def discover_tex_bibliographies(content: str, tex_path: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    cleaned = strip_tex_comments_preserve_lines(content)
    command_re = re.compile(
        r"\\(?P<command>bibliography|addbibresource)(?:\s*\[[^\]]*\])?\s*\{(?P<value>[^{}]+)\}",
        re.I,
    )
    project_root = tex_path.parent.resolve()
    found: list[Path] = []
    diagnostics: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for match in command_re.finditer(cleaned):
        command = match.group("command").lower()
        values = match.group("value").split(",") if command == "bibliography" else [match.group("value")]
        line = cleaned.count("\n", 0, match.start()) + 1
        for raw_value in values:
            raw_name = raw_value.strip()
            if not raw_name:
                continue
            if "\\" in raw_name or any(char in raw_name for char in "*?\x00") or re.match(r"^[A-Za-z]+:", raw_name):
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "unsafe-bibliography-reference",
                        "source": str(tex_path),
                        "line": line,
                        "reference": raw_name,
                        "message": "外部书目引用包含宏、URI、通配符或不安全字符，未读取。",
                    }
                )
                continue
            relative = Path(raw_name)
            if relative.is_absolute():
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "absolute-bibliography-reference",
                        "source": str(tex_path),
                        "line": line,
                        "reference": raw_name,
                        "message": "绝对路径书目引用未读取；仅允许项目根目录下的相对路径。",
                    }
                )
                continue
            if not relative.suffix:
                relative = relative.with_suffix(".bib")
            elif relative.suffix.lower() != ".bib":
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "unsupported-bibliography-extension",
                        "source": str(tex_path),
                        "line": line,
                        "reference": raw_name,
                        "message": "外部书目不是 .bib 文件，未读取。",
                    }
                )
                continue
            candidate = (project_root / relative).resolve(strict=False)
            if not _path_is_within(candidate, project_root):
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "bibliography-outside-project-root",
                        "source": str(tex_path),
                        "line": line,
                        "reference": raw_name,
                        "message": "书目路径越出主 TeX 项目根目录，已跳过。",
                    }
                )
                continue
            if not candidate.is_file():
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "bibliography-file-not-found",
                        "source": str(tex_path),
                        "line": line,
                        "reference": raw_name,
                        "message": "声明的外部 .bib 文件不存在；仅记录提取诊断，不作为文献缺陷。",
                    }
                )
                continue
            if candidate not in seen:
                found.append(candidate)
                seen.add(candidate)
    return found, diagnostics


def _entry_identity(entry: BibliographicEntry) -> tuple[str, ...]:
    if entry.doi:
        return ("doi", entry.doi)
    normalized_title = normalize_text(entry.title)
    if normalized_title and entry.year:
        return ("title-year", normalized_title, entry.year)
    return ("source-key", entry.source.lower(), entry.key.lower())


def merge_entries(groups: Iterable[Iterable[BibliographicEntry]]) -> list[BibliographicEntry]:
    merged: list[BibliographicEntry] = []
    seen: set[tuple[str, ...]] = set()
    for group in groups:
        for entry in group:
            identity = _entry_identity(entry)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(entry)
    return merged


def _extract_bundle(
    path: Path,
) -> tuple[list[BibliographicEntry], list[dict[str, Any]], set[Path]]:
    path = path.resolve(strict=True)
    suffix = path.suffix.lower()
    diagnostics: list[dict[str, Any]] = []
    source_paths: set[Path] = {path}
    if suffix == ".docx":
        content = read_docx_text(path)
    elif suffix == ".pdf":
        content = read_pdf_text(path)
        if not content.strip():
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "pdf-text-empty",
                    "source": str(path),
                    "line": None,
                    "reference": "",
                    "message": "pdftotext 未提取到可读文本；原 PDF 未修改。",
                }
            )
    elif suffix in {".bib", ".txt", ".md", ".tex", ".latex", ".rst"} or not suffix:
        content = read_text(path)
    else:
        raise ValueError(
            f"暂不支持格式 {suffix or '(无扩展名)'}；请提供 .bib、.tex、.md、.txt、.docx 或 .pdf。"
        )
    if suffix == ".bib":
        entries = parse_bibtex(content, str(path))
    else:
        groups: list[list[BibliographicEntry]] = [parse_text_references(content, str(path))]
        if suffix in {".tex", ".latex"}:
            bib_paths, found_diagnostics = discover_tex_bibliographies(content, path)
            diagnostics.extend(found_diagnostics)
            for bib_path in bib_paths:
                source_paths.add(bib_path.resolve(strict=True))
                try:
                    groups.append(parse_bibtex(read_text(bib_path), str(bib_path)))
                except (OSError, ValueError) as exc:
                    diagnostics.append(
                        {
                            "level": "warning",
                            "code": "bibliography-file-unreadable",
                            "source": str(path),
                            "line": None,
                            "reference": str(bib_path),
                            "message": f"外部 .bib 文件无法读取：{exc}",
                        }
                    )
        entries = merge_entries(groups)
    for index, entry in enumerate(entries, 1):
        if not entry.key:
            entry.key = f"ref-{index:03d}"
    return entries, diagnostics, source_paths


def extract_entries_with_diagnostics(path: Path) -> tuple[list[BibliographicEntry], list[dict[str, Any]]]:
    entries, diagnostics, _ = _extract_bundle(path)
    return entries, diagnostics


def extract_entries(path: Path) -> list[BibliographicEntry]:
    return extract_entries_with_diagnostics(path)[0]


def default_transport(url: str, headers: Mapping[str, str], timeout: float) -> FetchResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        raw, status, final_url = exc.read(), int(exc.code), exc.geturl()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NetworkFailure(str(exc)) from exc
    data: Any = None
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if 200 <= status < 300:
                raise NetworkFailure(f"无法解析 JSON 响应：{exc}") from exc
    return FetchResponse(status=status, data=data, raw=raw, url=final_url)


def _query(
    url: str,
    source: str,
    transport: Transport,
    headers: Mapping[str, str],
    timeout: float,
) -> tuple[FetchResponse | None, QueryAttempt]:
    queried_at = utc_now()
    try:
        response = transport(url, headers, timeout)
        if not response.raw and response.data is not None:
            response.raw = json.dumps(response.data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return response, QueryAttempt(
            source=source,
            url=response.url or url,
            queried_at=queried_at,
            http_status=response.status,
            response_sha256=sha256_bytes(response.raw) if response.raw else "",
        )
    except Exception as exc:
        return None, QueryAttempt(source=source, url=url, queried_at=queried_at, error=str(exc))


def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def _crossref_year(message: Mapping[str, Any]) -> str:
    for field_name in ("issued", "published-print", "published-online", "published", "created"):
        value = message.get(field_name)
        if not isinstance(value, Mapping):
            continue
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            return str(parts[0][0])
        if field_name == "created" and value.get("date-time"):
            match = YEAR_RE.search(str(value["date-time"]))
            if match:
                return match.group(1)
    return ""


def _crossref_updates(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for field_name in ("update-to", "updated-by"):
        values = message.get(field_name, [])
        if isinstance(values, Mapping):
            values = [values]
        if isinstance(values, list):
            for value in values:
                if isinstance(value, Mapping):
                    updates.append({"direction": field_name, **dict(value)})
    relation = message.get("relation", {})
    if isinstance(relation, Mapping):
        for rel_type, rel_values in relation.items():
            lowered = str(rel_type).lower().replace("_", "-")
            if any(term in lowered for term in UPDATE_TERMS):
                updates.append({"direction": str(rel_type), "records": rel_values})
    record_type = " ".join(str(message.get(name, "")) for name in ("type", "subtype")).lower()
    if any(term in record_type for term in ("retract", "withdraw", "correction", "expression-of-concern")):
        updates.append({"direction": "record-type", "type": record_type.strip()})
    return updates


def crossref_metadata(message: Mapping[str, Any]) -> dict[str, Any]:
    authors: list[str] = []
    raw_authors = message.get("author", [])
    for author in raw_authors if isinstance(raw_authors, list) else []:
        if not isinstance(author, Mapping):
            continue
        name = " ".join(str(author.get(part, "")).strip() for part in ("given", "family")).strip()
        name = name or str(author.get("name", "")).strip()
        if name:
            authors.append(name)
    return {
        "doi": normalize_doi(str(message.get("DOI", ""))),
        "title": clean_tex(_first(message.get("title"))),
        "authors": authors,
        "year": _crossref_year(message),
        "container": clean_tex(_first(message.get("container-title"))),
        "volume": str(message.get("volume", "") or ""),
        "issue": str(message.get("issue", "") or ""),
        "pages": str(message.get("page", "") or ""),
        "publisher": str(message.get("publisher", "") or ""),
        "url": str(message.get("URL", "") or ""),
        "updates": _crossref_updates(message),
        "agency": "Crossref",
    }


def datacite_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    attributes = record.get("attributes", record)
    if not isinstance(attributes, Mapping):
        attributes = {}
    titles = attributes.get("titles", [])
    title = ""
    if isinstance(titles, list) and titles:
        first = titles[0]
        title = str(first.get("title", "")) if isinstance(first, Mapping) else str(first)
    creators = attributes.get("creators", [])
    authors: list[str] = []
    if isinstance(creators, list):
        for creator in creators:
            if not isinstance(creator, Mapping):
                continue
            name = str(creator.get("name", "")).strip()
            name = name or " ".join(
                str(creator.get(part, "")).strip() for part in ("givenName", "familyName")
            ).strip()
            if name:
                authors.append(name)
    related = attributes.get("relatedIdentifiers", [])
    updates: list[dict[str, Any]] = []
    if isinstance(related, list):
        for relation in related:
            if not isinstance(relation, Mapping):
                continue
            normalized = str(relation.get("relationType", "")).lower().replace("_", "-")
            if any(term in normalized for term in UPDATE_TERMS):
                updates.append(dict(relation))
    container_obj = attributes.get("container", {})
    container = str(container_obj.get("title", "")) if isinstance(container_obj, Mapping) else ""
    return {
        "doi": normalize_doi(str(attributes.get("doi", "") or record.get("id", ""))),
        "title": clean_tex(title),
        "authors": authors,
        "year": str(attributes.get("publicationYear", "") or ""),
        "container": container,
        "volume": str(container_obj.get("volume", "") if isinstance(container_obj, Mapping) else ""),
        "issue": str(container_obj.get("issue", "") if isinstance(container_obj, Mapping) else ""),
        "pages": "",
        "publisher": str(attributes.get("publisher", "") or ""),
        "url": str(attributes.get("url", "") or ""),
        "updates": updates,
        "agency": "DataCite",
    }


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def surname(name: str) -> str:
    name = clean_tex(name)
    if not name:
        return ""
    if "," in name:
        candidate = name.split(",", 1)[0]
    else:
        tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]+", name)
        candidate = tokens[-1] if tokens else name
    return normalize_text(candidate).replace(" ", "")


def author_similarity(left: Sequence[str], right: Sequence[str]) -> float | None:
    left_set = {surname(name) for name in left if surname(name)}
    right_set = {surname(name) for name in right if surname(name)}
    if not left_set or not right_set:
        return None
    return len(left_set & right_set) / len(left_set | right_set)


def title_similarity(left: str, right: str) -> float | None:
    left_norm, right_norm = normalize_text(left), normalize_text(right)
    if not left_norm or not right_norm:
        return None
    return round(SequenceMatcher(None, left_norm, right_norm).ratio(), 4)


def compare_metadata(
    entry: BibliographicEntry, resolved: Mapping[str, Any]
) -> tuple[dict[str, Any], bool, list[str]]:
    comparison: dict[str, Any] = {}
    conflict = False
    warnings: list[str] = []
    returned_doi = normalize_doi(str(resolved.get("doi", "")))
    if entry.doi:
        matched = entry.doi == returned_doi
        comparison["doi"] = {"input": entry.doi, "returned": returned_doi, "match": matched}
        if returned_doi and not matched:
            conflict = True
        elif not returned_doi:
            warnings.append("resolved_doi_missing")
    else:
        comparison["doi"] = {"input": "", "returned": returned_doi, "match": None}
    returned_title = str(resolved.get("title", ""))
    title_score = title_similarity(entry.title, returned_title)
    comparison["title"] = {
        "input": entry.title,
        "returned": returned_title,
        "similarity": title_score,
    }
    if entry.title and not returned_title:
        warnings.append("resolved_title_missing")
    elif title_score is not None and title_score < 0.72:
        conflict = True
    elif title_score is not None and title_score < 0.90:
        warnings.append("title_similarity_below_preferred")
    returned_authors = [str(value) for value in resolved.get("authors", [])]
    author_score = author_similarity(entry.authors, returned_authors)
    comparison["authors"] = {
        "input": entry.authors,
        "returned": returned_authors,
        "surname_jaccard": None if author_score is None else round(author_score, 4),
    }
    if entry.authors and not returned_authors:
        warnings.append("resolved_authors_missing")
    elif author_score is not None and author_score < 0.45:
        conflict = True
    elif author_score is not None and author_score < 0.70:
        warnings.append("partial_author_match")
    returned_year = str(resolved.get("year", ""))
    year_match: bool | None = None
    year_difference: int | None = None
    if entry.year and not returned_year:
        warnings.append("resolved_year_missing")
    elif entry.year and returned_year and entry.year.isdigit() and returned_year.isdigit():
        year_difference = abs(int(entry.year) - int(returned_year))
        year_match = year_difference == 0
        if year_difference > 1:
            conflict = True
        elif year_difference == 1:
            warnings.append("publication_year_differs_by_one")
    comparison["year"] = {
        "input": entry.year,
        "returned": returned_year,
        "match": year_match,
        "difference": year_difference,
    }
    return comparison, conflict, warnings


def candidate_score(entry: BibliographicEntry, resolved: Mapping[str, Any]) -> float:
    weighted: list[tuple[float, float]] = []
    title_score = title_similarity(entry.title, str(resolved.get("title", "")))
    if title_score is not None:
        weighted.append((0.7, title_score))
    author_score = author_similarity(entry.authors, [str(a) for a in resolved.get("authors", [])])
    if author_score is not None:
        weighted.append((0.2, author_score))
    resolved_year = str(resolved.get("year", ""))
    if entry.year and resolved_year and entry.year.isdigit() and resolved_year.isdigit():
        difference = abs(int(entry.year) - int(resolved_year))
        weighted.append((0.1, 1.0 if difference == 0 else 0.6 if difference == 1 else 0.0))
    if not weighted:
        return 0.0
    return round(sum(weight * score for weight, score in weighted) / sum(weight for weight, _ in weighted), 4)


def _crossref_exact_url(doi: str, mailto: str = "") -> str:
    url = f"{CROSSREF_BASE}/works/{urllib.parse.quote(doi, safe='')}"
    return url + ("?" + urllib.parse.urlencode({"mailto": mailto}) if mailto else "")


def _datacite_exact_url(doi: str) -> str:
    return f"{DATACITE_BASE}/dois/{urllib.parse.quote(doi, safe='')}"


def _crossref_search_url(entry: BibliographicEntry, mailto: str = "") -> str:
    params: list[tuple[str, str]] = [("query.title", entry.title), ("rows", "3")]
    if entry.authors:
        params.append(("query.author", surname(entry.authors[0]) or entry.authors[0][:80]))
    if entry.year:
        params.append(("filter", f"from-pub-date:{entry.year}-01-01,until-pub-date:{entry.year}-12-31"))
    if mailto:
        params.append(("mailto", mailto))
    return f"{CROSSREF_BASE}/works?{urllib.parse.urlencode(params)}"


def _datacite_search_url(entry: BibliographicEntry) -> str:
    terms = [entry.title]
    if entry.authors:
        terms.append(surname(entry.authors[0]) or entry.authors[0][:80])
    if entry.year:
        terms.append(entry.year)
    return f"{DATACITE_BASE}/dois?{urllib.parse.urlencode({'query': ' '.join(terms), 'page[size]': '3'})}"


def _extract_crossref_exact(response: FetchResponse) -> dict[str, Any] | None:
    if response.status != 200 or not isinstance(response.data, Mapping):
        return None
    message = response.data.get("message")
    return crossref_metadata(message) if isinstance(message, Mapping) else None


def _extract_datacite_exact(response: FetchResponse) -> dict[str, Any] | None:
    if response.status != 200 or not isinstance(response.data, Mapping):
        return None
    data = response.data.get("data")
    return datacite_metadata(data) if isinstance(data, Mapping) else None


def _crossref_candidates(response: FetchResponse) -> list[dict[str, Any]]:
    if response.status != 200 or not isinstance(response.data, Mapping):
        return []
    message = response.data.get("message")
    items = message.get("items", []) if isinstance(message, Mapping) else []
    return [crossref_metadata(item) for item in items if isinstance(item, Mapping)]


def _datacite_candidates(response: FetchResponse) -> list[dict[str, Any]]:
    if response.status != 200 or not isinstance(response.data, Mapping):
        return []
    data = response.data.get("data", [])
    return [datacite_metadata(item) for item in data if isinstance(item, Mapping)] if isinstance(data, list) else []


def _base_result() -> dict[str, Any]:
    return {
        "status": "verification_unavailable",
        "reason": "not_started",
        "status_note": STATUS_EXPLANATIONS["verification_unavailable"],
        "warnings": [],
        "resolved_metadata": {},
        "comparison": {},
        "updates": [],
        "queries": [],
        "claim_support": {
            "status": "not_assessed",
            "note": "元数据核验不能判断该来源是否支持论文中的具体观点；需要来源全文或出版方直接证据。",
        },
    }


def verify_entry(
    entry: BibliographicEntry,
    transport: Transport = default_transport,
    *,
    offline: bool = False,
    unavailable_reason: str = "",
    timeout: float = 15.0,
    mailto: str = "",
    allow_title_search: bool = True,
) -> dict[str, Any]:
    attempts: list[QueryAttempt] = []
    result = _base_result()
    if offline:
        reason = unavailable_reason or "offline"
        result.update(
            reason=reason,
            status_note=(
                "隐私配置禁止书目元数据查询，未发送任何网络请求。"
                if reason == "privacy_disabled"
                else "离线模式：仅提取书目信息，未发送任何网络请求。"
            ),
        )
        return result
    headers = {
        "Accept": "application/json",
        "User-Agent": "paper-auditor/0.3 (bibliographic metadata verification)",
    }
    resolved: dict[str, Any] | None = None
    if entry.doi:
        response, attempt = _query(
            _crossref_exact_url(entry.doi, mailto), "Crossref", transport, headers, timeout
        )
        attempts.append(attempt)
        resolved = _extract_crossref_exact(response) if response else None
        if not resolved:
            fallback, attempt = _query(
                _datacite_exact_url(entry.doi), "DataCite", transport, headers, timeout
            )
            attempts.append(attempt)
            resolved = _extract_datacite_exact(fallback) if fallback else None
        if not resolved:
            statuses = [attempt.http_status for attempt in attempts]
            has_network_error = any(
                attempt.error
                or attempt.http_status == 429
                or (attempt.http_status is not None and attempt.http_status >= 500)
                for attempt in attempts
            )
            if not has_network_error and statuses and all(status == 404 for status in statuses):
                result.update(
                    status="not_found",
                    reason="no_record_found",
                    status_note=STATUS_EXPLANATIONS["not_found"],
                )
            else:
                result.update(
                    status="verification_unavailable",
                    reason="network_error",
                    status_note=STATUS_EXPLANATIONS["verification_unavailable"],
                )
            result["queries"] = [asdict(item) for item in attempts]
            return result
    else:
        if not allow_title_search:
            result.update(reason="title_search_disabled", status_note="无 DOI，且题名检索已禁用。")
            return result
        if len(normalize_text(entry.title)) < 12:
            result.update(reason="metadata_insufficient", status_note="没有 DOI，且题名元数据不足以安全检索。")
            return result
        candidates: list[dict[str, Any]] = []
        response, attempt = _query(
            _crossref_search_url(entry, mailto), "Crossref", transport, headers, timeout
        )
        attempts.append(attempt)
        if response:
            candidates.extend(_crossref_candidates(response))
        crossref_best = max((candidate_score(entry, item) for item in candidates), default=0.0)
        if crossref_best < 0.78:
            fallback, attempt = _query(
                _datacite_search_url(entry), "DataCite", transport, headers, timeout
            )
            attempts.append(attempt)
            if fallback:
                candidates.extend(_datacite_candidates(fallback))
        ranked = sorted(
            ((candidate_score(entry, item), item) for item in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked:
            has_network_error = any(
                attempt.error
                or attempt.http_status == 429
                or (attempt.http_status is not None and attempt.http_status >= 500)
                for attempt in attempts
            )
            status = "verification_unavailable" if has_network_error else "not_found"
            reason = "network_error" if has_network_error else "no_adequate_match"
            result.update(status=status, reason=reason, status_note=STATUS_EXPLANATIONS[status])
            result["queries"] = [asdict(item) for item in attempts]
            return result
        best_score, resolved = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        result["candidate_scores"] = [
            {"doi": item.get("doi", ""), "title": item.get("title", ""), "score": score}
            for score, item in ranked[:3]
        ]
        if best_score < 0.60:
            result.update(
                status="not_found",
                reason="no_adequate_match",
                status_note=STATUS_EXPLANATIONS["not_found"],
            )
            result["queries"] = [asdict(item) for item in attempts]
            return result
        if best_score < 0.78 or best_score - runner_up < 0.06:
            result.update(
                status="ambiguous",
                reason="candidate_separation_insufficient",
                status_note=STATUS_EXPLANATIONS["ambiguous"],
                resolved_metadata=resolved,
                queries=[asdict(item) for item in attempts],
            )
            return result
    assert resolved is not None
    comparison, conflict, warnings = compare_metadata(entry, resolved)
    updates = list(resolved.get("updates", []))
    if updates:
        status, reason = "retracted_or_updated", "update_relation_detected"
    elif conflict:
        status, reason = "identifier_conflict", "metadata_conflict"
    elif warnings:
        status, reason = "verified_with_warnings", "non_substantive_difference"
    else:
        status, reason = "verified", "metadata_match"
    result.update(
        status=status,
        reason=reason,
        status_note=STATUS_EXPLANATIONS[status],
        warnings=warnings,
        resolved_metadata=resolved,
        comparison=comparison,
        updates=updates,
        queries=[asdict(item) for item in attempts],
    )
    return result


def entry_to_dict(entry: BibliographicEntry) -> dict[str, Any]:
    return {
        "key": entry.key,
        "entry_type": entry.entry_type,
        "doi": entry.doi,
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "container": entry.container,
        "volume": entry.volume,
        "issue": entry.issue,
        "pages": entry.pages,
        "publisher": entry.publisher,
        "url": entry.url,
        "location": {"source": entry.source, "line": entry.line},
        "extraction": entry.extraction,
    }


def load_profile(path: Path | None) -> dict[str, Any]:
    if path is None:
        path = Path(__file__).resolve().parent.parent / "references" / "personal-profile.json"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}


def verify_file(
    input_path: Path,
    *,
    transport: Transport = default_transport,
    offline: bool = False,
    timeout: float = 15.0,
    mailto: str = "",
    allow_title_search: bool = True,
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    input_path = input_path.resolve(strict=True)
    entries, extraction_diagnostics, source_paths = _extract_bundle(input_path)
    privacy = dict((profile or {}).get("privacy", {}))
    metadata_allowed = bool(privacy.get("allow_bibliographic_metadata_queries", True))
    effective_offline = offline or not metadata_allowed
    unavailable_reason = "offline" if offline else "privacy_disabled" if not metadata_allowed else ""
    if not mailto:
        mailto = str(privacy.get("crossref_mailto", "") or "")
    results: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, 1):
        verification = verify_entry(
            entry,
            transport,
            offline=effective_offline,
            unavailable_reason=unavailable_reason,
            timeout=timeout,
            mailto=mailto,
            allow_title_search=allow_title_search,
        )
        results.append(
            {"id": f"REF-{index:03d}", "input_metadata": entry_to_dict(entry), **verification}
        )
    counts = Counter(item["status"] for item in results)
    mode = "offline" if offline else "privacy-disabled" if not metadata_allowed else "online-metadata-only"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "pass_id": "citation_integrity",
        "input": {
            "path": str(input_path),
            "sha256": sha256_bytes(input_path.read_bytes()),
            "entry_count": len(entries),
            "source_files": sorted(str(path) for path in source_paths),
        },
        "mode": mode,
        "privacy": {
            "sent_fields": [] if effective_offline else ["DOI or minimum title/first-author/year metadata"],
            "manuscript_full_text_sent": False,
            "citation_context_sent": False,
            "figures_sent": False,
        },
        "status_definitions": STATUS_EXPLANATIONS,
        "summary": {status: counts.get(status, 0) for status in STATUS_EXPLANATIONS},
        "extraction_diagnostics": extraction_diagnostics,
        "entries": results,
        "limitations": [
            "not_found 仅表示本次数据源未找到足够匹配，不能据此断言文献伪造。",
            "本报告不判断文献是否支持论文中的具体观点；该判断需要来源全文或出版方直接证据。",
            "题名检索是启发式匹配；书籍、标准、报告、学位论文与灰色文献可能需要专门目录人工核验。",
        ],
    }


def _md_escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def render_report(data: Mapping[str, Any]) -> str:
    summary = data.get("summary", {})
    lines = [
        "# 参考文献元数据核验报告",
        "",
        f"- 生成时间：`{data.get('generated_at', '')}`",
        f"- 输入文件：`{data.get('input', {}).get('path', '')}`",
        f"- 运行模式：`{data.get('mode', '')}`",
        f"- 提取条目：{data.get('input', {}).get('entry_count', 0)}",
        "- 隐私：未发送原稿全文、引用上下文或图件；在线模式只发送 DOI 或最小题名/作者/年份元数据。",
        "",
        "> 重要：`not_found` 只表示本次查询未找到足够匹配，不是“文献伪造”的证据。元数据核验也不能判断来源是否支持论文中的具体观点。",
        "",
        "## 状态汇总",
        "",
        "| 状态 | 数量 | 含义 |",
        "|---|---:|---|",
    ]
    for status, explanation in STATUS_EXPLANATIONS.items():
        lines.append(f"| `{status}` | {summary.get(status, 0)} | {_md_escape(explanation)} |")
    diagnostics = data.get("extraction_diagnostics", [])
    if diagnostics:
        lines.extend(["", "## 提取诊断", ""])
        for diagnostic in diagnostics:
            location = f"{diagnostic.get('source', '')}:{diagnostic.get('line', '')}"
            lines.append(
                f"- `{diagnostic.get('code', '')}` · `{location}` · {diagnostic.get('message', '')}"
            )
        lines.append("")
    lines.extend(["", "## 条目明细", ""])
    entries = data.get("entries", [])
    if not entries:
        lines.extend(["未提取到可核验的参考文献条目。", ""])
    for item in entries:
        original = item.get("input_metadata", {})
        resolved = item.get("resolved_metadata", {})
        location = original.get("location", {})
        lines.extend(
            [
                f"### {item.get('id', '')} · `{item.get('status', '')}`",
                "",
                f"- 来源位置：`{location.get('source', '')}:{location.get('line', '')}`",
                f"- 引用键：`{original.get('key', '')}`",
                f"- 输入 DOI：`{original.get('doi', '') or '未提供'}`",
                f"- 输入题名：{original.get('title', '') or '未能可靠提取'}",
                f"- 原因代码：`{item.get('reason', '')}`",
                f"- 核验说明：{item.get('status_note', '')}",
            ]
        )
        if item.get("warnings"):
            lines.append(f"- 非实质警告：`{', '.join(item['warnings'])}`")
        if resolved:
            lines.extend(
                [
                    f"- 返回来源：{resolved.get('agency', '')}",
                    f"- 返回 DOI：`{resolved.get('doi', '')}`",
                    f"- 返回题名：{resolved.get('title', '')}",
                    f"- 返回作者：{'; '.join(resolved.get('authors', []))}",
                    f"- 返回年份：{resolved.get('year', '')}",
                ]
            )
        comparison = item.get("comparison", {})
        if comparison:
            title = comparison.get("title", {})
            authors = comparison.get("authors", {})
            year = comparison.get("year", {})
            lines.extend(
                [
                    f"- 题名相似度：{title.get('similarity', '未比较')}",
                    f"- 作者姓氏重合度：{authors.get('surname_jaccard', '未比较')}",
                    f"- 年份差：{year.get('difference', '未比较')}",
                ]
            )
        if item.get("updates"):
            lines.append(f"- 更新/撤稿关系：`{json.dumps(item['updates'], ensure_ascii=False)}`")
        if item.get("candidate_scores"):
            lines.append("- 候选：")
            for candidate in item["candidate_scores"]:
                lines.append(
                    f"  - `{candidate.get('doi', '')}` · score={candidate.get('score', '')} · {candidate.get('title', '')}"
                )
        lines.append("- 查询记录：")
        if item.get("queries"):
            for query in item["queries"]:
                suffix = (
                    f"HTTP {query.get('http_status')}"
                    if query.get("http_status") is not None
                    else query.get("error", "未请求")
                )
                lines.append(
                    f"  - {query.get('source', '')} · `{query.get('queried_at', '')}` · {suffix} · {query.get('url', '')}"
                )
        else:
            lines.append("  - 无（离线、隐私限制或元数据不足）")
        lines.extend(["- 观点支持性：未评估；须查阅来源全文或出版方直接证据。", ""])
    lines.extend(
        [
            "## 使用边界",
            "",
            "- 先人工复核 `identifier_conflict`、`ambiguous`、`verified_with_warnings` 与 `retracted_or_updated`。",
            "- 对 `not_found` 应改用出版社、图书馆目录、标准数据库或学位论文库继续查证，不得直接写成伪造。",
            "- 在投稿前重新检查撤稿、更正与更新状态，因为这些状态会随时间变化。",
            "",
        ]
    )
    return "\n".join(lines)


def _protected_paths_from_data(data: Mapping[str, Any]) -> set[Path]:
    protected: set[Path] = set()
    input_info = data.get("input", {})
    if not isinstance(input_info, Mapping):
        return protected
    values: list[Any] = [input_info.get("path")]
    source_files = input_info.get("source_files", [])
    if isinstance(source_files, list):
        values.extend(source_files)
    for value in values:
        if value:
            protected.add(Path(str(value)).resolve(strict=False))
    return protected


def write_outputs(
    data: Mapping[str, Any],
    output_dir: Path,
    *,
    force: bool = False,
    protected_paths: Iterable[Path] = (),
) -> tuple[Path, Path]:
    """Write both reports after collision checks; never overwrite an input source."""
    output_dir = output_dir.resolve(strict=False)
    json_path = (output_dir / "references.json").resolve(strict=False)
    report_path = (output_dir / "citation-report.md").resolve(strict=False)
    protected = _protected_paths_from_data(data)
    protected.update(Path(path).resolve(strict=False) for path in protected_paths)
    for target in (json_path, report_path):
        if target in protected:
            raise ValueError(f"拒绝写出：输出路径与输入源相同：{target}")
        if target.is_symlink():
            raise ValueError(f"拒绝写出到符号链接目标：{target}")
    existing = [target for target in (json_path, report_path) if target.exists()]
    if existing and not force:
        listed = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"输出文件已存在，未覆盖：{listed}。如确认替换，请使用 --force。")
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "w" if force else "x"
    with json_path.open(mode, encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    try:
        with report_path.open(mode, encoding="utf-8") as handle:
            handle.write(render_report(data))
    except Exception:
        if not force:
            try:
                json_path.unlink()
            except OSError:
                pass
        raise
    return json_path, report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="核验 .bib 或论文中的书目元数据；默认仅发送最小元数据且不覆盖已有报告。"
    )
    parser.add_argument("input", type=Path, help=".bib、.tex、.md、.txt、.docx 或 .pdf 文件")
    parser.add_argument("--output-dir", type=Path, required=True, help="单独的核验输出目录")
    parser.add_argument("--offline", action="store_true", help="只提取，不执行任何网络请求")
    parser.add_argument("--no-title-search", action="store_true", help="无 DOI 条目不发送题名/作者/年份检索")
    parser.add_argument("--profile", type=Path, help="个人配置 JSON；默认读取 Skill 自带配置")
    parser.add_argument("--mailto", default="", help="Crossref polite-pool 联系邮箱（可选）")
    parser.add_argument("--timeout", type=float, default=15.0, help="每次元数据请求超时秒数")
    parser.add_argument("--force", action="store_true", default=False, help="覆盖已有报告；永不覆盖输入源")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_path = args.input.resolve(strict=True)
        profile = load_profile(args.profile)
        data = verify_file(
            input_path,
            offline=args.offline,
            timeout=max(1.0, args.timeout),
            mailto=args.mailto,
            allow_title_search=not args.no_title_search,
            profile=profile,
        )
        json_path, report_path = write_outputs(
            data,
            args.output_dir,
            force=args.force,
            protected_paths=(input_path,),
        )
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"已写入：{json_path}")
    print(f"已写入：{report_path}")
    print("提示：not_found 不等于伪造；本脚本不判断来源是否支持论文中的具体观点。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
