"""app_state tek JSON satiri: eszamanli yazmalar birbirini silmemeli (3 yonlu birlestirme)."""
import json
from unittest import mock

import app.storage as storage
from app.storage import merge_three_way


def test_unchanged_side_takes_other():
    base = {"users": {"a": 1}}
    assert merge_three_way(base, base, {"users": {"a": 1, "b": 2}}) == {"users": {"a": 1, "b": 2}}


def test_both_add_different_users_keeps_both():
    base = {"users": {"a": {"email": "a"}}}
    mine = {"users": {"a": {"email": "a"}, "b": {"email": "b"}}}
    theirs = {"users": {"a": {"email": "a"}, "c": {"email": "c"}}}
    assert set(merge_three_way(base, mine, theirs)["users"]) == {"a", "b", "c"}


def test_deletion_by_me_is_kept_and_their_unrelated_edit_too():
    base = {"users": {"a": 1, "b": 1}}
    mine = {"users": {"a": 1}}               # b'yi sildim
    theirs = {"users": {"a": 2, "b": 1}}      # onlar a'yi degistirdi
    assert merge_three_way(base, mine, theirs) == {"users": {"a": 2}}


def test_list_items_with_id_are_merged_by_id():
    base = {"products": [{"id": "p1", "price": 10}]}
    mine = {"products": [{"id": "p1", "price": 10}, {"id": "p2", "price": 5}]}       # ekledim
    theirs = {"products": [{"id": "p1", "price": 9}, {"id": "p3", "price": 7}]}      # guncelledi + ekledi
    out = merge_three_way(base, mine, theirs)["products"]
    assert [p["id"] for p in out] == ["p1", "p3", "p2"]
    assert out[0]["price"] == 9


def test_same_field_conflict_mine_wins():
    base = {"users": {"a": {"phone": "1"}}}
    assert merge_three_way(base, {"users": {"a": {"phone": "2"}}},
                           {"users": {"a": {"phone": "3"}}})["users"]["a"]["phone"] == "2"


def _resp(data):
    r = mock.Mock(status_code=200)
    r.raise_for_status = lambda: None
    r.json.return_value = [{"data": data}]
    r.text = json.dumps([{"data": data}])
    return r


def test_concurrent_saves_do_not_lose_each_others_users():
    """Iki istek ayni hali okuyup farkli kullanici ekliyor; ikisi de kalmali."""
    remote = {"data": storage.normalize_db({"users": {"a": {}}})}

    def fake_get(*_a, **_k):
        return _resp(json.loads(json.dumps(remote["data"])))

    def fake_post(*_a, **kw):
        remote["data"] = json.loads(json.dumps(kw["json"]["data"]))
        r = mock.Mock(); r.raise_for_status = lambda: None
        return r

    with mock.patch.object(storage, "supabase_enabled", return_value=True), \
         mock.patch.object(storage, "supabase_base_url", return_value="https://x"), \
         mock.patch.object(storage.requests, "get", side_effect=fake_get), \
         mock.patch.object(storage.requests, "post", side_effect=fake_post):
        req1 = storage.load_db()
        req2 = storage.load_db()
        req1["users"]["b"] = {"email": "b"}
        req2["users"]["c"] = {"email": "c"}
        storage.save_db(req1)
        storage.save_db(req2)          # eskiden req1'in "b"sini siliyordu
        assert set(remote["data"]["users"]) == {"a", "b", "c"}
        # ayni nesne tekrar kaydedilirse de sorun yok
        req2["users"]["d"] = {}
        storage.save_db(req2)
        assert set(remote["data"]["users"]) == {"a", "b", "c", "d"}
