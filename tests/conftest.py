"""Test ortami ayarlari.

Gizli anahtarlar koda gomulu degil, ortam degiskeninden okunur. Testler app
modulleri import edilmeden ONCE yalnizca teste ozel sahte degerler tanimlar
(gercek anahtar asla repoya yazilmaz).
"""
import os

os.environ.setdefault("B2B_API_KEY", "alm_b2b_test_only_key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-only-jwt-secret-not-for-production")
