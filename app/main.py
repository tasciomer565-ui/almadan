from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import socket
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import FastAPI, Header, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import (
    AuthError,
    auth_enabled,
    get_user,
    request_password_reset,
    refresh_session,
    sign_in,
    sign_up,
    update_password,
    update_user_metadata,
    send_otp,
    verify_otp,
)
from app.parser import parse_product_url
from app.forecast import calculate_discount_forecast
from app.push import VAPID_PUBLIC_KEY, push_enabled
from app.scoring import calculate_deal_score
from app.shopping import MARKET_STORES, calculate_unit_price, optimize_market_basket
from app.storage import (
    StorageError,
    create_product,
    current_price,
    load_db,
    price_values,
    save_db,
    storage_diagnostics,
    supabase_enabled,
    utc_now,
)
from app.tracker import refresh_all_products, refresh_owner_products, refresh_product


REFRESH_INTERVAL_SECONDS = 6 * 60 * 60
CRON_SECRET = os.getenv("CRON_SECRET", "")
APP_URL = os.getenv("ALMADAN_APP_URL", "https://almadan.vercel.app").rstrip("/")
PASSWORD_RESET_LIMIT = 2
PASSWORD_RESET_WINDOW = timedelta(minutes=15)


async def automatic_refresh_loop() -> None:
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
        await asyncio.to_thread(refresh_all_products)


def cleanup_default_coupons() -> None:
    try:
        from app.storage import load_db, save_db
        db = load_db()
        coupons = db.get("coupons", [])
        if coupons:
            default_ids = {"c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"}
            new_coupons = [c for c in coupons if c.get("id") not in default_ids]
            if len(new_coupons) != len(coupons):
                db["coupons"] = new_coupons
                save_db(db)
    except Exception as e:
        print(f"Error cleaning up default coupons: {e}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    cleanup_default_coupons()
    refresh_task = None
    if not os.getenv("VERCEL"):
        refresh_task = asyncio.create_task(automatic_refresh_loop())

    yield

    if refresh_task:
        refresh_task.cancel()
        with suppress(asyncio.CancelledError):
            await refresh_task


app = FastAPI(title="Fırsat Asistanı API", version="0.2.0", lifespan=lifespan)


def find_static_dir() -> Path:
    module_dir = Path(__file__).resolve().parent
    candidates = (
        module_dir / "static",
        module_dir / "app" / "static",
        Path.cwd() / "app" / "static",
        Path.cwd() / "static",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


STATIC_DIR = find_static_dir()
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ACCESS_COOKIE = "almadan_access_token"
REFRESH_COOKIE = "almadan_refresh_token"


def public_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return False
    return True


@app.middleware("http")
async def ensure_device_id(request: Request, call_next):
    device_id = request.headers.get("x-device-id") or request.cookies.get(
        "almadan_device_id"
    )

    if not device_id or len(device_id) < 8:
        device_id = str(uuid4())

    if not request.headers.get("x-device-id"):
        request.scope["headers"].append(
            (b"x-device-id", device_id.encode("ascii"))
        )

    response = await call_next(request)
    response.set_cookie(
        key="almadan_device_id",
        value=device_id,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.middleware("http")
async def resolve_auth_session(request: Request, call_next):
    request.state.user_id = None
    request.state.user_email = None
    request.state.user_metadata = {}
    refreshed_tokens = None
    access_token = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)

    if access_token and auth_enabled():
        try:
            user = await asyncio.to_thread(get_user, access_token)
            request.state.user_id = user.get("id")
            request.state.user_email = user.get("email")
            request.state.user_metadata = user.get("user_metadata") or {}
        except AuthError:
            if refresh_token:
                try:
                    refreshed_tokens = await asyncio.to_thread(
                        refresh_session,
                        refresh_token,
                    )
                    user = refreshed_tokens.get("user") or {}
                    request.state.user_id = user.get("id")
                    request.state.user_email = user.get("email")
                    request.state.user_metadata = user.get("user_metadata") or {}
                except AuthError:
                    refreshed_tokens = {}

    response = await call_next(request)
    if refreshed_tokens:
        set_auth_cookies(response, refreshed_tokens)
    elif refreshed_tokens == {}:
        clear_auth_cookies(response)
    return response


@app.exception_handler(StorageError)
async def storage_error_handler(_, exc: StorageError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "message": str(exc),
                "diagnostics": storage_diagnostics(),
            }
        },
    )


