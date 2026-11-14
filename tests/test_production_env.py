"""Uretim ortami algilama: Render'da HSTS, Secure cookie ve kapali API dokumani."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_PROBE = (
    "import app.main as m, app.security as s;"
    "print(s.IS_PRODUCTION, m.COOKIE_SECURE, m.app.docs_url, m.app.openapi_url,"
    " bool(s.SECURITY_HEADERS.get('Strict-Transport-Security')))"
)


def _probe(extra_env: dict[str, str]) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"RENDER", "VERCEL", "VERCEL_ENV", "ENABLE_API_DOCS"}}
    env.update(extra_env)
    env.setdefault("B2B_API_KEY", "alm_b2b_test_only_key")
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120, check=True)
    return out.stdout.strip().splitlines()[-1].split()


def test_render_is_production():
    assert _probe({"RENDER": "true"}) == ["True", "True", "None", "None", "True"]


def test_local_is_not_production():
    assert _probe({}) == ["False", "False", "/docs", "/openapi.json", "False"]


def test_docs_can_be_reenabled_in_production():
    is_prod, _, docs, openapi, _ = _probe({"RENDER": "true", "ENABLE_API_DOCS": "1"})
    assert is_prod == "True" and docs == "/docs" and openapi == "/openapi.json"


def test_cron_secret_error_does_not_leak_length(monkeypatch):
    import app.main as m

    monkeypatch.setenv("CRON_SECRET", "a" * 32)
    ok, reason = m._verify_cron_secret("short")
    assert not ok and "uzunlu" not in reason.lower()


def test_old_hardcoded_jwt_key_is_rejected():
    """Eski, depoda gomulu duran varsayilan anahtarla imzalanmis token kabul edilmemeli."""
    import time
    import uuid

    import jwt
    from fastapi.testclient import TestClient

    from app.main import app

    now = int(time.time())
    leaked = "almadan_supabase_gotrue_jwt_" + "secret_2026_default_key"
    token = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "iat": now, "exp": now + 60},
                       leaked, algorithm="HS256")
    r = TestClient(app).get("/api/v1/wardrobe/laundry-basket", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_no_hardcoded_secrets_in_app_source():
    import re

    pattern = re.compile(r"alm_b2b_[A-Za-z0-9]{4,}_giysem|gotrue_jwt_secret_2026")
    offenders = [str(p) for p in (ROOT / "app").rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
