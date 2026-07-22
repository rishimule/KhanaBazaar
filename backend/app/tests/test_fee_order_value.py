# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for the Order Value % (postpaid + security deposit) fee model."""
from datetime import date

from app.models.platform_fee import (
    FeeArrangement,
    FeeInvoice,
    InvoiceStatus,
    ServiceFeeConfig,
)


def test_invoice_model_and_enum_shape() -> None:
    assert {s.value for s in InvoiceStatus} == {
        "pending",
        "paid",
        "overdue",
        "waived",
        "cancelled",
    }
    inv = FeeInvoice(
        arrangement_id=1,
        store_id=1,
        service_id=1,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        sales_total=5000.0,
        fee_percent_snapshot=2.0,
        amount_due=100.0,
        status=InvoiceStatus.Pending,
        issued_on=date(2026, 2, 5),
        due_date=date(2026, 2, 12),
        suspend_after=date(2026, 2, 14),
    )
    assert inv.amount_due == 100.0
    assert inv.status == InvoiceStatus.Pending

    # new config + arrangement columns exist with expected defaults
    assert ServiceFeeConfig(service_id=1).order_value_payment_days == 7
    arr_fields = FeeArrangement.model_fields
    assert "order_value_activated_on" in arr_fields
    assert "last_billed_period_end" in arr_fields