@app.exception_handler(AuthError)
async def auth_error_handler(_, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


@app.get("/image-proxy")
def image_proxy(url: str) -> Response:
    if not public_image_url(url):
        raise HTTPException(status_code=400, detail="Geçersiz görsel adresi.")

    try:
        image = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
                ),
                "Referer": f"{urlparse(url).scheme}://{urlparse(url).netloc}/",
            },
            timeout=15,
        )
        image.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Ürün görseli alınamadı.") from exc

    content_type = image.headers.get("content-type", "")
    if not content_type.startswith("image/") or len(image.content) > 5_000_000:
        raise HTTPException(status_code=415, detail="Geçersiz ürün görseli.")

    return Response(
        content=image.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def require_device_id(x_device_id: str | None) -> str:
    if not x_device_id or len(x_device_id) < 8:
        raise HTTPException(status_code=400, detail="Geçerli cihaz kimliği gerekli")
    return x_device_id


def request_owner_id(request: Request, x_device_id: str | None) -> str:
    if request.state.user_id:
        return f"user:{request.state.user_id}"
    return require_device_id(x_device_id)


def owned_product(db: dict, product_id: str, owner_id: str) -> dict | None:
    return next(
        (
            product
            for product in db["products"]
            if product["id"] == product_id and product.get("owner_id") == owner_id
        ),
        None,
    )


def set_auth_cookies(response: Response, session: dict) -> None:
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    expires_in = int(session.get("expires_in") or 3600)

    if access_token:
        response.set_cookie(
            ACCESS_COOKIE,
            access_token,
            max_age=expires_in,
            httponly=True,
            secure=True,
            samesite="lax",
        )
    if refresh_token:
        response.set_cookie(
            REFRESH_COOKIE,
            refresh_token,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            secure=True,
            samesite="lax",
        )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)


def claim_device_data(device_id: str, user_id: str) -> None:
    db = load_db()
    user_owner = f"user:{user_id}"
    changed = False

    for collection in ("products", "notifications", "push_subscriptions"):
        for item in db.get(collection, []):
            if item.get("owner_id") == device_id:
                item["owner_id"] = user_owner
                changed = True

    if changed:
        save_db(db)


class ProductCreate(BaseModel):
    title: str = Field(min_length=2)
    url: str = Field(min_length=5)
    price: float = Field(gt=0)
    source: Literal[
        "trendyol",
        "hepsiburada",
        "amazon",
        "n11",
        "gratis",
        "rossmann",
        "supplementler",
        "proteinocean",
        "vatanbilgisayar",
        "itopya",
        "karaca",
        "lcwaikiki",
        "defacto",
        "mediamarkt",
        "teknosa",
        "zara",
        "migros",
        "boyner",
        "koton",
        "mavi",
        "bim",
        "a101",
        "sok",
        "file",
        "metro",
        "carrefoursa",
        "manual",
    ] = "manual"
    image_url: str | None = None
    original_price: float | None = None
    extra_info: dict | None = None


class UrlParseRequest(BaseModel):
    url: str = Field(min_length=5)


class ProductFromUrlRequest(BaseModel):
    url: str = Field(min_length=5)
    fallback_title: str | None = None
    fallback_price: float | None = Field(default=None, gt=0)


class PriceUpdate(BaseModel):
    price: float = Field(gt=0)


class AuthCredentials(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=8, max_length=128)
    gender: str | None = None
    phone: str | None = None
    notification_pref: str | None = None


class PasswordResetRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )


class PasswordUpdateRequest(BaseModel):
    access_token: str = Field(min_length=20)
    refresh_token: str | None = None
    password: str = Field(min_length=8, max_length=128)


class ProfileUpdateRequest(BaseModel):
    gender: Literal["belirtilmemiş", "erkek", "kadın"] = "belirtilmemiş"
    phone: str | None = Field(default=None, max_length=30)
    notification_pref: Literal["sms", "email", "both"] = "both"
    silence_enabled: bool = True
    skin_type: Literal["light", "medium", "dark"] | None = None


class OtpSendRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=20)


class OtpVerifyRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    code: str = Field(min_length=6, max_length=6)


def normalize_phone(phone: str) -> str:
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if cleaned.startswith("0090"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("05"):
        cleaned = "+90" + cleaned[1:]
    elif cleaned.startswith("5") and len(cleaned) == 10:
        cleaned = "+90" + cleaned
    elif cleaned.startswith("905") and len(cleaned) == 12:
        cleaned = "+" + cleaned
    elif not cleaned.startswith("+"):
        if len(cleaned) == 10 and cleaned.startswith("5"):
            cleaned = "+90" + cleaned
    return cleaned


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=512)
    auth: str = Field(min_length=8, max_length=256)


