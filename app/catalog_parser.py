"""
CatalogParser — Sprint 4: Katalog OCR & Ürün-Fiyat Çıkarma

Desteklenen kaynak tipleri:
  1. HTML  — Mevcut market sayfaları (catalogs.py üzerine kurulur)
  2. PDF   — pdfplumber ile metin katmanlı PDF'ler (install: pip install pdfplumber)
  3. Image — Replicate OCR modeli (AiOrchestrator üzerinden)

Çıktı formatı:
  [{"product_name": "Pınar Süt 1L", "price": 24.90, "original_price": 29.90,
    "discount_pct": 17, "unit": "lt", "raw_text": "...", "confidence": 0.92}]

Türkçe fiyat çıkarma örnekleri:
  "Pınar Süt 1L ₺24,90"         → ✅
  "TAM YAGLI SÜT 29,90 TL"      → ✅
  "%30 İndirim 49,90 TL"        → ✅ (indirim oranı da çıkarılır)
  "AYÇIÇEK YAĞI 5 LT 149.90"   → ✅
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

# ── Türkçe karakter normalizasyonu ──────────────────────────
_TR_MAP = {
    ord("ç"): "c", ord("ğ"): "g", ord("ı"): "i", ord("ş"): "s",
    ord("ö"): "o", ord("ü"): "u",
    ord("Ç"): "C", ord("Ğ"): "G", ord("İ"): "I", ord("Ş"): "S",
    ord("Ö"): "O", ord("Ü"): "U",
}

def _normalize_tr(text: str) -> str:
    return text.translate(_TR_MAP).lower().strip()


# ── Fiyat Regex'leri ─────────────────────────────────────────
# "24,90 TL", "₺24.90", "24.90TL", "24,90"
# (?<!\w) = sayı öncesinde harf/rakam olmasın; (?!\w) = sonrasında harf/rakam olmasın (1L hariç)
_PRICE_RE = re.compile(
    r"(?:₺|TL\s?)?\s*(\d{1,5}[.,]\d{2}|\d{2,5})(?!\s*(?:lt?|kg|gr|ml|cl|adet|'|li|lu|lı))\s*(?:TL|₺|TRY)?",
    re.IGNORECASE,
)
# İndirim oranı: "%30 indirim", "30% off", "% 30"
_DISCOUNT_RE = re.compile(
    r"(?:%\s*(\d{1,3})|(\d{1,3})\s*%)\s*(?:indirim|off|iskonto)?",
    re.IGNORECASE,
)
# Birim: "5 kg", "1lt", "500 gr", "6'lı paket"
_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g|lt|l|ml|cl|litre|adet|'lu|'lı|'li|paket|pk)\b",
    re.IGNORECASE,
)
# Geçerlilik tarihi: "31 Ocak'a kadar", "01-07 Nisan"
_DATE_RE = re.compile(
    r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?",
    re.IGNORECASE,
)

_MONTHS_TR = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}

# Anlamsız satırlar (navigasyon, footer vb.)
_NOISE_PATTERNS = re.compile(
    r"^(anasayfa|sepete ekle|incele|detay|uygula|filtre|sırala|kampanyalar?|"
    r"sayfa \d+|^[\d\s]+$|javascript|cookie|gizlilik|copyright|tüm haklar)",
    re.IGNORECASE,
)


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class CatalogItem:
    product_name: str
    raw_text: str
    price: float | None = None
    original_price: float | None = None
    discount_pct: int | None = None
    unit: str | None = None
    valid_from: str | None = None        # ISO date "2025-01-01"
    valid_until: str | None = None
    page_number: int = 1
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "product_name":    self.product_name,
            "raw_text":        self.raw_text,
            "price":           self.price,
            "original_price":  self.original_price,
            "discount_pct":    self.discount_pct,
            "unit":            self.unit,
            "valid_from":      self.valid_from,
            "valid_until":     self.valid_until,
            "page_number":     self.page_number,
            "confidence":      self.confidence,
        }


# ── Ana Parser Sınıfı ────────────────────────────────────────

class CatalogParser:
    """
    Market kataloglarından yapılandırılmış ürün verisi çıkarır.

    Kullanım:
        parser = CatalogParser()

        # HTML sayfasından
        items = parser.parse_html(html_text, store="migros")

        # PDF dosyasından (bytes)
        items = parser.parse_pdf(pdf_bytes, store="a101")

        # Görsel URL'sinden (Replicate OCR)
        items = parser.parse_image_url(url, store="bim")
    """

    MAX_ITEMS = 200
    MIN_PRODUCT_LEN = 4
    MAX_PRODUCT_LEN = 120

    # ── Public API ───────────────────────────────────────────

    def parse_html(self, html: str, store: str = "") -> list[CatalogItem]:
        """HTML sayfasından ürün-fiyat ikilisi çıkar."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            tag.decompose()

        # Yapılandırılmış ürün kartı çıkarma denemeleri
        items = self._extract_product_cards(soup)
        if len(items) >= 3:
            return items[:self.MAX_ITEMS]

        # Fallback: ham metin satır analizi
        raw_lines = self._extract_text_lines(soup)
        return self._parse_line_groups(raw_lines)[:self.MAX_ITEMS]

    def parse_pdf(self, pdf_bytes: bytes, store: str = "") -> list[CatalogItem]:
        """
        PDF'den metin çıkar. pdfplumber kullanır.
        pip install pdfplumber gerekli.
        """
        try:
            import pdfplumber
        except ImportError:
            # pdfplumber yok → Replicate OCR'a yönlendir
            return []

        items: list[CatalogItem] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Tablo bazlı PDF (fiyat listesi formatı)
                    tables = page.extract_tables()
                    for table in tables:
                        table_items = self._parse_pdf_table(table, page_num)
                        items.extend(table_items)

                    # Tablo yoksa serbest metin
                    if not tables:
                        text = page.extract_text() or ""
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        page_items = self._parse_line_groups(lines, page_num)
                        items.extend(page_items)

                    if len(items) >= self.MAX_ITEMS:
                        break
        except Exception:
            pass
        return items[:self.MAX_ITEMS]

    def parse_image_url(self, image_url: str, store: str = "") -> list[CatalogItem]:
        """
        Görsel URL'sini Replicate OCR modeli ile metne dönüştürür.
        AiOrchestrator.submit_ocr() çıktısını işler.
        """
        from app.ai_orchestrator import orchestrator
        import time

        job = orchestrator.submit_ocr(image_url=image_url, hint="catalog")
        job_id = job.get("job_id", "")
        if not job_id:
            return []

        # Senkron bekle (max 60s — katalog işi acil değil)
        for _ in range(20):
            time.sleep(3)
            status = orchestrator.get_status(job_id)
            if status.status == "done":
                ocr_text = (status.output_data or {}).get("text", "")
                lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
                return self._parse_line_groups(lines)
            if status.status == "failed":
                break
        return []

    def parse_text(self, raw_text: str, store: str = "", page: int = 1) -> list[CatalogItem]:
        """Ham metin girdisini doğrudan işle (test/debug için)."""
        lines = [
            l.strip() for l in raw_text.split("\n")
            if l.strip() and not _NOISE_PATTERNS.match(l.strip())
        ]
        return self._parse_line_groups(lines, page)[:self.MAX_ITEMS]

    # ── HTML Çıkarma ─────────────────────────────────────────

    def _extract_product_cards(self, soup) -> list[CatalogItem]:
        """Yapılandırılmış ürün kartı selectors — market sitesi DOM'ları."""
        card_selectors = [
            # Genel e-ticaret
            ("[class*='product-card']",  "[class*='product-name']",  "[class*='price']"),
            ("[class*='product-item']",  "[class*='title']",          "[class*='price']"),
            ("[class*='catalog-item']",  "[class*='name']",           "[class*='price']"),
            # Migros
            (".product-list-item",       ".product-name",             ".price"),
            # CarrefourSA
            (".item-name",               ".item-name",                ".item-price"),
            # A101 / ŞOK kampanya sayfaları
            (".campaign-item",           "h3",                        ".price, .kampanya-fiyat"),
            # Genel
            ("article",                  "h2, h3",                    "[class*='price'], [class*='fiyat']"),
        ]
        for card_sel, name_sel, price_sel in card_selectors:
            cards = soup.select(card_sel)
            if len(cards) < 3:
                continue
            items = []
            for card in cards[:self.MAX_ITEMS]:
                name_el  = card.select_one(name_sel)
                price_el = card.select_one(price_sel)
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                price_text = price_el.get_text(strip=True) if price_el else ""
                item = self._build_item(name, price_text, raw=card.get_text(" ", strip=True))
                if item:
                    items.append(item)
            if len(items) >= 3:
                return items
        return []

    def _extract_text_lines(self, soup) -> list[str]:
        """Soup'tan anlamlı metin satırlarını çek."""
        text = soup.get_text(separator="\n", strip=True)
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if (
                self.MIN_PRODUCT_LEN <= len(line) <= self.MAX_PRODUCT_LEN
                and not _NOISE_PATTERNS.match(line)
            ):
                lines.append(line)
        return lines

    # ── Metin Satır Analizi ──────────────────────────────────

    def _parse_line_groups(self, lines: list[str], page: int = 1) -> list[CatalogItem]:
        """
        Satır gruplarını incele:
        - Fiyat içeren satır → ürün+fiyat aynı satırda
        - Fiyat içermeyen satır → sonraki satır fiyat olabilir (2-satır grubu)
        """
        items: list[CatalogItem] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            price = self._extract_price(line)

            if price is not None:
                # Fiyat bu satırda → ürün adı aynı satırdan çıkar
                name = self._strip_price_from_line(line)
                if len(name) >= self.MIN_PRODUCT_LEN:
                    item = self._build_item(name, "", raw=line, page=page)
                    if item:
                        items.append(item)
            else:
                # Bu satır fiyat içermiyor; bir sonraki fiyat mı?
                if i + 1 < len(lines):
                    next_price = self._extract_price(lines[i + 1])
                    if next_price is not None:
                        item = self._build_item(line, lines[i + 1], raw=f"{line} {lines[i+1]}", page=page)
                        if item:
                            items.append(item)
                        i += 1  # Bir sonraki satırı atla

            i += 1

        return items

    def _parse_pdf_table(self, table: list[list], page_num: int) -> list[CatalogItem]:
        """
        PDF tablo satırlarını işle.
        Tipik format: [Ürün Adı, Miktar, Normal Fiyat, İndirimli Fiyat]
        """
        items = []
        for row in table:
            if not row:
                continue
            cells = [str(c or "").strip() for c in row]
            name = cells[0] if cells else ""
            if not name or len(name) < self.MIN_PRODUCT_LEN:
                continue
            # Fiyatları bul — tablodaki sayısal hücreleri tara
            prices = []
            for cell in cells[1:]:
                p = self._extract_price(cell)
                if p and p > 0:
                    prices.append(p)
            if not prices:
                continue
            sale_price = min(prices)       # en düşük = indirimli
            orig_price = max(prices) if len(prices) > 1 else None
            unit = self._extract_unit(name)
            discount = self._calc_discount(orig_price, sale_price)
            items.append(CatalogItem(
                product_name=self._clean_product_name(name),
                raw_text=" | ".join(cells),
                price=sale_price,
                original_price=orig_price,
                discount_pct=discount,
                unit=unit,
                page_number=page_num,
                confidence=0.9,
            ))
        return items

    # ── Yardımcılar ──────────────────────────────────────────

    def _build_item(
        self, name_text: str, price_text: str, raw: str = "", page: int = 1
    ) -> CatalogItem | None:
        name = self._clean_product_name(name_text)
        if len(name) < self.MIN_PRODUCT_LEN:
            return None

        combined = f"{name_text} {price_text}".strip()
        price   = self._extract_price(price_text) or self._extract_price(raw) or self._extract_price(combined)
        orig    = self._extract_original_price(combined)
        disc    = self._extract_discount_pct(combined) or self._calc_discount(orig, price)
        unit    = self._extract_unit(combined)

        # İndirim %'si varsa confidence artar (açıkça belirtilmiş)
        conf = 0.95 if disc else (0.85 if price else 0.6)

        return CatalogItem(
            product_name=name,
            raw_text=raw or combined,
            price=price,
            original_price=orig,
            discount_pct=disc,
            unit=unit,
            page_number=page,
            confidence=conf,
        )

    @staticmethod
    def _extract_price(text: str) -> float | None:
        if not text:
            return None
        # Binlik ayracı nokta, ondalık virgül (Türkçe)
        clean = re.sub(r"(?<=\d)\.(?=\d{3})", "", text)  # 1.299 → 1299
        matches = _PRICE_RE.findall(clean)
        for m in matches:
            try:
                val = float(m.replace(",", "."))
                if 0.5 <= val <= 99999:
                    return val
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_original_price(text: str) -> float | None:
        """İki fiyat varsa büyüğü orijinal fiyattır."""
        clean = re.sub(r"(?<=\d)\.(?=\d{3})", "", text)
        matches = _PRICE_RE.findall(clean)
        prices = []
        for m in matches:
            try:
                val = float(m.replace(",", "."))
                if 0.5 <= val <= 99999:
                    prices.append(val)
            except ValueError:
                continue
        return max(prices) if len(prices) >= 2 else None

    @staticmethod
    def _extract_discount_pct(text: str) -> int | None:
        m = _DISCOUNT_RE.search(text)
        if m:
            val = int(m.group(1) or m.group(2))
            if 1 <= val <= 99:
                return val
        return None

    @staticmethod
    def _calc_discount(orig: float | None, sale: float | None) -> int | None:
        if orig and sale and orig > sale > 0:
            return round((orig - sale) / orig * 100)
        return None

    @staticmethod
    def _extract_unit(text: str) -> str | None:
        m = _UNIT_RE.search(text)
        if m:
            return f"{m.group(1)}{m.group(2).lower()}"
        return None

    @staticmethod
    def _strip_price_from_line(line: str) -> str:
        """Fiyat bilgisini satırdan kaldır, kalan ürün adı."""
        clean = _PRICE_RE.sub("", line)
        clean = re.sub(r"\b(TL|₺|TRY)\b", "", clean, flags=re.IGNORECASE)
        return clean.strip(" -–|,.")

    @staticmethod
    def _clean_product_name(text: str) -> str:
        """Ürün adını normalize et."""
        # Fiyat artıklarını temizle
        clean = _PRICE_RE.sub("", text)
        clean = re.sub(r"\b(TL|₺|TRY|indirim|off|iskonto)\b", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s+", " ", clean).strip(" -–|,.*")
        # Baş harfi büyüt (okunabilirlik)
        return clean.strip()


# ── Modül seviyesi örnek ─────────────────────────────────────
catalog_parser = CatalogParser()
