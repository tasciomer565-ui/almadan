"""cache_get_latest: tazelik expires_at'ten, yas created_at'ten."""
from datetime import datetime, timedelta, timezone
from unittest import mock

import app.cache as cache


def _row(created_ago_h: float, expires_in_h: float):
    now = datetime.now(timezone.utc)
    return [{
        "products": [{"title": "x", "url": "u"}],
        "created_at": (now - timedelta(hours=created_ago_h)).isoformat(),
        "expires_at": (now + timedelta(hours=expires_in_h)).isoformat(),
    }]


def _latest(rows):
    resp = mock.Mock(ok=True, status_code=200)
    resp.json.return_value = rows
    with mock.patch.object(cache, "_enabled", return_value=True), \
         mock.patch.object(cache.requests, "get", return_value=resp):
        return cache.cache_get_latest("k|GENEL")


def test_long_ttl_record_is_fresh_with_real_age():
    # 48 saat TTL ile 5 saat once yazilmis kayit
    _, fresh, age = _latest(_row(created_ago_h=5, expires_in_h=43))
    assert fresh is True
    assert 4.9 < age < 5.1


def test_expired_record_is_stale_with_real_age():
    _, fresh, age = _latest(_row(created_ago_h=30, expires_in_h=-24))
    assert fresh is False
    assert 29.9 < age < 30.1


def test_legacy_record_with_ancient_created_at_falls_back_to_expiry():
    # Eski kayit: created_at haftalar once, expires 1 saat once dolmus (TTL 6)
    _, fresh, age = _latest(_row(created_ago_h=24 * 30, expires_in_h=-1))
    assert fresh is False
    assert 6.9 < age < 7.1


def test_no_row_returns_none():
    assert _latest([]) is None


def test_cache_set_writes_created_at_ttl_and_on_conflict():
    resp = mock.Mock(ok=True, status_code=201)
    with mock.patch.object(cache, "_enabled", return_value=True), \
         mock.patch.object(cache.requests, "post", return_value=resp) as post:
        cache.cache_set("k|GENEL", "k", "GENEL", [{"title": "x"}], ttl_hours=48)
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert "on_conflict=cache_key" in url
    created = datetime.fromisoformat(payload["created_at"])
    expires = datetime.fromisoformat(payload["expires_at"])
    assert abs((expires - created).total_seconds() - 48 * 3600) < 5
