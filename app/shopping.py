from __future__ import annotations

import hashlib
from typing import Any

from app.comparator import extract_volume_info


MARKET_STORES = (
    # 1. Zincir Marketler
    "bim", "a101", "sok", "hakmarekspres",
    "migros", "5mmigros", "migrosjet", "carrefoursa", "carrefoursagurme", "tarimkredi",
    "file", "macrocenter",
    "happycenter", "onurmarket", "mopas", "hakmar", "cagrimarket",
    "bizimtoptan", "metro", "secmarket",
    # 2. Teknoloji & Elektronik
    "teknosa", "mediamarkt", "vatanbilgisayar", "troy", "gurgencer", "pozitifteknoloji",
    "samsung", "huawei", "mistore", "evkur", "cetmen", "yigitavm", "ozsanal", "itopya",
    # 3. Kozmetik & Kişisel Bakım
    "gratis", "watsons", "rossmann", "eveshop", "sephora", "sevil", "yvesrocher",
    "flormar", "goldenrose", "mac", "kikomilano",
    # 4. Giyim, Ayakkabı & Moda
    "lcwaikiki", "defacto", "koton", "mavi", "ltb", "colins", "boyner", "ozdilek", "beymen", "vakko",
    "altinyildiz", "kigili", "sarar", "suvari", "hatemoglu", "tudors",
    "ipekyol", "twist", "machka", "penti",
    "zara", "bershka", "pullandbear", "stradivarius", "massimodutti", "hm", "mango",
    "flo", "instreet", "deichmann", "ayakkabidunyasi", "superstep", "sportive", "decathlon",
    # 5. Sağlık, Medikal & Optik
    "atasunoptik", "opmaroptik", "eleganceoptik", "mertoptik", "ebebek", "babymall", "joker", "gnc",
    # 6. Züccaciye, Ev Tekstili & Ev Yaşam
    "karaca", "pasabahce", "bernardo", "jumbo", "korkmaz", "schafer", "porland", "hisar",
    "englishhome", "madamecoco", "linens", "bellamaison", "karacahome",
    "ikea", "koctas", "koctasfix", "bauhaus", "tekzen",
    # E-Ticaret / Pazaryeri Ortakları (Arayüz uyumu için)
    "trendyol", "hepsiburada", "amazon", "n11", "supplementler", "proteinocean"
)

STORE_BRANCHES = {
    "besiktas": {
        "bim": 0.10,
        "a101": 0.11,
        "sok": 0.13,
        "file": 0.44,
        "carrefoursa": 0.38,
        "migros": 0.22,
        "metro": 3.80,
    },
    "kadikoy": {
        "bim": 0.10,
        "a101": 0.14,
        "sok": 0.15,
        "file": 0.90,
        "carrefoursa": 0.60,
        "migros": 0.24,
        "metro": 8.10,
    },
    "cankaya": {
        "bim": 0.10,
        "a101": 0.15,
        "sok": 0.12,
        "file": 1.20,
        "carrefoursa": 0.80,
        "migros": 0.25,
        "metro": 5.50,
    },
    "karsiyaka": {
        "bim": 0.10,
        "a101": 0.15,
        "sok": 0.13,
        "file": 999.00,
        "carrefoursa": 0.70,
        "migros": 0.23,
        "metro": 7.50,
    },
    "bodrum": {
        "bim": 0.20,
        "a101": 0.23,
        "sok": 0.32,
        "file": 999.00,
        "carrefoursa": 1.20,
        "migros": 0.45,
        "metro": 6.50,
    }
}

