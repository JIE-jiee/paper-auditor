#!/usr/bin/env python3
"""Deterministic quantitative-consistency checks for scholarly manuscripts.

The module is deliberately conservative: it emits a formal finding only when
the quantities being compared have explicit, compatible identities.  Missing
semantic context, unresolved formulae, and plot-reading tasks are returned as
review candidates instead of being presented as manuscript defects.

This first version is source-oriented.  It supports LaTeX, Markdown, and plain
text directly and exposes JSON-friendly output for later integration with
``audit_manuscript.py``.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "0.1.0"
DEFAULT_RELATIVE_TOLERANCE = Decimal("0.01")
DEFAULT_PERCENTAGE_POINT_TOLERANCE = Decimal("0.2")

# Dimension vectors use (mass, length, time).  Angle is kept separate because
# engineering manuscripts often distinguish rotation from a generic ratio.
DIMENSION_VECTORS: dict[str, tuple[int, int, int, int]] = {
    "dimensionless": (0, 0, 0, 0),
    "ratio": (0, 0, 0, 0),
    "mass": (1, 0, 0, 0),
    "length": (0, 1, 0, 0),
    "time": (0, 0, 1, 0),
    "frequency": (0, 0, -1, 0),
    "velocity": (0, 1, -1, 0),
    "acceleration": (0, 1, -2, 0),
    "force": (1, 1, -2, 0),
    "stress": (1, -1, -2, 0),
    "pressure": (1, -1, -2, 0),
    "stiffness": (1, 0, -2, 0),
    "moment": (1, 2, -2, 0),
    "density": (1, -3, 0, 0),
    "angle": (0, 0, 0, 1),
}


@dataclass(frozen=True)
class UnitDefinition:
    canonical: str
    dimension: str
    factor: Decimal

    @property
    def vector(self) -> tuple[int, int, int, int]:
        return DIMENSION_VECTORS[self.dimension]


def _unit(canonical: str, dimension: str, factor: str) -> UnitDefinition:
    return UnitDefinition(canonical, dimension, Decimal(factor))


# Factors convert a value to a coherent SI representation for comparison.
UNIT_ALIASES: dict[str, UnitDefinition] = {
    "%": _unit("%", "dimensionless", "0.01"),
    "N": _unit("N", "force", "1"),
    "kN": _unit("kN", "force", "1000"),
    "MN": _unit("MN", "force", "1000000"),
    "Pa": _unit("Pa", "stress", "1"),
    "kPa": _unit("kPa", "stress", "1000"),
    "MPa": _unit("MPa", "stress", "1000000"),
    "GPa": _unit("GPa", "stress", "1000000000"),
    "m": _unit("m", "length", "1"),
    "mm": _unit("mm", "length", "0.001"),
    "cm": _unit("cm", "length", "0.01"),
    "km": _unit("km", "length", "1000"),
    "s": _unit("s", "time", "1"),
    "ms": _unit("ms", "time", "0.001"),
    "Hz": _unit("Hz", "frequency", "1"),
    "kg": _unit("kg", "mass", "1"),
    "g_mass": _unit("g", "mass", "0.001"),
    "rad": _unit("rad", "angle", "1"),
    "deg": _unit("°", "angle", "0.017453292519943295"),
    "m/s": _unit("m/s", "velocity", "1"),
    "mm/s": _unit("mm/s", "velocity", "0.001"),
    "m/s^2": _unit("m/s²", "acceleration", "1"),
    "mm/s^2": _unit("mm/s²", "acceleration", "0.001"),
    "N/m": _unit("N/m", "stiffness", "1"),
    "N/mm": _unit("N/mm", "stiffness", "1000"),
    "kN/m": _unit("kN/m", "stiffness", "1000"),
    "kN/mm": _unit("kN/mm", "stiffness", "1000000"),
    "MN/m": _unit("MN/m", "stiffness", "1000000"),
    "N*m": _unit("N·m", "moment", "1"),
    "kN*m": _unit("kN·m", "moment", "1000"),
    "N/mm^2": _unit("N/mm²", "stress", "1000000"),
    "kN/m^2": _unit("kN/m²", "stress", "1000"),
    "kg/m^3": _unit("kg/m³", "density", "1"),
}


def _normalize_unit_key(value: str) -> str:
    value = value.strip().replace("~", "")
    wrapper = re.fullmatch(r"\\(?:mathrm|text)\s*\{\s*(.*?)\s*\}", value)
    if wrapper:
        value = wrapper.group(1)
    value = value.replace("\\,", "").replace("\\;", "")
    value = value.replace("\\cdot", "*").replace("\\times", "*")
    value = value.replace("·", "*").replace("⋅", "*").replace("×", "*")
    value = value.replace("²", "^2").replace("³", "^3")
    value = re.sub(r"\^\s*\{\s*([+-]?\d+)\s*\}", r"^\1", value)
    value = re.sub(r"\s+", "", value)
    if value == "°":
        return "deg"
    return value


def normalize_unit(value: str) -> UnitDefinition | None:
    """Return a unit definition without guessing ambiguous ``g`` usage."""

    key = _normalize_unit_key(value)
    if key == "g":
        return None
    return UNIT_ALIASES.get(key)


NUMBER_PATTERN = (
    r"[+\-−]?"
    r"(?:\d{1,3}(?:,\d{3})+(?:\.\d*)?|\d+(?:\.\d*)?|\.\d+)"
    r"(?:[eE][+\-]?\d+)?"
)


def parse_number(value: str) -> Decimal:
    cleaned = value.replace("−", "-").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc


def _alias_regex(alias: str) -> str:
    escaped = re.escape(alias)
    escaped = escaped.replace(r"\ ", r"\s*")
    return escaped


_RAW_UNIT_FORMS = {
    "%",
    "N",
    "kN",
    "MN",
    "Pa",
    "kPa",
    "MPa",
    "GPa",
    "m",
    "mm",
    "cm",
    "km",
    "s",
    "ms",
    "Hz",
    "kg",
    "g",
    "rad",
    "°",
    "m/s",
    "mm/s",
    "m/s^2",
    "m/s^{2}",
    "m/s²",
    "mm/s^2",
    "mm/s^{2}",
    "mm/s²",
    "N/m",
    "N/mm",
    "kN/m",
    "kN/mm",
    "MN/m",
    "N·m",
    "N\\cdot m",
    "kN·m",
    "kN\\cdot m",
    "N/mm^2",
    "N/mm^{2}",
    "N/mm²",
    "kN/m^2",
    "kN/m^{2}",
    "kN/m²",
    "kg/m^3",
    "kg/m^{3}",
    "kg/m³",
}
_UNIT_CORE_PATTERN = "(?:" + "|".join(
    _alias_regex(item) for item in sorted(_RAW_UNIT_FORMS, key=lambda item: (-len(item), item))
) + ")"
UNIT_PATTERN = rf"(?:\\(?:mathrm|text)\s*\{{\s*)?{_UNIT_CORE_PATTERN}(?:\s*\}})?"
VALUE_UNIT_RE = re.compile(
    rf"(?<![\w.])(?P<value>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})(?![A-Za-z])"
)


@dataclass(frozen=True)
class QuantityProfileEntry:
    canonical_symbol: str
    aliases: tuple[str, ...]
    meaning: str
    dimension: str
    canonical_unit: str
    scope: str
    require_definition: bool


def normalize_symbol(value: str) -> str:
    value = value.strip().strip("$")
    value = re.sub(r"\s+", "", value)
    value = value.replace("\\left", "").replace("\\right", "")
    value = re.sub(r"\\(?:mathrm|text)\{([^{}]+)\}", r"\1", value)
    value = re.sub(r"\{([^{}]+)\}", r"\1", value)
    value = value.replace("\\", "")
    value = value.replace("^", "^")
    return value


def load_quantity_profile(path: str | Path) -> list[QuantityProfileEntry]:
    profile_path = Path(path)
    lines = [
        line
        for line in profile_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return []
    rows = csv.DictReader(lines, delimiter="\t")
    required = {
        "canonical_symbol",
        "aliases",
        "meaning",
        "dimension",
        "canonical_unit",
        "scope",
        "require_definition",
    }
    if rows.fieldnames is None or not required.issubset(rows.fieldnames):
        missing = sorted(required - set(rows.fieldnames or []))
        raise ValueError(f"quantity profile missing columns: {', '.join(missing)}")
    entries: list[QuantityProfileEntry] = []
    for row in rows:
        canonical = row["canonical_symbol"].strip()
        if not canonical:
            continue
        dimension = row["dimension"].strip().casefold()
        if dimension and dimension not in DIMENSION_VECTORS:
            raise ValueError(f"unknown dimension {dimension!r} for {canonical!r}")
        canonical_unit = row["canonical_unit"].strip()
        if canonical_unit:
            unit_definition = normalize_unit(canonical_unit)
            if unit_definition is None:
                raise ValueError(f"unknown or ambiguous canonical unit {canonical_unit!r}")
            if dimension and unit_definition.vector != DIMENSION_VECTORS[dimension]:
                raise ValueError(
                    f"canonical unit {canonical_unit!r} conflicts with dimension {dimension!r}"
                )
        flag = row["require_definition"].strip().casefold()
        if flag not in {"true", "false"}:
            raise ValueError(
                f"require_definition must be true or false for {canonical!r}"
            )
        entries.append(
            QuantityProfileEntry(
                canonical_symbol=canonical,
                aliases=tuple(
                    item.strip() for item in row["aliases"].split("|") if item.strip()
                ),
                meaning=row["meaning"].strip(),
                dimension=dimension,
                canonical_unit=canonical_unit,
                scope=row["scope"].strip() or "global",
                require_definition=flag == "true",
            )
        )
    return entries


@dataclass(frozen=True)
class SectionMark:
    offset: int
    name: str


class SectionIndex:
    def __init__(self, text: str) -> None:
        self.text = text
        marks = [SectionMark(0, "Front matter")]
        offset = 0
        abstract_environment = False
        known_plain = {
            "abstract": "Abstract",
            "introduction": "Introduction",
            "methods": "Methods",
            "methodology": "Methodology",
            "results": "Results",
            "discussion": "Discussion",
            "results and discussion": "Results and Discussion",
            "conclusion": "Conclusion",
            "conclusions": "Conclusions",
            "references": "References",
        }
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if re.search(r"\\begin\{abstract\}", line):
                abstract_environment = True
                marks.append(SectionMark(offset, "Abstract"))
            markdown = re.match(r"^#{1,6}\s+(.+?)\s*#*$", stripped)
            latex = re.search(r"\\(?:sub)*section\*?\{([^{}]+)\}", line)
            if markdown:
                marks.append(SectionMark(offset, markdown.group(1).strip()))
            elif latex:
                marks.append(SectionMark(offset, latex.group(1).strip()))
            else:
                normalized = re.sub(r"\s+", " ", stripped).casefold().rstrip(":")
                if normalized in known_plain:
                    marks.append(SectionMark(offset, known_plain[normalized]))
            if abstract_environment and re.search(r"\\end\{abstract\}", line):
                abstract_environment = False
                marks.append(SectionMark(offset + len(line), "Front matter"))
            offset += len(line)
        deduplicated: list[SectionMark] = []
        for mark in marks:
            if deduplicated and mark.offset == deduplicated[-1].offset:
                deduplicated[-1] = mark
            elif not deduplicated or mark.name != deduplicated[-1].name:
                deduplicated.append(mark)
        self.marks = deduplicated
        self.offsets = [mark.offset for mark in deduplicated]
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer(r"\n", text))

    def section_at(self, offset: int) -> str:
        index = bisect.bisect_right(self.offsets, max(offset, 0)) - 1
        return self.marks[max(index, 0)].name

    def location(self, source: str, offset: int) -> dict[str, Any]:
        line_index = bisect.bisect_right(self.line_starts, max(offset, 0)) - 1
        line_start = self.line_starts[max(line_index, 0)]
        return {
            "source": source,
            "line": line_index + 1,
            "column": offset - line_start + 1,
            "section": self.section_at(offset),
        }


@dataclass(frozen=True)
class ValueOccurrence:
    raw_value: str
    value: Decimal
    raw_unit: str
    unit: UnitDefinition | None
    start: int
    end: int
    location: dict[str, Any]

    @property
    def normalized_value(self) -> Decimal | None:
        if self.unit is None:
            return None
        return self.value * self.unit.factor


@dataclass(frozen=True)
class MathSpan:
    start: int
    end: int
    raw: str
    kind: str
    location: dict[str, Any]


@dataclass(frozen=True)
class SymbolOccurrence:
    raw: str
    normalized: str
    canonical: str
    role: str
    definition: str | None
    start: int
    location: dict[str, Any]
    math_kind: str


def _short_quote(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip()[:220]


def _decimal_json(value: Decimal | None) -> float | int | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _rounding_uncertainty(raw_value: str, unit: UnitDefinition | None) -> Decimal:
    cleaned = raw_value.replace("−", "-").replace(",", "").lstrip("+-")
    exponent = 0
    if "e" in cleaned.casefold():
        mantissa, exponent_text = re.split(r"[eE]", cleaned, maxsplit=1)
        exponent = int(exponent_text)
    else:
        mantissa = cleaned
    decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
    quantum = Decimal(10) ** Decimal(exponent - decimals)
    factor = unit.factor if unit is not None else Decimal(1)
    return abs(quantum * factor) / Decimal(2)


def _comparison_tolerance(
    left: ValueOccurrence,
    right: ValueOccurrence,
    relative_tolerance: Decimal,
) -> Decimal:
    left_value = left.normalized_value if left.normalized_value is not None else left.value
    right_value = right.normalized_value if right.normalized_value is not None else right.value
    relative = max(abs(left_value), abs(right_value)) * relative_tolerance
    rounding = _rounding_uncertainty(left.raw_value, left.unit) + _rounding_uncertainty(
        right.raw_value, right.unit
    )
    return max(relative, rounding)


def _stable_id(prefix: str, check_id: str, pieces: Iterable[Any]) -> str:
    material = "\0".join([check_id, *(str(piece) for piece in pieces)])
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=5).hexdigest().upper()
    return f"{prefix}-{digest}"


def _finding(
    *,
    check_id: str,
    severity: str,
    confidence: float,
    location: dict[str, Any],
    observation: str,
    expected: str,
    reason: str,
    quote: str,
    related_locations: Sequence[dict[str, Any]] = (),
    calculation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identifier = _stable_id(
        "QNT",
        check_id,
        [
            location.get("source"),
            location.get("line"),
            *(f"{item.get('source')}:{item.get('line')}" for item in related_locations),
            observation,
        ],
    )
    result: dict[str, Any] = {
        "id": identifier,
        "category": "quantitative",
        "check_id": check_id,
        "severity": severity,
        "confidence": round(confidence, 2),
        "status": "confirmed" if confidence >= 0.95 else "likely",
        "location": location,
        "related_locations": list(related_locations),
        "quote": quote,
        "observation": observation,
        "expected": expected,
        "reason": reason,
        "evidence": [{"class": "A", "source": "manuscript"}],
        "suggested_fix": "核对原始计算、量值身份、单位和舍入后，统一所有对应位置。",
        "auto_fixable": False,
    }
    if calculation is not None:
        result["calculation"] = calculation
    return result


def _candidate(
    *,
    candidate_type: str,
    location: dict[str, Any],
    reason: str,
    quote: str,
    required_evidence: str,
    related_locations: Sequence[dict[str, Any]] = (),
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identifier = _stable_id(
        "QRC",
        candidate_type,
        [location.get("source"), location.get("line"), reason, *(item.get("line") for item in related_locations)],
    )
    result: dict[str, Any] = {
        "id": identifier,
        "type": candidate_type,
        "location": location,
        "related_locations": list(related_locations),
        "quote": quote,
        "reason": reason,
        "required_evidence": required_evidence,
    }
    if details:
        result.update(details)
    return result


def extract_values(text: str, source: str, sections: SectionIndex) -> list[ValueOccurrence]:
    values: list[ValueOccurrence] = []
    for match in VALUE_UNIT_RE.finditer(text):
        raw_unit = match.group("unit")
        definition = normalize_unit(raw_unit)
        values.append(
            ValueOccurrence(
                raw_value=match.group("value"),
                value=parse_number(match.group("value")),
                raw_unit=raw_unit,
                unit=definition,
                start=match.start(),
                end=match.end(),
                location=sections.location(source, match.start()),
            )
        )
    return values


def _latex_excluded_view(text: str) -> str:
    chars = list(text)
    offset = 0
    for line in text.splitlines(keepends=True):
        for index, char in enumerate(line):
            if char != "%":
                continue
            slash_count = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                slash_count += 1
                cursor -= 1
            if slash_count % 2 == 0:
                for position in range(offset + index, offset + len(line)):
                    if chars[position] not in "\r\n":
                        chars[position] = " "
                break
        offset += len(line)
    view = "".join(chars)
    for environment in ("verbatim", "verbatim*", "lstlisting", "minted"):
        pattern = re.compile(
            rf"\\begin\{{{re.escape(environment)}\}}.*?\\end\{{{re.escape(environment)}\}}",
            re.DOTALL,
        )
        for match in pattern.finditer(view):
            for position in range(match.start(), match.end()):
                if chars[position] not in "\r\n":
                    chars[position] = " "
    return "".join(chars)


def extract_math_spans(
    text: str, source: str, sections: SectionIndex, format_name: str
) -> list[MathSpan]:
    view = _latex_excluded_view(text) if format_name == "tex" else text
    candidates: list[tuple[int, int, str]] = []
    if format_name in {"tex", "md"}:
        patterns = [
            ("display", re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)),
            ("inline", re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", re.DOTALL)),
        ]
        if format_name == "tex":
            patterns.extend(
                [
                    ("inline", re.compile(r"\\\((.+?)\\\)", re.DOTALL)),
                    ("display", re.compile(r"\\\[(.+?)\\\]", re.DOTALL)),
                    (
                        "display",
                        re.compile(
                            r"\\begin\{(?:equation\*?|align\*?|gather\*?|multline\*?)\}"
                            r".*?\\end\{(?:equation\*?|align\*?|gather\*?|multline\*?)\}",
                            re.DOTALL,
                        ),
                    ),
                ]
            )
        for kind, pattern in patterns:
            candidates.extend((match.start(), match.end(), kind) for match in pattern.finditer(view))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected: list[tuple[int, int, str]] = []
    for start, end, kind in candidates:
        if any(existing_start <= start and end <= existing_end for existing_start, existing_end, _ in selected):
            continue
        selected.append((start, end, kind))
    return [
        MathSpan(
            start=start,
            end=end,
            raw=text[start:end],
            kind=kind,
            location=sections.location(source, start),
        )
        for start, end, kind in sorted(selected)
    ]


GREEK_COMMANDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho",
    "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi", "Omega",
}
IGNORED_MATH_COMMANDS = {
    "frac", "sqrt", "sum", "prod", "int", "left", "right", "mathrm", "mathbf", "mathit",
    "text", "operatorname", "label", "sin", "cos", "tan", "log", "ln", "exp", "min", "max",
}
SYMBOL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z\\])(?P<base>\\[A-Za-z]+|[A-Za-z])"
    r"(?P<sub>\s*_\s*(?:\{(?:[^{}]|\{[^{}]*\})*\}|\\[A-Za-z]+|[A-Za-z0-9]+))?"
    r"(?![A-Za-z])"
)


def _local_dummy_symbol(symbol: str, math_text: str) -> bool:
    if symbol not in {"i", "j", "k", "n"}:
        return False
    return bool(
        re.search(
            rf"\\(?:sum|prod)\s*_\s*\{{?\s*{re.escape(symbol)}\s*=",
            math_text,
        )
    )


def _definition_after(text: str, span: MathSpan) -> str | None:
    following = text[span.end : min(len(text), span.end + 220)]
    match = re.match(
        r"\s*(?:,\s*)?(?:(?:where|with)\s+)?"
        r"(?:is|denotes|represents|refers\s+to|indicates|is\s+defined\s+as)\s+"
        r"(?P<definition>[^.;\n]{2,180})",
        following,
        re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group("definition")).strip()


def extract_symbols(
    text: str,
    math_spans: Sequence[MathSpan],
    profile_entries: Sequence[QuantityProfileEntry],
) -> list[SymbolOccurrence]:
    alias_map: dict[str, str] = {}
    for entry in profile_entries:
        canonical = normalize_symbol(entry.canonical_symbol)
        alias_map[canonical] = canonical
        for alias in entry.aliases:
            alias_map[normalize_symbol(alias)] = canonical
    occurrences: list[SymbolOccurrence] = []
    for span in math_spans:
        definition = _definition_after(text, span)
        text_wrappers = [
            match.span()
            for match in re.finditer(r"\\(?:text|mathrm|operatorname)\{[^{}]*\}", span.raw)
        ]
        for match in SYMBOL_TOKEN_RE.finditer(span.raw):
            base = match.group("base")
            command = base[1:] if base.startswith("\\") else ""
            if command and command not in GREEK_COMMANDS:
                continue
            if command in IGNORED_MATH_COMMANDS:
                continue
            if any(start <= match.start() < end for start, end in text_wrappers):
                continue
            raw = match.group(0)
            normalized = normalize_symbol(raw)
            if normalized in {"e", "pi", "infty"}:
                continue
            if _local_dummy_symbol(normalized, span.raw):
                continue
            canonical = alias_map.get(normalized, normalized)
            occurrences.append(
                SymbolOccurrence(
                    raw=raw,
                    normalized=normalized,
                    canonical=canonical,
                    role="definition" if definition else "use",
                    definition=definition,
                    start=span.start + match.start(),
                    location={**span.location, "column": span.location["column"] + match.start()},
                    math_kind=span.kind,
                )
            )
    return occurrences


def _profile_maps(
    profile_entries: Sequence[QuantityProfileEntry],
) -> tuple[dict[str, QuantityProfileEntry], dict[str, QuantityProfileEntry]]:
    canonical: dict[str, QuantityProfileEntry] = {}
    aliases: dict[str, QuantityProfileEntry] = {}
    for entry in profile_entries:
        key = normalize_symbol(entry.canonical_symbol)
        canonical[key] = entry
        aliases[key] = entry
        for alias in entry.aliases:
            aliases[normalize_symbol(alias)] = entry
    return canonical, aliases


def _symbol_results(
    text: str,
    occurrences: Sequence[SymbolOccurrence],
    profile_entries: Sequence[QuantityProfileEntry],
    symbol_min_uses: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    canonical_entries, alias_entries = _profile_maps(profile_entries)
    grouped: dict[str, list[SymbolOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[occurrence.canonical].append(occurrence)
        entry = alias_entries.get(occurrence.normalized)
        if entry and occurrence.normalized != normalize_symbol(entry.canonical_symbol):
            findings.append(
                _finding(
                    check_id="symbol-noncanonical-form",
                    severity="Minor",
                    confidence=0.99,
                    location=occurrence.location,
                    observation=(
                        f"符号“{occurrence.raw}”是已配置别名；规范形式为"
                        f"“{entry.canonical_symbol}”。"
                    ),
                    expected="同一物理量在全文使用配置中声明的规范符号。",
                    reason="配置已明确别名关系，因此该差异可确定为记号不一致。",
                    quote=_short_quote(text, occurrence.start, occurrence.start + len(occurrence.raw)),
                )
            )
    for symbol, items in sorted(grouped.items()):
        items = sorted(items, key=lambda item: item.start)
        definitions = [item for item in items if item.role == "definition"]
        definition_before_first = bool(definitions and definitions[0].start <= items[0].start)
        entry = canonical_entries.get(symbol)
        if entry and entry.require_definition and not definition_before_first:
            findings.append(
                _finding(
                    check_id="symbol-first-use",
                    severity="Minor",
                    confidence=0.96,
                    location=items[0].location,
                    observation=f"配置符号“{entry.canonical_symbol}”在首次使用前未被定义。",
                    expected="在首次使用处说明符号含义、参考方向及必要单位。",
                    reason="稿件级数量配置明确要求该符号进行首次定义。",
                    quote=_short_quote(text, items[0].start, items[0].start + len(items[0].raw)),
                )
            )
        elif not entry and len(items) >= symbol_min_uses and not definition_before_first:
            candidates.append(
                _candidate(
                    candidate_type="symbol-definition-review",
                    location=items[0].location,
                    related_locations=[item.location for item in definitions[:1]],
                    quote=_short_quote(text, items[0].start, items[0].start + len(items[0].raw)),
                    reason=f"符号“{items[0].raw}”出现 {len(items)} 次，但首次出现处未识别到定义。",
                    required_evidence="检查符号表、where 子句和公式上下文；确认后写入 quantity profile。",
                    details={"symbol": symbol, "occurrence_count": len(items)},
                )
            )
    return findings, candidates


def _explicit_unit_equalities(
    text: str,
    values: Sequence[ValueOccurrence],
    relative_tolerance: Decimal,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for left, right in zip(values, values[1:]):
        if right.start - left.end > 80:
            continue
        between = text[left.end : right.start]
        after = text[right.end : min(len(text), right.end + 3)]
        explicit = bool(
            re.fullmatch(
                r"\s*(?:=|equals?|is\s+equivalent\s+to|corresponds\s+to)\s*",
                between,
                re.IGNORECASE,
            )
        )
        parenthetical = bool(re.fullmatch(r"\s*\(\s*", between) and re.match(r"\s*\)", after))
        if not (explicit or parenthetical):
            continue
        if left.unit is None or right.unit is None:
            continue
        if left.unit.vector != right.unit.vector:
            findings.append(
                _finding(
                    check_id="unit-equivalence-dimension-mismatch",
                    severity="Major",
                    confidence=0.99,
                    location=right.location,
                    related_locations=[left.location],
                    observation=(
                        f"等价表达连接了不相容量纲：{left.raw_value} {left.raw_unit} 与 "
                        f"{right.raw_value} {right.raw_unit}。"
                    ),
                    expected="等式或括号换算的两侧应表示同一物理量。",
                    reason="两侧单位的量纲向量不同。",
                    quote=_short_quote(text, left.start, right.end),
                    calculation={
                        "left_dimension": left.unit.dimension,
                        "right_dimension": right.unit.dimension,
                    },
                )
            )
            continue
        left_si = left.normalized_value
        right_si = right.normalized_value
        assert left_si is not None and right_si is not None
        tolerance = _comparison_tolerance(left, right, relative_tolerance)
        difference = abs(left_si - right_si)
        if difference > tolerance:
            findings.append(
                _finding(
                    check_id="unit-conversion-mismatch",
                    severity="Major",
                    confidence=0.99,
                    location=right.location,
                    related_locations=[left.location],
                    observation=(
                        f"明确单位换算不相等：{left.raw_value} {left.raw_unit} 与 "
                        f"{right.raw_value} {right.raw_unit}。"
                    ),
                    expected="等式或括号内的换算值在统一单位后应在舍入容差内相等。",
                    reason="按单位比例归一化后的差值超过配置和有效数字共同确定的容差。",
                    quote=_short_quote(text, left.start, right.end),
                    calculation={
                        "left_normalized": _decimal_json(left_si),
                        "right_normalized": _decimal_json(right_si),
                        "difference": _decimal_json(difference),
                        "tolerance": _decimal_json(tolerance),
                        "dimension": left.unit.dimension,
                    },
                )
            )
    return findings


FROM_TO_RE = re.compile(
    rf"(?P<direction>increased|rose|grew|decreased|reduced|dropped|fell)\s+"
    rf"from\s+(?P<from_value>{NUMBER_PATTERN})(?:\s*(?P<from_unit>{UNIT_PATTERN}))?\s+"
    rf"to\s+(?P<to_value>{NUMBER_PATTERN})(?:\s*(?P<to_unit>{UNIT_PATTERN}))?"
    rf"(?:\s*,?\s*(?:representing|corresponding\s+to|which\s+is|by))\s+"
    rf"(?P<reported>{NUMBER_PATTERN})\s*%",
    re.IGNORECASE,
)


def _from_to_percentages(
    text: str,
    source: str,
    sections: SectionIndex,
    percentage_point_tolerance: Decimal,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    increase_words = {"increased", "rose", "grew"}
    for match in FROM_TO_RE.finditer(text):
        start_value = parse_number(match.group("from_value"))
        end_value = parse_number(match.group("to_value"))
        from_unit_text = match.group("from_unit") or match.group("to_unit") or ""
        to_unit_text = match.group("to_unit") or match.group("from_unit") or ""
        from_unit = normalize_unit(from_unit_text) if from_unit_text else None
        to_unit = normalize_unit(to_unit_text) if to_unit_text else None
        location = sections.location(source, match.start())
        if (from_unit is None) != (to_unit is None):
            candidates.append(
                _candidate(
                    candidate_type="percentage-change-review",
                    location=location,
                    quote=_short_quote(text, match.start(), match.end()),
                    reason="from-to 表达中的单位不完整或存在歧义，无法安全复算。",
                    required_evidence="确认起点和终点量值使用相同单位。",
                )
            )
            continue
        if from_unit and to_unit and from_unit.vector != to_unit.vector:
            findings.append(
                _finding(
                    check_id="percentage-change-dimension-mismatch",
                    severity="Major",
                    confidence=0.99,
                    location=location,
                    observation="百分比变化的起点与终点使用了不相容量纲。",
                    expected="from-to 百分比只能在同一物理量的两个值之间计算。",
                    reason="起点与终点单位的量纲向量不同。",
                    quote=_short_quote(text, match.start(), match.end()),
                )
            )
            continue
        start_normalized = start_value * (from_unit.factor if from_unit else Decimal(1))
        end_normalized = end_value * (to_unit.factor if to_unit else Decimal(1))
        if start_normalized == 0:
            candidates.append(
                _candidate(
                    candidate_type="percentage-change-review",
                    location=location,
                    quote=_short_quote(text, match.start(), match.end()),
                    reason="百分比变化以零为基准，常规定义不可用。",
                    required_evidence="作者需说明百分比定义或改用绝对差值。",
                )
            )
            continue
        increasing = match.group("direction").casefold() in increase_words
        signed_change = end_normalized - start_normalized
        direction_ok = signed_change >= 0 if increasing else signed_change <= 0
        actual = (
            signed_change / abs(start_normalized) * Decimal(100)
            if increasing
            else -signed_change / abs(start_normalized) * Decimal(100)
        )
        reported = parse_number(match.group("reported"))
        if not direction_ok:
            findings.append(
                _finding(
                    check_id="percentage-direction-mismatch",
                    severity="Major",
                    confidence=0.99,
                    location=location,
                    observation=(
                        f"措辞“{match.group('direction')}”与起点 {match.group('from_value')} "
                        f"和终点 {match.group('to_value')} 的方向相反。"
                    ),
                    expected="变化方向、起终点数值和百分比应相互一致。",
                    reason="归一化后的终点相对起点沿相反方向变化。",
                    quote=_short_quote(text, match.start(), match.end()),
                    calculation={"actual_percentage": _decimal_json(actual)},
                )
            )
        difference = abs(actual - reported)
        reported_uncertainty = _rounding_uncertainty(match.group("reported"), None)
        tolerance = max(percentage_point_tolerance, reported_uncertainty)
        if difference > tolerance:
            findings.append(
                _finding(
                    check_id="percentage-change-mismatch",
                    severity="Major",
                    confidence=0.99,
                    location=location,
                    observation=(
                        f"from-to 数值对应约 {actual:.4g}% 的变化，但正文报告为 "
                        f"{reported}% 。"
                    ),
                    expected="按明确起点为基准重新计算并按合适有效数字报告百分比。",
                    reason="复算结果与报告百分比的差值超过百分点容差。",
                    quote=_short_quote(text, match.start(), match.end()),
                    calculation={
                        "from_normalized": _decimal_json(start_normalized),
                        "to_normalized": _decimal_json(end_normalized),
                        "actual_percentage": _decimal_json(actual),
                        "reported_percentage": _decimal_json(reported),
                        "difference_percentage_points": _decimal_json(difference),
                        "tolerance_percentage_points": _decimal_json(tolerance),
                    },
                )
            )
    return findings, candidates


METRIC_PATTERNS = [
    "peak interstory drift ratio",
    "maximum interstory drift ratio",
    "residual interstory drift ratio",
    "residual drift ratio",
    "peak drift ratio",
    "maximum drift ratio",
    "peak drift",
    "maximum drift",
    "fundamental period",
    "damping ratio",
    "base shear",
    "peak floor acceleration",
    "peak acceleration",
    "residual displacement",
    "maximum displacement",
    "initial stiffness",
    "post-yield stiffness",
]
METRIC_RE = re.compile(
    r"\b(" + "|".join(re.escape(item) for item in sorted(METRIC_PATTERNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
ENTITY_RE = re.compile(
    r"\b(?:specimen|model|case|frame|wall|system)\s+([A-Z][A-Z0-9-]*\d[A-Z0-9-]*)\b"
)
HAZARD_RE = re.compile(
    r"\b(DBE|MCE|MCER|SLE|BSE-\d[EN]?)\b|\b((?:2|10|50)%\s+in\s+50\s+years)\b",
    re.IGNORECASE,
)


def _sentence_bounds(text: str, offset: int) -> tuple[int, int]:
    left = text.rfind("\n", 0, offset)
    right = text.find("\n", offset)
    right = right if right != -1 else len(text)
    return left + 1, right


def _span_for_offset(spans: Sequence[MathSpan], offset: int) -> MathSpan | None:
    for span in spans:
        if span.start <= offset < span.end:
            return span
    return None


def _last_symbol_before_value(
    text: str,
    value: ValueOccurrence,
    spans: Sequence[MathSpan],
    alias_map: dict[str, str],
) -> str | None:
    span = _span_for_offset(spans, value.start)
    if span:
        prefix = text[span.start : value.start]
        matches = list(SYMBOL_TOKEN_RE.finditer(prefix))
        if matches:
            last = matches[-1]
            if re.fullmatch(r"\s*=\s*", prefix[last.end() :]):
                normalized = normalize_symbol(last.group(0))
                return alias_map.get(normalized, normalized)
    before_start = max(0, value.start - 50)
    before = text[before_start : value.start]
    match = re.search(r"\$([^$]{1,40})\$\s*(?:=|is|was|reached|of)\s*$", before, re.IGNORECASE)
    if match:
        normalized = normalize_symbol(match.group(1))
        return alias_map.get(normalized, normalized)
    return None


def _quantity_ledger(
    text: str,
    values: Sequence[ValueOccurrence],
    math_spans: Sequence[MathSpan],
    profile_entries: Sequence[QuantityProfileEntry],
) -> list[dict[str, Any]]:
    _, alias_entries = _profile_maps(profile_entries)
    alias_map = {
        alias: normalize_symbol(entry.canonical_symbol) for alias, entry in alias_entries.items()
    }
    records: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        sentence_start, sentence_end = _sentence_bounds(text, value.start)
        sentence = text[sentence_start:sentence_end]
        symbol = _last_symbol_before_value(text, value, math_spans, alias_map)
        metric_matches = list(METRIC_RE.finditer(sentence))
        metric = metric_matches[-1].group(1).casefold() if metric_matches else ""
        entity_match = ENTITY_RE.search(sentence)
        entity = entity_match.group(1) if entity_match else ""
        hazard_match = HAZARD_RE.search(sentence)
        hazard = next((item for item in hazard_match.groups() if item), "") if hazard_match else ""
        if symbol:
            metric_key = f"symbol:{symbol}"
            strength = "strong"
        elif metric:
            metric_key = f"metric:{metric}"
            strength = "strong" if entity and hazard else "weak"
        else:
            metric_key = ""
            strength = "none"
        normalized = value.normalized_value
        record_id = _stable_id("VAL", metric_key or "unkeyed", [value.location["source"], value.start, value.raw_value, value.raw_unit])
        records.append(
            {
                "id": record_id,
                "metric_key": metric_key,
                "metric": metric,
                "symbol": symbol or "",
                "entity": entity,
                "hazard": hazard.casefold(),
                "match_strength": strength,
                "raw_value": value.raw_value,
                "value": _decimal_json(value.value),
                "raw_unit": value.raw_unit,
                "canonical_unit": value.unit.canonical if value.unit else "",
                "dimension": value.unit.dimension if value.unit else "ambiguous",
                "normalized_value": _decimal_json(normalized),
                "origin": "equation" if _span_for_offset(math_spans, value.start) else "prose",
                "location": value.location,
                "quote": _short_quote(text, value.start, value.end),
                "_index": index,
            }
        )
    return records


def _dimension_and_cross_section_results(
    text: str,
    values: Sequence[ValueOccurrence],
    ledger: Sequence[dict[str, Any]],
    profile_entries: Sequence[QuantityProfileEntry],
    relative_tolerance: Decimal,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    canonical_entries, _ = _profile_maps(profile_entries)
    assignments: dict[str, list[tuple[dict[str, Any], ValueOccurrence]]] = defaultdict(list)
    for record in ledger:
        symbol = record["symbol"]
        if not symbol:
            continue
        value = values[record["_index"]]
        assignments[symbol].append((record, value))
        entry = canonical_entries.get(symbol)
        if entry and entry.dimension and value.unit is not None:
            expected_vector = DIMENSION_VECTORS[entry.dimension]
            if value.unit.vector != expected_vector:
                findings.append(
                    _finding(
                        check_id="quantity-unit-dimension-mismatch",
                        severity="Major",
                        confidence=0.99,
                        location=value.location,
                        observation=(
                            f"符号“{entry.canonical_symbol}”配置为 {entry.dimension}，"
                            f"但赋值使用单位“{value.raw_unit}”（{value.unit.dimension}）。"
                        ),
                        expected="符号的显式数值单位应与稿件级数量配置的量纲一致。",
                        reason="符号身份和单位量纲均已明确，二者不相容。",
                        quote=_short_quote(text, value.start, value.end),
                    )
                )
    for symbol, items in assignments.items():
        known = [(record, value) for record, value in items if value.unit is not None]
        if len(known) < 2:
            continue
        first_record, first_value = known[0]
        for record, value in known[1:]:
            assert first_value.unit is not None and value.unit is not None
            if first_value.unit.vector != value.unit.vector:
                findings.append(
                    _finding(
                        check_id="symbol-unit-conflict",
                        severity="Major",
                        confidence=0.99,
                        location=value.location,
                        related_locations=[first_value.location],
                        observation=(
                            f"同一符号“{symbol}”被赋予不相容量纲："
                            f"{first_value.raw_unit} 与 {value.raw_unit}。"
                        ),
                        expected="同一作用域内的符号应始终表示同一量纲的物理量。",
                        reason="两处均为明确符号赋值，且单位量纲不同。",
                        quote=record["quote"],
                    )
                )

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in ledger:
        if not record["metric_key"] or record["normalized_value"] is None:
            continue
        groups[(record["metric_key"], record["entity"], record["hazard"])].append(record)
    for key, records in groups.items():
        if len(records) < 2:
            continue
        for left_index in range(len(records)):
            for right_index in range(left_index + 1, len(records)):
                left_record = records[left_index]
                right_record = records[right_index]
                if left_record["location"]["section"].casefold() == right_record["location"]["section"].casefold():
                    continue
                left_value = values[left_record["_index"]]
                right_value = values[right_record["_index"]]
                if left_value.unit is None or right_value.unit is None or left_value.unit.vector != right_value.unit.vector:
                    continue
                tolerance = _comparison_tolerance(left_value, right_value, relative_tolerance)
                left_normalized = left_value.normalized_value
                right_normalized = right_value.normalized_value
                assert left_normalized is not None and right_normalized is not None
                difference = abs(left_normalized - right_normalized)
                if difference <= tolerance:
                    continue
                details = {
                    "metric_key": key[0],
                    "entity": key[1],
                    "hazard": key[2],
                    "left_normalized": _decimal_json(left_normalized),
                    "right_normalized": _decimal_json(right_normalized),
                    "difference": _decimal_json(difference),
                    "tolerance": _decimal_json(tolerance),
                }
                if left_record["match_strength"] == right_record["match_strength"] == "strong":
                    findings.append(
                        _finding(
                            check_id="cross-section-value-conflict",
                            severity="Major",
                            confidence=0.96,
                            location=right_record["location"],
                            related_locations=[left_record["location"]],
                            observation=(
                                f"同一量值键“{key[0]}”在不同章节报告了不一致数值："
                                f"{left_record['raw_value']} {left_record['raw_unit']} 与 "
                                f"{right_record['raw_value']} {right_record['raw_unit']}。"
                            ),
                            expected="同一对象、工况和量值在摘要、正文与结论中应保持一致。",
                            reason="符号或完整对象锚点一致，单位归一化后的差值超过舍入容差。",
                            quote=right_record["quote"],
                            calculation=details,
                        )
                    )
                else:
                    candidates.append(
                        _candidate(
                            candidate_type="cross-section-value-review",
                            location=right_record["location"],
                            related_locations=[left_record["location"]],
                            quote=right_record["quote"],
                            reason=(
                                f"相同术语附近出现不同量值，但实体、工况或统计口径不足以确定为同一结果。"
                            ),
                            required_evidence="确认两处的试件、危险水准、统计量和比较基准是否相同。",
                            details=details,
                        )
                    )
    return findings, candidates


FIGURE_REF_RE = re.compile(
    r"\bFigs?\.?|\bFigures?",
    re.IGNORECASE,
)
FIGURE_TARGET_RE = re.compile(
    r"(?:Figs?\.?|Figures?)\s*~?"
    r"(?:\\(?:ref|cref)\{(?P<label>[^{}]+)\}|(?P<number>\d+(?:[a-z])?))",
    re.IGNORECASE,
)
PEAK_WORD_RE = re.compile(r"\b(?:peak|maximum|max\.?|highest)\b", re.IGNORECASE)


def _figure_paths(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for environment in re.finditer(
        r"\\begin\{figure\*?\}(?P<body>.*?)\\end\{figure\*?\}", text, re.DOTALL
    ):
        body = environment.group("body")
        label = re.search(r"\\label\{([^{}]+)\}", body)
        graphic = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", body)
        if label:
            mapping[label.group(1).strip()] = graphic.group(1).strip() if graphic else ""
    return mapping


def _figure_peak_candidates(
    text: str,
    source: str,
    sections: SectionIndex,
    values: Sequence[ValueOccurrence],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    paths = _figure_paths(text)
    seen_sentences: set[tuple[int, int]] = set()
    for value in values:
        sentence_start, sentence_end = _sentence_bounds(text, value.start)
        if (sentence_start, sentence_end) in seen_sentences:
            continue
        sentence = text[sentence_start:sentence_end]
        if not FIGURE_REF_RE.search(sentence) or not PEAK_WORD_RE.search(sentence):
            continue
        target = FIGURE_TARGET_RE.search(sentence)
        if not target:
            continue
        sentence_values = [item for item in values if sentence_start <= item.start < sentence_end]
        peak = PEAK_WORD_RE.search(sentence)
        assert peak is not None
        after_peak = [item for item in sentence_values if item.start >= sentence_start + peak.end()]
        claimed = after_peak[0] if after_peak else sentence_values[0]
        label = target.group("label") or ""
        number = target.group("number") or ""
        candidates.append(
            _candidate(
                candidate_type="figure-peak-review",
                location=sections.location(source, sentence_start + target.start()),
                quote=re.sub(r"\s+", " ", sentence).strip()[:220],
                reason="正文对图中峰值作出明确数值陈述，但曲线、坐标轴和工况需要视觉或源数据复核。",
                required_evidence="读取原始绘图数据，或在清晰图件中核对坐标轴、单位、曲线和峰值。",
                details={
                    "figure_label": label,
                    "figure_number": number,
                    "figure_path": paths.get(label, ""),
                    "claimed_value": _decimal_json(claimed.value),
                    "claimed_unit": claimed.unit.canonical if claimed.unit else claimed.raw_unit,
                },
            )
        )
        seen_sentences.add((sentence_start, sentence_end))
    return candidates


def _formula_review_candidates(
    text: str,
    math_spans: Sequence[MathSpan],
    symbols: Sequence[SymbolOccurrence],
    profile_entries: Sequence[QuantityProfileEntry],
) -> list[dict[str, Any]]:
    if not profile_entries:
        return []
    configured = {normalize_symbol(entry.canonical_symbol) for entry in profile_entries}
    candidates: list[dict[str, Any]] = []
    for span in math_spans:
        if span.kind != "display" or "=" not in span.raw:
            continue
        span_symbols = sorted(
            {item.canonical for item in symbols if span.start <= item.start < span.end}
        )
        unknown = [symbol for symbol in span_symbols if symbol not in configured]
        if not unknown:
            continue
        candidates.append(
            _candidate(
                candidate_type="formula-dimension-review",
                location=span.location,
                quote=re.sub(r"\s+", " ", span.raw).strip()[:220],
                reason="公式包含未配置量纲的符号，无法完整执行量纲判断。",
                required_evidence="为未知符号补充 quantity profile 的含义、量纲和规范单位。",
                details={"unknown_symbols": unknown, "known_symbols": [item for item in span_symbols if item in configured]},
            )
        )
    return candidates


def analyze_quantitative_text(
    text: str,
    *,
    source: str = "manuscript.tex",
    format_name: str | None = None,
    quantity_profile: Sequence[QuantityProfileEntry] | None = None,
    quantity_profile_path: str | Path | None = None,
    relative_tolerance: Decimal | float | str = DEFAULT_RELATIVE_TOLERANCE,
    percentage_point_tolerance: Decimal | float | str = DEFAULT_PERCENTAGE_POINT_TOLERANCE,
    symbol_min_uses: int = 2,
) -> dict[str, Any]:
    """Analyze manuscript text and return JSON-friendly findings and ledgers."""

    if quantity_profile is not None and quantity_profile_path is not None:
        raise ValueError("provide quantity_profile or quantity_profile_path, not both")
    entries = list(quantity_profile or [])
    if quantity_profile_path is not None:
        entries = load_quantity_profile(quantity_profile_path)
    if format_name is None:
        suffix = Path(source).suffix.casefold()
        format_name = "tex" if suffix == ".tex" else "md" if suffix == ".md" else "txt"
    if format_name not in {"tex", "md", "txt"}:
        raise ValueError("quantitative source analyzer supports tex, md, and txt")
    relative = Decimal(str(relative_tolerance))
    percentage_tolerance = Decimal(str(percentage_point_tolerance))
    if relative < 0 or percentage_tolerance < 0 or symbol_min_uses < 1:
        raise ValueError("tolerances must be non-negative and symbol_min_uses must be positive")

    sections = SectionIndex(text)
    values = extract_values(text, source, sections)
    math_spans = extract_math_spans(text, source, sections, format_name)
    symbols = extract_symbols(text, math_spans, entries)
    ledger = _quantity_ledger(text, values, math_spans, entries)

    findings: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    symbol_findings, symbol_candidates = _symbol_results(
        text, symbols, entries, symbol_min_uses
    )
    findings.extend(symbol_findings)
    candidates.extend(symbol_candidates)
    findings.extend(_explicit_unit_equalities(text, values, relative))
    percentage_findings, percentage_candidates = _from_to_percentages(
        text, source, sections, percentage_tolerance
    )
    findings.extend(percentage_findings)
    candidates.extend(percentage_candidates)
    dimension_findings, cross_section_candidates = _dimension_and_cross_section_results(
        text, values, ledger, entries, relative
    )
    findings.extend(dimension_findings)
    candidates.extend(cross_section_candidates)
    candidates.extend(_figure_peak_candidates(text, source, sections, values))
    candidates.extend(_formula_review_candidates(text, math_spans, symbols, entries))

    # Remove private integration fields from the public ledger.
    public_ledger = [{key: value for key, value in item.items() if key != "_index"} for item in ledger]
    finding_by_id = {item["id"]: item for item in findings}
    candidate_by_id = {item["id"]: item for item in candidates}
    ordered_findings = sorted(
        finding_by_id.values(),
        key=lambda item: (item["location"]["source"], item["location"]["line"], item["check_id"], item["id"]),
    )
    ordered_candidates = sorted(
        candidate_by_id.values(),
        key=lambda item: (item["location"]["source"], item["location"]["line"], item["type"], item["id"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "pass_id": "quantitative",
        "format": format_name,
        "summary": {
            "finding_count": len(ordered_findings),
            "review_candidate_count": len(ordered_candidates),
            "value_count": len(values),
            "symbol_count": len(symbols),
        },
        "coverage": {
            "numeric_units": "deterministic",
            "latex_symbols": "deterministic-ledger-with-review-candidates" if format_name == "tex" else "not-applicable",
            "formula_dimensions": "profile-backed-explicit-assignments-only",
            "figure_values": "visual-review-required",
        },
        "findings": ordered_findings,
        "review_candidates": ordered_candidates,
        "symbols": [
            {
                "raw": item.raw,
                "normalized": item.normalized,
                "canonical": item.canonical,
                "role": item.role,
                "definition": item.definition,
                "math_kind": item.math_kind,
                "location": item.location,
            }
            for item in symbols
        ],
        "values": public_ledger,
        "equations": [
            {
                "raw": re.sub(r"\s+", " ", span.raw).strip(),
                "kind": span.kind,
                "location": span.location,
                "dimension_status": "candidate" if span.kind == "display" and "=" in span.raw else "not-requested",
            }
            for span in math_spans
            if span.kind == "display"
        ],
    }


def analyze_file(
    path: str | Path,
    *,
    quantity_profile_path: str | Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    source_path = Path(path).resolve(strict=True)
    text = source_path.read_text(encoding="utf-8-sig")
    result = analyze_quantitative_text(
        text,
        source=source_path.name,
        quantity_profile_path=quantity_profile_path,
        **kwargs,
    )
    result["input"] = {"path": str(source_path), "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}
    result["sources"] = [{"source": source_path.name, "sha256": result["input"]["sha256"]}]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="执行保守的论文公式、符号、单位与数值一致性检查。"
    )
    parser.add_argument("manuscript", help="UTF-8 .tex/.md/.txt 稿件")
    parser.add_argument("--quantity-profile", help="稿件级 quantity-profile.tsv")
    parser.add_argument("--output", help="JSON 输出路径；省略时写到标准输出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = analyze_file(
            args.manuscript,
            quantity_profile_path=args.quantity_profile,
        )
    except (OSError, ValueError) as exc:
        print(f"quantitative-checks: {exc}", file=sys.stderr)
        return 2
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            print(f"quantitative-checks: 输出已存在，未覆盖：{output}", file=sys.stderr)
            return 2
        output.write_text(serialized, encoding="utf-8", newline="\n")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
