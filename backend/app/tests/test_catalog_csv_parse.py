# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pure parser/validator tests for the catalog CSV importer.

No DB fixtures — `services/catalog_csv.py` is deliberately DB-free so these
rules are testable from bytes alone.
"""

import csv
import io

import pytest

from app.services.catalog_csv import (
    ALL_COLUMNS,
    MAX_ROWS,
    REQUIRED_COLUMNS,
    CatalogCsvError,
    parse_catalog_csv,
    template_csv,
)

BASE_ROW = {
    "service_slug": "grocery",
    "service_name": "Grocery",
    "category_slug": "fruits",
    "category_name": "Fruits",
    "subcategory_slug": "fresh-fruits",
    "subcategory_name": "Fresh Fruits",
    "product_slug": "banana-1kg",
    "product_name": "Banana 1kg",
    "base_price": "60",
}


def build_csv(rows: list[dict[str, object]], columns: list[str] | None = None) -> bytes:
    fieldnames = columns or list(ALL_COLUMNS)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")


def row(**overrides: object) -> dict[str, object]:
    return {**BASE_ROW, **overrides}


# ─── File-level failures ───────────────────────────────────────


def test_missing_required_columns_lists_them() -> None:
    raw = build_csv([row()], columns=["service_slug", "service_name"])
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(raw)
    assert exc.value.code == "missing_columns"
    assert "base_price" in exc.value.columns
    assert "product_slug" in exc.value.columns


def test_unknown_column_is_a_file_error_not_a_silent_ignore() -> None:
    """A typo'd `base_prices` must not import every product at the wrong price."""
    columns = [*REQUIRED_COLUMNS, "base_prices"]
    raw = build_csv([row(base_prices="99")], columns=columns)
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(raw)
    assert exc.value.code == "unknown_columns"
    assert exc.value.columns == ["base_prices"]


def test_duplicate_column_rejected() -> None:
    raw = b"service_slug,service_slug\na,b\n"
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(raw)
    assert exc.value.code == "duplicate_columns"


def test_header_only_file_is_empty() -> None:
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(build_csv([]))
    assert exc.value.code == "empty_file"


def test_no_header_at_all() -> None:
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(b"")
    assert exc.value.code == "empty_file"


def test_non_utf8_rejected() -> None:
    raw = build_csv([row()]).replace(b"Grocery", b"Gr\xf8cery")
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(raw)
    assert exc.value.code == "encoding_invalid"


def test_row_limit_enforced() -> None:
    rows = [row(product_slug=f"p-{i}") for i in range(MAX_ROWS + 1)]
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(build_csv(rows))
    assert exc.value.code == "row_limit"


def test_oversize_file_rejected() -> None:
    with pytest.raises(CatalogCsvError) as exc:
        parse_catalog_csv(b"x" * (5 * 1024 * 1024 + 1))
    assert exc.value.code == "file_too_large"


# ─── Tolerances ────────────────────────────────────────────────


def test_bom_and_crlf_and_padded_header_tolerated() -> None:
    """Excel's "CSV UTF-8" writes a BOM and CRLF; headers often carry spaces."""
    header = ",".join(f" {c.upper()} " for c in ALL_COLUMNS)
    values = ",".join(str(row().get(c, "")) for c in ALL_COLUMNS)
    raw = ("﻿" + header + "\r\n" + values + "\r\n").encode("utf-8")
    parsed = parse_catalog_csv(raw)
    assert len(parsed) == 1
    assert parsed[0].ok, parsed[0].errors
    assert parsed[0].data["service_slug"] == "grocery"


def test_blank_lines_are_skipped_not_reported() -> None:
    raw = build_csv([row()]) + b"\n,,,,,,,,\n\n"
    parsed = parse_catalog_csv(raw)
    assert len(parsed) == 1


def test_quoted_comma_in_name_survives() -> None:
    parsed = parse_catalog_csv(build_csv([row(category_name="Fruits, Veg & More")]))
    assert parsed[0].ok, parsed[0].errors
    assert parsed[0].data["category_name"] == "Fruits, Veg & More"


def test_blank_optional_cells_are_absent_not_empty_string() -> None:
    """Apply must be able to tell "leave alone" from "set to empty"."""
    parsed = parse_catalog_csv(build_csv([row()]))
    assert "brand" not in parsed[0].data
    assert "product_description" not in parsed[0].data


def test_line_numbers_are_data_relative() -> None:
    parsed = parse_catalog_csv(
        build_csv([row(product_slug="a"), row(product_slug="b")])
    )
    assert [p.line_number for p in parsed] == [1, 2]


# ─── Row-level field validation ────────────────────────────────


@pytest.mark.parametrize(
    "bad_slug",
    ["gro cery", "grocery-", "-grocery", "gro--cery", "gro_cery", "grocery!", "grócery"],
)
def test_slug_must_be_kebab_case(bad_slug: str) -> None:
    parsed = parse_catalog_csv(build_csv([row(service_slug=bad_slug)]))
    codes = {e["code"] for e in parsed[0].errors}
    assert "slug_invalid" in codes


def test_uppercase_slug_is_normalized_not_rejected() -> None:
    """Matches `create_product_admin`, which lowercases a supplied slug — so
    `Grocery` and `grocery` must resolve to the same path rather than one of
    them being an error."""
    parsed = parse_catalog_csv(build_csv([row(service_slug="Grocery")]))
    assert parsed[0].ok, parsed[0].errors
    assert parsed[0].data["service_slug"] == "grocery"