def get_store_distance(
    store: str,
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
) -> float:
    if location_name in STORE_BRANCHES:
        if store in STORE_BRANCHES[location_name]:
            return STORE_BRANCHES[location_name][store]
        # MD5 Hash stable fallback (stable distance between 0.1km and 3.1km)
        h = int(hashlib.md5(store.encode("utf-8")).hexdigest(), 16)
        return round(0.1 + (h % 30) / 10, 2)
    
    if lat is not None and lng is not None:
        # Define fixed offsets for each store brand to simulate branch coordinates
        offsets = {
            "bim": (0.001, -0.001), # ~150m
            "a101": (-0.0015, 0.001), # ~200m
            "sok": (0.002, 0.002), # ~300m
            "file": (-0.005, -0.004), # ~700m
            "carrefoursa": (0.008, 0.006), # ~1.1km
            "migros": (-0.003, 0.004), # ~500m
            "metro": (0.045, -0.035), # ~6.5km
        }
        if store in offsets:
            dlat, dlng = offsets[store]
        else:
            # MD5 Hash stable offset fallback
            h = int(hashlib.md5(store.encode("utf-8")).hexdigest(), 16)
            dlat = ((h % 50) - 25) / 10000.0  # -0.0025 to +0.0025
            dlng = (((h >> 8) % 50) - 25) / 10000.0
            
        import math
        R = 6371.0
        lat2 = lat + dlat
        lng2 = lng + dlng
        
        d_lat_rad = math.radians(lat2 - lat)
        d_lng_rad = math.radians(lng2 - lng)
        a = (math.sin(d_lat_rad / 2) ** 2 +
             math.cos(math.radians(lat)) * math.cos(math.radians(lat2)) *
             math.sin(d_lng_rad / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)
            
    return 0.0


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


def normalize_offers(name: str, offers: dict[str, float] | None) -> dict[str, float]:
    if not offers:
        return {}

    normalized: dict[str, float] = {}
    for store, value in offers.items():
        store_key = store.casefold().strip()
        if store_key in MARKET_STORES and value is not None and float(value) > 0:
            normalized[store_key] = round(float(value), 2)
    return normalized


def calculate_unit_price(name: str, price: float) -> dict[str, Any] | None:
    res = extract_volume_info(name)
    if not res:
        return None
    amount, unit = res
    if not amount or amount <= 0 or not unit:
        return None
    return {
        "amount": amount,
        "unit": unit,
        "unit_price": round(float(price) / amount, 2),
    }


SHIPPING_RULES = {
    "trendyol": (300.0, 40.0),
    "hepsiburada": (300.0, 40.0),
    "amazon": (0.0, 0.0),
    "n11": (200.0, 35.0),
    "supplementler": (250.0, 30.0),
    "proteinocean": (250.0, 30.0),
    "migros": (750.0, 50.0),
    "5mmigros": (750.0, 50.0),
    "migrosjet": (750.0, 50.0),
    "carrefoursa": (500.0, 45.0),
    "carrefoursagurme": (500.0, 45.0),
}


def get_shipping_fee(store: str, subtotal: float) -> float:
    if subtotal <= 0:
        return 0.0
    limit, fee = SHIPPING_RULES.get(store, (0.0, 0.0))
    if subtotal < limit:
        return fee
    return 0.0


def calculate_assignment_cost(assignment, normalized_items, allowed_stores):
    subtotals = {store: 0.0 for store in allowed_stores}
    for idx, item in enumerate(normalized_items):
        store = assignment[idx]
        subtotals[store] += item["offers"][store] * item["quantity"]
    
    total = 0.0
    for store, sub in subtotals.items():
        if sub > 0:
            total += sub + get_shipping_fee(store, sub)
    return total, subtotals


def optimize_market_basket(
    items: list[dict[str, Any]],
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
    max_distance: float | None = None,
) -> dict[str, Any]:
    normalized_items: list[dict[str, Any]] = []
    missing_items: list[dict[str, Any]] = []

    # Calculate store distances
    store_distances = {}
    for store in MARKET_STORES:
        store_distances[store] = get_store_distance(store, lat, lng, location_name)

    # Filter allowed stores based on max_distance
    allowed_stores = list(MARKET_STORES)
    distance_fallback_applied = False
    
    if max_distance is not None:
        filtered = [s for s in MARKET_STORES if store_distances[s] <= max_distance]
        if filtered:
            allowed_stores = filtered
        else:
            closest_store = min(MARKET_STORES, key=lambda s: store_distances[s])
            allowed_stores = [closest_store]
            distance_fallback_applied = True

    for index, item in enumerate(items):
        name = str(item.get("name") or item.get("title") or "").strip()
        if not name:
            continue
        quantity = max(1, int(item.get("quantity") or 1))
        offers = normalize_offers(name, item.get("offers"))
        if not offers:
            missing_items.append(
                {
                    "id": item.get("id") or f"item-{index + 1}",
                    "name": name,
                }
            )
            continue
        normalized_items.append(
            {
                "id": item.get("id") or f"item-{index + 1}",
                "name": name,
                "quantity": quantity,
                "offers": offers,
            }
        )

    if missing_items:
        return {
            "available": False,
            "price_source": "unavailable",
            "message": (
                "Bu ürünler için doğrulanmış canlı mağaza fiyatı bulunamadı. "
                "Tahmini fiyat gösterilmedi."
            ),
            "missing_items": missing_items,
            "items": normalized_items,
            "single_store": None,
            "split_basket": None,
            "baseline_total": 0.0,
            "store_distances": store_distances,
            "distance_fallback_applied": False,
        }

    if not normalized_items:
        return {
            "available": False,
            "price_source": "unavailable",
            "message": "Karşılaştırılacak ürün bulunamadı.",
            "missing_items": [],
            "items": [],
            "single_store": None,
            "split_basket": None,
            "baseline_total": 0.0,
            "store_distances": store_distances,
            "distance_fallback_applied": distance_fallback_applied,
        }

    common_stores = set(normalized_items[0]["offers"])
    for item in normalized_items[1:]:
        common_stores.intersection_update(item["offers"])
    allowed_stores = [store for store in allowed_stores if store in common_stores]

    if not allowed_stores:
        return {
            "available": False,
            "price_source": "provided_offers",
            "message": "Sepetteki tüm ürünleri birlikte satan ortak bir mağaza bulunamadı.",
            "missing_items": [],
            "items": normalized_items,
            "single_store": None,
            "split_basket": None,
            "baseline_total": 0.0,
            "store_distances": store_distances,
            "distance_fallback_applied": distance_fallback_applied,
        }

    single_options: list[dict[str, Any]] = []
    for store in allowed_stores:
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
        shipping_fee = get_shipping_fee(store, subtotal)
        total = round(subtotal + shipping_fee, 2)
        single_options.append(
            {
                "store": store,
                "subtotal": round(subtotal, 2),
                "shipping_fee": round(shipping_fee, 2),
                "total": total,
                "items": breakdown,
            }
        )

    single_options.sort(key=lambda option: option["total"])
    best_single = single_options[0]
    baseline_total = max(option["total"] for option in single_options)
    best_single["savings"] = round(baseline_total - best_single["total"], 2)

    # Hill-climbing assignment for split basket to minimize (subtotal + shipping)
    assignment = []
    for item in normalized_items:
        allowed_offers = {s: item["offers"][s] for s in allowed_stores}
        best_store = min(allowed_offers.items(), key=lambda x: x[1])[0]
        assignment.append(best_store)

    improved = True
    while improved:
        improved = False
        current_cost, _ = calculate_assignment_cost(assignment, normalized_items, allowed_stores)
        for idx, item in enumerate(normalized_items):
            current_store = assignment[idx]
            for other_store in allowed_stores:
                if other_store == current_store:
                    continue
                assignment[idx] = other_store
                new_cost, _ = calculate_assignment_cost(assignment, normalized_items, allowed_stores)
                if new_cost < current_cost - 0.01:
                    current_cost = new_cost
                    improved = True
                    break
                else:
                    assignment[idx] = current_store
            if improved:
                break

    # Construct split groups based on the optimized assignment
    split_groups: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(normalized_items):
        store = assignment[idx]
        unit_price = item["offers"][store]
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
    groups = []
    for store in sorted(split_groups):
        group = split_groups[store]
        subtotal = round(group["subtotal"], 2)
        shipping_fee = get_shipping_fee(store, subtotal)
        total = round(subtotal + shipping_fee, 2)
        group["subtotal"] = subtotal
        group["shipping_fee"] = round(shipping_fee, 2)
        group["total"] = total
        groups.append(group)
        split_total += total

    split_total = round(split_total, 2)
    return {
        "available": True,
        "price_source": "provided_offers",
        "message": None,
        "missing_items": [],
        "items": normalized_items,
        "single_store": {
            **best_single,
            "alternatives": single_options[1:],
        },
        "split_basket": {
            "stores": groups,
            "total": split_total,
            "savings": round(best_single["total"] - split_total, 2),
        },
        "baseline_total": round(baseline_total, 2),
        "store_distances": store_distances,
        "distance_fallback_applied": distance_fallback_applied,
    }