class PushSubscriptionRequest(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: PushSubscriptionKeys


def password_reset_key(email: str) -> str:
    normalized_email = email.strip().casefold()
    return hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()


def password_reset_retry_after(db: dict, email: str) -> int:
    now = datetime.now(timezone.utc)
    key = password_reset_key(email)
    attempts = db.setdefault("password_reset_attempts", {})
    timestamps = attempts.get(key, [])
    valid_timestamps = []

    for value in timestamps:
        try:
            created_at = datetime.fromisoformat(value)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if now - created_at < PASSWORD_RESET_WINDOW:
            valid_timestamps.append(created_at)

    attempts[key] = [value.isoformat() for value in valid_timestamps]
    if len(valid_timestamps) < PASSWORD_RESET_LIMIT:
        return 0

    retry_at = min(valid_timestamps) + PASSWORD_RESET_WINDOW
    return max(1, int((retry_at - now).total_seconds()) + 1)


def record_password_reset(db: dict, email: str) -> None:
    key = password_reset_key(email)
    attempts = db.setdefault("password_reset_attempts", {})
    attempts.setdefault(key, []).append(utc_now())


def calculate_discount_authenticity(product: dict) -> dict:
    history = product.get("price_history", [])
    current = current_price(product)
    orig_price = product.get("original_price")
    
    result = {
        "status": "unknown",
        "message": "Gerçeklik analizi için henüz yeterli fiyat geçmişi yok.",
        "badge_color": "gray",
        "discount_percent": 0
    }
    
    if orig_price and orig_price > current:
        result["discount_percent"] = round(((orig_price - current) / orig_price) * 100)
    elif len(history) > 1:
        first_price = history[0]["price"]
        if first_price > current:
            result["discount_percent"] = round(((first_price - current) / first_price) * 100)

    if len(history) < 2:
        if orig_price and orig_price > current:
            result["status"] = "pending"
            result["message"] = f"Mağaza %{result['discount_percent']} indirim iddia ediyor. Gerçekliği doğrulamak için takipteyiz."
            result["badge_color"] = "blue"
        return result
        
    prices = [h["price"] for h in history]
    min_price = min(prices[:-1]) if len(prices) > 1 else prices[0]
    mean_price = sum(prices) / len(prices)
    
    if current < min_price and current < mean_price * 0.98:
        result["status"] = "authentic"
        result["message"] = "Gerçek İndirim! Ürünün fiyatı geçmişteki en ucuz fiyatının da altında."
        result["badge_color"] = "green"
    elif orig_price and orig_price > current and current >= mean_price * 0.99:
        result["status"] = "fake"
        result["message"] = f"Şüpheli İndirim! Mağaza %{result['discount_percent']} indirim iddia ediyor ama ürünün fiyatı normal ortalamasının üzerinde veya aynı."
        result["badge_color"] = "red"
    elif len(prices) >= 3 and prices[-2] > prices[-3] and current < prices[-2]:
        result["status"] = "manipulated"
        result["message"] = "Fiyat Oyunu! Ürün fiyatı yakın zamanda önce şişirilmiş, sonra tekrar indirilmiş."
        result["badge_color"] = "yellow"
    else:
        result["status"] = "normal"
        result["message"] = "Ürün fiyatı normal dalgalanma aralığında seyrediyor."
        result["badge_color"] = "gray"
        
    return result


def enrich_product(product: dict) -> dict:
    price = current_price(product)
    decision = calculate_deal_score(price, price_values(product)[:-1])
    authenticity = calculate_discount_authenticity(product)
    forecast = calculate_discount_forecast(product)

    return {
        **product,
        "current_price": price,
        "deal_score": decision.score,
        "verdict": decision.verdict,
        "reason": decision.reason,
        "discount_analysis": authenticity,
        "discount_forecast": forecast,
        "last_checked_at": product.get("last_checked_at"),
        "last_check_status": product.get("last_check_status", "pending"),
        "last_check_message": product.get(
            "last_check_message",
            "Henüz otomatik kontrol yapılmadı.",
        ),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> Response:
    service_worker_file = STATIC_DIR / "sw.js"
    if service_worker_file.is_file():
        return FileResponse(
            service_worker_file,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )
    return RedirectResponse("/static/sw.js", status_code=307)


@app.get("/auth/session")
def auth_session(request: Request) -> dict:
    return {
        "authenticated": bool(request.state.user_id),
        "user": (
            {
                "id": request.state.user_id,
                "email": request.state.user_email,
                "gender": request.state.user_metadata.get("gender") if request.state.user_metadata else None,
                "phone": request.state.user_metadata.get("phone") if request.state.user_metadata else None,
                "notification_pref": request.state.user_metadata.get("notification_pref") if request.state.user_metadata else None,
                "silence_hours": request.state.user_metadata.get("silence_hours") if request.state.user_metadata else None,
                "skin_type": request.state.user_metadata.get("skin_type") if request.state.user_metadata else None,
            }
            if request.state.user_id
            else None
        ),
        "enabled": auth_enabled(),
    }
 
 
@app.post("/auth/signup")
def auth_signup(
    payload: AuthCredentials,
    response: Response,
    x_device_id: str | None = Header(default=None),
) -> dict:
    session = sign_up(
        payload.email,
        payload.password,
        payload.gender,
        payload.phone,
        payload.notification_pref,
    )
    user = session.get("user") or {}
 
    if session.get("access_token"):
        set_auth_cookies(response, session)
        if user.get("id") and x_device_id:
            claim_device_data(x_device_id, user["id"])
 
    user_id = user.get("id")
    if user_id:
        user_owner = f"user:{user_id}"
        db = load_db()
        db.setdefault("users", {})[user_owner] = {
            "email": user.get("email") or payload.email,
            "gender": user.get("user_metadata", {}).get("gender") if user else None,
            "phone": user.get("user_metadata", {}).get("phone") if user else None,
            "notification_pref": user.get("user_metadata", {}).get("notification_pref") if user else None,
            "skin_type": user.get("user_metadata", {}).get("skin_type") if user else None,
        }
        save_db(db)

    return {
        "authenticated": bool(session.get("access_token")),
        "requires_email_confirmation": not bool(session.get("access_token")),
        "user": {
            "id": user.get("id"),
            "email": user.get("email") or payload.email,
            "gender": user.get("user_metadata", {}).get("gender") if user else None,
            "phone": user.get("user_metadata", {}).get("phone") if user else None,
            "notification_pref": user.get("user_metadata", {}).get("notification_pref") if user else None,
            "skin_type": user.get("user_metadata", {}).get("skin_type") if user else None,
        },
    }
 
 
@app.post("/auth/login")
def auth_login(
    payload: AuthCredentials,
    response: Response,
    x_device_id: str | None = Header(default=None),
) -> dict:
    session = sign_in(payload.email, payload.password)
    user = session.get("user") or {}
    set_auth_cookies(response, session)
 
    if user.get("id") and x_device_id:
        claim_device_data(x_device_id, user["id"])
 
    user_id = user.get("id")
    if user_id:
        user_owner = f"user:{user_id}"
        db = load_db()
        db.setdefault("users", {})[user_owner] = {
            "email": user.get("email") or payload.email,
            "gender": user.get("user_metadata", {}).get("gender") if user else None,
            "phone": user.get("user_metadata", {}).get("phone") if user else None,
            "notification_pref": user.get("user_metadata", {}).get("notification_pref") if user else None,
            "skin_type": user.get("user_metadata", {}).get("skin_type") if user else None,
        }
        save_db(db)

    return {
        "authenticated": True,
        "user": {
            "id": user.get("id"),
            "email": user.get("email") or payload.email,
            "gender": user.get("user_metadata", {}).get("gender") if user else None,
            "phone": user.get("user_metadata", {}).get("phone") if user else None,
            "notification_pref": user.get("user_metadata", {}).get("notification_pref") if user else None,
            "skin_type": user.get("user_metadata", {}).get("skin_type") if user else None,
        },
    }


@app.post("/auth/otp/send")
def auth_otp_send(payload: OtpSendRequest) -> dict:
    normalized_phone = normalize_phone(payload.phone)
    try:
        send_otp(normalized_phone)
        return {"status": "ok", "phone": normalized_phone}
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.args[0])


@app.post("/auth/otp/verify")
def auth_otp_verify(
    payload: OtpVerifyRequest,
    response: Response,
    x_device_id: str | None = Header(default=None),
) -> dict:
    normalized_phone = normalize_phone(payload.phone)
    try:
        session = verify_otp(normalized_phone, payload.code)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.args[0])

    user = session.get("user") or {}
    set_auth_cookies(response, session)
 
    if user.get("id") and x_device_id:
        claim_device_data(x_device_id, user["id"])
 
    user_id = user.get("id")
    if user_id:
        user_owner = f"user:{user_id}"
        db = load_db()
        db.setdefault("users", {})[user_owner] = {
            "email": user.get("email") or "",
            "gender": user.get("user_metadata", {}).get("gender") if user else None,
            "phone": normalized_phone,
            "notification_pref": user.get("user_metadata", {}).get("notification_pref") if user else None,
            "skin_type": user.get("user_metadata", {}).get("skin_type") if user else None,
        }
        save_db(db)

    return {
        "authenticated": True,
        "user": {
            "id": user.get("id"),
            "email": user.get("email") or "",
            "gender": user.get("user_metadata", {}).get("gender") if user else None,
            "phone": normalized_phone,
            "notification_pref": user.get("user_metadata", {}).get("notification_pref") if user else None,
            "skin_type": user.get("user_metadata", {}).get("skin_type") if user else None,
        },
    }


