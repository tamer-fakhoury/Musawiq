"""Canonical downloadable import templates."""

from __future__ import annotations

SALES_TEMPLATE_CSV = (
    "product_id,product_name,order_date,quantity,sales_amount,order_id,currency,sku\n"
    "prod-001,Classic T-Shirt,2026-01-15,2,49.90,order-1001,USD,TSHIRT-BLK-M\n"
)


def template_bytes() -> bytes:
    return SALES_TEMPLATE_CSV.encode("utf-8")


__all__ = ["SALES_TEMPLATE_CSV", "template_bytes"]
