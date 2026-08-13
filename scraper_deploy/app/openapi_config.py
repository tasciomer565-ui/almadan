"""
OpenAPI / Swagger Konfigürasyonu — Sprint 9

FastAPI otomatik olarak /docs (Swagger UI) ve /redoc (ReDoc) üretir.
Bu modül:
  1. Zenginleştirilmiş metadata (tag grupları, lisans, iletişim)
  2. Güvenlik şeması (Bearer JWT)
  3. Ortama göre sunucu listesi
  4. Tag açıklamaları (Türkçe)
"""
from __future__ import annotations

import os

APP_VERSION = "9.0.0"
APP_TITLE   = "Almadan API"
APP_DESCRIPTION = """
## Almadan — Akıllı Alışveriş Asistanı

Türkiye'nin lider fiyat karşılaştırma ve alışveriş asistanı API'si.
1.000.000+ ürün, gerçek zamanlı fiyat takibi, AI destekli arama.

### Kimlik Doğrulama

Tüm korumalı endpoint'ler `Authorization: Bearer <JWT>` header'ı gerektirir.
JWT token'ı `/api/auth/login` endpoint'inden alınır.

### Hız Sınırı

| Kullanıcı Tipi | İstek / dakika |
|---|---|
| Anonim | 30 |
| Kayıtlı | 120 |
| Premium | 600 |
| Partner API | Sözleşmeye göre |

### Bölge

`fra1` (Frankfurt) — Vercel Edge Network üzerinde.
"""

CONTACT = {
    "name":  "Almadan Destek",
    "email": "api@almadan.app",
    "url":   "https://almadan.app",
}

LICENSE = {
    "name": "Proprietary",
    "url":  "https://almadan.app/terms",
}

SERVERS = [
    {"url": "https://almadan.vercel.app", "description": "Production"},
    {"url": "http://localhost:8000",       "description": "Lokal Geliştirme"},
]

TAGS_METADATA = [
    {
        "name":        "Kimlik Doğrulama",
        "description": "Kayıt, giriş, şifre sıfırlama, OAuth (Google/Apple)",
    },
    {
        "name":        "Ürün Takibi",
        "description": "Watchlist yönetimi, fiyat geçmişi, anlık oran hesaplama",
    },
    {
        "name":        "Alışveriş Sepeti",
        "description": "Mağaza bazlı sepet optimizasyonu ve birim fiyat karşılaştırma",
    },
    {
        "name":        "Arama",
        "description": "Metin ve semantik (vektör) ürün araması",
    },
    {
        "name":        "Tahmin",
        "description": "Fiyat tahmini (WLS regresyon + Prophet), trend analizi",
    },
    {
        "name":        "Yapay Zeka",
        "description": "Görsel analiz (buzdolabı → liste), A/B test, guardrail sistemi",
    },
    {
        "name":        "Analitik & Dashboard",
        "description": "Tasarruf paneli, kullanıcı analitikleri, puan sistemi",
    },
    {
        "name":        "Ekosistem",
        "description": "Kupon takası, grup alışverişi, eko-skor, partner API",
    },
    {
        "name":        "Bildirimler",
        "description": "Web Push bildirimleri (VAPID)",
    },
    {
        "name":        "KVKK / GDPR",
        "description": "Kişisel veri silme (unutulma hakkı), veri dışa aktarma",
    },
    {
        "name":        "Admin",
        "description": "Sistem yönetimi, scraper sağlığı, A/B test yönetimi",
    },
    {
        "name":        "Kırılmazlık",
        "description": "Circuit breaker, chaos engineering, önbellek yönetimi",
    },
    {
        "name":        "Cron",
        "description": "Vercel Cron job endpoint'leri (x-cron-secret gerektirir)",
    },
]

SECURITY_SCHEMES = {
    "BearerAuth": {
        "type":         "http",
        "scheme":       "bearer",
        "bearerFormat": "JWT",
        "description":  "/api/auth/login ile alınan JWT token",
    },
    "PartnerApiKey": {
        "type":        "apiKey",
        "in":          "header",
        "name":        "X-API-Key",
        "description": "Partner entegrasyon anahtarı (pk_live_... formatı)",
    },
}


def build_openapi_overrides() -> dict:
    """FastAPI'ye enjekte edilecek ek OpenAPI alanları."""
    return {
        "info": {
            "x-logo": {
                "url":             "https://almadan.app/logo.png",
                "altText":         "Almadan Logo",
                "backgroundColor": "#FFFFFF",
            }
        },
        "x-tagGroups": [
            {"name": "Kullanıcı",    "tags": ["Kimlik Doğrulama", "Ürün Takibi", "Alışveriş Sepeti", "Bildirimler"]},
            {"name": "Zeka",         "tags": ["Arama", "Tahmin", "Yapay Zeka"]},
            {"name": "Platform",     "tags": ["Ekosistem", "Analitik & Dashboard"]},
            {"name": "Uyumluluk",    "tags": ["KVKK / GDPR"]},
            {"name": "Operasyonel",  "tags": ["Admin", "Kırılmazlık", "Cron"]},
        ],
    }


def custom_openapi(app) -> dict:
    """
    FastAPI uygulamasına özel OpenAPI şeması enjekte eder.
    app.openapi = lambda: custom_openapi(app) şeklinde kullanılır.
    """
    from fastapi.openapi.utils import get_openapi

    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=APP_TITLE,
        version=APP_VERSION,
        description=APP_DESCRIPTION,
        contact=CONTACT,
        license_info=LICENSE,
        tags=TAGS_METADATA,
        routes=app.routes,
        servers=SERVERS,
    )

    # Güvenlik şemaları
    schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
        SECURITY_SCHEMES
    )

    # Global güvenlik (tüm endpoint'ler opsiyonel bearer kabul eder)
    schema["security"] = [{"BearerAuth": []}]

    # ReDoc / Redocly için extension'lar
    overrides = build_openapi_overrides()
    schema["info"].update(overrides.get("info", {}))
    schema["x-tagGroups"] = overrides.get("x-tagGroups", [])

    app.openapi_schema = schema
    return schema