@app.post("/auth/logout")
def auth_logout(response: Response) -> dict:
    clear_auth_cookies(response)
    return {"status": "ok"}


@app.put("/auth/profile")
def auth_profile_update(request: Request, payload: ProfileUpdateRequest) -> dict:
    if not request.state.user_id:
        raise HTTPException(status_code=401, detail="Profil ayarları için giriş yapmalısın.")

    phone = (payload.phone or "").strip()
    if payload.notification_pref in {"sms", "both"} and not phone:
        raise HTTPException(
            status_code=422,
            detail="SMS bildirimleri için telefon numarası gereklidir.",
        )

    metadata = {
        **(request.state.user_metadata or {}),
        "gender": payload.gender,
        "phone": phone or None,
        "notification_pref": payload.notification_pref,
        "silence_hours": (
            {"start": 22, "end": 8} if payload.silence_enabled else None
        ),
        "skin_type": payload.skin_type,
    }

    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token and auth_enabled():
        update_user_metadata(access_token, metadata)

    owner_id = f"user:{request.state.user_id}"
    db = load_db()
    db.setdefault("users", {}).setdefault(owner_id, {}).update(
        {"email": request.state.user_email, **metadata}
    )
    save_db(db)

    return {
        "status": "ok",
        "user": {
            "id": request.state.user_id,
            "email": request.state.user_email,
            **metadata,
        },
    }


