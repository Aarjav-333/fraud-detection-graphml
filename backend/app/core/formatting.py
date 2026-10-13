"""Formatting shared by notifications and emails."""
from datetime import datetime


def format_inr(amount: float) -> str:
    """Rupees with Indian digit grouping: 125000 -> '₹1,25,000', 99.5 -> '₹99.50'."""
    negative = amount < 0
    rupees, paise = divmod(round(abs(amount) * 100), 100)
    digits = str(int(rupees))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    text = "₹" + digits + (f".{paise:02d}" if paise else "")
    return "-" + text if negative else text


def format_timestamp(value: datetime | None) -> str:
    """'13 Oct 2026, 14:05 UTC' - transactions are recorded in UTC."""
    return value.strftime("%d %b %Y, %H:%M UTC") if value else "—"
