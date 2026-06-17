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
from app.security import (
    apply_security_headers,
    auth_wall_middleware,
    csrf_middleware,
    generate_csrf_token,
    log_activity,
    require_admin,
    require_premium,
    sanitize,
    get_oauth_url,
    OAUTH_PROVIDERS,
)


REFRESH_INTERVAL_SECONDS = 6 * 60 * 60
CRON_SECRET = os.getenv("CRON_SECRET", "")
APP_URL = os.getenv("ALMADAN_APP_URL", "https://almadan.vercel.app").rstrip("/")
PASSWORD_RESET_LIMIT = 2
PASSWORD_RESET_WINDOW = timedelta(minutes=15)


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


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    apply_security_headers(response)
    # CSRF token'ı cookie olarak sun (JS okumaz, header'dan gönderir)
    if not request.cookies.get("csrf_token"):
        device_id = request.cookies.get("almadan_device_id", "anonymous")
        csrf = generate_csrf_token(device_id)
        response.set_cookie(
            "csrf_token", csrf,
            max_age=7200, httponly=False, secure=True, samesite="strict"
        )
    return response


@app.middleware("http")
async def _auth_wall(request: Request, call_next):
    return await auth_wall_middleware(request, call_next)


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


class PoseRequest(BaseModel):
    image_base64: str