@app.post("/auth/forgot-password")
def auth_forgot_password(payload: PasswordResetRequest) -> dict:
    db = load_db()
    retry_after = password_reset_retry_after(db, payload.email)
    if retry_after:
        minutes = max(1, (retry_after + 59) // 60)
        raise HTTPException(
            status_code=429,
            detail=(
                "Çok fazla şifre sıfırlama isteği gönderdin. "
                f"Yaklaşık {minutes} dakika sonra tekrar deneyebilirsin."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    request_password_reset(payload.email, APP_URL)
    record_password_reset(db, payload.email)
    save_db(db)
    return {
        "status": "ok",
        "message": "Şifre sıfırlama bağlantısı e-postana gönderildi.",
    }


@app.post("/auth/reset-password")
def auth_reset_password(
    payload: PasswordUpdateRequest,
    response: Response,
) -> dict:
    user = update_password(payload.access_token, payload.password)
    set_auth_cookies(
        response,
        {
            "access_token": payload.access_token,
            "refresh_token": payload.refresh_token,
            "expires_in": 3600,
        },
    )
    return {
        "status": "ok",
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
        },
    }


@app.get("/storage-health")
def storage_health() -> dict:
    db = load_db()
    return {
        "status": "ok",
        "storage": "supabase" if supabase_enabled() else "local",
        "products": len(db["products"]),
    }


@app.get("/", include_in_schema=False)
def home() -> Response:
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return RedirectResponse("/index.html", status_code=307)


@app.get("/products")
def list_products(
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> list[dict]:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    return [
        enrich_product(product)
        for product in db["products"]
        if product.get("owner_id") == owner_id
    ]


@app.post("/products")
def add_product(
    payload: ProductCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()

    existing = next(
        (
            product
            for product in db["products"]
            if product.get("owner_id") == owner_id
            and product.get("url") == payload.url
        ),
        None,
    )
    if existing:
        return enrich_product(existing)

    product = create_product(
        title=payload.title,
        url=payload.url,
        price=payload.price,
        source=payload.source,
        image_url=payload.image_url,
        owner_id=owner_id,
        original_price=payload.original_price,
        extra_info=payload.extra_info,
    )
    db["products"].append(product)
    try:
        save_db(db)
    except StorageError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Ürün veritabanına kaydedilemedi: {type(exc).__name__}: {exc}",
        ) from exc
    
    from app.comparator import update_product_comparison
    background_tasks.add_task(update_product_comparison, product["id"])
    
    return enrich_product(product)


@app.get("/api/search")
def search_products(
    request: Request,
    query: str,
    category: Literal[
        "general", "grocery", "electronics", "fashion", "cosmetics", "home"
    ] = "general",
) -> dict:
    if not query or len(query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Arama sorgusu en az 2 karakter olmalıdır.")
    
    user_gender = None
    if hasattr(request.state, "user_metadata") and request.state.user_metadata:
        user_gender = request.state.user_metadata.get("gender")
        
    from app.comparator import apply_gender_to_query, search_products_by_name, generate_search_suggestion
    gendered_query = (
        apply_gender_to_query(query, user_gender)
        if category == "fashion"
        else query
    )
    
    products = search_products_by_name(gendered_query)
    fallback_applied = any(p.get("extra_info", {}).get("fallback") for p in products)
    
    suggestion = None
    if not products:
        suggestion = generate_search_suggestion(query)
        
    return {
        "products": products,
        "suggestion": suggestion,
        "query": query,
        "effective_query": gendered_query,
        "category": category,
        "fallback_applied": fallback_applied
    }


@app.post("/parse-url")
def parse_url(payload: UrlParseRequest) -> dict:
    parsed = parse_product_url(payload.url)
    return {
        "title": parsed.title,
        "price": parsed.price,
        "image_url": parsed.image_url,
        "source": parsed.source,
        "canonical_url": parsed.canonical_url,
        "confidence": parsed.confidence,
        "warnings": parsed.warnings,
        "original_price": parsed.original_price,
        "extra_info": parsed.extra_info,
    }


@app.post("/products/from-url")
def add_product_from_url(
    payload: ProductFromUrlRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    parsed = parse_product_url(payload.url)
    title = parsed.title or payload.fallback_title
    price = parsed.price or payload.fallback_price

    if not title or not price:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Ürün otomatik tamamlanamadı. Başlık veya fiyat eksik.",
                "parsed": {
                    "title": parsed.title,
                    "price": parsed.price,
                    "image_url": parsed.image_url,
                    "source": parsed.source,
                    "canonical_url": parsed.canonical_url,
                    "confidence": parsed.confidence,
                    "warnings": parsed.warnings,
                },
            },
        )

    db = load_db()
    product = create_product(
        title=title,
        url=parsed.canonical_url,
        price=price,
        source=parsed.source,
        image_url=parsed.image_url,
        owner_id=owner_id,
        original_price=parsed.original_price,
        extra_info=parsed.extra_info,
    )
    db["products"].append(product)
    try:
        save_db(db)
    except StorageError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Ürün veritabanına kaydedilemedi: {type(exc).__name__}: {exc}",
        ) from exc
    
    from app.comparator import update_product_comparison
    background_tasks.add_task(update_product_comparison, product["id"])
    
    return enrich_product(product)


@app.post("/products/{product_id}/compare")
def force_compare_prices(
    product_id: str,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()

    product = owned_product(db, product_id, owner_id)
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    from app.comparator import compare_prices
    comparison = compare_prices(product["title"], product["source"])
    product["price_comparison"] = comparison
    save_db(db)
    return enrich_product(product)


@app.post("/products/{product_id}/prices")
def add_price(
    product_id: str,
    payload: PriceUpdate,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()

    product = owned_product(db, product_id, owner_id)
    if product:
        product["price_history"].append(
            {
                "price": payload.price,
                "seen_at": utc_now(),
            }
        )
        product["updated_at"] = utc_now()
        save_db(db)
        return enrich_product(product)

    raise HTTPException(status_code=404, detail="Ürün bulunamadı")


@app.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    product = owned_product(db, product_id, owner_id)

    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    db["products"] = [
        item for item in db["products"] if item["id"] != product_id
    ]
    db["notifications"] = [
        item
        for item in db["notifications"]
        if item.get("product_id") != product_id
    ]
    save_db(db)
    return {"status": "deleted"}


@app.post("/products/{product_id}/refresh")
def refresh_one_product(
    product_id: str,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    if not owned_product(db, product_id, owner_id):
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    try:
        result = refresh_product(product_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı") from None

    return {
        **result,
        "product": enrich_product(result["product"]),
    }


@app.post("/refresh-all")
def refresh_all(
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    return refresh_owner_products(owner_id)


@app.api_route("/cron/refresh-all", methods=["GET", "POST"])
def cron_refresh_all(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
) -> dict:
    authorization = request.headers.get("authorization", "")
    valid_secret = (
        x_cron_secret == CRON_SECRET
        or authorization == f"Bearer {CRON_SECRET}"
    )
    if not CRON_SECRET or not valid_secret:
        raise HTTPException(status_code=401, detail="Geçersiz cron anahtarı")

    return refresh_all_products()


@app.get("/api/catalogs")
def list_catalog_status() -> list[dict]:
    db = load_db()
    snapshots = db.get("catalog_snapshots", {})
    return sorted(
        snapshots.values(),
        key=lambda item: str(item.get("store", "")),
    )


@app.get("/notifications")
def list_notifications(
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> list[dict]:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    return [
        item
        for item in db["notifications"]
        if item.get("owner_id") == owner_id
    ][:50]


@app.post("/notifications/read-all")
def read_all_notifications(
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()

    for notification in db["notifications"]:
        if notification.get("owner_id") == owner_id:
            notification["read"] = True

    save_db(db)
    return {"status": "ok"}


@app.get("/push/config")
def push_config() -> dict:
    return {
        "enabled": push_enabled(),
        "public_key": VAPID_PUBLIC_KEY if push_enabled() else None,
    }


@app.post("/push/subscriptions")
def save_push_subscription(
    payload: PushSubscriptionRequest,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    if not push_enabled():
        raise HTTPException(
            status_code=503,
            detail="Web bildirimleri sunucuda henüz etkinleştirilmedi.",
        )
    if (
        urlparse(payload.endpoint).scheme != "https"
        or not public_image_url(payload.endpoint)
    ):
        raise HTTPException(
            status_code=400,
            detail="Geçersiz push abonelik adresi.",
        )

    db = load_db()
    subscriptions = db.setdefault("push_subscriptions", [])
    existing = next(
        (
            item
            for item in subscriptions
            if item.get("endpoint") == payload.endpoint
        ),
        None,
    )
    subscription_data = {
        "owner_id": owner_id,
        "endpoint": payload.endpoint,
        "keys": payload.keys.model_dump(),
        "updated_at": utc_now(),
    }

    if existing:
        existing.update(subscription_data)
    else:
        subscriptions.append(
            {
                "id": str(uuid4()),
                "created_at": utc_now(),
                **subscription_data,
            }
        )

    save_db(db)
    return {"status": "subscribed"}


@app.delete("/push/subscriptions")
def delete_push_subscription(
    payload: PushSubscriptionRequest,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    subscriptions = db.setdefault("push_subscriptions", [])
    db["push_subscriptions"] = [
        item
        for item in subscriptions
        if not (
            item.get("owner_id") == owner_id
            and item.get("endpoint") == payload.endpoint
        )
    ]
    save_db(db)
    return {"status": "unsubscribed"}


@app.get("/daily-deals")
def daily_deals(
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> list[dict]:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    products = [
        enrich_product(product)
        for product in db["products"]
        if product.get("owner_id") == owner_id
    ]
    products.sort(key=lambda product: product["deal_score"], reverse=True)
    return products[:20]


class SharedListItem(BaseModel):
    id: str | None = None
    name: str
    checked: bool = False
    quantity: str | int | None = None
    updated_at: str | None = None


class SharedListPayload(BaseModel):
    items: list[SharedListItem]
    base_version: int | None = None


class CouponPayload(BaseModel):
    store: str = Field(min_length=2)
    code: str = Field(min_length=2)
    description: str = ""
    min_amount: float = Field(default=0, ge=0)
    discount: float = Field(gt=0)
    active: bool = True


class BasketItemPayload(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1, le=99)
    offers: dict[str, float] | None = None


class BasketOptimizePayload(BaseModel):
    items: list[BasketItemPayload]
    location_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    max_distance: float | None = None


class ReceiptOcrRequest(BaseModel):
    image_base64: str | None = None


@app.get("/api/coupons")
def list_coupons() -> list[dict]:
    db = load_db()
    return db.get("coupons", [])


@app.post("/api/coupons")
def create_coupon(payload: CouponPayload) -> dict:
    store = payload.store.casefold().strip()
    if store not in MARKET_STORES:
        raise HTTPException(status_code=400, detail="Desteklenmeyen market.")
    db = load_db()
    coupon = {
        "id": str(uuid4()),
        **payload.model_dump(),
        "store": store,
        "description": (
            payload.description
            or f"{payload.min_amount:.0f} TL uzeri {payload.discount:.0f} TL indirim"
        ),
        "created_at": utc_now(),
    }
    db.setdefault("coupons", []).append(coupon)
    save_db(db)
    return coupon


@app.delete("/api/coupons/{coupon_id}")
def delete_coupon(coupon_id: str) -> dict:
    db = load_db()
    before = len(db.get("coupons", []))
    db["coupons"] = [
        coupon
        for coupon in db.get("coupons", [])
        if coupon.get("id") != coupon_id
    ]
    if len(db["coupons"]) == before:
        raise HTTPException(status_code=404, detail="Kupon bulunamadi.")
    save_db(db)
    return {"status": "deleted", "id": coupon_id}


@app.post("/api/cart/optimize")
def optimize_cart(payload: BasketOptimizePayload) -> dict:
    db = load_db()
    return optimize_market_basket(
        [item.model_dump() for item in payload.items],
        db.get("coupons", []),
        lat=payload.lat,
        lng=payload.lng,
        location_name=payload.location_name,
        max_distance=payload.max_distance,
    )


@app.get("/api/unit-price")
def unit_price(name: str, price: float) -> dict:
    result = calculate_unit_price(name, price)
    return {"found": bool(result), "analysis": result}


@app.get("/api/barcode/{code}")
def api_barcode_lookup(code: str) -> dict:
    from app.comparator import lookup_barcode, search_products_by_name
    match = lookup_barcode(code)
    if not match:
        return {"found": False, "message": "Barkod veritabanında bulunamadı."}
    
    results = search_products_by_name(match["search_query"])
    return {
        "found": True,
        "title": match["title"],
        "search_query": match["search_query"],
        "results": results
    }


@app.post("/api/ocr/receipt")
def ocr_receipt(payload: ReceiptOcrRequest) -> dict:
    img = payload.image_base64 or ""
    if "cosmetics" in img:
        return {
            "store": "gratis",
            "detected_items": [
                {"title": "İpana 3D White Diş Macunu 75 ml", "price": 45.90},
                {"title": "Loreal Paris Nemlendirici Krem 50 ml", "price": 189.90},
                {"title": "Elidor Şampuan 400 ml", "price": 79.90}
            ]
        }
    elif "electronics" in img:
        return {
            "store": "vatanbilgisayar",
            "detected_items": [
                {"title": "Samsung T7 Portable SSD 1 TB", "price": 2899.00},
                {"title": "Logitech G305 Mouse", "price": 1099.00}
            ]
        }
    else:
        return {
            "store": "migros",
            "detected_items": [
                {"title": "Yudum Ayçiçek Yağı 5 L", "price": 189.90},
                {"title": "Sütaş Süzme Peynir 500 gr", "price": 89.50},
                {"title": "Eriş Un 5 Kg", "price": 72.90},
                {"title": "Doğuş Filiz Çay 1 Kg", "price": 145.00}
            ]
        }


@app.post("/api/lists")
def create_shared_list(payload: SharedListPayload) -> dict:
    db = load_db()
    import string
    import random
    chars = string.ascii_lowercase + string.digits
    for _ in range(10):
        list_id = "".join(random.choice(chars) for _ in range(6))
        if list_id not in db["shared_lists"]:
            break
    else:
        list_id = str(uuid4())[:8]
        
    db["shared_lists"][list_id] = {
        "items": [
            {
                **item.model_dump(),
                "updated_at": item.updated_at or utc_now(),
            }
            for item in payload.items
        ],
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "version": 1,
    }
    save_db(db)
    return {
        "id": list_id,
        "items": db["shared_lists"][list_id]["items"],
        "created_at": db["shared_lists"][list_id]["created_at"],
        "version": 1,
    }


@app.get("/api/lists/{id}")
def get_shared_list(id: str) -> dict:
    db = load_db()
    shared = db.get("shared_lists", {}).get(id)
    if not shared:
        raise HTTPException(status_code=404, detail="Paylaşılan liste bulunamadı")
    return {
        "id": id,
        "items": shared["items"],
        "created_at": shared.get("created_at"),
        "updated_at": shared.get("updated_at"),
        "version": int(shared.get("version", 1)),
    }


@app.put("/api/lists/{id}")
def update_shared_list(id: str, payload: SharedListPayload) -> dict:
    db = load_db()
    if id not in db.get("shared_lists", {}):
        raise HTTPException(status_code=404, detail="Paylaşılan liste bulunamadı")
    
    shared = db["shared_lists"][id]
    current_version = int(shared.get("version", 1))
    incoming = [item.model_dump() for item in payload.items]

    if payload.base_version is not None and payload.base_version < current_version:
        by_id = {
            str(item.get("id")): item
            for item in shared.get("items", [])
            if item.get("id")
        }
        for item in incoming:
            item_id = str(item.get("id") or "")
            existing = by_id.get(item_id)
            if (
                not existing
                or str(item.get("updated_at") or "")
                >= str(existing.get("updated_at") or "")
            ):
                by_id[item_id] = item
        incoming = list(by_id.values())

    now = utc_now()
    shared["items"] = [
        {**item, "updated_at": item.get("updated_at") or now}
        for item in incoming
    ]
    shared["updated_at"] = now
    shared["version"] = current_version + 1
    save_db(db)
    return {
        "id": id,
        "items": shared["items"],
        "updated_at": shared["updated_at"],
        "version": shared["version"],
    }
