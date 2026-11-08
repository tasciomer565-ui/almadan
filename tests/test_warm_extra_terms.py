"""Ek önbellek ısıtma terimleri ve ısıtma betiğinin aday seçimi."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.brands import BRANDS
from app.warm_extra_terms import POPULAR_MODEL_TERMS, extra_warm_terms

ROOT = Path(__file__).resolve().parent.parent


def _load_warm_script():
    spec = importlib.util.spec_from_file_location("warm_price_cache_under_test", ROOT / "scripts" / "warm_price_cache.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extra_terms_unique_and_cover_models_and_brands():
    terms = extra_warm_terms()
    assert len(terms) == len(set(terms))
    assert "iphone 15" in terms and "samsung galaxy s24" in terms
    for meta in BRANDS.values():
        assert meta["name"].lower() in terms
    assert set(POPULAR_MODEL_TERMS) <= set(terms)


def test_pick_terms_includes_extras_first_and_skips_fresh():
    warm = _load_warm_script()
    picked = warm.pick_terms({}, limit=10_000)
    extra_items = [c for c in picked if c["slug"].startswith("x:")]
    assert extra_items, "ek terimler aday listesine girmedi"
    # En yüksek öncelik: ek terimler listenin başında.
    first_non_extra = next(i for i, c in enumerate(picked) if not c["slug"].startswith("x:"))
    assert all(c["slug"].startswith("x:") for c in picked[:first_non_extra])
    assert len({c["key"] for c in picked}) == len(picked)  # aynı anahtar iki kez taranmaz

    # Taze kayıt (>6 saat ömrü kalmış) atlanmalı.
    target = extra_items[0]
    fresh = {target["key"]: datetime.now(timezone.utc) + timedelta(hours=40)}
    again = warm.pick_terms(fresh, limit=10_000)
    assert target["key"] not in {c["key"] for c in again}
