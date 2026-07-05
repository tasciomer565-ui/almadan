from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import os
import re
import socket
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request, BackgroundTasks
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
    supabase_base_url,
    supabase_enabled,
    supabase_headers,
    utc_now,
)
from app.tracker import refresh_all_products, refresh_owner_products, refresh_product
from app.security import (
    apply_security_headers,
    auth_wall_middleware,
    csrf_middleware,
    generate_csrf_token,
    log_activity,
    require_admin,
    require_login,
    require_premium,
    sanitize,
    get_oauth_url,
    OAUTH_PROVIDERS,
)


REFRESH_INTERVAL_SECONDS = 6 * 60 * 60  # sprint12
CRON_SECRET = os.getenv("CRON_SECRET", "")
APP_URL = os.getenv("ALMADAN_APP_URL", "https://almadan.vercel.app").rstrip("/")
PASSWORD_RESET_LIMIT = 2
PASSWORD_RESET_WINDOW = timedelta(minutes=15)
COOKIE_SECURE = bool(os.getenv("VERCEL")) or os.getenv("VERCEL_ENV") == "production"


def cron_request_authorized(request: Request) -> bool:
    """Vercel'in Bearer başlığıyla ve manuel X-Cron-Secret ile doğrula."""
    if not CRON_SECRET:
        return False
    candidates = (
        request.headers.get("authorization", "").removeprefix("Bearer ").strip(),
        request.headers.get("x-cron-secret", "").strip(),
        request.headers.get("x-vercel-cron-secret", "").strip(),
    )
    return any(
        candidate and hmac.compare_digest(candidate, CRON_SECRET)
        for candidate in candidates
    )


def require_cron_request(request: Request) -> None:
    if not cron_request_authorized(request):
        raise HTTPException(status_code=401, detail="Geçersiz cron anahtarı")


async def automatic_refresh_loop() -> None:
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
        await asyncio.to_thread(refresh_all_products)


@asynccontextmanager
async def lifespan(_: FastAPI):
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
    # TEK KAYNAK: public/static — Vercel /static'i doğrudan public/ klasöründen sunar,
    # FastAPI de aynı klasörü kullanmalı; yoksa iki kopya sessizce ayrışır (2026-07-06 kazası)
    module_dir = Path(__file__).resolve().parent
    candidates = (
        module_dir.parent / "public" / "static",
        Path.cwd() / "public" / "static",
        module_dir / "static",
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
async def _auth_wall(request: Request, call_next):
    return await auth_wall_middleware(request, call_next)


@app.middleware("http")
async def ensure_device_id(request: Request, call_next):
    device_id = request.headers.get("x-device-id") or request.cookies.get(
        "almadan_device_id"
    )

    if not device_id or len(device_id) < 8:
        device_id = str(uuid4())

    request.state.device_id = device_id

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
        secure=COOKIE_SECURE,
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


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    apply_security_headers(response)
    # CSRF token'ı cookie olarak sun (JS okumaz, header'dan gönderir)
    if not request.cookies.get("csrf_token"):
        device_id = getattr(request.state, "device_id", None) or request.cookies.get("almadan_device_id", "anonymous")
        csrf = generate_csrf_token(device_id)
        response.set_cookie(
            "csrf_token", csrf,
            max_age=7200, httponly=False, secure=COOKIE_SECURE, samesite="strict"
        )
    return response


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    return await csrf_middleware(request, call_next)


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


proxy_cache = {}
MAX_CACHE_SIZE = 50

@app.get("/image-proxy")
def image_proxy(url: str) -> Response:
    if not public_image_url(url):
        raise HTTPException(status_code=400, detail="Geçersiz görsel adresi.")

    if url in proxy_cache:
        # Move to end for LRU behavior
        content, content_type = proxy_cache.pop(url)
        proxy_cache[url] = (content, content_type)
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Cache": "HIT"
            },
        )

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

    # Save to cache
    proxy_cache[url] = (image.content, content_type)
    if len(proxy_cache) > MAX_CACHE_SIZE:
        # Evict oldest key
        first_key = next(iter(proxy_cache))
        proxy_cache.pop(first_key)

    return Response(
        content=image.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Cache": "MISS"
        },
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
            secure=COOKIE_SECURE,
            samesite="lax",
        )
    if refresh_token:
        response.set_cookie(
            REFRESH_COOKIE,
            refresh_token,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
        )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)


def claim_device_data(device_id: str, user_id: str) -> None:
    db = load_db()
    user_owner = f"user:{user_id}"
    changed = False

    for collection in (
        "products",
        "notifications",
        "push_subscriptions",
        "receipts",
    ):
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


class AlternativesRequest(BaseModel):
    title: str
    original_url: str | None = None
    source: str | None = None
    image_url: str | None = None

class ReviewCreateRequest(BaseModel):
    user_name: str | None = "Anonim Kullanıcı"
    rating: int = Field(ge=1, le=5)
    comment: str

class UrlParseRequest(BaseModel):
    url: str = Field(min_length=5)


class ProductFromUrlRequest(BaseModel):
    url: str = Field(min_length=5)
    fallback_title: str | None = None
    fallback_price: float | None = Field(default=None, gt=0)


class PriceUpdate(BaseModel):
    price: float = Field(gt=0)


class ExtraInfoUpdate(BaseModel):
    extra_info: dict



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


@app.get("/api/auth/oauth/{provider}")
def auth_oauth_redirect(provider: str, request: Request) -> RedirectResponse:
    """Social login: Google veya Apple OAuth yönlendirmesi."""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen provider: {provider}")
    from app.storage import supabase_base_url
    supabase_url = supabase_base_url()
    anon_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    redirect_to = f"{APP_URL}/auth/callback"
    url = get_oauth_url(provider, redirect_to, supabase_url, anon_key)
    log_activity(request, "oauth_redirect", {"provider": provider})
    return RedirectResponse(url)


@app.get("/api/auth/callback", include_in_schema=False)
def auth_oauth_callback(request: Request, response: Response) -> RedirectResponse:
    """
    Supabase OAuth callback: URL fragment'taki token'ları cookie'ye yazar.
    Tarayıcı JS tarafı zaten Supabase JS client ile handle eder;
    bu endpoint /login?oauth=1 yönlendirmesidir.
    """
    return RedirectResponse("/?oauth=1")


@app.get("/api/profile/me")
def profile_me(request: Request) -> dict:
    """Giriş yapmış kullanıcının profil bilgisi + rolü."""
    if not request.state.user_id:
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")
    from app.storage import supabase_get
    try:
        rows = supabase_get(
            "profiles",
            params={"id": f"eq.{request.state.user_id}", "select": "*"},
        )
        profile = rows[0] if rows else {}
    except Exception:
        profile = {}
    return {
        "user_id": request.state.user_id,
        "email": request.state.user_email,
        "role": profile.get("role", "free"),
        "stripe_status": profile.get("stripe_status", "inactive"),
        "display_name": profile.get("display_name"),
        "preferences": profile.get("preferences", {}),
    }


@app.get("/api/activity-log")
async def get_activity_log(request: Request, limit: int = 50) -> dict:
    """Kullanıcının son aktivitelerini döner (kendi kaydı)."""
    if not request.state.user_id:
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")
    from app.storage import supabase_get
    try:
        rows = supabase_get(
            "activity_logs",
            params={
                "user_id": f"eq.{request.state.user_id}",
                "order": "created_at.desc",
                "limit": str(min(limit, 200)),
                "select": "event,metadata,ip_address,created_at",
            },
        )
    except Exception:
        rows = []
    return {"events": rows}


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
        return FileResponse(index_file, media_type="text/html; charset=utf-8")
    return RedirectResponse("/index.html", status_code=307)


# ── İstemci hata raporları ──────────────────────────────────
_client_errors: "deque[dict]" = None  # lazy init


@app.post("/api/client-error", include_in_schema=False)
async def client_error_report(request: Request) -> dict:
    """Frontend hata raporlarını logla (Vercel function logs'ta görünür)."""
    global _client_errors
    from collections import deque
    if _client_errors is None:
        _client_errors = deque(maxlen=100)
    try:
        body = await request.json()
    except Exception:
        return {"ok": False}
    entry = {
        "kind": str(body.get("kind", ""))[:32],
        "message": str(body.get("message", ""))[:500],
        "source": str(body.get("source", ""))[:200],
        "lineno": int(body.get("lineno") or 0),
        "url": str(body.get("url", ""))[:200],
        "ua": str(body.get("ua", ""))[:120],
        "at": utc_now(),
    }
    _client_errors.append(entry)
    import logging
    logging.getLogger("almadan.client").error(
        "CLIENT-ERROR [%s] %s (%s:%s) sayfa=%s",
        entry["kind"], entry["message"], entry["source"], entry["lineno"], entry["url"])
    return {"ok": True}


@app.get("/api/client-errors", include_in_schema=False)
async def client_error_list(request: Request) -> list[dict]:
    """Son istemci hatalarını listele (yalnızca admin)."""
    await require_admin(request)
    return list(_client_errors or [])


@app.get("/hakkinda", include_in_schema=False)
@app.get("/gizlilik", include_in_schema=False)
@app.get("/iletisim", include_in_schema=False)
def static_page(request: Request) -> Response:
    page_file = STATIC_DIR / f"{request.url.path.strip('/')}.html"
    if page_file.is_file():
        return FileResponse(page_file, media_type="text/html; charset=utf-8")
    return RedirectResponse("/", status_code=307)


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


