from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_FILE = DATA_DIR / "db.json"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().strip("\"'").rstrip("/")
SUPABASE_KEY = "".join(
    os.getenv("SUPABASE_SERVICE_KEY", "").strip().strip("\"'").split()
)
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "app_state")
STATE_ID = "main"


class StorageError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db() -> dict[str, Any]:
    return {
        "products": [],
        "notifications": [],
        "password_reset_attempts": {},
        "push_subscriptions": [],
        "users": {},
        "shared_lists": {},
        "queued_notifications": [],
        "catalog_snapshots": {},
        "receipts": [],
    }


def normalize_db(db: Any) -> dict[str, Any]:
    if not isinstance(db, dict):
        db = default_db()
    if not isinstance(db.get("products"), list):
        db["products"] = []
    if not isinstance(db.get("notifications"), list):
        db["notifications"] = []
    if not isinstance(db.get("password_reset_attempts"), dict):
        db["password_reset_attempts"] = {}
    if not isinstance(db.get("push_subscriptions"), list):
        db["push_subscriptions"] = []
    if not isinstance(db.get("users"), dict):
        db["users"] = {}
    if not isinstance(db.get("shared_lists"), dict):
        db["shared_lists"] = {}
    if not isinstance(db.get("queued_notifications"), list):
        db["queued_notifications"] = []
    if not isinstance(db.get("catalog_snapshots"), dict):
        db["catalog_snapshots"] = {}
    if not isinstance(db.get("receipts"), list):
        db["receipts"] = []
    return db


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_base_url() -> str:
    url = SUPABASE_URL
    if url.startswith("SUPABASE_URL="):
        url = url.split("=", 1)[1].strip().strip("\"'")

    for suffix in ("/rest/v1", "/rest/v1/"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]

    if not url.startswith(("https://", "http://")):
        raise StorageError(
            "SUPABASE_URL geçersiz. Değer https://...supabase.co biçiminde olmalı."
        )

    return url.rstrip("/")


def supabase_project_ref() -> str | None:
    host = supabase_base_url().split("://", 1)[-1].split("/", 1)[0]
    suffix = ".supabase.co"
    return host[: -len(suffix)] if host.endswith(suffix) else None


def service_key_claims() -> dict[str, Any]:
    if not SUPABASE_KEY.startswith("eyJ"):
        return {}

    try:
        payload = SUPABASE_KEY.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def authorization_error_message() -> str:
    expected_ref = supabase_project_ref()
    claims = service_key_claims()
    key_ref = claims.get("ref")
    role = claims.get("role")

    if expected_ref and key_ref and expected_ref != key_ref:
        return (
            "Supabase URL ile service_role anahtarı farklı projelere ait. "
            f"URL proje kodu: {expected_ref}; anahtar proje kodu: {key_ref}."
        )
    if role and role != "service_role":
        return (
            "SUPABASE_SERVICE_KEY alanına service_role yerine "
            f"{role} anahtarı girilmiş."
        )
    return (
        "Supabase service_role anahtarı reddedildi. Anahtar eksik kopyalanmış, "
        "yenilenmiş veya bu projeye ait olmayabilir."
    )


def storage_diagnostics() -> dict[str, Any]:
    try:
        key_str = str(SUPABASE_KEY or "")
        if key_str.startswith("sb_secret_"):
            key_type = "sb_secret"
        elif key_str.startswith("eyJ"):
            key_type = "legacy_jwt"
        elif key_str:
            key_type = "unknown"
        else:
            key_type = "missing"
    except Exception:
        key_type = "error"

    try:
        project_ref = supabase_project_ref() if SUPABASE_URL else None
    except Exception as exc:
        project_ref = f"Error: {exc}"

    return {
        "project_ref": project_ref,
        "key_type": key_type,
        "key_length": len(SUPABASE_KEY) if SUPABASE_KEY else 0,
        "table": SUPABASE_TABLE,
    }


def supabase_headers() -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Almadan-Backend/1.0",
    }
    if SUPABASE_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers


def load_local_db() -> dict[str, Any]:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Vercel gibi salt-okunur ortamlarda klasör oluşturma hatasını yoksay
        pass

    if not DB_FILE.exists():
        return default_db()

    try:
        with DB_FILE.open("r", encoding="utf-8") as f:
            return normalize_db(json.load(f))
    except OSError:
        return default_db()


def load_supabase_db() -> dict[str, Any]:
    try:
        response = requests.get(
            f"{supabase_base_url()}/rest/v1/{SUPABASE_TABLE}",
            headers=supabase_headers(),
            params={"id": f"eq.{STATE_ID}", "select": "data"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in {401, 403}:
            reason = exc.response.text.strip() if exc.response is not None else ""
            message = authorization_error_message()
            if reason:
                message = f"{message} Supabase yanıtı: {reason[:300]}"
            raise StorageError(message) from exc
        if status == 404:
            raise StorageError(
                "Supabase app_state tablosu bulunamadı."
            ) from exc
        raise StorageError(f"Supabase bağlantısı başarısız: {exc}") from exc

    if rows:
        return normalize_db(rows[0]["data"])

    initial = load_local_db()
    save_supabase_db(initial)
    return initial


def load_db() -> dict[str, Any]:
    if supabase_enabled():
        return load_supabase_db()

    return load_local_db()


def save_local_db(db: dict[str, Any]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    try:
        with DB_FILE.open("w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        if not supabase_enabled():
            raise StorageError(f"Yerel veritabanı kaydedilemedi: {exc}") from exc


def save_supabase_db(db: dict[str, Any]) -> None:
    try:
        response = requests.post(
            f"{supabase_base_url()}/rest/v1/{SUPABASE_TABLE}",
            headers={
                **supabase_headers(),
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            params={"on_conflict": "id"},
            json={
                "id": STATE_ID,
                "data": normalize_db(db),
                "updated_at": utc_now(),
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else None
        reason = exc.response.text.strip() if exc.response is not None else ""
        if status in {401, 403}:
            message = authorization_error_message()
            if reason:
                message = f"{message} Supabase yanıtı: {reason[:300]}"
            raise StorageError(message) from exc
        if status == 404:
            raise StorageError(
                "Supabase app_state tablosu bulunamadı."
            ) from exc
        detail = f" Supabase yanıtı: {reason[:500]}" if reason else ""
        raise StorageError(
            f"Supabase kayıt işlemi başarısız (HTTP {status or 'bağlantı'}).{detail}"
        ) from exc


def save_db(db: dict[str, Any]) -> None:
    if supabase_enabled():
        save_supabase_db(db)
        return

    save_local_db(db)


def create_product(
    title: str,
    url: str,
    price: float,
    source: str,
    image_url: str | None = None,
    owner_id: str | None = None,
    original_price: float | None = None,
    extra_info: dict | None = None,
) -> dict[str, Any]:
    now = utc_now()

    return {
        "id": str(uuid4()),
        "title": title,
        "url": url,
        "source": source,
        "image_url": image_url,
        "owner_id": owner_id,
        "original_price": original_price,
        "extra_info": extra_info or {},
        "created_at": now,
        "updated_at": now,
        "last_checked_at": None,
        "last_check_status": "pending",
        "last_check_message": "Henüz otomatik kontrol yapılmadı.",
        "price_history": [
            {
                "price": price,
                "seen_at": now,
            }
        ],
    }


def current_price(product: dict[str, Any]) -> float:
    history = product.get("price_history", [])
    if not history:
        return 0

    return float(history[-1].get("price", 0))


def price_values(product: dict[str, Any]) -> list[float]:
    return [float(item.get("price", 0)) for item in product.get("price_history", [])]
