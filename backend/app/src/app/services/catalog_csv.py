# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""CSV column spec, parsing and field validation for admin catalog imports.

Deliberately **pure**: no database, no session, no settings. Everything here is
decidable from the bytes of the uploaded file alone, which keeps the rules
unit-testable without a Postgres fixture and keeps the DB-aware planning in
`services/catalog_import.py`.

Shape of the file — one row per product, carrying its whole ancestor path:

    service_slug,service_name,category_slug,category_name,
    subcategory_slug,subcategory_name,product_slug,product_name,base_price

Slugs are **required and are the identity** (see the design decision in the
module docstring of `catalog_import.py`): a rename is "same slug, new name".
Nothing here slugifies a name, because a derived slug would silently fork a
duplicate product the first time an operator edited a name.

Two classes of failure:

* :class:`CatalogCsvError` — the file as a whole is unusable (bad encoding,
  missing or unknown columns, empty, over the row cap). Raised, and surfaced by
  the router as a 4xx. Nothing is staged.
* per-row errors — collected onto :class:`ParsedRow.errors` and staged, so the
  operator gets one report listing every bad line instead of fixing them one
  upload at a time.

An **unknown column is a file-level error, not a silent ignore**. A typo'd
`base_prices` would otherwise import every product at the wrong price with no
indication anything was wrong.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Non-English catalog languages. English lives in the unsuffixed
# `product_name` / `product_description` columns because every level needs it —
# the admin read models treat the English translation as the display name.
TRANSLATABLE_LANGS: Tuple[str, ...] = ("hi", "mr", "gu", "pa")

LEVELS: Tuple[str, ...] = ("service", "category", "subcategory", "product")

REQUIRED_COLUMNS: Tuple[str, ...] = (
    "service_slug",
    "service_name",
    "category_slug",
    "category_name",
    "subcategory_slug",
    "subcategory_name",
    "product_slug",
    "product_name",
    "base_price",
)

OPTIONAL_COLUMNS: Tuple[str, ...] = (
    "service_description",
    "service_sort_order",
    "category_description",
    "category_sort_order",
    "subcategory_description",
    "subcategory_sort_order",
    "product_description",
    "brand",
    "unit",
    "product_image_url",
    *tuple(f"product_name_{lang}" for lang in TRANSLATABLE_LANGS),
    *tuple(f"product_desc_{lang}" for lang in TRANSLATABLE_LANGS),
)

ALL_COLUMNS: Tuple[str, ...] = (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)

# Caps. The row cap is what keeps upload-time validation inside a request
# budget; apply is a Celery job and does not depend on it.
MAX_ROWS = 5_000
MAX_BYTES = 5 * 1024 * 1024

MAX_NAME_LEN = 200
MAX_DESCRIPTION_LEN = 2_000
MAX_SHORT_TEXT_LEN = 120  # brand, unit
MAX_URL_LEN = 500
MAX_PRICE = 999_999.0

# Lowercase kebab-case, no leading/trailing/double hyphen. Matches what
# `_slugify` in api/catalog_admin.py produces, so a slug created through the
# per-row UI is always a legal CSV slug.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HTTP_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

# Sentinel key for cells beyond the header width (csv.DictReader restkey).
_RESTKEY = "__extra__"