@app.get("/api/opportunities")
def list_opportunities(
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

    _log_event(owner_id, "product_track", {
        "title": payload.title,
        "url": payload.url,
        "price": payload.price,
        "source": payload.source,
        "email": getattr(request.state, "user_email", None) or "Anonymous"
    })
    
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
    lat: float | None = None,
    lon: float | None = None,
    mode: Literal["hybrid", "local", "global"] = "hybrid",
) -> dict:
    if not query or len(query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Arama sorgusu en az 2 karakter olmalıdır.")
    
    user_gender = None
    if hasattr(request.state, "user_metadata") and request.state.user_metadata:
        user_gender = request.state.user_metadata.get("gender")
        
    from app.comparator import (
        apply_gender_to_query,
        generate_search_suggestion,
        normalize_turkish_search_query,
        search_products_by_name,
    )
    normalized_query = normalize_turkish_search_query(query)
    gendered_query = (
        apply_gender_to_query(normalized_query, user_gender)
        if category == "fashion"
        else normalized_query
    )
    
    products = search_products_by_name(gendered_query, category=category, lat=lat, lon=lon, mode=mode)
    fallback_applied = any(p.get("extra_info", {}).get("fallback") for p in products)
    is_stale = any(p.get("stale_cache") for p in products)
    stale_age = next((p.get("stale_age", "") for p in products if p.get("stale_cache")), "")

    suggestion = None
    if not products:
        suggestion = generate_search_suggestion(query)

    from app.cache import make_cache_key
    cache_key = make_cache_key(gendered_query, category)

    uid = getattr(request.state, "user_id", None)
    _log_event(uid, "url_search", {
        "query": query,
        "category": category,
        "result_count": len(products),
        "fallback": fallback_applied,
        "email": getattr(request.state, "user_email", None) or "Anonymous"
    })

    return {
        "products": products,
        "suggestion": suggestion,
        "query": query,
        "effective_query": gendered_query,
        "category": category,
        "fallback_applied": fallback_applied,
        "is_stale": is_stale,
        "stale_age": stale_age,
        "cache_key": cache_key,
    }


@app.post("/parse-url")
def parse_url(payload: UrlParseRequest) -> dict:
    import hashlib, time
    from functools import lru_cache

    # URL önbelleği — aynı URL için 60 dakika sonuç sakla
    _url_cache = getattr(parse_url, "_cache", {})
    parse_url._cache = _url_cache
    
    cache_key = hashlib.md5(payload.url.strip().encode()).hexdigest()
    now = time.time()
    if cache_key in _url_cache:
        cached_at, cached_data = _url_cache[cache_key]
        if now - cached_at < 3600:  # 60 dakika
            return cached_data
    
    parsed = parse_product_url(payload.url)
    result = {
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
    
    # Sadece başarılı sonuçları önbellekle
    if parsed.price and parsed.title:
        _url_cache[cache_key] = (now, result)
        # Önbelleği 500 girişle sınırla
        if len(_url_cache) > 500:
            oldest = sorted(_url_cache.items(), key=lambda x: x[1][0])[:100]
            for k, _ in oldest:
                del _url_cache[k]
    
    return result


@app.post("/api/find-alternatives")
async def find_alternatives(payload: AlternativesRequest):
    from app.search_orchestrator import master_search, marketplace_scan
    import re

    # Kaynak mağazadan kategori tahmini
    FASHION_SOURCES = {"lcwaikiki","defacto","koton","mavi","zara","bershka","boyner","yargici",
                       "hm","flo","kinetix","adidas","nike","reebok","puma","lescon","superstep",
                       "mango","ipekyol","twist","ltb","colins","kigili","sarar","altinyildiz",
                       "derimod","damat","vakko","beymen","instreet","deichmann","ayakkabidunyasi"}
    TECH_SOURCES = {"mediamarkt","teknosa","vatanbilgisayar","itopya","casper","huawei",
                    "samsung","lg","sony","apple","xiaomi","asus","lenovo"}
    HOME_SOURCES = {"evidea","vivense","karaca","englishhome","ikea","koctas","madamecoco"}
    BABY_SOURCES = {"ebebek"}

    src = (payload.source or "").lower()
    if src in FASHION_SOURCES:
        forced_category = "MODA"
    elif src in TECH_SOURCES:
        forced_category = "TEKNOLOJİ"
    elif src in HOME_SOURCES:
        forced_category = "EV"
    elif src in BABY_SOURCES:
        forced_category = "BEBEK"
    else:
        # Pazaryerleri (trendyol, hepsiburada, amazon, n11) için ürün başlığından kategori tahmin et
        from app.search_orchestrator import classify_intent
        title_category = classify_intent(payload.title)
        forced_category = title_category if title_category != "GENEL" else None

    # Başlığı temizle ve kısa bir arama sorgusuna dönüştür
    cleaned = re.sub(r'[^\w\s]', ' ', payload.title)
    # Sayıları koru (8 GB, 4K, vb.) — sadece harf/harf karışımı kelimeler için >1 şartı
    words = [w for w in cleaned.split() if len(w) > 1 or w.isdigit()]
    # Pazarlama/dolgu kelimelerini at — ürün tipi kelimeleri (bebek arabası vb.) 6 kelime sınırına sığsın
    _FILLER = {"tek", "tuşla", "tusla", "kolay", "katlanan", "katlanabilir", "yeni",
               "orijinal", "garantili", "pratik", "şık", "sik", "özel", "ozel",
               "fonksiyonlu", "ayarlanabilir", "ve", "ile", "için", "icin", "uyumlu"}
    core = [w for w in words if w.lower() not in _FILLER]
    if len(core) >= 2:
        words = core
    # İlk 6 kelimeyi al — önemli model bilgisi (GB, RAM) kesilebilir
    query = " ".join(words[:6]) if words else payload.title

    if forced_category:
        products = await marketplace_scan(query, forced_category=forced_category)
    else:
        products = await master_search(query)

    # Kılıf/aksesuar/cam koruyucu gibi yanlış ürünleri filtrele
    from app.comparator import is_logical_product
    products = [p for p in products if is_logical_product(query, p.get("title", ""))]

    if payload.original_url:
        from urllib.parse import urlparse
        orig_path = urlparse(payload.original_url).path
        filtered = []
        for p in products:
            p_path = urlparse(p["url"]).path
            if p_path != orig_path:
                filtered.append(p)
        products = filtered

        # Trendyol özel "Diğer Satıcılar" çekimi - string split ile güvenli
        if "trendyol.com" in payload.original_url:
            from app.parser import safe_product_get
            import json as _json
            try:
                resp = safe_product_get(payload.original_url)
                if resp and resp.ok:
                    from bs4 import BeautifulSoup as _BS
                    _soup = _BS(resp.text, "lxml")
                    for _script in _soup.find_all("script"):
                        _st = _script.string or ""
                        if "window.__INITIAL_STATE__=" in _st:
                            try:
                                _json_str = _st.split("window.__INITIAL_STATE__=")[1]
                                for _sep in [";window.__SEARCH_APP_INITIAL_STATE__=", ";window.__"]:
                                    if _sep in _json_str:
                                        _json_str = _json_str.split(_sep)[0]
                                        break
                                else:
                                    _json_str = _json_str.rsplit(";", 1)[0]
                                _state = _json.loads(_json_str.strip())
                                _merchants = _state.get("product", {}).get("productDetails", {}).get("otherMerchants", [])
                                for _m in _merchants:
                                    _mp = _m.get("price", {}).get("discountedPrice", {}).get("value")
                                    _mn = _m.get("merchant", {}).get("name")
                                    _mu = _m.get("merchant", {}).get("sellerLink", "")
                                    _ms = _m.get("merchant", {}).get("sellerScore")
                                    _md = bool(_m.get("deliveryInformation", {}).get("fastDeliveryOptions", []))
                                    if _mp and _mn:
                                        products.append({
                                            "title": payload.title,
                                            "price": float(_mp),
                                            "url": f"https://www.trendyol.com{_mu}" if _mu else payload.original_url,
                                            "source": f"Trendyol ({_mn})",
                                            "image_url": getattr(payload, "image_url", None),
                                            "extra_info": {"rating": _ms, "fast_delivery": _md}
                                        })
                            except Exception:
                                pass
                            break
            except Exception:
                pass

    # Defensive: filter out non-dict entries (corrupt cache data)
    products = [p for p in products if isinstance(p, dict)]

    # Fiyatı olmayan/0 olan sonuçlar karşılaştırmada işe yaramaz
    products = [p for p in products if (p.get("price") or 0) > 0]

    # Model kodu: harf ile başlayıp rakam içeren (S24, A54, vb.)
    query_words = re.findall(r'\w+', query.lower())
    query_word_set = set(query_words)
    # Harf+rakam model kodu: S24, A54, vb. (rakamla başlayanlar hariç)
    model_codes = {w for w in query_words
                   if 2 <= len(w) <= 5 and re.match(r'[a-z]', w) and re.search(r'\d', w)}
    # Saf rakam model numarası: iPhone 16, PS5 gibi (2 hane: 10-99)
    digit_models = {w for w in query_words if re.match(r'^\d{2,3}$', w)}

    # Varyant anahtar kelimeleri: sorgu yoksa başlıkta olmamalı
    VARIANT_SUFFIXES = {"fe", "plus", "ultra", "pro", "lite", "max", "mini", "neo", "edge", "fold", "flip"}
    query_variants = VARIANT_SUFFIXES & query_word_set

    # Anlamlı sorgu kelimeleri (TR normalize, 3+ harf) — örtüşme kontrolü için
    _tr_map = str.maketrans("şğıöüçâî", "sgioucai")
    significant_words = {w.translate(_tr_map) for w in query_words if len(w) >= 3}

    def is_same_model(p: dict) -> bool:
        """Model kodu varsa başlıkta geçmeli; sorgu varyantı yoksa başlıkta da olmamalı."""
        title_words = set(re.findall(r'\w+', (p.get("title") or "").lower()))
        # Sorguyla hiç anlamlı kelime örtüşmesi yoksa alakasız (fallback/popüler ürün sızıntısı)
        if significant_words:
            title_norm = {w.translate(_tr_map) for w in title_words}
            overlap = len(significant_words & title_norm)
            required = 1 if len(significant_words) <= 2 else 2
            if overlap < required:
                return False
        if model_codes and not (model_codes & title_words):
            return False  # S24 aranıyor ama başlıkta s24 yok → at
        if digit_models and not (digit_models & title_words):
            return False  # "16" aranıyor ama başlıkta yok → iPhone 12 at
        # Varyant filtresi her zaman çalışır (model_codes bağımsız)
        title_variants = VARIANT_SUFFIXES & title_words
        if title_variants - query_variants:
            return False  # "plus" başlıkta var ama sorguda yok → at
        return True

    # Her zaman filtrele (model_codes boş olsa bile variant filtresi çalışsın)
    products = [p for p in products if is_same_model(p)]

    def relevance(p: dict) -> float:
        title_lower = (p.get("title") or "").lower()
        title_words = set(re.findall(r'\w+', title_lower))
        base = len(query_word_set & title_words) / max(len(query_word_set), 1)
        if model_codes:
            matching = model_codes & title_words
            model_bonus = len(matching) * 5
            title_model_codes = {w for w in title_words
                                 if 2 <= len(w) <= 5 and re.match(r'[a-z]', w) and re.search(r'\d', w)}
            wrong_models = title_model_codes - model_codes
            model_penalty = sum(5 for m in wrong_models if m not in query_word_set)
        else:
            model_bonus = 0
            model_penalty = 0
        return base + model_bonus - model_penalty

    products.sort(key=lambda p: (-relevance(p), p.get("price") or 0))

    # Her kaynaktan en fazla 3 ürün al (tekrarlayan mağazaları sınırla)
    from collections import defaultdict

    def _dedup(items: list[dict]) -> list[dict]:
        source_count: dict[str, int] = defaultdict(int)
        out = []
        seen: set[str] = set()
        for p in items:
            url_key = (p.get("url") or "").split("?")[0]
            if url_key in seen:
                continue
            seen.add(url_key)
            src_key = p.get("source", "other")
            if source_count[src_key] < 3:
                out.append(p)
                source_count[src_key] += 1
        return out

    deduped = _dedup(products)

    # 2. deneme: hiç sonuç yoksa sorguyu kısaltıp tekrar ara (marka + model genelde ilk 3 kelime)
    if not deduped:
        retry_query = " ".join(query.split()[:3])
        if retry_query and retry_query != query:
            try:
                if forced_category:
                    retry_products = await marketplace_scan(retry_query, forced_category=forced_category)
                else:
                    retry_products = await master_search(retry_query)
                retry_products = [p for p in retry_products
                                  if isinstance(p, dict) and (p.get("price") or 0) > 0]
                retry_products = [p for p in retry_products
                                  if is_logical_product(query, p.get("title", "")) and is_same_model(p)]
                retry_products.sort(key=lambda p: (-relevance(p), p.get("price") or 0))
                deduped = _dedup(retry_products)
            except Exception:
                pass

    # Son çare: hazır mağaza arama linkleri — kullanıcı hiçbir zaman eli boş dönmesin
    search_links = []
    if not deduped:
        from urllib.parse import quote_plus
        q_enc = quote_plus(query)
        search_links = [
            {"source": "trendyol", "label": "Trendyol'da ara", "url": f"https://www.trendyol.com/sr?q={q_enc}"},
            {"source": "hepsiburada", "label": "Hepsiburada'da ara", "url": f"https://www.hepsiburada.com/ara?q={q_enc}"},
            {"source": "amazon", "label": "Amazon'da ara", "url": f"https://www.amazon.com.tr/s?k={q_enc}"},
            {"source": "n11", "label": "N11'de ara", "url": f"https://www.n11.com/arama?q={q_enc}"},
            {"source": "google", "label": "Google Shopping'de ara", "url": f"https://www.google.com/search?tbm=shop&q={q_enc}"},
        ]

    return {
        "alternatives": deduped[:20],
        "search_links": search_links,
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

    _log_event(owner_id, "product_track", {
        "title": title,
        "url": parsed.canonical_url,
        "price": price,
        "source": parsed.source,
        "email": getattr(request.state, "user_email", None) or "Anonymous"
    })
    
    from app.comparator import update_product_comparison
    background_tasks.add_task(update_product_comparison, product["id"])
    
    return enrich_product(product)


@app.get("/api/products/{product_id}/reviews")
def get_reviews(product_id: str) -> dict:
    db = load_db()
    reviews = db.get("reviews", [])
    product_reviews = [r for r in reviews if r.get("product_id") == product_id]
    # En yeniler en üstte
    product_reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"reviews": product_reviews}


@app.post("/api/products/{product_id}/reviews")
def add_review(
    product_id: str,
    payload: ReviewCreateRequest,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    
    if "reviews" not in db:
        db["reviews"] = []
        
    import uuid
    from datetime import datetime, timezone
    new_review = {
        "id": str(uuid.uuid4()),
        "product_id": product_id,
        "owner_id": owner_id,
        "user_name": payload.user_name or "Anonim Kullanıcı",
        "rating": payload.rating,
        "comment": payload.comment,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    db["reviews"].append(new_review)
    save_db(db)
    
    return {"status": "success", "review": new_review}


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


@app.post("/products/{product_id}/extra-info")
def update_product_extra_info(
    product_id: str,
    payload: ExtraInfoUpdate,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    product = owned_product(db, product_id, owner_id)
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    product.setdefault("extra_info", {}).update(payload.extra_info)
    product["updated_at"] = utc_now()
    save_db(db)
    return enrich_product(product)



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


@app.get("/cron/refresh-all")
def cron_refresh_all(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
) -> dict:
    require_cron_request(request)
    return refresh_all_products()


@app.get("/api/catalogs")
def list_catalog_status() -> list[dict]:
    db = load_db()
    snapshots = db.get("catalog_snapshots", {})
    return sorted(snapshots.values(), key=lambda item: str(item.get("store", "")))


@app.post("/api/catalogs/scan")
async def catalog_scan(request: Request, payload: dict = None) -> dict:
    """
    Katalog taramasını manuel tetikle (admin veya cron).
    store parametresi ile belirli bir markete filtre uygulanabilir.
    """
    cron_secret = request.headers.get("x-cron-secret", "")
    user_id     = getattr(request.state, "user_id", None)
    is_admin    = False
    if user_id:
        from app.security import _get_user_role
        role = await _get_user_role(request)
        is_admin = role == "admin"

    if not is_admin and not cron_request_authorized(request):
        raise HTTPException(403, "Yetkisiz erişim.")

    store_filter = (payload or {}).get("store") if payload else None

    from app.notification_orchestrator import catalog_automation
    result = await asyncio.to_thread(catalog_automation.run, store_filter)
    log_activity(request, "catalog_scan", {"store": store_filter, **result})
    return result


@app.post("/api/catalogs/match")
async def catalog_match(request: Request, payload: dict) -> dict:
    """
    Gelen watchlist ile katalog öğelerini eşleştir.
    Body: {"watchlist": ["Pınar Süt", "Ariel 3kg"], "store": "migros"}
    """
    watchlist = payload.get("watchlist", [])
    store     = payload.get("store", "")
    if not watchlist:
        raise HTTPException(400, "watchlist boş olamaz.")

    from app.matching_engine import matching_engine
    from app.catalog_parser import catalog_parser
    from app.catalogs import fetch_catalog, CATALOG_SOURCES

    # İlgili mağazanın güncel katalogunu çek
    source = next((s for s in CATALOG_SOURCES if s.store == store), None)
    catalog_items = []
    if source:
        try:
            snapshot = await asyncio.to_thread(fetch_catalog, source)
            html_text = "\n".join(snapshot.get("items", []))
            catalog_items = catalog_parser.parse_text(html_text, store=store)
        except Exception:
            pass

    user_id   = getattr(request.state, "user_id", None)
    device_id = request.cookies.get("almadan_device_id")
    summary   = matching_engine.match(
        watchlist=watchlist,
        catalog_items=catalog_items,
        store=store,
        user_id=user_id,
        device_id=device_id,
    )
    return {
        "store":          store,
        "watchlist_count": summary.total_watchlist,
        "catalog_count":  summary.total_catalog,
        "match_count":    summary.match_count,
        "deal_count":     summary.deal_count,
        "matches": [
            {
                "watchlist_title": m.watchlist_title,
                "catalog_product": m.catalog_product,
                "store":           m.store,
                "score":           m.score,
                "price":           m.price,
                "original_price":  m.original_price,
                "discount_pct":    m.discount_pct,
                "unit":            m.unit,
                "is_deal":         m.is_deal,
            }
            for m in summary.matches
        ],
    }


@app.get("/cron/catalog-scan")
async def cron_catalog_scan(request: Request) -> dict:
    """
    Vercel Cron: Pazartesi ve Perşembe haftalık katalog taraması.
    schedule: "0 6 * * 1,4"  (Pazartesi + Perşembe 06:00 UTC)
    """
    require_cron_request(request)

    from app.notification_orchestrator import catalog_automation
    result = await asyncio.to_thread(catalog_automation.run)
    return {"cron": "catalog-scan", **result}


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
    category_hint: Literal["grocery", "cosmetics", "electronics"] | None = None


class ReceiptItemPayload(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    price: float = Field(ge=0)
    quantity: float = Field(default=1, gt=0, le=999)
    category: Literal[
        "grocery",
        "cosmetics",
        "electronics",
        "fashion",
        "supplement",
        "health",
        "home",
        "other",
    ] = "other"


class ReceiptCreateRequest(BaseModel):
    store: str = Field(min_length=2, max_length=80)
    purchased_at: str
    payment_method: Literal[
        "unknown", "cash", "card", "meal_card", "other"
    ] = "unknown"
    items: list[ReceiptItemPayload] = Field(default_factory=list, max_length=250)
    total: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)
    raw_ocr_text: str | None = None


@app.post("/api/cart/optimize")
def optimize_cart(payload: BasketOptimizePayload) -> dict:
    return optimize_market_basket(
        [item.model_dump() for item in payload.items],
        lat=payload.lat,
        lng=payload.lng,
        location_name=payload.location_name,
        max_distance=payload.max_distance,
    )


@app.get("/api/unit-price")
def unit_price(name: str, price: float) -> dict:
    result = calculate_unit_price(name, price)
    return {"found": bool(result), "analysis": result}


# ── Admin Dashboard ────────────────────────────────────────────────────────

@app.get("/api/admin/stats")
def admin_stats(days: int = 7) -> dict:
    """Performans istatistikleri — sadece geliştirici modunda kullanılır."""
    from app.admin_metrics import get_dashboard_stats
    return get_dashboard_stats(days=min(days, 30))


@app.post("/api/admin/sync-google-sheets")
async def sync_google_sheets(request: Request, user=Depends(require_login)):
    """
    Kullanıcı bazlı verileri Google Sheets'e senkronize eder.
    3 sekme: Yapıştırılan Linkler / Takip Edilen Ürünler / Takip Edilen Mağazalar
    Gerekli env: GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID
    """
    if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or not os.getenv("GOOGLE_SHEET_ID"):
        raise HTTPException(
            status_code=503,
            detail="Google Sheets henüz yapılandırılmamış. GOOGLE_SERVICE_ACCOUNT_JSON ve GOOGLE_SHEET_ID env değişkenlerini Vercel'e ekleyin.",
        )
    try:
        from app.sheets_sync import sync_to_sheets
        result = sync_to_sheets(load_db())
        return result
    except Exception as exc:
        import traceback, logging as _lg
        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-600:]}"
        _lg.getLogger(__name__).error("Google Sheets sync hatası: %s", detail)
        raise HTTPException(status_code=500, detail=detail)


# VTON ve AI endpoint'leri kaldırıldı (Sprint 12 — stabilizasyon)


@app.delete("/api/cache")
def clear_search_cache(query: str | None = None, category: str | None = None) -> dict:
    """Cache'i temizle — query+category verilirse sadece o key'i sil, verilmezse etkisiz."""
    from app.cache import make_cache_key, cache_invalidate
    if query:
        key = make_cache_key(query, category or "GENEL")
        cache_invalidate(key)
        return {"deleted": key}
    return {"deleted": None, "message": "Tüm cache silmek için Supabase'den manuel temizleyin."}


def _barcode_from_sources(barcode: str) -> dict | None:
    """
    Çoklu kaynak barkod araması.
    Kaynak sırası: Open Food Facts → UPCitemdb → N11 ürün arama
    Her kaynak başarısız olursa sonraki denenir; tümü başarısız olursa None döner.
    """
    import logging as _log
    log = _log.getLogger(__name__)

    # ── Kaynak 1: Open Food Facts ──────────────────────────────────────────
    try:
        r = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
            params={"fields": "code,product_name,product_name_tr,generic_name,brands,image_front_url,image_url,quantity"},
            headers={"User-Agent": "Almadan/1.0 (https://almadan.vercel.app)"},
            timeout=6,
        )
        log.info("OFF status %s for barcode %s", r.status_code, barcode)
        if r.ok:
            data = r.json()
            if int(data.get("status") or 0) == 1:
                p = data.get("product") or {}
                title = (p.get("product_name_tr") or p.get("product_name") or p.get("generic_name") or "").strip()
                if title:
                    brand = str(p.get("brands") or "").split(",", 1)[0].strip()
                    qty   = str(p.get("quantity") or "").strip()
                    img   = str(p.get("image_front_url") or p.get("image_url") or "").strip()
                    return {"title": title, "brand": brand, "quantity": qty,
                            "image_url": img, "search_query": " ".join(x for x in (brand, title, qty) if x),
                            "source": "open_food_facts"}
            log.info("OFF: product not found (status=%s)", data.get("status"))
        else:
            log.warning("OFF HTTP %s for barcode %s", r.status_code, barcode)
    except Exception as exc:
        log.warning("OFF exception for barcode %s: %s", barcode, exc)

    # ── Kaynak 2: Go-UPC (Türkiye dahil global, ücretsiz tier) ───────────
    try:
        r_goupc = requests.get(
            "https://go-upc.com/api/v1/code/" + barcode,
            headers={"Authorization": "Bearer " + (os.getenv("GO_UPC_API_KEY") or "")},
            timeout=5,
        )
        if r_goupc.ok:
            d = r_goupc.json()
            prod = d.get("product") or {}
            title = (prod.get("name") or "").strip()
            if title:
                brand = (prod.get("brand") or "").strip()
                img   = (prod.get("imageUrl") or "").strip()
                return {"title": title, "brand": brand, "quantity": "",
                        "image_url": img, "search_query": " ".join(x for x in (brand, title) if x),
                        "source": "go_upc"}
    except Exception as exc:
        log.warning("Go-UPC exception for barcode %s: %s", barcode, exc)

    # ── Kaynak 3: UPCitemdb (ücretsiz tier, 100 sorgu/gün) ────────────────
    try:
        r2 = requests.get(
            "https://api.upcitemdb.com/prod/trial/lookup",
            params={"upc": barcode},
            headers={"Accept": "application/json"},
            timeout=5,
        )
        log.info("UPCitemdb status %s for barcode %s", r2.status_code, barcode)
        if r2.ok:
            data2 = r2.json()
            items = data2.get("items") or []
            if items:
                item = items[0]
                title = item.get("title", "").strip()
                if title:
                    brand = item.get("brand", "").strip()
                    img   = (item.get("images") or [""])[0]
                    return {"title": title, "brand": brand, "quantity": "",
                            "image_url": img, "search_query": " ".join(x for x in (brand, title) if x),
                            "source": "upcitemdb"}
    except Exception as exc:
        log.warning("UPCitemdb exception for barcode %s: %s", barcode, exc)

    # N11 arama fallback kaldırıldı — barkod numarasını isim gibi aratınca yanlış ürün geliyor.
    return None


@app.get("/api/barcode/{code}")
def api_barcode_lookup(code: str) -> dict:
    from app.comparator import lookup_barcode, search_products_by_name
    barcode = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(barcode) not in (8, 12, 13):
        raise HTTPException(status_code=400, detail="Geçersiz barkod formatı. EAN-8, EAN-13 veya UPC-A olmalıdır.")

    db = load_db()
    cached = db.setdefault("barcode_products", {}).get(barcode)
    if cached:
        suggested_category = cached.get("category", "general")
        results = search_products_by_name(cached["search_query"], category=suggested_category)
        return {
            "found": True,
            "title": cached["title"],
            "brand": cached.get("brand", ""),
            "image_url": cached.get("image_url", ""),
            "search_query": cached["search_query"],
            "suggested_category": suggested_category,
            "source": "cache",
            "cached": True,
            "results": results,
        }

    match = lookup_barcode(barcode)
    if not match:
        match = _barcode_from_sources(barcode)

    if not match:
        return {
            "found": False,
            "barcode": barcode,
            "message": f"'{barcode}' barkodu hiçbir kaynakta bulunamadı.",
            "allow_manual": True,
        }

    # local_seed match için eksik alanları tamamla
    match = {
        "brand": "",
        "quantity": "",
        "image_url": "",
        "source": "local_seed",
        **match,
    }

    # Ürün adından kategori tahmin et
    receipt_cat = category_mapping(match["title"] + " " + match.get("brand", ""))
    # receipt kategorisini API kategorisine çevir
    _cat_map = {
        "electronics": "electronics",
        "cosmetics": "cosmetics",
        "supplement": "general",
        "fashion": "fashion",
        "home": "home",
        "grocery": "grocery",
    }
    suggested_category = _cat_map.get(receipt_cat, "general")

    db["barcode_products"][barcode] = {
        **match,
        "barcode": barcode,
        "category": suggested_category,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    save_db(db)

    results = search_products_by_name(match["search_query"], category=suggested_category)

    # ── Fuzzy Match Kapısı (%60 eşik) ──────────────────────────────────────
    # Barkoddan gelen ürün adı ile market sonuçlarını karşılaştır.
    # Yeterince eşleşmeyen sonuç varsa kullanıcıya gösterme.
    from app.matching_engine import FuzzyMatcher
    _fm = FuzzyMatcher()
    barcode_title = match["title"]

    # Barkod adındaki anlamlı kelimeler sonuçta geçiyor mu?
    barcode_words = [w.lower() for w in barcode_title.split() if len(w) > 2]
    validated_results = []
    for r in results:
        candidate_title = r.get("title") or r.get("name") or ""
        match_score = _fm.score(barcode_title, candidate_title)
        # Kelime bazlı ek kontrol: barkod kelimelerinin yarısı sonuçta varsa kabul et
        candidate_lower = candidate_title.lower()
        word_hits = sum(1 for w in barcode_words if w in candidate_lower)
        word_ratio = word_hits / len(barcode_words) if barcode_words else 0
        if match_score >= 0.40 or word_ratio >= 0.5:
            r["_match_score"] = max(match_score, word_ratio)
            validated_results.append(r)

    if not validated_results:
        # Eşleşme yok ama ürün tanındı → tüm sonuçları göster (kullanıcı seçsin)
        for r in results[:8]:
            r["_match_score"] = 0
            validated_results.append(r)

    # En yüksek skora göre sırala
    validated_results.sort(key=lambda x: x.get("_match_score", 0), reverse=True)

    return {
        "found": True,
        "title": match["title"],
        "brand": match.get("brand", ""),
        "image_url": match.get("image_url", ""),
        "search_query": match["search_query"],
        "suggested_category": suggested_category,
        "source": match.get("source", "local_seed"),
        "cached": False,
        "results": validated_results,
    }

RECEIPT_ITEM_CATEGORIES = (
    "grocery",
    "cosmetics",
    "electronics",
    "fashion",
    "supplement",
    "health",
    "home",
    "other",
)


def category_mapping(title: str, fallback: str | None = None) -> str:
    lower = title.casefold()
    keyword_map = {
        "supplement": (
            "whey", "protein", "creatine", "kreatin", "bcaa", "gainer",
            "vitamin", "kolajen", "collagen", "takviye", "amino",
        ),
        "electronics": (
            "ssd", "ram", "laptop", "notebook", "telefon", "kulaklık",
            "kulaklik", "mouse", "klavye", "işlemci", "islemci", "anakart",
            "monitör", "monitor", "tablet", "kamera", "şarj", "sarj",
        ),
        "cosmetics": (
            "şampuan", "sampuan", "krem", "ruj", "maskara", "parfüm",
            "parfum", "deodorant", "roll-on", "diş macunu", "dis macunu",
            "nemlendirici", "tonik", "serum", "oje", "allık", "allik",
        ),
        "fashion": (
            "tişört", "tshirt", "gomlek", "gömlek", "pantolon", "elbise",
            "ayakkabı", "ayakkabi", "çorap", "corap", "mont", "ceket",
        ),
        "health": (
            "bebek", "mama", "bez", "medikal", "lens", "optik", "ilaç",
            "ilac", "ateş ölçer", "ates olcer",
        ),
        "home": (
            "deterjan", "yumuşatıcı", "yumusatici", "çamaşır", "camasir",
            "bulaşık", "bulasik", "peçete", "pecete", "havlu", "tabak",
            "bardak", "tencere", "temizleyici",
        ),
        "grocery": (
            "süt", "sut", "yoğurt", "yogurt", "peynir", "yumurta", "ekmek",
            "domates", "patates", "soğan", "sogan", "yağ", "yag", "un",
            "şeker", "seker", "pirinç", "pirinc", "makarna", "çay", "cay",
            "kahve", "su", "kola", "meyve", "sebze", "et", "tavuk",
            "kuzu", "dana", "kıyma", "kiyma", "kasap",
        ),
    }
    for category, keywords in keyword_map.items():
        if any(keyword in lower for keyword in keywords):
            return category
    if fallback in RECEIPT_ITEM_CATEGORIES:
        return str(fallback)
    return "grocery"


def categorize_receipt(text: str) -> str:
    return category_mapping(text, "grocery")


def parse_receipt_amount(value: str) -> float | None:
    cleaned = value.strip().replace(" ", "").lstrip("*")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def extract_receipt_metadata(text: str) -> dict:
    import re
    import unicodedata

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    store = lines[0] if lines else ""
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )

    date = ""
    date_match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    if date_match:
        day, month, year = date_match.groups()
        date = f"{year}-{month}-{day}"

    amount_pattern = r"\*?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
    total = None
    total_match = re.search(
        rf"(?:GENEL\s+TOPLAM|TOPLAM|TUTAR)\D{{0,24}}{amount_pattern}",
        text,
        flags=re.IGNORECASE,
    )
    if total_match:
        total = parse_receipt_amount(total_match.group(1))
    if total is None:
        amounts = [
            parsed for parsed in (
                parse_receipt_amount(match.group(1))
                for line in lines[-12:]
                for match in re.finditer(amount_pattern, line)
            )
            if parsed is not None
        ]
        if amounts:
            total = amounts[-1]

    payment_method = "unknown"
    if any(term in normalized for term in ("kred", "kart", "credit card", "visa", "mastercard")):
        payment_method = "card"
    elif any(term in normalized for term in ("nakit", "cash")):
        payment_method = "cash"
    elif any(term in normalized for term in ("yemek kart", "sodexo", "multinet", "ticket", "setcard")):
        payment_method = "meal_card"

    return {
        "store": store,
        "purchased_at": date,
        "total": total,
        "payment_method": payment_method,
    }


def parse_receipt_details(
    text: str,
    category_hint: str | None = None,
) -> dict:
    import re

    detected_items = []
    receipt_info = []
    price_pattern = re.compile(
        r"(?<!\d)(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2}(?!\d)"
    )
    blacklist_terms = (
        "tarih",
        "saat",
        "cuma",
        "cumartesi",
        "pazar",
        "pazartesi",
        "salı",
        "sali",
        "çarşamba",
        "carsamba",
        "perşembe",
        "persembe",
        "mahmudiye",
        "caddesi",
        "cadde",
        "mah",
        "mahalle",
        "sokak",
        "vergi",
        "mersis",
        "kasiyer",
        "fis",
        "fiş",
        "belge",
        "sube",
        "şube",
        "adres",
        "tel",
        "telefon",
        "adi",
        "adı",
        "no:",
        "no ",
        "www.",
        "http",
    )
    blacklist_phrase_terms = tuple(
        term for term in blacklist_terms
        if len(term) > 4 or any(char in term for char in ":. ")
    )
    blacklist_word_terms = tuple(
        term for term in blacklist_terms
        if term not in blacklist_phrase_terms
    )
    ignored_labels = (
        "toplam",
        "ara toplam",
        "kdv",
        "nakit",
        "para üstü",
        "kredi kart",
        "ödenecek",
        "tutar",
        "pos",
        "onay",
        "provizyon",
        "slip",
    )

    def normalize_price(value: str) -> float | None:
        cleaned = value.strip().replace(" ", "")
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
            if cleaned.count(".") > 1:
                parts = cleaned.split(".")
                cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except ValueError:
            return None

    def clean_title(value: str) -> str:
        value = re.sub(r"^[^\wÇĞİÖŞÜçğıöşü]+", "", value)
        value = re.sub(r"^(?:\d+\s*[xX*]\s*)+", "", value)
        value = re.sub(r"^\d+(?:[.,]\d+)?\s*(?:kg|gr|g|lt|l|adet|ad)\b", "", value, flags=re.I)
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"\b(adet|kdv|no|fis|fiş)\b[:.]?", "", value, flags=re.I)
        return value.strip(" -:*")

    def has_product_letters(value: str) -> bool:
        return bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", value))

    def is_noise_line(folded: str) -> bool:
        if any(label in folded for label in ignored_labels):
            return True
        if any(term in folded for term in blacklist_phrase_terms):
            return True
        return any(
            re.search(rf"(?<!\w){re.escape(term)}(?!\w)", folded)
            for term in blacklist_word_terms
        ) or bool(re.search(r"\bmg\b", folded))

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        folded = line.casefold()
        if is_noise_line(folded):
            receipt_info.append(line)
            continue

        matches = list(price_pattern.finditer(line))
        if not matches:
            receipt_info.append(line)
            continue

        accepted = False
        for match in reversed(matches):
            before = line[:match.start()].strip()
            after = line[match.end():].strip()
            before_title = clean_title(before)
            after_title = clean_title(after)
            title = before_title if has_product_letters(before_title) else after_title
            if len(title) < 3 or title.isdigit() or not has_product_letters(title):
                continue
            price = normalize_price(match.group(0))
            if price is None or not (0.10 <= price <= 50000.0):
                continue
            detected_items.append({
                "title": title,
                "price": round(price, 2),
                "quantity": 1,
                "category": category_mapping(title, category_hint),
            })
            accepted = True
            break
        if not accepted:
            receipt_info.append(line)

    return {
        "items": detected_items,
        "receipt_info": receipt_info[:40],
    }


def parse_receipt_text(text: str) -> list[dict]:
    return parse_receipt_details(text).get("items", [])


def receipt_store_from_text(text: str, category_hint: str | None = None) -> str:
    normalized = text.casefold()
    stores = (
        "migros",
        "carrefoursa",
        "a101",
        "bim",
        "şok",
        "sok",
        "file",
        "metro",
        "gratis",
        "rossmann",
        "watsons",
        "vatan bilgisayar",
        "mediamarkt",
        "teknosa",
    )
    for store in stores:
        if store in normalized:
            return store.replace("şok", "sok").replace(" ", "")
    return "Bilinmeyen mağaza"


def receipt_total(items: list[dict]) -> float:
    return round(
        sum(
            float(item.get("price") or 0) * float(item.get("quantity") or 1)
            for item in items
        ),
        2,
    )


def normalize_receipt_items(
    items: list[dict],
    category_hint: str | None = None,
) -> list[dict]:
    normalized = []
    for item in items:
        title = str(item.get("title") or "").strip()
        normalized.append({
            **item,
            "title": title,
            "price": round(float(item.get("price") or 0), 2),
            "quantity": float(item.get("quantity") or 1),
            "category": str(
                item.get("category") or category_mapping(title, category_hint)
            ),
        })
    return normalized


def normalize_receipt_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Fiş tarihi geçersiz.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def receipt_summary(receipts: list[dict], month: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    selected_month = month or now.strftime("%Y-%m")
    try:
        month_start = datetime.strptime(selected_month, "%Y-%m").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Ay YYYY-AA biçiminde olmalı.")

    if month_start.month == 1:
        previous_start = month_start.replace(
            year=month_start.year - 1, month=12
        )
    else:
        previous_start = month_start.replace(month=month_start.month - 1)

    def receipt_month(receipt: dict) -> str:
        return str(receipt.get("purchased_at") or "")[:7]

    selected = [
        receipt for receipt in receipts
        if receipt_month(receipt) == selected_month
    ]
    previous_key = previous_start.strftime("%Y-%m")
    previous = [
        receipt for receipt in receipts
        if receipt_month(receipt) == previous_key
    ]

    store_totals: dict[str, float] = {}
    category_totals: dict[str, float] = {}
    item_totals: dict[str, dict] = {}
    for receipt in selected:
        total = float(receipt.get("total") or 0)
        store = str(receipt.get("store") or "Bilinmeyen")
        store_totals[store] = round(store_totals.get(store, 0) + total, 2)
        for item in receipt.get("items", []):
            item_total = round(
                float(item.get("price") or 0) *
                float(item.get("quantity") or 1),
                2,
            )
            category = str(item.get("category") or "other")
            category_totals[category] = round(
                category_totals.get(category, 0) + item_total,
                2,
            )
            title = str(item.get("title") or "Ürün")
            aggregate = item_totals.setdefault(
                title.casefold(),
                {"title": title, "total": 0.0, "quantity": 0.0},
            )
            aggregate["total"] = round(aggregate["total"] + item_total, 2)
            aggregate["quantity"] += float(item.get("quantity") or 1)

    total = round(sum(float(item.get("total") or 0) for item in selected), 2)
    previous_total = round(
        sum(float(item.get("total") or 0) for item in previous),
        2,
    )
    change_percent = None
    if previous_total > 0:
        change_percent = round(((total - previous_total) / previous_total) * 100, 1)

    monthly_totals: dict[str, float] = {}
    for receipt in receipts:
        key = receipt_month(receipt)
        if len(key) == 7:
            monthly_totals[key] = round(
                monthly_totals.get(key, 0) +
                float(receipt.get("total") or 0),
                2,
            )

    return {
        "month": selected_month,
        "total": total,
        "previous_total": previous_total,
        "change_percent": change_percent,
        "receipt_count": len(selected),
        "store_totals": dict(
            sorted(store_totals.items(), key=lambda item: item[1], reverse=True)
        ),
        "category_totals": category_totals,
        "top_items": sorted(
            item_totals.values(),
            key=lambda item: item["total"],
            reverse=True,
        )[:8],
        "monthly_totals": dict(sorted(monthly_totals.items())[-6:]),
    }


@app.post("/api/ocr/receipt")
def ocr_receipt(payload: ReceiptOcrRequest) -> dict:
    img = payload.image_base64 or ""
    default_date = datetime.now(timezone.utc).date().isoformat()

    demo_items = {
        "grocery": [
            {"title": "Yudum Ayçiçek Yağı 5 L", "price": 189.90},
            {"title": "Sütaş Peynir 500 gr", "price": 89.50},
            {"title": "Eriş Un 5 Kg", "price": 72.90},
            {"title": "Doğuş Filiz Çay 1 Kg", "price": 145.00},
        ],
        "cosmetics": [
            {"title": "İpana 3D White Diş Macunu 75 ml", "price": 45.90},
            {"title": "Loreal Paris Nemlendirici Krem 50 ml", "price": 189.90},
            {"title": "Elidor Şampuan 400 ml", "price": 79.90},
        ],
        "electronics": [
            {"title": "Samsung T7 Portable SSD 1 TB", "price": 2899.00},
            {"title": "Logitech G305 Mouse", "price": 1099.00},
        ],
    }
    category_hint = payload.category_hint or "grocery"

    if img == "mock_data" or img in {"grocery", "cosmetics", "electronics"}:
        items = normalize_receipt_items(
            demo_items[category_hint if img == "mock_data" else img],
            category_hint,
        )
        demo_store = {
            "grocery": "migros",
            "cosmetics": "gratis",
            "electronics": "vatanbilgisayar",
        }[category_hint if img == "mock_data" else img]
        return {
            "store": demo_store,
            "purchased_at": default_date,
            "total": receipt_total(items),
            "detected_items": items,
            "receipt_info": ["Demo fiş verisi"],
        }
    if "cosmetics_receipt" in img or "electronics_receipt" in img:
        category_hint = "cosmetics" if "cosmetics_receipt" in img else "electronics"
        items = normalize_receipt_items(demo_items[category_hint], category_hint)
        return {
            "store": "gratis" if category_hint == "cosmetics" else "vatanbilgisayar",
            "purchased_at": default_date,
            "total": receipt_total(items),
            "detected_items": items,
            "receipt_info": ["Demo fiş verisi"],
        }

    try:
        img_data = img if img.startswith("data:image/") else f"data:image/png;base64,{img}"
        response = requests.post(
            "https://api.ocr.space/parse/image",
            headers={"apikey": os.getenv("OCR_SPACE_API_KEY", "helloworld")},
            data={
                "base64Image": img_data,
                "language": "tur",
                "isOverlayRequired": "false",
            },
            timeout=15,
        )
        response.raise_for_status()
        parsed_results = response.json().get("ParsedResults", [])
        raw_ocr_text = "\n".join(
            str(result.get("ParsedText") or "").strip()
            for result in parsed_results
            if str(result.get("ParsedText") or "").strip()
        ).strip()
        if not raw_ocr_text:
            raise HTTPException(status_code=422, detail="OCR metni bulunamadı.")

        detected_category = categorize_receipt(raw_ocr_text)
        metadata = extract_receipt_metadata(raw_ocr_text)
        try:
            parsed_receipt = parse_receipt_details(raw_ocr_text, detected_category)
        except Exception:
            parsed_receipt = {"items": [], "receipt_info": [raw_ocr_text]}
        detected = [
            {**item, "category": detected_category}
            for item in parsed_receipt.get("items", [])
        ]
        return {
            "status": "processed",
            "message": "Fiş işlendi ve analiz edildi",
            "store": metadata.get("store") or receipt_store_from_text(
                raw_ocr_text,
                detected_category,
            ),
            "purchased_at": metadata.get("purchased_at") or "",
            "payment_method": metadata.get("payment_method") or "unknown",
            "total": (
                metadata.get("total")
                if metadata.get("total") is not None
                else receipt_total(detected)
            ),
            "detected_items": detected,
            "receipt_info": parsed_receipt.get("receipt_info", []),
            "raw_ocr_text": raw_ocr_text,
            "category": detected_category,
            "auto_categorized": True,
        }
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        print(f"OCR.space API error: {exc}")

    raise HTTPException(status_code=422, detail="OCR metni bulunamadı.")


@app.get("/api/receipts")
def list_receipts(
    request: Request,
    month: str | None = None,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    receipts = [
        receipt for receipt in db.get("receipts", [])
        if receipt.get("owner_id") == owner_id
    ]
    receipts.sort(
        key=lambda receipt: receipt.get("purchased_at") or "",
        reverse=True,
    )
    filtered = receipts
    if month:
        filtered = [
            receipt for receipt in receipts
            if str(receipt.get("purchased_at") or "").startswith(month)
        ]
    return {"receipts": filtered, "summary": receipt_summary(receipts, month)}


@app.post("/api/receipts")
def create_receipt(
    payload: ReceiptCreateRequest,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    raw_ocr_text = (payload.raw_ocr_text or "").strip()
    detected_category = categorize_receipt(raw_ocr_text)
    try:
        items = []
        for item in payload.items:
            row = item.model_dump()
            # Kullanıcının/OCR inceleme ekranının verdiği kategori korunur.
            # Yalnızca "other" ise ürün adından veya fiş genelinden tahmin et.
            if row.get("category") == "other":
                row["category"] = category_mapping(
                    str(row.get("title") or ""),
                    detected_category,
                )
            items.append(row)
    except Exception:
        items = []
    try:
        calculated_total = receipt_total(items)
    except Exception:
        calculated_total = 0.0
        items = []
    try:
        total = (
            round(float(payload.total), 2)
            if payload.total is not None
            else calculated_total
        )
    except Exception:
        total = calculated_total
    note = payload.note
    if raw_ocr_text and (not items or not total):
        note = raw_ocr_text
    receipt = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "store": payload.store.strip(),
        "purchased_at": (
            normalize_receipt_date(payload.purchased_at)
            if payload.purchased_at
            else ""
        ),
        "payment_method": payload.payment_method,
        "category": detected_category,
        "items": items,
        "subtotal": calculated_total,
        "total": total,
        "note": note,
        "raw_ocr_text": raw_ocr_text,
        "auto_categorized": True,
        "created_at": utc_now(),
    }
    db.setdefault("receipts", []).append(receipt)
    save_db(db)
    receipt["message"] = "Fiş işlendi ve analiz edildi"
    return receipt


@app.delete("/api/receipts/{receipt_id}")
def delete_receipt(
    receipt_id: str,
    request: Request,
    x_device_id: str | None = Header(default=None),
) -> dict:
    owner_id = request_owner_id(request, x_device_id)
    db = load_db()
    before = len(db.get("receipts", []))
    db["receipts"] = [
        receipt for receipt in db.get("receipts", [])
        if not (
            receipt.get("id") == receipt_id
            and receipt.get("owner_id") == owner_id
        )
    ]
    if len(db["receipts"]) == before:
        raise HTTPException(status_code=404, detail="Fiş bulunamadı.")
    save_db(db)
    return {"status": "deleted", "id": receipt_id}


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


# ══════════════════════════════════════════════════════════════
# Sprint 5 — İşletme Analitiği & Kullanıcı Tutundurma
# ══════════════════════════════════════════════════════════════

# ── Kullanıcı Dashboard ───────────────────────────────────────

@app.get("/api/dashboard")
def get_dashboard(request: Request, user=Depends(require_login)):
    """
    Kullanıcının tasarruf paneli verileri.
    Döndürür: toplam tasarruf, aylık grafik, market karşılaştırma,
              son indirimler, fiyat uyarıları, A/B varyantları.
    """
    from app.analytics_engine import analytics_engine
    from app.ab_testing import ab_engine

    user_id = user.get("id") or user.get("sub")
    device_id = request.headers.get("X-Device-ID")

    data = analytics_engine.get_dashboard_data(
        user_id,
        device_id=device_id,
        ab_engine=ab_engine,
    )
    return analytics_engine.to_dict(data)


@app.get("/api/dashboard/savings")
def get_savings(request: Request, user=Depends(require_login)):
    """Kullanıcının detaylı tasarruf özetini döndürür."""
    from app.analytics_engine import analytics_engine

    user_id = user.get("id") or user.get("sub")
    summary = analytics_engine.get_savings_summary(user_id)
    return {
        "total_saved": summary.total_saved,
        "save_count": summary.save_count,
        "points": summary.points,
        "streak_days": summary.streak_days,
        "monthly": summary.monthly,
        "by_store": summary.by_store,
    }


@app.get("/api/dashboard/price-history")
def get_price_history(
    request: Request,
    product: str,
    user=Depends(require_login),
):
    """Bir ürün için fiyat geçmişi (Chart.js için zaman serisi)."""
    from app.analytics_engine import analytics_engine

    user_id = user.get("id") or user.get("sub")
    product_clean = sanitize(product, max_length=100)
    history = analytics_engine.get_price_history(user_id, product_clean)
    return {"product": product_clean, "history": history}


# ── Etkinlik Takibi ───────────────────────────────────────────

class AnalyticsEventPayload(BaseModel):
    event_type: str = Field(..., max_length=50)
    payload: dict = Field(default_factory=dict)
    session_id: str | None = None
    platform: str = "web"


@app.post("/api/analytics/event")
def track_analytics_event(
    request: Request,
    body: AnalyticsEventPayload,
    user=Depends(require_login),
):
    """Kullanıcı etkinliği kaydeder (arama, görüntüleme, watchlist, vb.)."""
    from app.analytics_engine import analytics_engine
    from app.retention_service import award_points

    user_id  = user.get("id") or user.get("sub")
    device_id = request.headers.get("X-Device-ID")

    analytics_engine.track_event(
        sanitize(body.event_type, max_length=50),
        user_id=user_id,
        device_id=device_id,
        session_id=body.session_id,
        payload=body.payload,
        platform=body.platform,
    )

    # Uygulama açma puanı (günlük 1 kez)
    points_earned = 0
    if body.event_type == "open_app":
        points_earned = award_points(user_id, "app_open")

    return {"ok": True, "points_earned": points_earned}


# ── A/B Test Yönetimi ──────────────────────────────────────────

@app.get("/api/ab/variant/{experiment_key}")
def get_ab_variant(
    request: Request,
    experiment_key: str,
    user=Depends(require_login),
):
    """Kullanıcının deneyden aldığı varyantı döndürür."""
    from app.ab_testing import ab_engine

    user_id   = user.get("id") or user.get("sub")
    device_id = request.headers.get("X-Device-ID")
    key_clean = sanitize(experiment_key, max_length=60)
    variant   = ab_engine.get_variant(user_id, key_clean, device_id=device_id)
    return {"experiment": key_clean, "variant": variant}


class ABEventPayload(BaseModel):
    event_name: str = Field(..., max_length=60)
    value: float | None = None


@app.post("/api/ab/event/{experiment_key}")
def track_ab_event(
    request: Request,
    experiment_key: str,
    body: ABEventPayload,
    user=Depends(require_login),
):
    """A/B deney olayı kaydeder (dönüşüm, tıklama vb.)."""
    from app.ab_testing import ab_engine

    user_id   = user.get("id") or user.get("sub")
    device_id = request.headers.get("X-Device-ID")
    ok = ab_engine.track_event(
        sanitize(experiment_key, max_length=60),
        sanitize(body.event_name, max_length=60),
        user_id=user_id,
        device_id=device_id,
        value=body.value,
    )
    return {"ok": ok}


# ── Admin A/B Paneli ──────────────────────────────────────────

@app.get("/api/admin/ab/experiments")
def list_ab_experiments(user=Depends(require_admin)):
    from app.ab_testing import ab_engine
    return ab_engine.list_experiments()


class CreateExperimentPayload(BaseModel):
    key: str = Field(..., max_length=60)
    description: str = Field(default="", max_length=200)
    variants: list[str] = Field(default=["control", "variant_a"])
    traffic_pct: int = Field(default=100, ge=1, le=100)


@app.post("/api/admin/ab/experiments")
def create_ab_experiment(body: CreateExperimentPayload, user=Depends(require_admin)):
    from app.ab_testing import ab_engine
    result = ab_engine.create_experiment(
        sanitize(body.key, max_length=60),
        sanitize(body.description, max_length=200),
        variants=body.variants,
        traffic_pct=body.traffic_pct,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Deney oluşturulamadı")
    return result


@app.get("/api/admin/ab/results/{experiment_key}")
def get_ab_results(experiment_key: str, user=Depends(require_admin)):
    from app.ab_testing import ab_engine
    return ab_engine.get_results(sanitize(experiment_key, max_length=60))


@app.delete("/api/admin/ab/experiments/{experiment_key}")
def stop_ab_experiment(
    experiment_key: str,
    winner: str | None = None,
    user=Depends(require_admin),
):
    from app.ab_testing import ab_engine
    ok = ab_engine.stop_experiment(
        sanitize(experiment_key, max_length=60),
        winner_variant=sanitize(winner, max_length=40) if winner else None,
    )
    return {"ok": ok}


# ── Admin Sistem Sağlığı ──────────────────────────────────────

@app.get("/api/admin/health")
def admin_system_health(user=Depends(require_admin)):
    """
    Admin kontrol paneli: scraper sağlığı, AI job istatistikleri,
    DAU ve katalog tarama geçmişi.
    """
    from app.analytics_engine import analytics_engine
    return analytics_engine.get_admin_dashboard()


@app.get("/api/admin/health/scrapers")
def admin_scraper_health(user=Depends(require_admin)):
    from app.analytics_engine import analytics_engine
    return {"scrapers": analytics_engine.get_system_health()}


# ── Puan Sistemi ──────────────────────────────────────────────

@app.get("/api/points")
def get_my_points(user=Depends(require_login)):
    from app.retention_service import get_user_points
    user_id = user.get("id") or user.get("sub")
    return {"user_id": user_id, "points": get_user_points(user_id)}


class AwardPointsPayload(BaseModel):
    user_id: str
    reason: str
    custom_amount: int | None = None


@app.post("/api/admin/points/award")
def admin_award_points(body: AwardPointsPayload, user=Depends(require_admin)):
    from app.retention_service import award_points
    pts = award_points(
        body.user_id,
        sanitize(body.reason, max_length=60),
        custom_amount=body.custom_amount,
    )
    return {"awarded": pts}


# ── Digest Cron & Manuel Tetikleyici ─────────────────────────

@app.get("/cron/weekly-digest")
async def cron_weekly_digest(request: Request):
    """Vercel Cron: Her Pazartesi 07:00 UTC."""
    require_cron_request(request)
    from app.retention_service import retention_service
    result = await asyncio.to_thread(retention_service.run_weekly_digest)
    return {"ok": True, **result}


@app.post("/api/admin/digest/send")
async def send_digest_now(
    user=Depends(require_admin),
    target_user_id: str | None = None,
):
    """Admin: belirli bir kullanıcıya anında digest gönder."""
    from app.retention_service import retention_service
    if target_user_id:
        ok = await asyncio.to_thread(retention_service.send_single_digest, target_user_id)
        return {"ok": ok}
    result = await asyncio.to_thread(retention_service.run_weekly_digest, dry_run=False)
    return {"ok": True, **result}


# ══════════════════════════════════════════════════════════════
# Sprint 6 — İleri Seviye AI & Zeka Katmanı (Madde 101-120)
# ══════════════════════════════════════════════════════════════

# ── Semantik Arama ────────────────────────────────────────────

class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=200)
    store: str | None = None
    category: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(default=0.70, ge=0.0, le=1.0)


@app.post("/api/search/semantic")
async def semantic_search(
    request: Request,
    body: SemanticSearchRequest,
    user=Depends(require_login),
):
    """
    Anlamsal ürün araması.
    'Kışlık kahvaltılık' yazınca peynir, zeytin, reçel birlikte gelir.
    """
    from app.semantic_search import semantic_search as ss

    user_id = user.get("id") or user.get("sub")
    results = await asyncio.to_thread(
        ss.search,
        sanitize(body.query, max_length=200),
        store=body.store,
        category=body.category,
        limit=body.limit,
        threshold=body.threshold,
        user_id=user_id,
    )
    return {
        "query": body.query,
        "results": [
            {
                "product_key":   r.product_key,
                "product_title": r.product_title,
                "store":         r.store,
                "category":      r.category,
                "price":         r.price,
                "similarity":    round(r.similarity, 4),
            }
            for r in results
        ],
        "count": len(results),
    }


@app.post("/api/admin/search/index")
async def index_catalog_for_search(
    store: str | None = None,
    user=Depends(require_admin),
):
    """Admin: katalog ürünlerini vektör DB'ye yazar (cron veya manuel)."""
    from app.semantic_search import semantic_search as ss
    result = await asyncio.to_thread(ss.index_catalog_items, store)
    return result


# ── Fiyat Tahmini ─────────────────────────────────────────────

@app.get("/api/forecast/{product_key}")
async def get_price_forecast(
    product_key: str,
    store: str = "migros",
    days: int = 14,
    user=Depends(require_login),
):
    """
    Bir ürün için önümüzdeki N günlük fiyat tahmini.
    Grafik için: [{forecast_date, predicted_price, confidence_low, confidence_high, trend}]
    """
    from app.price_forecaster import price_forecaster

    key_clean = sanitize(product_key, max_length=150)
    result = await asyncio.to_thread(
        price_forecaster.forecast_from_db,
        key_clean,
        key_clean.split("::")[-1].replace("-", " ").title(),
        store,
        days=min(days, 30),
    )
    return {
        "product_key":       result.product_key,
        "store":             result.store,
        "model_version":     result.model_version,
        "historical_avg":    result.historical_avg,
        "data_points_used":  result.data_points_used,
        "guardrail_blocked": result.guardrail_blocked,
        "guardrail_reason":  result.guardrail_reason,
        "predictions": [
            {
                "date":             p.forecast_date.isoformat(),
                "price":            p.predicted_price,
                "confidence_low":   p.confidence_low,
                "confidence_high":  p.confidence_high,
                "trend":            p.trend,
                "change_pct":       p.change_pct,
            }
            for p in result.predictions
        ],
    }


# ── Buzdolabı Analizi (Computer Vision) ──────────────────────

class FridgeAnalysisRequest(BaseModel):
    image_url: str = Field(..., max_length=500)


@app.post("/api/vision/fridge")
async def analyze_fridge(
    request: Request,
    body: FridgeAnalysisRequest,
    user=Depends(require_login),
):
    """
    Buzdolabı fotoğrafından eksik ürün listesi oluşturur.
    Döndürür: detected_items + shopping_list
    """
    from app.vision_analyzer import vision_analyzer

    user_id   = user.get("id") or user.get("sub")
    device_id = request.headers.get("X-Device-ID")

    result = await asyncio.to_thread(
        vision_analyzer.analyze_fridge,
        body.image_url,
        user_id=user_id,
        device_id=device_id,
    )
    return {
        "analysis_type":         result.analysis_type,
        "model_used":            result.model_used,
        "detected_items":        result.detected_items,
        "shopping_list":         result.shopping_list,
        "guardrail_blocked_items": result.guardrail_blocked_items,
        "error":                 result.error,
    }


@app.post("/api/vision/receipt")
async def analyze_receipt(
    request: Request,
    body: FridgeAnalysisRequest,
    user=Depends(require_login),
):
    """Fiş/fatura fotoğrafından ürün-fiyat listesi çıkarır."""
    from app.vision_analyzer import vision_analyzer

    user_id = user.get("id") or user.get("sub")
    result = await asyncio.to_thread(
        vision_analyzer.analyze_receipt,
        body.image_url,
        user_id=user_id,
    )
    return {
        "model_used":    result.model_used,
        "items":         result.detected_items,
        "error":         result.error,
    }


# ── AI İzleme (Admin) ─────────────────────────────────────────

@app.get("/api/admin/ai/monitor")
def get_ai_monitor(hours: int = 24, user=Depends(require_admin)):
    """AI servis maliyet ve hata özeti (son N saat)."""
    from app.ai_monitor import AIMonitor
    return {
        "period_hours": hours,
        "cost_summary": AIMonitor.get_cost_summary(hours),
        "recent_errors": AIMonitor.get_recent_errors(20),
    }


@app.get("/api/admin/ai/latency/{service}")
def get_ai_latency(service: str, hours: int = 24, user=Depends(require_admin)):
    """Belirtilen AI servisinin latency p50/p95/p99 dağılımı."""
    from app.ai_monitor import AIMonitor
    return AIMonitor.get_latency_percentiles(sanitize(service, max_length=40), hours)


# ── Guardrail Kontrolü (Test/Admin) ──────────────────────────

class GuardrailCheckRequest(BaseModel):
    price: float
    historical_avg: float = 0.0
    forecast_series: list[float] = Field(default_factory=list)


@app.post("/api/admin/guardrails/check-price")
def check_price_guardrail(body: GuardrailCheckRequest, user=Depends(require_admin)):
    """Admin: bir fiyat tahminini guardrail'dan geçirir (test için)."""
    from app.guardrails import Guardrails
    g = Guardrails()
    results = g.run_all_price_checks(
        body.price,
        historical_avg=body.historical_avg,
        forecast_series=body.forecast_series or None,
    )
    return {
        "all_passed": g.all_passed(results),
        "checks": [
            {
                "check_type": r.check_type,
                "passed":     r.passed,
                "reason":     r.reason,
            }
            for r in results
        ],
    }


# ── Semantik İndeksleme Cron ──────────────────────────────────

@app.get("/cron/semantic-index")
async def cron_semantic_index(request: Request):
    """Vercel Cron: Her gün 04:00 UTC — katalog → vektör DB."""
    require_cron_request(request)
    from app.semantic_search import semantic_search as ss
    result = await asyncio.to_thread(ss.index_catalog_items)
    return {"ok": True, **result}


# ══════════════════════════════════════════════════════════════
# Sprint 7 — Ekosistem & İş Ortaklığı (Madde 121-140)
# ══════════════════════════════════════════════════════════════

# ── Partner API Gateway ──────────────────────────────────────

class CreatePartnerPayload(BaseModel):
    partner_id: str   = Field(..., max_length=60)
    display_name: str = Field(..., max_length=120)
    scopes: list[str]
    rate_limit_rpm: int = Field(default=60, ge=1, le=1000)
    webhook_url: str | None = None
    webhook_secret: str | None = None


@app.post("/api/admin/partners")
def create_partner_endpoint(body: CreatePartnerPayload, user=Depends(require_admin)):
    """Admin: yeni partner ve API key oluşturur."""
    from app.partner_gateway import create_partner
    try:
        result = create_partner(
            sanitize(body.partner_id, max_length=60),
            sanitize(body.display_name, max_length=120),
            body.scopes,
            rate_limit_rpm=body.rate_limit_rpm,
            webhook_url=body.webhook_url,
            webhook_secret=body.webhook_secret,
        )
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/admin/partners/{partner_id}/rotate-key")
def rotate_partner_key(partner_id: str, user=Depends(require_admin)):
    """Admin: partner API key'ini yeniler."""
    from app.partner_gateway import rotate_key
    try:
        return rotate_key(sanitize(partner_id, max_length=60))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Partner API doğrulama dependency
async def _partner_auth(request: Request, scope: str) -> "PartnerKey":
    from app.partner_gateway import partner_gateway
    raw_key = (
        request.headers.get("X-Partner-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ")
    )
    try:
        return partner_gateway.authenticate(raw_key, scope)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.get("/api/partner/prices")
async def partner_get_prices(
    request: Request,
    q: str,
    store: str | None = None,
):
    """Partner API: ürün fiyatlarını sorgular (scope: read:prices)."""
    await _partner_auth(request, "read:prices")
    from app.search_orchestrator import search_orchestrator
    results = await asyncio.to_thread(
        search_orchestrator.search,
        sanitize(q, max_length=100),
        store=store,
    )
    return {"query": q, "results": results}


@app.get("/api/partner/eco-scores/{product_key}")
async def partner_get_eco_score(request: Request, product_key: str):
    """Partner API: ürün eko-skorunu sorgular (scope: read:eco_scores)."""
    await _partner_auth(request, "read:eco_scores")
    from app.eco_score import eco_score_engine
    result = eco_score_engine.score(
        sanitize(product_key, max_length=150),
        product_key.replace("-", " "),
    )
    return {
        "product_key": result.product_key,
        "eco_score":   result.eco_score,
        "grade":       result.grade,
        "color":       result.color,
        "breakdown":   result.breakdown,
    }


# ── Kupon & Puan Dönüşümü ─────────────────────────────────────

class ExchangePointsPayload(BaseModel):
    points_to_spend: int = Field(..., ge=100, le=50000)
    partner_id: str = Field(default="almadan", max_length=60)
    validity_days: int = Field(default=30, ge=1, le=90)


@app.post("/api/coupons/exchange")
def exchange_points(
    request: Request,
    body: ExchangePointsPayload,
    user=Depends(require_login),
):
    """Kullanıcı puanlarını indirim kuponuna dönüştürür."""
    from app.coupon_engine import coupon_engine
    user_id = user.get("id") or user.get("sub")
    result = coupon_engine.exchange_points_for_coupon(
        user_id,
        body.points_to_spend,
        partner_id=sanitize(body.partner_id, max_length=60),
        validity_days=body.validity_days,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "code":            result.code,
        "discount_amount": result.discount_amount,
        "partner_id":      result.partner_id,
        "expires_at":      result.expires_at,
    }


@app.get("/api/coupons")
def list_user_coupons(user=Depends(require_login)):
    """Kullanıcının aktif kuponlarını listeler."""
    from app.coupon_engine import coupon_engine
    user_id = user.get("id") or user.get("sub")
    return coupon_engine.get_user_coupons(user_id)


class ValidateCouponPayload(BaseModel):
    code: str = Field(..., max_length=40)
    order_total: float = Field(..., ge=0)


@app.post("/api/coupons/validate")
def validate_coupon(body: ValidateCouponPayload, user=Depends(require_login)):
    """Kuponu doğrular ve indirim tutarını hesaplar (kullanmaz)."""
    from app.coupon_engine import coupon_engine
    user_id = user.get("id") or user.get("sub")
    result = coupon_engine.validate_coupon(
        sanitize(body.code, max_length=40).upper(),
        user_id=user_id,
        order_total=body.order_total,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "valid":           True,
        "discount_amount": result.discount_amount,
        "discount_pct":    result.discount_pct,
    }


@app.post("/api/coupons/redeem")
def redeem_coupon(body: ValidateCouponPayload, user=Depends(require_login)):
    """Kuponu kullanır (geri alınamaz)."""
    from app.coupon_engine import coupon_engine
    user_id = user.get("id") or user.get("sub")
    result = coupon_engine.redeem_coupon(
        sanitize(body.code, max_length=40).upper(),
        user_id=user_id,
        order_total=body.order_total,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"redeemed": True, "discount_applied": result.discount_applied}


@app.post("/api/admin/coupons")
def admin_create_coupon(request: Request, body: dict, user=Depends(require_admin)):
    """Admin: partner için toplu kupon oluşturur."""
    from app.coupon_engine import coupon_engine
    result = coupon_engine.create_partner_coupon(
        sanitize(str(body.get("partner_id", "almadan")), max_length=60),
        coupon_type=body.get("coupon_type", "percentage"),
        discount_pct=body.get("discount_pct"),
        discount_amount=body.get("discount_amount"),
        min_spend=float(body.get("min_spend", 0)),
        max_uses=int(body.get("max_uses", 100)),
        validity_days=int(body.get("validity_days", 30)),
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"code": result.code, "partner_id": result.partner_id}


# ── Grup Alışveriş ────────────────────────────────────────────

class CreateGroupBuyPayload(BaseModel):
    product_title: str  = Field(..., max_length=200)
    store: str          = Field(..., max_length=60)
    current_price: float= Field(..., gt=0)
    target_price: float = Field(..., gt=0)
    target_quantity: int= Field(..., ge=2, le=1000)
    district: str       = Field(default="", max_length=60)
    expiry_days: int    = Field(default=7, ge=1, le=30)


@app.post("/api/group-buys")
def create_group_buy(
    body: CreateGroupBuyPayload,
    user=Depends(require_login),
):
    """Yeni grup alışverişi başlatır."""
    from app.group_buy import group_buy_engine
    user_id = user.get("id") or user.get("sub")
    result = group_buy_engine.create_group_buy(
        sanitize(body.product_title, max_length=200),
        sanitize(body.store, max_length=60),
        current_price=body.current_price,
        target_price=body.target_price,
        target_quantity=body.target_quantity,
        organizer_id=user_id,
        district=sanitize(body.district, max_length=60),
        expiry_days=body.expiry_days,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"group_id": result.group_id, "ok": True}


@app.post("/api/group-buys/{group_id}/join")
def join_group_buy(
    group_id: int,
    quantity: int = 1,
    user=Depends(require_login),
):
    """Grup alışverişine katıl."""
    from app.group_buy import group_buy_engine
    user_id = user.get("id") or user.get("sub")
    result = group_buy_engine.join_group_buy(group_id, user_id, quantity=quantity)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"ok": True, "group_id": group_id}


@app.delete("/api/group-buys/{group_id}/leave")
def leave_group_buy(group_id: int, user=Depends(require_login)):
    """Gruptan ayrıl."""
    from app.group_buy import group_buy_engine
    user_id = user.get("id") or user.get("sub")
    result = group_buy_engine.leave_group_buy(group_id, user_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"ok": True}


@app.get("/api/group-buys")
def list_group_buys(
    district: str = "",
    product: str = "",
    limit: int = 20,
    user=Depends(require_login),
):
    """Bölgedeki grup alışverişlerini listeler."""
    from app.group_buy import group_buy_engine
    return group_buy_engine.get_nearby_groups(
        district=sanitize(district, max_length=60),
        product_query=sanitize(product, max_length=100),
        limit=min(limit, 50),
    )


@app.get("/api/group-buys/{group_id}")
def get_group_buy(group_id: int, user=Depends(require_login)):
    """Grup detaylarını döndürür."""
    from app.group_buy import group_buy_engine
    detail = group_buy_engine.get_group_details(group_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    return detail


@app.get("/api/group-buys/my/list")
def my_group_buys(user=Depends(require_login)):
    """Kullanıcının katıldığı gruplar."""
    from app.group_buy import group_buy_engine
    user_id = user.get("id") or user.get("sub")
    return group_buy_engine.get_user_groups(user_id)


# ── Eko-Skor ─────────────────────────────────────────────────

@app.get("/api/eco-score/{product_key}")
def get_eco_score(
    product_key: str,
    title: str = "",
    packaging: str = "unknown",
    origin: str = "unknown",
    user=Depends(require_login),
):
    """Ürün için Eko-Skor hesaplar."""
    from app.eco_score import eco_score_engine
    key_clean = sanitize(product_key, max_length=150)
    result = eco_score_engine.score(
        key_clean,
        sanitize(title or key_clean, max_length=200),
        packaging_hint=packaging,
        origin_hint=origin,
    )
    return {
        "product_key":   result.product_key,
        "eco_score":     result.eco_score,
        "grade":         result.grade,
        "color":         result.color,
        "is_eco_friendly": result.is_eco_friendly,
        "breakdown":     result.breakdown,
        "certifications": result.certifications,
        "packaging_type": result.packaging_type,
    }


class BasketEcoPayload(BaseModel):
    product_keys: list[str] = Field(..., max_length=50)


@app.post("/api/eco-score/basket")
def basket_eco_score(body: BasketEcoPayload, user=Depends(require_login)):
    """Alışveriş sepetinin ortalama Eko-Skorunu hesaplar."""
    from app.eco_score import eco_score_engine
    summary = eco_score_engine.get_eco_summary(
        [sanitize(k, max_length=150) for k in body.product_keys]
    )
    return summary


# ── Grup Alışveriş Expire Cron ────────────────────────────────

@app.get("/cron/group-buy-expire")
async def cron_group_buy_expire(request: Request):
    """Vercel Cron: Her saat — süresi dolan grupları kapatır."""
    require_cron_request(request)
    from app.group_buy import group_buy_engine
    count = await asyncio.to_thread(group_buy_engine.expire_old_groups)
    return {"ok": True, "expired_count": count}


# -- Sprint 8: Kirilmazlik & Gozlemlenebilirlik --

# -- Circuit Breaker --

@app.get("/api/admin/circuit-breakers")
async def list_circuit_breakers(request: Request, admin=Depends(require_admin)):
    from app.resilience import get_all_circuit_states
    return {"circuit_breakers": get_all_circuit_states()}


@app.post("/api/admin/circuit-breakers/{service}/reset")
async def reset_circuit_breaker_endpoint(service: str, request: Request, admin=Depends(require_admin)):
    VALID_SERVICES = {"supabase", "replicate", "openai", "scrapers", "push"}
    if service not in VALID_SERVICES:
        raise HTTPException(status_code=400, detail=f"Gecersiz servis: {service}")
    from app.resilience import reset_circuit_breaker
    reset_circuit_breaker(service)
    return {"ok": True, "service": service, "state": "closed"}


# -- Performans Istatistikleri --

@app.get("/api/admin/performance/latency")
async def get_performance_stats(request: Request, hours: int = 1, admin=Depends(require_admin)):
    from app.observability import get_latency_stats
    stats = await asyncio.to_thread(get_latency_stats, hours)
    return {"hours": hours, "endpoints": stats}


@app.get("/api/admin/cache/stats")
async def get_cache_stats_endpoint(request: Request, admin=Depends(require_admin)):
    from app.cache_strategy import get_cache_stats
    return get_cache_stats()


@app.post("/api/admin/cache/invalidate")
async def invalidate_cache_endpoint(request: Request, admin=Depends(require_admin)):
    from app.cache_strategy import get_price_cache, get_search_cache, get_product_cache
    get_price_cache().clear()
    get_search_cache().clear()
    get_product_cache().clear()
    return {"ok": True, "message": "Tum L1 cache temizlendi"}


# -- Chaos Engineering --

class ChaosStartPayload(BaseModel):
    scenario: str


@app.post("/api/admin/chaos/start")
async def chaos_start(request: Request, body: ChaosStartPayload, admin=Depends(require_admin)):
    from app.chaos import run_scenario
    result = await asyncio.to_thread(run_scenario, body.scenario, triggered_by="admin_api")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/admin/chaos/stop/{scenario_name}")
async def chaos_stop(scenario_name: str, request: Request, admin=Depends(require_admin)):
    from app.chaos import get_chaos_runner
    stopped = get_chaos_runner().stop(scenario_name)
    return {"ok": stopped, "scenario": scenario_name}


@app.get("/api/admin/chaos/scenarios")
async def list_chaos_scenarios(request: Request, admin=Depends(require_admin)):
    from app.chaos import SCENARIOS, FaultType
    return {
        "scenarios": [
            {
                "name": k,
                "target_service": v["target_service"],
                "fault_type": v["fault_type"].value if isinstance(v["fault_type"], FaultType) else v["fault_type"],
                "duration_sec": v.get("duration_sec", 30),
            }
            for k, v in SCENARIOS.items()
        ]
    }


# -- Sistem Saglik Kontrol --

@app.get("/health")
async def health_check():
    from app.resilience import get_all_circuit_states
    from app.cache_strategy import get_cache_stats
    cb_states = get_all_circuit_states()
    open_cbs = [c for c in cb_states if c["state"] == "open"]
    return {
        "status": "degraded" if open_cbs else "ok",
        "open_circuit_breakers": open_cbs,
        "cache": get_cache_stats(),
        "region": os.getenv("VERCEL_REGION", "fra1"),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# -- Cron: Metrik Temizleme --

@app.get("/cron/cleanup-metrics")
async def cron_cleanup_metrics(request: Request):
    require_cron_request(request)
    import requests as _req_c
    _sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    _sb_key = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
    if not _sb_url:
        return {"ok": True, "skipped": True}
    hdrs = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}", "Content-Type": "application/json"}
    try:
        _req_c.post(f"{_sb_url}/rest/v1/rpc/cleanup_request_metrics", headers=hdrs, timeout=10)
        _req_c.post(f"{_sb_url}/rest/v1/rpc/cleanup_old_logs", headers=hdrs, timeout=10)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# -- Sprint 9: Final Sprint - Uyumluluk & Dokumantasyon --

# -- OpenAPI ozellestirilmis sema --

from app.openapi_config import custom_openapi, APP_VERSION, APP_TITLE

app.title = APP_TITLE
app.version = APP_VERSION
app.openapi = lambda: custom_openapi(app)

# -- KVKK / GDPR Endpoint'leri --

@app.delete("/api/me/forget", tags=["KVKK / GDPR"])
async def right_to_be_forgotten(request: Request, user=Depends(require_login)):
    """
    KVKK Madde 7 / GDPR Article 17 - Unutulma Hakki.
    Kullaniciya ait tum kisisel veriyi siler ve Supabase Auth hesabini kapatir.
    Bu islem geri alinamaz.
    """
    from app.gdpr import gdpr_service
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Kullanici kimlik bilgisi alinamadi")
    result = await asyncio.to_thread(gdpr_service.forget, user_id)
    status = 200 if result.success else 207
    return JSONResponse(content=result.to_dict(), status_code=status)


@app.get("/api/me/export", tags=["KVKK / GDPR"])
async def data_export(request: Request, user=Depends(require_login)):
    """
    KVKK Madde 11 / GDPR Article 15 - Veri Erisim Hakki (SAR).
    Kullaniciya ait tum verilerin JSON paketi olarak dondurulur.
    """
    from app.gdpr import gdpr_service
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Kullanici kimlik bilgisi alinamadi")
    sar = await asyncio.to_thread(gdpr_service.export, user_id)
    return {
        "user_id":      sar.user_id,
        "generated_at": sar.generated_at,
        "data":         sar.data,
    }


@app.put("/api/me/consent/{consent_type}", tags=["KVKK / GDPR"])
async def update_consent(
    consent_type: str,
    request: Request,
    user=Depends(require_login),
):
    """
    Onay guncelleme: marketing, analytics, push, data_sharing.
    """
    VALID_TYPES = {"marketing", "analytics", "push", "data_sharing"}
    if consent_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Gecersiz onay turu: {consent_type}")
    body = await request.json()
    granted = bool(body.get("granted", False))
    user_id = user.get("id") or user.get("sub")
    import requests as _req_c
    _sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    _sb_key = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
    if _sb_url:
        hdrs = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}",
                "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
        row = {
            "user_id": user_id,
            "consent_type": consent_type,
            "granted": granted,
            "granted_at": datetime.now(timezone.utc).isoformat() if granted else None,
            "revoked_at": datetime.now(timezone.utc).isoformat() if not granted else None,
        }
        _req_c.post(f"{_sb_url}/rest/v1/user_consents", headers=hdrs, json=row, timeout=5)
    return {"ok": True, "consent_type": consent_type, "granted": granted}


@app.get("/api/me/consents", tags=["KVKK / GDPR"])
async def get_consents(request: Request, user=Depends(require_login)):
    """Kullanicinin mevcut onay durumlarini listeler."""
    user_id = user.get("id") or user.get("sub")
    import requests as _req_c
    _sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    _sb_key = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
    if not _sb_url:
        return {"consents": []}
    hdrs = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}",
            "Content-Type": "application/json"}
    try:
        r = _req_c.get(f"{_sb_url}/rest/v1/user_consents",
                       params={"user_id": f"eq.{user_id}", "select": "consent_type,granted,granted_at,revoked_at"},
                       headers=hdrs, timeout=5)
        return {"consents": r.json() if r.ok else []}
    except Exception:
        return {"consents": []}


