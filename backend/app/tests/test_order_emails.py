# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("task_name,args", [
    ("send_order_placed_seller_async", (1,)),
    ("send_order_confirmed_customer_async", ([1, 2],)),
    ("send_order_status_changed_async", (1, "packed", "customer")),
    ("send_order_status_changed_async", (1, "cancelled", "seller")),
])
def test_email_tasks_callable_in_console_mode(task_name: str, args: tuple[Any, ...]) -> None:
    from app import worker
    with patch("app.core.config.settings.EMAIL_PROVIDER", "console"):
        fn = getattr(worker, task_name)
        result = fn(*args)
    assert result is None
