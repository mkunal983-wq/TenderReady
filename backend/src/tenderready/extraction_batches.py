"""Small, exact-offset extraction batches with conservative source context.

This planner does not interpret requirements. It recognizes explicit product
headings and keeps their source text alongside bounded primary ranges. Every
character belongs to exactly one primary range; context is never fabricated.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class BatchContext:
    kind: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ExtractionBatch:
    start: int
    end: int
    contexts: tuple[BatchContext, ...] = ()


@dataclass(frozen=True)
class _Line:
    start: int
    end: int
    value: str


_SCOPE = re.compile(r"(?:Configuration|Lot|Variant)\s+[A-Z0-9][A-Za-z0-9.-]*\s*:?[ \t]*$", re.I)
_PRODUCT_ROW = re.compile(r"(Tablet|Desktop|Laptop|Notebook|Ultrabook|Macbook|Monitor|Printer)\b(?=\s+(?:Screen|Processor|Memory|Storage|RAM|Display|Technical)\b)", re.I)
_PRODUCT_WRAP = re.compile(r"(?:Laptop|Notebook|Ultrabook|Macbook|Desktop|devices|categories|tebook)", re.I)
_CLAUSE = re.compile(r"\s*\d+(?:\.\d+)*\.[ \t]+\S")
_TABLE_HEADER = re.compile(r"\bItem\b.*\b(?:specification|description)\b", re.I)


def _lines(text: str) -> list[_Line]:
    result, offset = [], 0
    for line in text.splitlines(keepends=True):
        result.append(_Line(offset, offset + len(line), line))
        offset += len(line)
    return result


def _context(text: str, kind: str, start: int, end: int) -> BatchContext:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return BatchContext(kind, start, end, text[start:end])


def _bounded_ranges(text: str, start: int, end: int, max_chars: int):
    """Prefer paragraph/clause boundaries; keep complete short clauses together."""
    lines = _lines(text[start:end])
    preferred = {start + line.start for line in lines if _CLAUSE.match(line.value)}
    preferred.update(start + line.end for line in lines if not line.value.strip())
    line_breaks = [start + line.end for line in lines]
    cursor = start
    while end - cursor > max_chars:
        limit = cursor + max_chars
        options = [p for p in preferred if cursor + max_chars // 4 <= p <= limit]
        if not options:
            options = [p for p in line_breaks if cursor < p <= limit]
        boundary = max(options) if options else text.rfind(' ', cursor + 1, limit + 1) + 1
        if boundary <= cursor:
            boundary = limit
        yield cursor, boundary
        cursor = boundary
    if cursor < end:
        yield cursor, end


def plan_batches(text: str, max_chars: int = 1500) -> list[ExtractionBatch]:
    """Plan exact primary ranges, with optional exact product/table context.

    Offsets are relative to the supplied text (typically a persisted page/span).
    Context resets at a new product heading or numbered non-table clause. Small
    pages without explicit product groups remain one batch. This is deliberately
    conservative; arbitrary visual tables require human review.
    """
    if not 128 <= max_chars <= 10000:
        raise ValueError('max_chars must be between 128 and 10000')
    if not text:
        return []
    lines = _lines(text)
    events: dict[int, tuple[BatchContext, ...]] = {0: ()}
    active: tuple[BatchContext, ...] = ()
    header = None
    for index, line in enumerate(lines):
        stripped = line.value.strip()
        if _TABLE_HEADER.search(stripped):
            header_end = line.end
            # Wrapped column names are source context too, not new requirements.
            if index + 1 < len(lines) and lines[index + 1].value.strip().lower() in {'requirement', 'quantity', 'quantity required'}:
                header_end = lines[index + 1].end
            header = _context(text, 'table_header', line.start, header_end)
        scope = None
        block_start = line.start
        if _SCOPE.fullmatch(stripped):
            scope = _context(text, 'product_scope', line.start, line.end)
            # A PDF extractor often puts a wrapped item name before Configuration A.
            # Walk only an immediately adjacent product-name block, never a spec row.
            back = index - 1
            while back >= 0 and index - back <= 5:
                previous = lines[back].value.strip()
                if not previous or ':' in previous or not _PRODUCT_WRAP.search(previous):
                    break
                block_start = lines[back].start
                back -= 1
        else:
            match = _PRODUCT_ROW.match(stripped)
            if match:
                start = line.start + line.value.index(match.group(1))
                scope = _context(text, 'product_scope', start, start + len(match.group(1)))
        if scope:
            active = tuple(c for c in (header, scope) if c is not None)
            events[block_start] = active
        elif active and _CLAUSE.match(line.value):
            # Supplier/eligibility clauses following a table do not inherit its last product.
            active = ()
            header = None
            events[line.start] = active
    boundaries = sorted({0, len(text), *events})
    result = []
    active = ()
    for start, end in zip(boundaries, boundaries[1:]):
        active = events.get(start, active)
        for first, last in _bounded_ranges(text, start, end, max_chars):
            result.append(ExtractionBatch(first, last, active))
    return result
