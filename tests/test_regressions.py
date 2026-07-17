"""Bugun yapilan iki duzeltmenin regresyon testleri:

1) public/static/app.js -- _SUN_SVG/_MOON_SVG sabitlerinin dosya basinda
   (kullanildiklari yerden ONCE) tanimli oldugu (TDZ / "Cannot access
   before initialization" hatasi bir daha olusmasin).
2) app/main.py find_alternatives -- yenilenmis/teshir urunler ayni relevance
   grubunda fiyata gore siralamada GERIYE itiliyor (silinmiyor), kaynak urun
   yenilenmis DEGILKEN.
"""
from pathlib import Path

from app.comparator import is_refurbished_title

APP_JS = Path(__file__).resolve().parent.parent / "public" / "static" / "app.js"


def test_sun_moon_svg_constants_defined_before_first_use():
    text = APP_JS.read_text(encoding="utf-8")
    assert "_SUN_SVG" in text and "_MOON_SVG" in text

    def_sun = text.index("const _SUN_SVG")
    def_moon = text.index("const _MOON_SVG")
    first_use_sun = text.index("_SUN_SVG", def_sun + len("const _SUN_SVG"))
    first_use_moon = text.index("_MOON_SVG", def_moon + len("const _MOON_SVG"))

    assert def_sun < first_use_sun
    assert def_moon < first_use_moon

    # Sabitler dosyanin cok erken bir noktasinda (fonksiyon govdesi icinde
    # degil, ust seviyede) tanimli olmali -- TDZ hatasi genelde bir fonksiyon
    # kullanimdan SONRA modul en altinda tanimlanmis sabite erismeye
    # calisirken olusuyordu. Burada tanim, dosyanin ilk %5'i icinde olmali.
    assert def_sun < len(text) * 0.05
    assert def_moon < len(text) * 0.05


def _refurb_penalty(product: dict, source_is_refurb: bool) -> int:
    """app/main.py find_alternatives icindeki refurb_penalty mantiginin
    izole edilmis kopyasi -- fonksiyon nested oldugu icin dogrudan import
    edilemiyor, algoritma burada regresyon amaciyla yeniden test ediliyor."""
    return 1 if (not source_is_refurb and product.get("condition") == "refurbished") else 0


def test_refurbished_products_pushed_back_not_removed_when_source_not_refurb():
    source_title = "Apple iPhone 15 128 GB Mavi"
    candidates = [
        {"title": "Apple iPhone 15 128 GB Yenilenmiş A Kalite", "price": 20000.0},
        {"title": "Apple iPhone 15 128 GB Mavi Sıfır", "price": 25000.0},
    ]
    source_is_refurb = is_refurbished_title(source_title)
    assert source_is_refurb is False

    for p in candidates:
        if is_refurbished_title(p["title"]):
            p["condition"] = "refurbished"

    # Ayni relevance grubunda (relevance=0 sabit varsayilir) sirala
    candidates.sort(key=lambda p: (_refurb_penalty(p, source_is_refurb), p["price"]))

    # Yenilenmis urun (daha ucuz olmasina ragmen) listede kalmali (silinmemeli)
    titles = [p["title"] for p in candidates]
    assert "Apple iPhone 15 128 GB Yenilenmiş A Kalite" in titles
    # ama GERIYE itilmis olmali -- sifir urun once gelmeli
    assert candidates[0]["title"] == "Apple iPhone 15 128 GB Mavi Sıfır"
    assert candidates[1]["condition"] == "refurbished"


def test_refurb_penalty_not_applied_when_source_itself_refurb():
    source_title = "Apple iPhone 15 128 GB Yenilenmiş"
    source_is_refurb = is_refurbished_title(source_title)
    assert source_is_refurb is True

    candidate = {"title": "Apple iPhone 15 128 GB Yenilenmiş A Kalite", "price": 20000.0}
    if is_refurbished_title(candidate["title"]):
        candidate["condition"] = "refurbished"

    assert _refurb_penalty(candidate, source_is_refurb) == 0