class CatalogCsvError(Exception):
    """The file cannot be parsed at all. Carries a machine-readable code."""

    def __init__(self, code: str, message: str, columns: Optional[Sequence[str]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.columns: List[str] = list(columns or ())

    def to_detail(self) -> Dict[str, Any]:
        detail: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.columns:
            detail["columns"] = self.columns
        return detail


@dataclass
class ParsedRow:
    """One CSV data line after normalization.

    ``data`` holds only non-empty cells: a blank optional cell is dropped rather
    than stored as ``""`` so the apply pass can tell "leave this field alone"
    from "set it to empty".
    """

    line_number: int
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, column: str, code: str, message: str) -> None:
        self.errors.append({"column": column, "code": code, "message": message})


def _err(row: ParsedRow, column: str, code: str, message: str) -> None:
    row.add_error(column, code, message)


def _decode(raw: bytes) -> str:
    if len(raw) > MAX_BYTES:
        raise CatalogCsvError(
            "file_too_large",
            f"File must be at most {MAX_BYTES // (1024 * 1024)} MB",
        )
    try:
        # utf-8-sig strips the BOM Excel writes when saving as "CSV UTF-8".
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogCsvError(
            "encoding_invalid",
            "File must be UTF-8 encoded (re-save as 'CSV UTF-8' from Excel)",
        ) from exc


def _read_header(reader: csv.DictReader) -> List[str]:  # type: ignore[type-arg]
    header = reader.fieldnames
    if not header:
        raise CatalogCsvError("empty_file", "File has no header row")
    normalized = [(h or "").strip().lower() for h in header]

    dupes = sorted({h for h in normalized if normalized.count(h) > 1 and h})
    if dupes:
        raise CatalogCsvError(
            "duplicate_columns", "Column appears more than once", dupes
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in normalized]
    if missing:
        raise CatalogCsvError(
            "missing_columns", "Required columns are missing", missing
        )

    unknown = [h for h in normalized if h and h not in ALL_COLUMNS]
    if unknown:
        raise CatalogCsvError(
            "unknown_columns",
            "Unrecognized columns — fix the spelling or remove them",
            unknown,
        )
    return normalized


def _cell(raw_row: Dict[str, Any], column: str) -> str:
    value = raw_row.get(column)
    if value is None:
        return ""
    if isinstance(value, list):  # only possible for the restkey
        return " ".join(str(v) for v in value).strip()
    return str(value).strip()


def _validate_text(
    row: ParsedRow, column: str, value: str, max_len: int, *, required: bool
) -> None:
    if not value:
        if required:
            _err(row, column, "required_missing", f"{column} is required")
        return
    if len(value) > max_len:
        _err(
            row,
            column,
            "too_long",
            f"{column} must be at most {max_len} characters",
        )
        return
    row.data[column] = value


def _validate_slug(row: ParsedRow, column: str, value: str) -> None:
    if not value:
        _err(row, column, "required_missing", f"{column} is required")
        return
    lowered = value.lower()
    if not _SLUG_RE.match(lowered):
        _err(
            row,
            column,
            "slug_invalid",
            f"{column} must be lowercase letters, digits and single hyphens",
        )
        return
    if len(lowered) > MAX_NAME_LEN:
        _err(row, column, "too_long", f"{column} is too long")
        return
    row.data[column] = lowered


def _validate_price(row: ParsedRow, value: str) -> None:
    if not value:
        _err(row, "base_price", "required_missing", "base_price is required")
        return
    try:
        price = float(value)
    except ValueError:
        _err(row, "base_price", "price_invalid", "base_price must be a number")
        return
    if price != price or price in (float("inf"), float("-inf")):
        _err(row, "base_price", "price_invalid", "base_price must be a number")
        return
    if price <= 0 or price > MAX_PRICE:
        _err(
            row,
            "base_price",
            "price_invalid",
            f"base_price must be > 0 and <= {int(MAX_PRICE)}",
        )
        return
    row.data["base_price"] = price


def _validate_sort_order(row: ParsedRow, column: str, value: str) -> None:
    if not value:
        return
    try:
        order = int(value)
    except ValueError:
        _err(row, column, "sort_order_invalid", f"{column} must be a whole number")
        return
    if order < 0:
        _err(row, column, "sort_order_invalid", f"{column} must be >= 0")
        return
    row.data[column] = order


def _validate_image_url(row: ParsedRow, value: str) -> None:
    if not value:
        return
    if len(value) > MAX_URL_LEN:
        _err(
            row,
            "product_image_url",
            "too_long",
            f"product_image_url must be at most {MAX_URL_LEN} characters",
        )
        return
    if not _HTTP_URL_RE.match(value):
        _err(
            row,
            "product_image_url",
            "image_url_invalid",
            "product_image_url must start with http:// or https://",
        )
        return
    row.data["product_image_url"] = value


def _validate_translations(row: ParsedRow, raw_row: Dict[str, Any]) -> None:
    """Optional per-language product columns.

    ``MasterProductTranslation.name`` is NOT NULL, so a description with no name
    cannot be written — that is an error rather than a silently dropped cell.
    """
    for lang in TRANSLATABLE_LANGS:
        name_col = f"product_name_{lang}"
        desc_col = f"product_desc_{lang}"
        name = _cell(raw_row, name_col)
        desc = _cell(raw_row, desc_col)
        if desc and not name:
            _err(
                row,
                desc_col,
                "lang_name_missing",
                f"{desc_col} needs {name_col} as well",
            )
            continue
        _validate_text(row, name_col, name, MAX_NAME_LEN, required=False)
        _validate_text(row, desc_col, desc, MAX_DESCRIPTION_LEN, required=False)


def _validate_row(line_number: int, raw_row: Dict[str, Any]) -> ParsedRow:
    row = ParsedRow(line_number=line_number)

    if raw_row.get(_RESTKEY):
        _err(
            row,
            _RESTKEY,
            "too_many_fields",
            "Row has more cells than the header has columns",
        )

    for level in LEVELS:
        _validate_slug(row, f"{level}_slug", _cell(raw_row, f"{level}_slug"))
        _validate_text(
            row,
            f"{level}_name",
            _cell(raw_row, f"{level}_name"),
            MAX_NAME_LEN,
            required=True,
        )

    for level in ("service", "category", "subcategory"):
        _validate_text(
            row,
            f"{level}_description",
            _cell(raw_row, f"{level}_description"),
            MAX_DESCRIPTION_LEN,
            required=False,
        )
        _validate_sort_order(
            row, f"{level}_sort_order", _cell(raw_row, f"{level}_sort_order")
        )

    _validate_text(
        row,
        "product_description",
        _cell(raw_row, "product_description"),
        MAX_DESCRIPTION_LEN,
        required=False,
    )
    _validate_text(row, "brand", _cell(raw_row, "brand"), MAX_SHORT_TEXT_LEN, required=False)
    _validate_text(row, "unit", _cell(raw_row, "unit"), MAX_SHORT_TEXT_LEN, required=False)
    _validate_price(row, _cell(raw_row, "base_price"))
    _validate_image_url(row, _cell(raw_row, "product_image_url"))
    _validate_translations(row, raw_row)

    return row


# ─── Cross-row (in-file) checks ────────────────────────────────

# Fields that make up a parent's definition, per level. Two rows supplying
# different non-empty values for the same field is a conflict; one row omitting
# a field the other supplies is not (the supplied value simply wins).
_PARENT_FIELDS: Dict[str, Tuple[str, ...]] = {
    "service": ("service_name", "service_description", "service_sort_order"),
    "category": ("category_name", "category_description", "category_sort_order"),
    "subcategory": (
        "subcategory_name",
        "subcategory_description",
        "subcategory_sort_order",
    ),
}


def _parent_key(row: ParsedRow, level: str) -> Optional[Tuple[str, ...]]:
    """Slug path identifying a parent, or None if any part failed validation."""
    order = {"service": 1, "category": 2, "subcategory": 3}[level]
    parts: List[str] = []
    for lvl in LEVELS[:order]:
        slug = row.data.get(f"{lvl}_slug")
        if not isinstance(slug, str):
            return None
        parts.append(slug)
    return tuple(parts)


def _check_cross_row(rows: List[ParsedRow]) -> None:
    """Flag duplicate product paths and contradictory parent definitions."""
    seen_products: Dict[Tuple[str, ...], int] = {}
    parent_defs: Dict[Tuple[str, Tuple[str, ...]], Dict[str, Tuple[Any, int]]] = {}

    for row in rows:
        for level, fields in _PARENT_FIELDS.items():
            key = _parent_key(row, level)
            if key is None:
                continue
            defs = parent_defs.setdefault((level, key), {})
            for fname in fields:
                if fname not in row.data:
                    continue
                value = row.data[fname]
                prior = defs.get(fname)
                if prior is None:
                    defs[fname] = (value, row.line_number)
                elif prior[0] != value:
                    _err(
                        row,
                        fname,
                        "parent_conflict",
                        (
                            f"{fname} for {level} '{key[-1]}' conflicts with "
                            f"row {prior[1]} ({prior[0]!r} vs {value!r})"
                        ),
                    )

        product_key = _parent_key(row, "subcategory")
        product_slug = row.data.get("product_slug")
        if product_key is None or not isinstance(product_slug, str):
            continue
        full = (*product_key, product_slug)
        prior_line = seen_products.get(full)
        if prior_line is not None:
            _err(
                row,
                "product_slug",
                "duplicate_product",
                f"Same product path already appears on row {prior_line}",
            )
        else:
            seen_products[full] = row.line_number


def parse_catalog_csv(raw: bytes) -> List[ParsedRow]:
    """Decode, validate the header, then validate every data row.

    Raises :class:`CatalogCsvError` for file-level problems. Row-level problems
    ride along on each :class:`ParsedRow`, so one upload reports every bad line.
    """
    text = _decode(raw)
    reader = csv.DictReader(io.StringIO(text), restkey=_RESTKEY)
    header = _read_header(reader)
    reader.fieldnames = header  # normalized (stripped + lowercased)

    rows: List[ParsedRow] = []
    for index, raw_row in enumerate(reader, start=1):
        if index > MAX_ROWS:
            raise CatalogCsvError(
                "row_limit", f"File must contain at most {MAX_ROWS} rows"
            )
        # Skip fully blank lines — trailing newlines and spreadsheet padding
        # should not each become an error row.
        if not any(_cell(raw_row, c) for c in ALL_COLUMNS):
            continue
        rows.append(_validate_row(index, raw_row))

    if not rows:
        raise CatalogCsvError("empty_file", "File contains no data rows")

    _check_cross_row(rows)
    return rows


def template_csv() -> str:
    """Header plus one illustrative row, served by the template endpoint."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(ALL_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "service_slug": "grocery",
            "service_name": "Grocery",
            "service_description": "Everyday household groceries",
            "service_sort_order": 0,
            "category_slug": "fruits-vegetables",
            "category_name": "Fruits & Vegetables",
            "category_description": "Fresh produce",
            "category_sort_order": 0,
            "subcategory_slug": "fresh-fruits",
            "subcategory_name": "Fresh Fruits",
            "subcategory_description": "Seasonal fruit",
            "subcategory_sort_order": 0,
            "product_slug": "banana-robusta-1kg",
            "product_name": "Banana Robusta 1kg",
            "product_description": "Fresh robusta bananas",
            "base_price": "60",
            "brand": "Local Farm",
            "unit": "kg",
            "product_image_url": "https://example.com/banana.jpg",
            "product_name_hi": "केला रोबस्टा 1 किग्रा",
            "product_desc_hi": "ताज़े रोबस्टा केले",
        }
    )
    return buf.getvalue()