@app.get("/api/admin/gdpr/requests", tags=["Admin"])
async def list_gdpr_requests(
    request: Request,
    admin=Depends(require_admin),
    limit: int = 50,
):
    """Son GDPR/KVKK taleplerini listeler (admin)."""
    import requests as _req_c
    _sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    _sb_key = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
    if not _sb_url:
        return {"requests": []}
    hdrs = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}",
            "Content-Type": "application/json"}
    r = _req_c.get(
        f"{_sb_url}/rest/v1/gdpr_requests",
        params={"select": "*", "order": "requested_at.desc", "limit": limit},
        headers=hdrs, timeout=5,
    )
    return {"requests": r.json() if r.ok else []}


# -- /api/status + Health Check --

import json as _json
import pathlib as _pathlib

_LOG_DIR  = _pathlib.Path("app_logs")
_LAST_TEST = _LOG_DIR / "last_test.json"
_FAIL_LOG  = _LOG_DIR / "failure.log"

def _read_last_test() -> dict:
    try:
        if _LAST_TEST.exists():
            return _json.loads(_LAST_TEST.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

@app.get("/api/status")
async def api_status():
    """
    Sistem saglik durumunu dondurur.
    last_test.json dosyasindaki son health-check sonucunu okur.
    """
    last = _read_last_test()
    from app.resilience import get_all_circuit_states
    cb_states = get_all_circuit_states()
    open_cbs  = [c["service"] for c in cb_states if c["state"] == "open"]
    return {
        "status":        "degraded" if open_cbs else "ok",
        "last_test":     last.get("result", "never_run"),
        "last_run":      last.get("ts"),
        "open_circuits": open_cbs,
        "error":         last.get("error"),
        "version":       "9.0.0",
    }


@app.post("/api/admin/run-health-check")
async def run_health_check_endpoint(request: Request, admin=Depends(require_admin)):
    """Health check testlerini tetikler ve sonucu last_test.json'a yazar."""
    import subprocess, sys
    _LOG_DIR.mkdir(exist_ok=True)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/health_check_test.py", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=60,
        )
        passed = proc.returncode == 0
        result_data = {
            "result": "success" if passed else "failure",
            "ts": datetime.now(timezone.utc).isoformat(),
            "stdout": proc.stdout[-3000:],
            "error": None if passed else proc.stdout[-1000:] + proc.stderr[-500:],
        }
        _LAST_TEST.write_text(_json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not passed:
            with open(_FAIL_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[{result_data['ts']}] Health check FAILED\n")
                f.write(result_data["error"] or "")
                f.write("\n" + "-"*60 + "\n")
        # Bildirim gönder (hata → her zaman; düzelme → önceki hata ise)
        prev = _read_last_test().get("result")
        from app.notifier import notify_health_result
        notify_sent = await asyncio.to_thread(
            notify_health_result,
            result_data["result"],
            error=result_data.get("error"),
            prev_result=prev,
        )
        result_data["notify_sent"] = notify_sent
        return result_data
    except subprocess.TimeoutExpired:
        return {"result": "timeout", "ts": datetime.now(timezone.utc).isoformat(), "error": "Test 60s timeout"}
    except Exception as exc:
        return {"result": "error", "ts": datetime.now(timezone.utc).isoformat(), "error": str(exc)}


# -- Notifier Entegrasyonu --

def _verify_cron_secret(x_cron_secret: str | None) -> tuple[bool, str]:
    """
    X-Cron-Secret header'ını doğrular.
    Returns: (ok: bool, reason: str)
    reason asla secret değerini içermez — loglarda görünmesi güvenlidir.
    """
    env_secret = os.getenv("CRON_SECRET", "").strip()
    if not env_secret:
        return False, "CRON_SECRET env var tanımlı değil"
    if not x_cron_secret:
        return False, "X-Cron-Secret header eksik"
    if len(x_cron_secret.strip()) != len(env_secret):
        return False, "Secret uzunluğu eşleşmiyor"
    if not hmac.compare_digest(env_secret, x_cron_secret.strip()):
        return False, "Secret değeri eşleşmiyor"
    return True, "ok"


def _require_cron_or_admin_sync(x_cron_secret: str | None) -> None:
    """Secret doğrulamasını senkron olarak yapar (admin session olmadan)."""
    ok, reason = _verify_cron_secret(x_cron_secret)
    if not ok:
        _IS_DEV = os.getenv("VERCEL_ENV", "development") != "production"
        detail = f"Yetkisiz erişim. Sebep: {reason}" if _IS_DEV else "Yetkisiz erişim."
        raise HTTPException(status_code=403, detail=detail)


@app.get("/api/admin/notifier/status")
async def notifier_status_endpoint(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
):
    """
    Bildirim kanallarının yapılandırılıp yapılandırılmadığını gösterir.
    GET — X-Cron-Secret header'ı veya admin oturumu ile erişilir.
    """
    ok, _ = _verify_cron_secret(x_cron_secret)
    if not ok:
        try:
            await require_admin(request)
        except HTTPException:
            _require_cron_or_admin_sync(x_cron_secret)  # detaylı hata fırlatır

    from app.notifier import notifier_status
    return notifier_status()


@app.post("/api/admin/notifier/test")
async def notifier_test(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
):
    """
    Yapılandırılmış bildirim kanallarına test mesajı gönderir.
    POST — X-Cron-Secret header'ı veya admin oturumu ile erişilir.
    """
    ok, _ = _verify_cron_secret(x_cron_secret)
    if not ok:
        try:
            await require_admin(request)
        except HTTPException:
            _require_cron_or_admin_sync(x_cron_secret)  # detaylı hata fırlatır

    from app.notifier import notify_failure
    result = await asyncio.to_thread(
        notify_failure,
        "Bu bir test bildirimidir. Sistem normal çalışıyor.",
        test_name="manual_test",
    )
    return {"sent": result, "any_sent": any(result.values())}


# ── Tüketim & Hatırlatıcı Modülü ─────────────────────────────────────────────

class ReminderPayload(BaseModel):
    product_url:        str
    product_title:      str = ""
    last_purchase_date: str          # ISO date "YYYY-MM-DD"
    reorder_days:       int          # Tekrar alma periyodu (gün)
    remind_before_days: int = 5      # Kaç gün önce hatırlat


def _calc_reminder_dates(last_purchase_date: str, reorder_days: int, remind_before_days: int) -> dict:
    """Tahmini bitiş ve hatırlatıcı tarihini hesaplar."""
    from datetime import date, timedelta
    purchase = date.fromisoformat(last_purchase_date)
    end_date      = purchase + timedelta(days=reorder_days)
    reminder_date = end_date - timedelta(days=remind_before_days)
    today         = date.today()
    days_left     = (end_date - today).days
    return {
        "estimated_end_date": end_date.isoformat(),
        "reminder_date":      reminder_date.isoformat(),
        "days_until_empty":   days_left,
    }


@app.post("/api/reminders")
async def create_reminder(payload: ReminderPayload, request: Request, user=Depends(require_login)):
    """Ürün için tüketim hatırlatıcısı oluşturur."""
    dates = _calc_reminder_dates(
        payload.last_purchase_date, payload.reorder_days, payload.remind_before_days
    )
    row = {
        "user_id":            user["id"],
        "product_url":        payload.product_url,
        "product_title":      payload.product_title,
        "last_purchase_date": payload.last_purchase_date,
        "reorder_days":       payload.reorder_days,
        "remind_before_days": payload.remind_before_days,
        "notified":           False,
    }
    resp = requests.post(
        f"{supabase_base_url()}/rest/v1/product_reminders",
        headers={**supabase_headers(), "Prefer": "return=representation"},
        json=row, timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise HTTPException(status_code=500, detail="Hatırlatıcı kaydedilemedi.")
    return {**data[0], **dates}


@app.get("/api/reminders")
async def list_reminders(request: Request, user=Depends(require_login)):
    """Kullanıcının tüm hatırlatıcılarını listeler, tarih hesaplamalarıyla birlikte."""
    resp = requests.get(
        f"{supabase_base_url()}/rest/v1/product_reminders",
        headers=supabase_headers(),
        params={"user_id": f"eq.{user['id']}", "select": "*", "order": "last_purchase_date.asc"},
        timeout=10,
    )
    rows = resp.json() if resp.ok else []
    enriched = []
    for r in rows:
        dates = _calc_reminder_dates(r["last_purchase_date"], r["reorder_days"], r["remind_before_days"])
        enriched.append({**r, **dates})
    return {"reminders": enriched}


@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str, request: Request, user=Depends(require_login)):
    """Hatırlatıcıyı siler (sadece kendi kaydı)."""
    requests.delete(
        f"{supabase_base_url()}/rest/v1/product_reminders",
        headers=supabase_headers(),
        params={"id": f"eq.{reminder_id}", "user_id": f"eq.{user['id']}"},
        timeout=10,
    )
    return {"deleted": reminder_id}


@app.get("/cron/check-reminders")
async def cron_check_reminders(request: Request):
    """
    Vercel Cron: Her gün sabah 08:00'de çalışır.
    Hatırlatıcı tarihi gelen ürünler için bildirim gönderir.
    """
    require_cron_request(request)
    from datetime import date
    from app.notifier import notify_restock_reminder

    today = date.today().isoformat()

    # reminder_date <= bugün AND notified = false
    # Hesaplanan tarihler DB'de değil — uygulama katmanında filtreleriz
    resp = requests.get(
        f"{supabase_base_url()}/rest/v1/product_reminders",
        headers=supabase_headers(),
        params={"notified": "eq.false", "select": "*"},
        timeout=10,
    )
    rows = resp.json() if resp.ok else []

    sent = 0
    for r in rows:
        try:
            dates = _calc_reminder_dates(r["last_purchase_date"], r["reorder_days"], r["remind_before_days"])
            if dates["reminder_date"] > today:
                continue  # henüz hatırlatma günü değil

            result = await asyncio.to_thread(
                notify_restock_reminder,
                r.get("product_title") or r["product_url"],
                days_until_empty=max(0, dates["days_until_empty"]),
                product_url=r["product_url"],
            )
            if any(result.values()):
                requests.patch(
                    f"{supabase_base_url()}/rest/v1/product_reminders",
                    headers=supabase_headers(),
                    params={"id": f"eq.{r['id']}"},
                    json={"notified": True},
                    timeout=10,
                )
                sent += 1
        except Exception:
            pass

    return {"checked": len(rows), "notified": sent, "date": today}


# ── Mağaza Bülten & Takip Modülü ─────────────────────────────────────────────

# Türkçe gün adı → İngilizce slug eşlemesi (publication_day DB'de İngilizce saklanıyor)
_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

ALL_STORES_MAP = {
    "market": ["bim", "a101", "sok", "hakmarekspres", "migros", "5mmigros", "migrosjet", "carrefoursa", "carrefoursagurme", "tarimkredi", "file", "macrocenter", "happycenter", "onurmarket", "mopas", "hakmar", "cagrimarket", "bizimtoptan", "metro", "secmarket"],
    "tech": ["teknosa", "mediamarkt", "vatanbilgisayar", "troy", "gurgencer", "pozitifteknoloji", "samsung", "huawei", "mistore", "evkur", "cetmen", "yigitavm", "ozsanal", "itopya"],
    "beauty": ["gratis", "watsons", "rossmann", "eveshop", "sephora", "sevil", "yvesrocher", "flormar", "goldenrose", "mac", "kikomilano"],
    "fashion": ["lcwaikiki", "defacto", "koton", "mavi", "ltb", "colins", "boyner", "ozdilek", "beymen", "vakko", "trendyolmilla", "altinyildiz", "kigili", "sarar", "suvari", "hatemoglu", "tudors", "ipekyol", "twist", "machka", "penti", "zara", "bershka", "pullandbear", "stradivarius", "massimodutti", "hm", "mango", "flo", "instreet", "deichmann", "ayakkabidunyasi", "superstep", "sportive", "decathlon"],
    "health": ["atasunoptik", "opmaroptik", "eleganceoptik", "mertoptik", "ebebek", "babymall", "joker", "gnc"],
    "home": ["karaca", "pasabahce", "bernardo", "jumbo", "korkmaz", "schafer", "porland", "hisar", "englishhome", "madamecoco", "linens", "bellamaison", "karacahome", "ikea", "koctas", "koctasfix", "bauhaus", "tekzen"],
    "online": ["trendyol", "hepsiburada", "amazon", "n11", "supplementler", "proteinocean"]
}

def _format_store_name(slug: str) -> str:
    known = {
        "bim": "BİM", "a101": "A101", "sok": "ŞOK", "migros": "Migros", "carrefoursa": "CarrefourSA",
        "carrefoursagurme": "CarrefourSA Gurme", "lcwaikiki": "LC Waikiki", "boyner": "Boyner",
        "trendyol": "Trendyol", "trendyolmilla": "Trendyolmilla", "hepsiburada": "Hepsiburada", "amazon": "Amazon", "n11": "n11",
        "mac": "MAC", "kigili": "Kiğılı", "defacto": "DeFacto", "gratis": "Gratis",
        "watsons": "Watsons", "vatanbilgisayar": "Vatan Bilgisayar", "mediamarkt": "MediaMarkt",
        "5mmigros": "5M Migros", "migrosjet": "Migros Jet", "tarimkredi": "Tarım Kredi",
        "macrocenter": "Macrocenter", "happycenter": "Happy Center", "onurmarket": "Onur Market",
        "bizimtoptan": "Bizim Toptan", "secmarket": "Seç Market", "hakmarekspres": "Hakmar Ekspres",
        "pozitifteknoloji": "Pozitif Teknoloji", "mistore": "Mi Store", "ozsanal": "Özşanal",
        "eveshop": "Eve Shop", "yvesrocher": "Yves Rocher", "kikomilano": "Kiko Milano",
        "goldenrose": "Golden Rose", "beymen": "Beymen", "pullandbear": "Pull&Bear",
        "massimodutti": "Massimo Dutti", "hm": "H&M", "ayakkabidunyasi": "Ayakkabı Dünyası",
        "atasunoptik": "Atasun Optik", "opmaroptik": "Opmar Optik", "eleganceoptik": "Elegance Optik",
        "mertoptik": "Mert Optik", "ebebek": "e-bebek", "babymall": "BabyMall",
        "pasabahce": "Paşabahçe", "englishhome": "English Home", "madamecoco": "Madame Coco",
        "bellamaison": "Bella Maison", "karacahome": "Karaca Home", "koctas": "Koçtaş",
        "koctasfix": "Koçtaş Fix"
    }
    return known.get(slug, slug.capitalize())

_STORE_DESCRIPTIONS = {
    "bim": "Haftalık aktüel ürün katalogları ve fırsatlar anında gelsin.",
    "a101": "Her perşembe yeni aktüel ürünler ve indirimli kampanyalar.",
    "sok": "Haftalık ŞOK aktüel katalog ve özel fırsatlar.",
    "migros": "Migros kampanya ve indirimlerini kaçırma.",
    "carrefoursa": "CarrefourSA haftalık fırsatları ve kampanya bildirimler.",
    "carrefoursagurme": "Gurme ürünlerde özel indirim ve kampanyalar.",
    "hakmarekspres": "Hakmar Ekspres aktüel ürün ve fırsatlar.",
    "5mmigros": "5M Migros büyük format kampanyaları.",
    "migrosjet": "Migros Jet market kampanya ve indirimleri.",
    "tarimkredi": "Tarım Kredi kooperatif ürün ve fırsatlar.",
    "macrocenter": "Premium market kampanya ve özel ürünler.",
    "happycenter": "Happy Center ürün ve indirim haberleri.",
    "mediamarkt": "Teknoloji ürünlerinde en iyi fırsatlar ve kampanyalar.",
    "vatanbilgisayar": "Bilgisayar ve elektronik kampanyalarını takip et.",
    "pozitifteknoloji": "Teknoloji ürünlerinde özel indirimler.",
    "mistore": "Xiaomi ürünlerinde indirim ve yeni ürün duyuruları.",
    "teknosa": "Teknoloji ürünleri kampanya ve indirim haberleri.",
    "samsung": "Samsung yeni ürün ve kampanya duyuruları.",
    "gratis": "Kozmetik ve kişisel bakım kampanyaları.",
    "watsons": "Watsons indirim ve kampanya bildirimleri.",
    "rossmann": "Rossmann kozmetik fırsatları ve kampanyalar.",
    "sephora": "Sephora güzellik ürünleri kampanya ve indirimleri.",
    "flormar": "Flormar makyaj ürünleri kampanya ve haberleri.",
    "goldenrose": "Golden Rose kozmetik ürün indirimleri.",
    "mac": "MAC Cosmetics yeni koleksiyon ve kampanyalar.",
    "kikomilano": "Kiko Milano fırsatları ve yeni ürünler.",
    "yvesrocher": "Yves Rocher doğal güzellik ürün kampanyaları.",
    "lcwaikiki": "LCW yeni sezon ve indirim kampanyaları.",
    "defacto": "DeFacto giyim kampanyaları ve sezon indirimleri.",
    "koton": "Koton yeni koleksiyon ve özel indirimler.",
    "mavi": "Mavi marka kampanya ve yeni koleksiyon haberleri.",
    "boyner": "Boyner marka koleksiyon ve kampanya bildirimleri.",
    "beymen": "Beymen lüks moda kampanya ve özel teklifler.",
    "trendyolmilla": "Trendyolmilla marka fırsatlar ve indirimler.",
    "hm": "H&M yeni sezon ve kampanya haberleri.",
    "zara": "Zara yeni koleksiyon ve indirim dönemleri.",
    "mango": "Mango moda kampanya ve koleksiyon haberleri.",
    "decathlon": "Decathlon spor ürünleri kampanya ve indirimleri.",
    "flo": "FLO ayakkabı kampanyaları ve yeni sezon haberleri.",
    "ayakkabidunyasi": "Ayakkabı Dünyası kampanya ve indirim bildirimleri.",
    "atasunoptik": "Atasun Optik gözlük kampanyaları ve haberleri.",
    "opmaroptik": "Opmar Optik fırsatları ve kampanyaları.",
    "ebebek": "e-bebek anne-bebek ürünleri kampanya ve haberleri.",
    "pasabahce": "Paşabahçe ev ürünleri kampanya ve koleksiyonlar.",
    "englishhome": "English Home ev tekstili kampanya ve indirimleri.",
    "madamecoco": "Madame Coco ev dekor kampanya ve haberleri.",
    "bellamaison": "Bella Maison ev ürünleri kampanya ve indirimleri.",
    "karacahome": "Karaca Home mutfak ve ev ürünleri kampanyaları.",
    "koctas": "Koçtaş yapı market kampanya ve indirimleri.",
    "ikea": "IKEA yeni ürün ve kampanya haberleri.",
    "trendyol": "Trendyol flash indirim ve kampanya bildirimleri.",
    "hepsiburada": "Hepsiburada büyük indirim günleri ve fırsatlar.",
    "amazon": "Amazon özel teklifler ve flaş indirimler.",
    "n11": "n11 kampanya ve indirimli ürün haberleri.",
}

DEFAULT_STORE_NEWSLETTERS = []
for cat, slugs in ALL_STORES_MAP.items():
    for slug in slugs:
        DEFAULT_STORE_NEWSLETTERS.append({
            "slug": slug,
            "name": _format_store_name(slug),
            "category": cat,
            "publication_note": "",
            "description": _STORE_DESCRIPTIONS.get(slug, "Bu mağazanın kampanya ve indirimlerini takip et."),
        })


@app.get("/api/stores")
async def list_stores(request: Request):
    """
    Tüm aktif mağazaları döndürür.
    Giriş yapan kullanıcı için hangileri takip edildiğini de işaretler.
    """
    stores = [dict(store) for store in DEFAULT_STORE_NEWSLETTERS]
    sb_url = ""
    sb_hdrs: dict[str, str] = {}
    if supabase_enabled():
        try:
            sb_url = supabase_base_url()
            sb_hdrs = supabase_headers()
            r = requests.get(
                f"{sb_url}/rest/v1/store_newsletters",
                headers=sb_hdrs,
                params={"active": "eq.true", "select": "*", "order": "name.asc"},
                timeout=10,
            )
            rows = r.json() if r.ok else []
            if rows:
                db_slugs = {r["slug"]: r for r in rows}
                for i, st in enumerate(stores):
                    if st["slug"] in db_slugs:
                        stores[i] = db_slugs[st["slug"]]
                existing_slugs = {st["slug"] for st in stores}
                for r_data in rows:
                    if r_data["slug"] not in existing_slugs:
                        stores.append(r_data)
        except Exception:
            pass

    # Oturum varsa takip listesini çek
    followed_slugs: set[str] = set()
    try:
        user_id = getattr(request.state, "user_id", None)
        if user_id and sb_url:
            fr = requests.get(
                f"{sb_url}/rest/v1/followed_stores",
                headers=sb_hdrs,
                params={"user_id": f"eq.{user_id}", "select": "store_slug"},
                timeout=10,
            )
            followed_slugs = {row["store_slug"] for row in (fr.json() if fr.ok else [])}
    except Exception:
        pass

    # Takipçi sayılarını çek
    try:
        if not sb_url:
            raise RuntimeError("Supabase devre dışı")
        cr = requests.get(
            f"{sb_url}/rest/v1/followed_stores",
            headers=sb_hdrs,
            params={"select": "store_slug"},
            timeout=10,
        )
        follower_counts: dict[str, int] = {}
        for row in (cr.json() if cr.ok else []):
            s = row["store_slug"]
            follower_counts[s] = follower_counts.get(s, 0) + 1
    except Exception:
        follower_counts = {}

    for s in stores:
        s["followed"]       = s["slug"] in followed_slugs
        s["follower_count"] = follower_counts.get(s["slug"], 0)

    return {"stores": stores}


@app.get("/api/stores/followed")
async def get_followed_stores(request: Request, user=Depends(require_login)):
    """Kullanıcının takip ettiği mağaza slug listesini döner."""
    r = requests.get(
        f"{supabase_base_url()}/rest/v1/followed_stores",
        headers=supabase_headers(),
        params={"user_id": f"eq.{user['user_id']}", "select": "store_slug"},
        timeout=10,
    )
    slugs = [row["store_slug"] for row in (r.json() if r.ok else [])]
    return {"followed": slugs}


def _log_event(user_id: str | None, event_type: str, payload: dict, session_id: str | None = None):
    """Kullanıcı davranış eventi Supabase'e kaydet (hata sessizce yutulur)."""
    # 1. Supabase'e kaydet
    try:
        requests.post(
            f"{supabase_base_url()}/rest/v1/user_events",
            headers=supabase_headers(),
            json={"user_id": user_id, "session_id": session_id, "event_type": event_type, "payload": payload},
            timeout=5,
        )
    except Exception:
        pass

    # 2. Yerel JSONL log dosyasına kaydet
    try:
        from pathlib import Path
        import json
        from datetime import datetime, timezone
        
        data_dir = Path(__file__).resolve().parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        log_file = data_dir / "user_activity_logs.jsonl"
        
        email = payload.get("email") or "Anonymous"
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id or "Anonymous",
            "email": email,
            "event_type": event_type,
            "payload": payload,
            "session_id": session_id
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
        # 3. Google Drive Webhook tanımlıysa arka planda gönder
        webhook_url = os.getenv("GOOGLE_DRIVE_WEBHOOK_URL", "").strip()
        if webhook_url:
            import threading
            
            def _send_webhook():
                try:
                    requests.post(webhook_url, json=log_entry, timeout=5)
                except Exception:
                    pass
            
            threading.Thread(target=_send_webhook, daemon=True).start()
    except Exception:
        pass


def validated_store_slug(slug: str) -> str:
    value = str(slug or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9-]{1,80}", value):
        raise HTTPException(status_code=400, detail="Geçersiz mağaza.")
    return value


@app.post("/api/stores/{slug}/follow")
async def follow_store(slug: str, request: Request, user=Depends(require_login)):
    """Mağazayı takip et (idempotent — zaten takip ediliyorsa sessiz döner)."""
    slug = validated_store_slug(slug)
    user_email = getattr(request.state, "user_email", None)
    uid = user["user_id"]
    try:
        response = requests.post(
            f"{supabase_base_url()}/rest/v1/followed_stores",
            headers={**supabase_headers(), "Prefer": "resolution=merge-duplicates"},
            params={"on_conflict": "user_id,store_slug"},
            json={"user_id": uid, "store_slug": slug, "email": user_email},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Mağaza takibi şu anda kaydedilemedi.") from exc
    _log_event(uid, "store_follow", {"store_slug": slug, "action": "follow", "email": user_email})
    return {"followed": slug}


# ── Bildirimler ──────────────────────────────────────────────────────────────

@app.get("/api/notifications")
async def list_notifications(request: Request, user=Depends(require_login)):
    """Kullanıcının okunmamış + son 30 bildirimini döner."""
    sb_url = supabase_base_url()
    r = requests.get(
        f"{sb_url}/rest/v1/user_notifications",
        headers=supabase_headers(),
        params={
            "user_id": f"eq.{user['user_id']}",
            "select": "id,store_slug,title,body,url,is_read,created_at",
            "order": "created_at.desc",
            "limit": "30",
        },
        timeout=10,
    )
    return {"notifications": r.json() if r.ok else []}


@app.patch("/api/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, request: Request, user=Depends(require_login)):
    """Bildirimi okundu olarak işaretle."""
    sb_url = supabase_base_url()
    requests.patch(
        f"{sb_url}/rest/v1/user_notifications",
        headers=supabase_headers(),
        params={"id": f"eq.{notif_id}", "user_id": f"eq.{user['user_id']}"},
        json={"is_read": True},
        timeout=10,
    )
    return {"ok": True}


@app.post("/api/notifications/read-all")
async def mark_all_notifications_read(request: Request, user=Depends(require_login)):
    """Tüm bildirimleri okundu işaretle."""
    sb_url = supabase_base_url()
    requests.patch(
        f"{sb_url}/rest/v1/user_notifications",
        headers=supabase_headers(),
        params={"user_id": f"eq.{user['user_id']}", "is_read": "eq.false"},
        json={"is_read": True},
        timeout=10,
    )
    return {"ok": True}


@app.delete("/api/stores/{slug}/follow")
async def unfollow_store(slug: str, request: Request, user=Depends(require_login)):
    """Mağaza takibini bırak."""
    slug = validated_store_slug(slug)
    uid = user["user_id"]
    try:
        response = requests.delete(
            f"{supabase_base_url()}/rest/v1/followed_stores",
            headers=supabase_headers(),
            params={"user_id": f"eq.{uid}", "store_slug": f"eq.{slug}"},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Mağaza takibi şu anda güncellenemedi.") from exc
    user_email = getattr(request.state, "user_email", None)
    _log_event(uid, "store_follow", {"store_slug": slug, "action": "unfollow", "email": user_email})
    return {"unfollowed": slug}


@app.get("/api/stores/{slug}/campaigns")
async def store_campaigns(slug: str):
    """Mağazanın aktif kampanyalarını döndürür (herkes görebilir)."""
    from datetime import date
    today = date.today().isoformat()
    r = requests.get(
        f"{supabase_base_url()}/rest/v1/store_campaigns",
        headers=supabase_headers(),
        params={
            "store_slug": f"eq.{slug}",
            "select": "*",
            "or": f"(valid_until.is.null,valid_until.gte.{today})",
            "order": "created_at.desc",
            "limit": "20",
        },
        timeout=10,
    )
    rows = r.json() if r.ok else []
    return {"slug": slug, "campaigns": rows}


@app.post("/api/admin/stores/{slug}/campaign")
async def create_campaign(slug: str, request: Request, admin=Depends(require_admin)):
    """Admin: mağaza için yeni kampanya kaydı ekler."""
    body = await request.json()
    row = {
        "store_slug":  slug,
        "title":       body.get("title", ""),
        "description": body.get("description", ""),
        "catalog_url": body.get("catalog_url", ""),
        "valid_from":  body.get("valid_from"),
        "valid_until": body.get("valid_until"),
        "notified":    False,
    }
    resp = requests.post(
        f"{supabase_base_url()}/rest/v1/store_campaigns",
        headers={**supabase_headers(), "Prefer": "return=representation"},
        json=row, timeout=10,
    )
    data = resp.json() if resp.ok else []
    return data[0] if data else {}


@app.get("/cron/store-newsletters")
async def cron_store_newsletters(request: Request):
    """
    Vercel Cron: Her gün 09:00'da çalışır.

    Mantık:
      1. Bugünün haftanın gününe göre publication_day eşleşen mağazaları bul.
      2. O mağazaların notified=False kampanyaları varsa bildirim gönder.
      3. Takipçi sayısını hesapla, notify_store_update() çağır.
      4. Kampanyayı notified=True yap.
    """
    require_cron_request(request)
    from datetime import date
    from app.notifier import notify_store_update

    today_weekday = date.today().weekday()  # 0=Pzt … 6=Paz
    today_str     = date.today().isoformat()

    sb_url = supabase_base_url()
    sb_hdrs = supabase_headers()

    ar = requests.get(
        f"{sb_url}/rest/v1/store_newsletters",
        headers=sb_hdrs,
        params={"active": "eq.true", "select": "slug,name"},
        timeout=10,
    )
    active_stores = ar.json() if ar.ok else []

    triggered = []
    for store in active_stores:
        slug = store["slug"]

        cr = requests.get(
            f"{sb_url}/rest/v1/store_campaigns",
            headers=sb_hdrs,
            params={
                "store_slug": f"eq.{slug}", "notified": "eq.false",
                "select": "*", "or": f"(valid_from.is.null,valid_from.lte.{today_str})",
            },
            timeout=10,
        )
        campaigns = cr.json() if cr.ok else []
        if not campaigns:
            continue

        fr = requests.get(
            f"{sb_url}/rest/v1/followed_stores",
            headers=sb_hdrs,
            params={"store_slug": f"eq.{slug}", "select": "user_id,email"},
            timeout=10,
        )
        followers = fr.json() if fr.ok else []
        follower_count = len(followers)

        latest = campaigns[0]
        campaign_title = latest.get("title", "")
        catalog_url    = latest.get("catalog_url", "")
        valid_until    = latest.get("valid_until", "")

        # 1) Admin/sistem bildirimi (Telegram/SMTP) — mevcut kanal
        result = await asyncio.to_thread(
            notify_store_update,
            store["name"],
            campaign_title=campaign_title,
            catalog_url=catalog_url,
            valid_until=valid_until,
            follower_count=follower_count,
        )

        notif_title = f"{store['name']} — Yeni Kampanya!"
        notif_body  = campaign_title or f"{store['name']}'de yeni bir kampanya başladı."

        # 2) Her takipçiye uygulama-içi bildirim + email
        for follower in followers:
            uid   = follower.get("user_id")
            email = follower.get("email") or ""

            # Uygulama-içi bildirim kaydı
            if uid:
                requests.post(
                    f"{sb_url}/rest/v1/user_notifications",
                    headers=sb_hdrs,
                    json={
                        "user_id":    uid,
                        "store_slug": slug,
                        "title":      notif_title,
                        "body":       notif_body,
                        "url":        catalog_url or "/",
                        "is_read":    False,
                    },
                    timeout=10,
                )

            # Takipçi emaili varsa bireysel mail gönder
            if email:
                try:
                    import os, smtplib
                    from email.mime.multipart import MIMEMultipart
                    from email.mime.text import MIMEText
                    smtp_host = os.getenv("SMTP_HOST", "").strip()
                    smtp_port = int(os.getenv("SMTP_PORT", "587"))
                    smtp_user = os.getenv("SMTP_USER", "").strip()
                    smtp_pass = os.getenv("SMTP_PASS", "").strip()
                    from_addr = os.getenv("SMTP_FROM", smtp_user).strip() or smtp_user
                    if smtp_host and smtp_user:
                        until_txt = f" (Son geçerlilik: {valid_until})" if valid_until else ""
                        catalog_btn = f'<a href="{catalog_url}" style="display:inline-block;margin-top:16px;padding:10px 20px;background:#287a50;color:#fff;border-radius:8px;text-decoration:none;font-weight:700;">Kampanyayı İncele →</a>' if catalog_url else ""
                        html = f"""<div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:24px;">
  <h2 style="color:#287a50;margin:0 0 8px;">🏪 {store['name']} — Yeni Kampanya!</h2>
  <p style="color:#444;margin:0 0 4px;">{notif_body}{until_txt}</p>
  {catalog_btn}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee;">
  <p style="font-size:11px;color:#888;">Bu bildirim, <a href="https://www.almadan.app">Almadan</a>'dan {store['name']} mağazasını takip ettiğin için gönderildi.</p>
</div>"""
                        msg = MIMEMultipart("alternative")
                        msg["Subject"] = f"[Almadan] {store['name']}'de yeni kampanya!"
                        msg["From"]    = f"Almadan <{from_addr}>"
                        msg["To"]      = email
                        msg.attach(MIMEText(notif_body, "plain", "utf-8"))
                        msg.attach(MIMEText(html, "html", "utf-8"))
                        if smtp_port == 465:
                            with smtplib.SMTP_SSL(smtp_host, 465, timeout=8) as srv:
                                srv.login(smtp_user, smtp_pass)
                                srv.sendmail(from_addr, email, msg.as_string())
                        else:
                            with smtplib.SMTP(smtp_host, smtp_port, timeout=8) as srv:
                                srv.starttls()
                                srv.login(smtp_user, smtp_pass)
                                srv.sendmail(from_addr, email, msg.as_string())
                except Exception as mail_err:
                    logger.warning("Follower email gönderilemedi %s: %s", email, mail_err)

        if follower_count > 0 or any(result.values()):
            ids = [c["id"] for c in campaigns]
            for cid in ids:
                requests.patch(
                    f"{sb_url}/rest/v1/store_campaigns",
                    headers=sb_hdrs,
                    params={"id": f"eq.{cid}"},
                    json={"notified": True},
                    timeout=10,
                )
            triggered.append({"slug": slug, "campaigns_notified": len(ids), "followers": follower_count})

    return {"date": today_str, "triggered": triggered, "total_stores_checked": len(active_stores)}


@app.get("/cron/sync-sheets")
async def cron_sync_sheets(request: Request):
    """Vercel Cron: Her gün 02:00'da çalışır — Google Sheets'i günceller."""
    require_cron_request(request)
    if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or not os.getenv("GOOGLE_SHEET_ID"):
        return {"skipped": True, "reason": "Google Sheets env vars not configured"}
    try:
        from app.sheets_sync import sync_to_sheets
        result = sync_to_sheets(load_db())
        return {"ok": True, **result}
    except Exception as exc:
        import traceback
        logger.error("cron/sync-sheets hatası: %s", traceback.format_exc())
        return {"ok": False, "error": str(exc)}