def test_blank_required_cell_reported_per_column() -> None:
    parsed = parse_catalog_csv(build_csv([row(product_name="", product_slug="")]))
    by_column = {e["column"]: e["code"] for e in parsed[0].errors}
    assert by_column["product_name"] == "required_missing"
    assert by_column["product_slug"] == "required_missing"


@pytest.mark.parametrize("bad_price", ["", "abc", "0", "-5", "1000000", "nan", "inf"])
def test_base_price_bounds(bad_price: str) -> None:
    parsed = parse_catalog_csv(build_csv([row(base_price=bad_price)]))
    codes = {e["code"] for e in parsed[0].errors}
    assert codes & {"price_invalid", "required_missing"}


def test_base_price_parsed_as_float() -> None:
    parsed = parse_catalog_csv(build_csv([row(base_price="123.45")]))
    assert parsed[0].ok
    assert parsed[0].data["base_price"] == pytest.approx(123.45)


@pytest.mark.parametrize("bad", ["-1", "1.5", "abc"])
def test_sort_order_must_be_non_negative_int(bad: str) -> None:
    parsed = parse_catalog_csv(build_csv([row(service_sort_order=bad)]))
    codes = {e["code"] for e in parsed[0].errors}
    assert "sort_order_invalid" in codes


@pytest.mark.parametrize("bad_url", ["example.com/x.jpg", "ftp://x/y.jpg", "/media/x.jpg"])
def test_image_url_must_be_http(bad_url: str) -> None:
    parsed = parse_catalog_csv(build_csv([row(product_image_url=bad_url)]))
    codes = {e["code"] for e in parsed[0].errors}
    assert "image_url_invalid" in codes


def test_overlong_name_reported() -> None:
    parsed = parse_catalog_csv(build_csv([row(product_name="x" * 201)]))
    codes = {e["code"] for e in parsed[0].errors}
    assert "too_long" in codes


def test_translation_description_without_name_is_an_error() -> None:
    """MasterProductTranslation.name is NOT NULL — a bare description cannot
    be written, so it must not be silently dropped."""
    parsed = parse_catalog_csv(build_csv([row(product_desc_hi="ताज़े केले")]))
    by_column = {e["column"]: e["code"] for e in parsed[0].errors}
    assert by_column["product_desc_hi"] == "lang_name_missing"


def test_translation_name_alone_is_fine() -> None:
    parsed = parse_catalog_csv(build_csv([row(product_name_hi="केला")]))
    assert parsed[0].ok, parsed[0].errors
    assert parsed[0].data["product_name_hi"] == "केला"


def test_extra_cells_beyond_header_reported() -> None:
    raw = build_csv([row()]).rstrip(b"\n") + b",surprise\n"
    parsed = parse_catalog_csv(raw)
    codes = {e["code"] for e in parsed[0].errors}
    assert "too_many_fields" in codes


# ─── Cross-row (in-file) checks ────────────────────────────────


def test_duplicate_product_path_flagged_on_later_row() -> None:
    parsed = parse_catalog_csv(build_csv([row(), row()]))
    assert parsed[0].ok
    by_column = {e["column"]: e for e in parsed[1].errors}
    assert by_column["product_slug"]["code"] == "duplicate_product"
    assert "row 1" in by_column["product_slug"]["message"]


def test_same_product_slug_in_different_subcategory_is_allowed() -> None:
    """Product uniqueness is per-subcategory, so this is two distinct products."""
    parsed = parse_catalog_csv(
        build_csv(
            [
                row(),
                row(subcategory_slug="dried-fruits", subcategory_name="Dried Fruits"),
            ]
        )
    )
    assert all(p.ok for p in parsed), [p.errors for p in parsed]


def test_conflicting_parent_name_flagged() -> None:
    parsed = parse_catalog_csv(
        build_csv(
            [
                row(product_slug="a"),
                row(product_slug="b", category_name="Fruits & Veg"),
            ]
        )
    )
    assert parsed[0].ok
    by_column = {e["column"]: e for e in parsed[1].errors}
    assert by_column["category_name"]["code"] == "parent_conflict"
    assert "row 1" in by_column["category_name"]["message"]


def test_parent_field_supplied_on_only_one_row_is_not_a_conflict() -> None:
    """Omitting a field is "leave alone", so the supplying row simply wins."""
    parsed = parse_catalog_csv(
        build_csv(
            [
                row(product_slug="a"),
                row(product_slug="b", category_description="Fresh produce"),
            ]
        )
    )
    assert all(p.ok for p in parsed), [p.errors for p in parsed]


def test_same_category_slug_under_two_services_is_not_a_conflict() -> None:
    parsed = parse_catalog_csv(
        build_csv(
            [
                row(),
                row(service_slug="pharmacy", service_name="Pharmacy", category_name="Fruit Supplements"),
            ]
        )
    )
    assert all(p.ok for p in parsed), [p.errors for p in parsed]


# ─── Template ──────────────────────────────────────────────────


def test_template_is_a_valid_single_row_import() -> None:
    parsed = parse_catalog_csv(template_csv().encode("utf-8"))
    assert len(parsed) == 1
    assert parsed[0].ok, parsed[0].errors


def test_template_header_matches_column_spec() -> None:
    header = template_csv().splitlines()[0].split(",")
    assert header == list(ALL_COLUMNS)
