from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from app.storage import supabase_base_url


SUPABASE_PUBLISHABLE_KEY = "".join(
    os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip().strip("\"'").split()
)


class AuthError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def auth_enabled() -> bool:
    return bool(SUPABASE_PUBLISHABLE_KEY)


def auth_headers(access_token: str | None = None) -> dict[str, str]:
    if not auth_enabled():
        raise AuthError(
            "SUPABASE_PUBLISHABLE_KEY ayarlanmamış.",
            status_code=503,
        )

    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Almadan-Backend/1.0",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def auth_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            f"{supabase_base_url()}/auth/v1/{path.lstrip('/')}",
            headers=auth_headers(access_token),
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Kimlik servisine ulaşılamadı: {exc}", 503) from exc

    if not response.ok:
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = (
            body.get("msg")
            or body.get("message")
            or body.get("error_description")
            or "Kimlik doğrulama işlemi tamamlanamadı."
        )
        raise AuthError(message, response.status_code)

    if not response.content:
        return {}
    return response.json()


def sign_up(
    email: str,
    password: str,
    gender: str | None = None,
    phone: str | None = None,
    notification_pref: str | None = None,
) -> dict[str, Any]:
    payload = {"email": email, "password": password}
    metadata = {}
    if gender:
        metadata["gender"] = gender
    if phone:
        metadata["phone"] = phone
    if notification_pref:
        metadata["notification_pref"] = notification_pref

    if metadata:
        payload["options"] = {"data": metadata}

    return auth_request(
        "POST",
        "signup",
        payload=payload,
    )


def sign_in(email: str, password: str) -> dict[str, Any]:
    return auth_request(
        "POST",
        "token?grant_type=password",
        payload={"email": email, "password": password},
    )


def refresh_session(refresh_token: str) -> dict[str, Any]:
    return auth_request(
        "POST",
        "token?grant_type=refresh_token",
        payload={"refresh_token": refresh_token},
    )


def get_user(access_token: str) -> dict[str, Any]:
    return auth_request("GET", "user", access_token=access_token)


def request_password_reset(email: str, redirect_to: str) -> dict[str, Any]:
    return auth_request(
        "POST",
        f"recover?redirect_to={quote(redirect_to, safe=':/')}",
        payload={"email": email},
    )


def update_password(access_token: str, password: str) -> dict[str, Any]:
    return auth_request(
        "PUT",
        "user",
        payload={"password": password},
        access_token=access_token,
    )


def update_user_metadata(access_token: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return auth_request(
        "PUT",
        "user",
        payload={"data": metadata},
        access_token=access_token,
    )
