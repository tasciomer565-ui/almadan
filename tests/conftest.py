"""Test ortamı ayarları.

Güvenlik düzeltmesiyle B2B anahtarı artık koda gömülü değil, B2B_API_KEY
ortam değişkeninden okunuyor. Testler app modülleri import edilmeden ÖNCE
sahte bir test anahtarı tanımlar (gerçek anahtar asla repoya yazılmaz).
"""
import os

os.environ.setdefault("B2B_API_KEY", "alm_b2b_test_only_key")
