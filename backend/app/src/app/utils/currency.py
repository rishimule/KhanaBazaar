# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Indian Rupee formatting helper.

Indian numbering groups digits as ``xx,xx,xxx.xx`` (lakh/crore), not the
Western ``xxx,xxx.xx``. ``locale.format_string`` is process-global and
unsafe to mutate in a server, so we group manually.
"""

from decimal import Decimal


def format_inr(value: float | Decimal) -> str:
    if value < 0:
        raise ValueError("format_inr does not support negative values")

    whole = int(value)
    paise = int(round((float(value) - whole) * 100))
    if paise == 100:
        whole += 1
        paise = 0

    whole_str = str(whole)
    if len(whole_str) <= 3:
        grouped = whole_str
    else:
        head, tail = whole_str[:-3], whole_str[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        grouped = ",".join(groups) + "," + tail

    return f"₹{grouped}.{paise:02d}"
