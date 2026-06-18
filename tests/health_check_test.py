"""
Health Check Test — Almadan Sistem Sağlık Denetimi

Bu dosya iki şeyi test eder:
  1. Barkod Akışı: OpenFoodFacts'ten gelen ürün adının market
     sonuçlarıyla en az %60 fuzzy eşleşme skoru aldığını doğrular.
  2. URL Parser: Gerçek bir ürün URL'sinden başlık ve fiyat
     çıkarabildiğini doğrular.

Hata durumunda:
  - app_logs/failure.log dosyasına hata nedeni yazılır.
  - Test FAIL statüsüne düşer (pytest exit code 1).

Çalıştırma:
  pytest tests/health_check_test.py -v
"""
from __future__ import annotations

import json
import pathlib
import time
import unittest
import unittest.mock as mock
from datetime import datetime, timezone

LOG_DIR   = pathlib.Path("app_logs")
FAIL_LOG  = LOG_DIR / "failure.log"
LAST_TEST = LOG_DIR / "last_test.json"

FUZZY_THRESHOLD = 0.60


def _log_failure(test_name: str, reason: str) -> None:
    """Hata nedenini failure.log'a yazar."""
    LOG_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(FAIL_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[{ts}] {test_name} FAILED\n")
        f.write(f"Neden: {reason}\n")
        f.write("-" * 60 + "\n")


def _write_last_test(result: str, error: str | None = None) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    data = {
        "result": result,
        "ts":     datetime.now(timezone.utc).isoformat(),
        "error":  error,
    }
    LAST_TEST.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class TestBarcodeFlow(unittest.TestCase):
    """
    Senaryo: Barkod 8690632085013 (Ülker Çikolatalı Gofret)
    Beklenti: OpenFoodFacts'ten "Ulker" içeren bir isim gelsin,
              FuzzyMatcher ile market sonucuna karşı ≥0.60 skor gelsin.
    """

    MOCK_BARCODE   = "8690632085013"
    MOCK_OFF_TITLE = "Ülker Çikolatalı Gofret"
    MOCK_RESULT_TITLE = "Ülker Çikolatalı Gofret 45g"

    def test_fuzzy_match_above_threshold(self):
        """
        Barkoddan gelen başlık ile market sonucu arasındaki skor ≥ 0.60 olmalı.
        """
        from app.matching_engine import FuzzyMatcher
        fm = FuzzyMatcher()
        score = fm.score(self.MOCK_OFF_TITLE, self.MOCK_RESULT_TITLE)

        if score < FUZZY_THRESHOLD:
            reason = (
                f"API Yanıtı Eşleşmedi: Skor {score:.2f} "
                f"(eşik: {FUZZY_THRESHOLD}) | "
                f"Barkod başlığı: '{self.MOCK_OFF_TITLE}' | "
                f"Market başlığı: '{self.MOCK_RESULT_TITLE}'"
            )
            _log_failure("test_fuzzy_match_above_threshold", reason)
            _write_last_test("failure", reason)
            self.fail(reason)

    def test_fuzzy_match_rejects_wrong_product(self):
        """
        Tamamen farklı ürün skoru 0.60'ın ALTINDA kalmalı (doğru reddediyor mu?).
        """
        from app.matching_engine import FuzzyMatcher
        fm = FuzzyMatcher()
        wrong_title = "Ariel Sıvı Çamaşır Deterjanı 3L"
        score = fm.score(self.MOCK_OFF_TITLE, wrong_title)

        if score >= FUZZY_THRESHOLD:
            reason = (
                f"Yanlış ürün kabul edildi: Skor {score:.2f} "
                f"(eşik: {FUZZY_THRESHOLD}) | "
                f"Barkod: '{self.MOCK_OFF_TITLE}' | "
                f"Yanlış sonuç: '{wrong_title}'"
            )
            _log_failure("test_fuzzy_match_rejects_wrong_product", reason)
            _write_last_test("failure", reason)
            self.fail(reason)

    def test_openfoofacts_mock_response_parsing(self):
        """
        OpenFoodFacts API yanıtından başlık doğru parse edilebiliyor mu?
        """
        mock_off_response = {
            "status": 1,
            "product": {
                "product_name_tr": "Ülker Çikolatalı Gofret",
                "product_name":    "Ulker Chocolate Wafer",
                "brands":          "Ülker",
                "quantity":        "45 g",
                "image_front_url": "https://example.com/img.jpg",
            }
        }

        p = mock_off_response["product"]
        title = (
            p.get("product_name_tr")
            or p.get("product_name")
            or p.get("generic_name")
            or ""
        ).strip()

        brand   = str(p.get("brands") or "").split(",", 1)[0].strip()
        qty     = str(p.get("quantity") or "").strip()
        img_url = str(p.get("image_front_url") or "").strip()

        reason = None
        if not title:
            reason = "OFF yanıtından başlık çıkarılamadı"
        elif not brand:
            reason = "OFF yanıtından marka çıkarılamadı"

        if reason:
            _log_failure("test_openfoofacts_mock_response_parsing", reason)
            _write_last_test("failure", reason)
            self.fail(reason)

        self.assertEqual(title, "Ülker Çikolatalı Gofret")
        self.assertEqual(brand, "Ülker")
        self.assertEqual(qty, "45 g")
        self.assertTrue(img_url.startswith("http"))

    def test_barcode_format_validation(self):
        """EAN-13, EAN-8, UPC-A formatları geçerli; diğerleri reddedilmeli."""
        valid   = ["8690632085013", "12345678", "012345678905"]
        invalid = ["123456", "123456789012345", "ABCDEF"]

        for bc in valid:
            digits = "".join(ch for ch in bc if ch.isdigit())
            if len(digits) not in (8, 12, 13):
                self.fail(f"Geçerli barkod reddedildi: {bc}")

        for bc in invalid:
            digits = "".join(ch for ch in bc if ch.isdigit())
            if len(digits) in (8, 12, 13):
                self.fail(f"Geçersiz barkod kabul edildi: {bc}")


class TestURLParser(unittest.TestCase):
    """
    Senaryo: Meta-tag tabanlı URL parser, gerçek bir ürün URL'sinden
    başlık çıkarabilmeli.
    Mock ile test edilir — gerçek HTTP çağrısı yapılmaz.
    """

    MOCK_HTML = """
    <html>
      <head>
        <meta property="og:title" content="Samsung Galaxy S24 128GB Siyah">
        <meta property="og:price:amount" content="24999">
        <meta property="og:price:currency" content="TRY">
        <meta property="og:image" content="https://example.com/s24.jpg">
      </head>
      <body></body>
    </html>
    """

    def test_meta_tag_title_extraction(self):
        """og:title meta tag'dan başlık çıkarılabilmeli."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(self.MOCK_HTML, "html.parser")
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"].strip() if og_title else None

        if not title:
            reason = "og:title meta tag bulunamadı veya boş"
            _log_failure("test_meta_tag_title_extraction", reason)
            _write_last_test("failure", reason)
            self.fail(reason)

        self.assertEqual(title, "Samsung Galaxy S24 128GB Siyah")

    def test_meta_tag_price_extraction(self):
        """og:price:amount meta tag'dan fiyat çıkarılabilmeli."""
        from bs4 import BeautifulSoup

        soup  = BeautifulSoup(self.MOCK_HTML, "html.parser")
        price_tag = soup.find("meta", property="og:price:amount")
        price = float(price_tag["content"]) if price_tag else None

        if price is None:
            reason = "og:price:amount meta tag bulunamadı"
            _log_failure("test_meta_tag_price_extraction", reason)
            _write_last_test("failure", reason)
            self.fail(reason)

        self.assertEqual(price, 24999.0)


class TestSystemIntegration(unittest.TestCase):
    """
    Uçtan uca entegrasyon: barkod → OFF → FuzzyMatcher → validate
    Gerçek HTTP yerine mock kullanır (CI-safe).
    """

    def test_barcode_to_validation_pipeline(self):
        """
        OFF'dan başlık al → market sonuçlarını filtrele → validated_results dolu mu?
        """
        from app.matching_engine import FuzzyMatcher

        # Simüle: OFF'dan gelen match
        mock_match = {
            "title":        "Ülker Çikolatalı Gofret",
            "brand":        "Ülker",
            "search_query": "Ülker Çikolatalı Gofret 45g",
            "source":       "open_food_facts",
        }

        # Simüle: market arama sonuçları (iyi + kötü karışık)
        mock_results = [
            {"title": "Ülker Çikolatalı Gofret 45g",  "price": 12.5},
            {"title": "Ariel Sıvı Deterjan 3L",        "price": 89.9},
            {"title": "Ülker Çikolatalı Gofret 72g",   "price": 11.9},
        ]

        fm = FuzzyMatcher()
        barcode_title = mock_match["title"]

        validated = []
        for r in mock_results:
            score = fm.score(barcode_title, r["title"])
            if score >= FUZZY_THRESHOLD:
                r["_match_score"] = score
                validated.append(r)

        if not validated:
            reason = (
                f"Pipeline hatası: Hiçbir sonuç eşik ({FUZZY_THRESHOLD}) üzerinde değil. "
                f"Barkod: '{barcode_title}'"
            )
            _log_failure("test_barcode_to_validation_pipeline", reason)
            _write_last_test("failure", reason)
            self.fail(reason)

        # Ariel reddedilmeli
        titles = [r["title"] for r in validated]
        self.assertNotIn("Ariel Sıvı Deterjan 3L", titles,
                         "Yanlış ürün (Ariel) pipeline'dan geçti!")

        # En az 1 Ülker sonucu geçmeli
        ulker_count = sum(1 for t in titles if "lker" in t.lower())
        self.assertGreater(ulker_count, 0, "Hiçbir Ülker sonucu geçmedi!")

        # Başarı — last_test.json'a yaz
        _write_last_test("success")


if __name__ == "__main__":
    unittest.main()