@app.post("/api/detect-pose")
def detect_pose(payload: PoseRequest) -> dict:
    import base64
    import io
    import math
    import numpy as np
    from PIL import Image

    try:
        base64_data = payload.image_base64
        if "," in base64_data:
            _, base64_data = base64_data.split(",", 1)

        img_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_rgb = np.array(img)
        h, w, _ = img_rgb.shape
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Görsel çözümlenemedi: {str(exc)}")

    # Try running MediaPipe Pose
    try:
        import mediapipe as mp
        mp_pose = mp.solutions.pose
        with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose:
            results = pose.process(img_rgb)
            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
                right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]

                # Check visibility threshold (0.4 is reasonable)
                if left_shoulder.visibility > 0.4 and right_shoulder.visibility > 0.4:
                    dx = left_shoulder.x - right_shoulder.x
                    dy = left_shoulder.y - right_shoulder.y
                    tilt_angle = math.atan2(dy, dx)

                    # Midpoint neck anchor
                    neck_x = (left_shoulder.x + right_shoulder.x) / 2
                    neck_y = (left_shoulder.y + right_shoulder.y) / 2

                    # shoulder_left is the left side of the image (smaller X) which corresponds to RIGHT_SHOULDER
                    # shoulder_right is the right side of the image (greater X) which corresponds to LEFT_SHOULDER
                    return {
                        "success": True,
                        "shoulder_left": [right_shoulder.x, right_shoulder.y],
                        "shoulder_right": [left_shoulder.x, left_shoulder.y],
                        "tilt_angle": tilt_angle,
                        "body_width": dx,
                        "neck_anchor": [neck_x, neck_y],
                        "source": "mediapipe"
                    }
    except Exception as mp_err:
        print(f"MediaPipe failed, falling back to NumPy: {mp_err}")

    # Fallback NumPy Contrast/Edge scan algorithm
    try:
        samples = [
            img_rgb[min(5, h-1), min(5, w-1)],
            img_rgb[min(5, h-1), w // 2],
            img_rgb[min(5, h-1), max(0, w-6)],
            img_rgb[h // 2, min(5, w-1)],
            img_rgb[h // 2, max(0, w-6)],
            img_rgb[max(0, h-6), min(5, w-1)],
            img_rgb[max(0, h-6), max(0, w-6)]
        ]
        bg_color = np.mean(samples, axis=0)

        def is_different(pixel):
            diff = np.sqrt(np.sum((pixel - bg_color) ** 2))
            return diff > 35.0

        lefts = []
        rights = []
        y_step = max(2, h // 75)
        for y in range(int(h * 0.33), int(h * 0.80), y_step):
            first_x = -1
            last_x = -1
            for x in range(int(w * 0.03), int(w * 0.97)):
                if is_different(img_rgb[y, x]):
                    if first_x == -1:
                        first_x = x
                    last_x = x
            if first_x != -1 and last_x != -1 and (last_x - first_x) > (w * 0.13):
                lefts.append((first_x, y))
                rights.append((last_x, y))

        if len(lefts) >= 5:
            widths = [r[0] - l[0] for l, r in zip(lefts, rights)]
            centers = [(l[0] + r[0]) / 2 for l, r in zip(lefts, rights)]

            avg_width = sum(widths) / len(widths)
            avg_center = sum(centers) / len(centers)

            if avg_width < w * 0.23: avg_width = w * 0.43
            if avg_width > w * 0.8: avg_width = w * 0.53
            if avg_center < w * 0.2 or avg_center > w * 0.8: avg_center = w * 0.5

            min_x, min_x_y = w, h // 2
            max_x, max_x_y = 0, h // 2

            for l, r in zip(lefts, rights):
                lx, ly = l
                rx, ry = r
                if int(h * 0.4) <= ly <= int(h * 0.6):
                    if lx < min_x:
                        min_x = lx
                        min_x_y = ly
                    if rx > max_x:
                        max_x = rx
                        max_x_y = ry

            tilt_angle = 0.0
            if max_x > min_x and abs(max_x_y - min_x_y) < h * 0.13:
                tilt_angle = math.atan2(max_x_y - min_x_y, max_x - min_x)
                if abs(tilt_angle) > 0.35:
                    tilt_angle = 0.0

            detected_top_y = int(h * 0.37)
            for y in range(int(h * 0.16), int(h * 0.50), 2):
                diff_count = 0
                for x in range(int(w * 0.13), int(w * 0.87)):
                    if is_different(img_rgb[y, x]):
                        diff_count += 1
                if diff_count > 15:
                    detected_top_y = y + int(h * 0.13)
                    break

            detected_top_y = max(int(h * 0.3), min(detected_top_y, int(h * 0.43)))

            return {
                "success": True,
                "shoulder_left": [min_x / w, min_x_y / h],
                "shoulder_right": [max_x / w, max_x_y / h],
                "tilt_angle": tilt_angle,
                "body_width": avg_width / w,
                "neck_anchor": [avg_center / w, detected_top_y / h],
                "source": "contrast_fallback"
            }
    except Exception as fallback_err:
        print(f"NumPy fallback failed: {fallback_err}")

    return {
        "success": False,
        "shoulder_left": [0.25, 0.4],
        "shoulder_right": [0.75, 0.4],
        "tilt_angle": 0.0,
        "body_width": 0.5,
        "neck_anchor": [0.5, 0.37],
        "source": "default_fallback",
        "error_message": "Both MediaPipe and NumPy scan failed, using default values."
    }


class SkinRequest(BaseModel):
    image_base64: str


class CosmeticColorRequest(BaseModel):
    skin_type: str
    undertone: str
    query: str


@app.post("/api/analyze-skin")
def analyze_skin(payload: SkinRequest) -> dict:
    import base64
    import io
    import numpy as np
    from PIL import Image

    try:
        base64_data = payload.image_base64
        if "," in base64_data:
            _, base64_data = base64_data.split(",", 1)

        img_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_rgb = np.array(img)
        h, w, _ = img_rgb.shape
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Görsel çözümlenemedi: {str(exc)}")

    skin_type = "medium"
    skin_color_hex = "#f5deb3"
    undertone = "Warm (Sıcak)"
    detected_rgb = [245, 222, 179]
    source = "numpy_fallback"

    try:
        import mediapipe as mp
        mp_face_mesh = mp.solutions.face_mesh
        with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, min_detection_confidence=0.5) as face_mesh:
            results = face_mesh.process(img_rgb)
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                xs = [lm.x for lm in landmarks]
                ys = [lm.y for lm in landmarks]
                min_x, max_x = int(min(xs) * w), int(max(xs) * w)
                min_y, max_y = int(min(ys) * h), int(max(ys) * h)

                min_x = max(0, min_x)
                max_x = min(w - 1, max_x)
                min_y = max(0, min_y)
                max_y = min(h - 1, max_y)

                face_w = max_x - min_x
                face_h = max_y - min_y

                sample_pts = [
                    (min_x + face_w // 2, min_y + face_h // 2),
                    (min_x + int(face_w * 0.3), min_y + int(face_h * 0.6)),
                    (min_x + int(face_w * 0.7), min_y + int(face_h * 0.6)),
                    (min_x + face_w // 2, min_y + int(face_h * 0.3))
                ]

                pixels = []
                for cx, cy in sample_pts:
                    if 0 <= cx < w and 0 <= cy < h:
                        pixels.append(img_rgb[cy, cx])

                if pixels:
                    detected_rgb = np.mean(pixels, axis=0).astype(int).tolist()
                    source = "mediapipe_face_mesh"
    except Exception as mp_err:
        print(f"MediaPipe Face Mesh failed, using NumPy fallback: {mp_err}")

    if source == "numpy_fallback":
        center_x_start = int(w * 0.35)
        center_x_end = int(w * 0.65)
        center_y_start = int(h * 0.35)
        center_y_end = int(h * 0.65)
        center_region = img_rgb[center_y_start:center_y_end, center_x_start:center_x_end]
        detected_rgb = np.mean(center_region, axis=(0, 1)).astype(int).tolist()

    r, g, b = detected_rgb
    luminance = 0.299 * r + 0.587 * g + 0.114 * b

    if luminance > 195:
        skin_type = "light"
        skin_color_hex = f"#{r:02x}{g:02x}{b:02x}"
        undertone = "Cool (Soğuk)"
    elif luminance > 115:
        skin_type = "medium"
        skin_color_hex = f"#{r:02x}{g:02x}{b:02x}"
        undertone = "Warm (Sıcak)"
    else:
        skin_type = "dark"
        skin_color_hex = f"#{r:02x}{g:02x}{b:02x}"
        undertone = "Neutral (Nötr)"

    return {
        "success": True,
        "skin_type": skin_type,
        "skin_color_hex": skin_color_hex,
        "undertone": undertone,
        "detected_rgb": detected_rgb,
        "source": source
    }


@app.post("/api/analyze-cosmetic-color")
def analyze_cosmetic_color(payload: CosmeticColorRequest) -> dict:
    skin_type = payload.skin_type
    undertone = payload.undertone
    q = payload.query.strip().lower()

    if skin_type == "light":
        if any(w in q for w in ["pembe", "mor", "eflatun", "gül", "rose", "berry", "plum", "mürdüm"]):
            comment = (
                "✨ **[HOLOGRAFİK ANALİZ RAPORU]**\n\n"
                "Cilt alt tonun derinlemesine tarandı ve veriler süzülerek havada belirdi. **Soğuk/Açık alt tonun**, "
                "yerçekimsiz laboratuvarımızın gravitasyonel alanı ile %98 oranında mükemmel bir kuantum rezonansı yakaladı!\n\n"
                "**Fiziksel Öneri:** Yazdığın bu ton, foton saçılım fiziğine göre cildindeki mavi ışık dalga boyunu yansıtarak "
                "yüzeysel yansımayı %32 oranında artıracaktır. Havada asılı duran dijital vitrinimizdeki pembe pigment yoğunluğu yüksek "
                "bu kozmetik ürün, sana yerçekimsiz bir parlaklık kazandıracak.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Cilt tipinize en uyumlu pembe/gül kozmetik alternatifleri için fiyat karşılaştır."
            )
        elif any(w in q for w in ["kiremit", "bronz", "turuncu", "şeftali", "seftali", "kahve", "nude", "terracotta"]):
            comment = (
                "⚠️ **[GRAVİTASYONEL ALAN UYARISI]**\n\n"
                "Analiz panellerimizden gelen veriler, **soğuk/açık teninle** sıcak kiremit/turuncu tonlarının kuantum frekansının çakıştığını gösteriyor! "
                "Bu durum, cildindeki foton yansımasını soğurarak yorgun veya solgun bir görünüm oluşturabilir.\n\n"
                "**Fiziksel Öneri:** Sıcak tonlar yerine, ışık yansımasını maksimize edecek soğuk pembe veya mürdüm tonlarına yönelmenizi öneririz. "
                "Bu sayede yerçekimsiz alandaki aura canlılık katsayısı optimum düzeyde kalacaktır.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Cilt tipinize özel daha uyumlu alternatif tonları listele."
            )
        else:
            comment = (
                "ℹ️ **[HOLOGRAFİK BİLGİ SEVİYESİ]**\n\n"
                "Yüklediğin veriler doğrultusunda, belirttiğin ürünün açık tenin üzerindeki fotonik spektrum etkisi 'Nötr' olarak ölçülmüştür. "
                "Bu ton gravitasyonel alanımızı bozmaz fakat yerçekimsiz ortamda üstün bir parlaklık da sağlamaz.\n\n"
                "**Fiziksel Öneri:** Daha yüksek kontrast ve kuantum yansıması elde etmek için pembe/mor yansımalı soğuk tonları tercih edebilirsiniz.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Cilt tipinize özel diğer alternatifleri karşılaştırın."
            )
    elif skin_type == "medium":
        if any(w in q for w in ["şeftali", "seftali", "kiremit", "bronz", "turuncu", "coral", "mercan", "nude", "kahve", "terracotta"]):
            comment = (
                "✨ **[HOLOGRAFİK ANALİZ RAPORU]**\n\n"
                "Cilt analiz verilerin süzülerek havada belirdi. **Sıcak alt tonlu buğday tenin**, "
                "yerçekimsiz stüdyomuzdaki altın dalga boyundaki foton yansımalarıyle mükemmel bir uyum yakaladı.\n\n"
                "**Fiziksel Öneri:** Şeftali, mercan ve bronz tonları, buğday teninin yaydığı sıcak spektrumu emerek doğal bir ışıltı katacak "
                "ve yüzeydeki ışık kırılmasını %25 optimize edecektir. Havada asılı duran dijital vitrinimizdeki bu ürün, yüzüne kusursuz bir teknolojik aura verecektir.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Buğday ten için en popüler şeftali/mercan alternatifleri karşılaştır."
            )
        elif any(w in q for w in ["eflatun", "pembe", "mor", "berry", "plum", "soğuk pembe"]):
            comment = (
                "⚠️ **[GRAVİTASYONEL ALAN UYARISI]**\n\n"
                "Cilt analiz panellerimiz, soğuk eflatun/pembe tonlarının **sıcak buğday teninle** fotonik bir uyumsuzluk yarattığını tespit etti. "
                "Bu tonlar ten renginizle çakışarak cildi solgun gösterebilir.\n\n"
                "**Fiziksel Öneri:** Sıcak şeftali, terracotta ve mercan tonlarındaki allık ve rujları tercih etmeniz yerçekimsiz alandaki dengenizi koruyacaktır.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Buğday teninizle en uyumlu sıcak tonlu makyaj alternatiflerine gözatın."
            )
        else:
            comment = (
                "ℹ️ **[HOLOGRAFİK BİLGİ SEVİYESİ]**\n\n"
                "Buğday teniniz üzerinde bu rengin analiz değeri 'Nötr' seviyededir. Işık yansımasını ne artırır ne azaltır.\n\n"
                "**Fiziksel Öneri:** Şeftali ve mercan yansımalı tonlar ile altın ışıltılı pigmentler tercih edilirse kuantum auranız daha dengeli duracaktır.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Cildinize özel sıcak yansımalı diğer ürünleri inceleyin."
            )
    else:
        if any(w in q for w in ["altın", "altin", "gold", "bronz", "mürdüm", "plum", "berry", "koyu kırmızı", "bordo", "kahve", "bakır", "bakir"]):
            comment = (
                "✨ **[HOLOGRAFİK ANALİZ RAPORU]**\n\n"
                "Verilerin süzülerek havada belirdi. Derin **esmer tenin ve nötr/sıcak alt tonun**, yerçekimsiz stüdyomuzdaki yüksek dalga boylu ışık huzmeleriyle "
                "tam uyum içinde rezonansa girdi.\n\n"
                "**Fiziksel Öneri:** Bronz, altın ışıltıları, mürdüm ve derin bordo tonları, esmer teninizdeki ışık soğurmasını azaltarak yüzey yansımasını %35 oranında artıracaktır. "
                "Havada asılı duran vitrinimizdeki bu pigmentler, yüzünüze fütüristik bir derinlik ve parlaklık kazandıracak.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Esmer ten için en uyumlu altın/bordo makyaj ürünleri karşılaştır."
            )
        elif any(w in q for w in ["toz pembe", "açık pembe", "pastel", "beyaz", "eflatun"]):
            comment = (
                "⚠️ **[GRAVİTASYONEL ALAN UYARISI]**\n\n"
                "Analizörlerimiz, çok açık pastel ve soğuk toz pembe tonlarının esmer teniniz üzerinde 'tebeşirimsi' ve mat bir yansıma kırılması yarattığını gösteriyor. "
                "Bu durum yerçekimsiz estetiğimizi olumsuz etkileyebilir.\n\n"
                "**Fiziksel Öneri:** Açık pastel tonlar yerine, derin mürdüm, bordo ve altın ışıltılı bakır tonlarına yönelmeniz daha kusursuz bir teknolojik görünüm sağlayacaktır.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Esmer teninize özel derin pigmentli alternatifleri listele."
            )
        else:
            comment = (
                "ℹ️ **[HOLOGRAFİK BİLGİ SEVİYESİ]**\n\n"
                "Esmer teniniz için bu ürünün yansıma etkisi 'Nötr' seviyesindedir. \n\n"
                "**Fiziksel Öneri:** Derin mürdüm veya altın yansımalı tonları tercih etmeniz esmer teninizin asilliğini fütüristik aura ile birleştirecektir.\n\n"
                "🔗 *[Holografik Satın Alma Köprüsü]*: Cilt tonunuz için özel önerilen diğer ürünleri karşılaştırın."
            )

    return {"success": True, "comment": comment}


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
        
    from app.comparator import apply_gender_to_query, search_products_by_name, generate_search_suggestion
    gendered_query = (
        apply_gender_to_query(query, user_gender)
        if category == "fashion"
        else query
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


# ── VTON Endpoints ────────────────────────────────────────────────────────

@app.post("/api/vton/submit")
def vton_submit(payload: dict, request: Request) -> dict:
    """VTON işi kuyruğa ekle. portrait_url ve garment_url gerekli."""
    from app.ai_processor import create_job, process_vton_job
    portrait_url = payload.get("portrait_url", "")
    garment_url = payload.get("garment_url", "")
    if not portrait_url or not garment_url:
        raise HTTPException(status_code=400, detail="portrait_url ve garment_url zorunlu.")
    user_id = None
    if hasattr(request.state, "user") and request.state.user:
        user_id = request.state.user.get("id")
    job = create_job(portrait_url, garment_url, user_id)
    job_id = job.get("job_id", "")
    # Vercel'de background task yok; sync işle (timeout riski var, kabul edilebilir)
    # Üretim için Vercel Cron veya ayrı bir worker servisi önerilir.
    import threading
    threading.Thread(target=process_vton_job, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/vton/{job_id}")
def vton_status(job_id: str) -> dict:
    """VTON iş durumunu sorgula."""
    from app.ai_processor import get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "result_url": job.get("result_url"),
        "error": job.get("error_msg"),
    }


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

    # ── Kaynak 2: UPCitemdb (ücretsiz tier, 100 sorgu/gün) ────────────────
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

    # ── Kaynak 3: N11 ürün arama (barkod numarasını query olarak gönder) ──
    try:
        from app.comparator import search_n11_direct
        n11_results, _ = search_n11_direct(barcode)
        if n11_results:
            first = n11_results[0]
            return {"title": first["title"], "brand": "", "quantity": "",
                    "image_url": first.get("image_url", ""),
                    "search_query": first["title"],
                    "source": "n11_search"}
    except Exception as exc:
        log.warning("N11 barcode fallback exception for %s: %s", barcode, exc)

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
    return {
        "found": True,
        "title": match["title"],
        "brand": match.get("brand", ""),
        "image_url": match.get("image_url", ""),
        "search_query": match["search_query"],
        "suggested_category": suggested_category,
        "source": match.get("source", "local_seed"),
        "cached": False,
        "results": results,
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
        items = [
            {
                **item.model_dump(exclude={"category"}),
                "category": detected_category,
            }
            for item in payload.items
        ]
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
