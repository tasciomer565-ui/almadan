from __future__ import annotations

import hashlib
from typing import Any

from app.comparator import extract_volume_info


MARKET_STORES = (
    "bim",
    "a101",
    "sok",
    "file",
    "metro",
    "carrefoursa",
    "migros",
)


def _base_price(name: str) -> float:
    lower = name.casefold()
    price_rules = (
        (("yag", "yağ"), 185.0),
        (("sut", "süt"), 32.0),
        (("peynir",), 92.0),
        (("un",), 78.0),
        (("cay", "çay"), 148.0),
        (("seker", "şeker"), 142.0),
        (("kahve",), 175.0),
        (("deterjan",), 225.0),
        (("yumurta",), 115.0),
    )
    for keywords, price in price_rules:
        if any(keyword in lower for keyword in keywords):
            return price
    return 55.0


def simulated_market_prices(name: str) -> dict[str, float]:
    """Return stable demo prices until licensed market feeds are connected."""
    base = _base_price(name)
    digest = hashlib.sha256(name.casefold().encode("utf-8")).digest()
    prices: dict[str, float] = {}
    for index, store in enumerate(MARKET_STORES):
        variance = 0.84 + ((digest[index] % 32) / 100)
        prices[store] = round(base * variance, 2)
    return prices


def normalize_offers(name: str, offers: dict[str, float] | None) -> dict[str, float]:
    generated = simulated_market_prices(name)
    if not offers:
        return generated

    normalized = generated.copy()
    for store, value in offers.items():
        store_key = store.casefold().strip()
        if store_key in MARKET_STORES and value is not None and float(value) > 0:
            normalized[store_key] = round(float(value), 2)
    return normalized


def calculate_unit_price(name: str, price: float) -> dict[str, Any] | None:
    amount, unit = extract_volume_info(name)
    if not amount or amount <= 0 or not unit:
        return None
    return {
        "amount": amount,
        "unit": unit,
        "unit_price": round(float(price) / amount, 2),
    }


def _best_coupon(
    store: str,
    subtotal: float,
    coupons: list[dict[str, Any]],
) -> dict[str, Any] | None:
    eligible = [
        coupon
        for coupon in coupons
        if coupon.get("active", True)
        and str(coupon.get("store", "")).casefold() == store
        and subtotal >= float(coupon.get("min_amount", 0) or 0)
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda item: float(item.get("discount", 0) or 0))


def _apply_coupon(
    store: str,
    subtotal: float,
    coupons: list[dict[str, Any]],
) -> tuple[float, dict[str, Any] | None]:
    coupon = _best_coupon(store, subtotal, coupons)
    if not coupon:
        return round(subtotal, 2), None
    discount = min(subtotal, float(coupon.get("discount", 0) or 0))
    applied = {
        "id": coupon.get("id"),
        "store": store,
        "code": coupon.get("code"),
        "discount": round(discount, 2),
        "min_amount": float(coupon.get("min_amount", 0) or 0),
    }
    return round(subtotal - discount, 2), applied


def optimize_market_basket(
    items: list[dict[str, Any]],
    coupons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    coupons = coupons or []
    normalized_items: list[dict[str, Any]] = []

    for index, item in enumerate(items):
        name = str(item.get("name") or item.get("title") or "").strip()
        if not name:
            continue
        quantity = max(1, int(item.get("quantity") or 1))
        offers = normalize_offers(name, item.get("offers"))
        normalized_items.append(
            {
                "id": item.get("id") or f"item-{index + 1}",
                "name": name,
                "quantity": quantity,
                "offers": offers,
            }
        )

    if not normalized_items:
        return {
            "items": [],
            "single_store": None,
            "split_basket": None,
            "baseline_total": 0.0,
        }

    single_options: list[dict[str, Any]] = []
    for store in MARKET_STORES:
        breakdown = []
        subtotal = 0.0
        for item in normalized_items:
            line_total = item["offers"][store] * item["quantity"]
            subtotal += line_total
            breakdown.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "unit_price": item["offers"][store],
                    "line_total": round(line_total, 2),
                }
            )
        total, coupon = _apply_coupon(store, subtotal, coupons)
        single_options.append(
            {
                "store": store,
                "subtotal": round(subtotal, 2),
                "total": total,
                "coupon": coupon,
                "items": breakdown,
            }
        )

    single_options.sort(key=lambda option: option["total"])
    best_single = single_options[0]
    baseline_total = max(option["total"] for option in single_options)
    best_single["savings"] = round(baseline_total - best_single["total"], 2)

    split_groups: dict[str, dict[str, Any]] = {}
    for item in normalized_items:
        store, unit_price = min(item["offers"].items(), key=lambda offer: offer[1])
        group = split_groups.setdefault(
            store,
            {"store": store, "subtotal": 0.0, "items": []},
        )
        line_total = unit_price * item["quantity"]
        group["subtotal"] += line_total
        group["items"].append(
            {
                "id": item["id"],
                "name": item["name"],
                "quantity": item["quantity"],
                "unit_price": unit_price,
                "line_total": round(line_total, 2),
                "unit_analysis": calculate_unit_price(item["name"], unit_price),
            }
        )

    split_total = 0.0
    applied_coupons = []
    groups = []
    for store in sorted(split_groups):
        group = split_groups[store]
        subtotal = round(group["subtotal"], 2)
        total, coupon = _apply_coupon(store, subtotal, coupons)
        group["subtotal"] = subtotal
        group["total"] = total
        group["coupon"] = coupon
        groups.append(group)
        split_total += total
        if coupon:
            applied_coupons.append(coupon)

    split_total = round(split_total, 2)
    return {
        "items": normalized_items,
        "single_store": {
            **best_single,
            "alternatives": single_options[1:],
        },
        "split_basket": {
            "stores": groups,
            "total": split_total,
            "savings": round(best_single["total"] - split_total, 2),
            "coupons": applied_coupons,
        },
        "baseline_total": round(baseline_total, 2),
    }
