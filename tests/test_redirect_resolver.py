from unittest.mock import Mock, patch

from app.parser import (
    normalize_product_url,
    parse_product_url,
    resolve_short_url,
    title_from_product_url,
    translate_deep_link,
)

def test_translate_deep_link():
    t1 = translate_deep_link("trendyol://?Page=Product&ContentId=123456&BoutiqueId=61")
    assert t1 == "https://www.trendyol.com/p-123456", f"Failed: {t1}"

    h1 = translate_deep_link("hepsiburada://?Page=Product&ProductId=hbv00000xxxxx")
    assert h1 == "https://www.hepsiburada.com/p-hbv00000xxxxx", f"Failed: {h1}"

    n1 = translate_deep_link("n11://?Page=Product&ProductId=987654")
    assert n1 == "https://www.n11.com/p-987654", f"Failed: {n1}"

    s1 = translate_deep_link("https://www.trendyol.com/p-123")
    assert s1 == "https://www.trendyol.com/p-123", f"Failed: {s1}"

    print("test_translate_deep_link passed!")


def test_resolve_short_url():
    url = "https://bit.ly/3zY8g8J"
    resolved = resolve_short_url(url)
    print(f"Short link {url} resolved to: {resolved}")
    
    s2 = "https://www.trendyol.com/brand/product-p-123"
    resolved2 = resolve_short_url(s2)
    assert resolved2 == s2, f"Failed: {resolved2}"

    print("test_resolve_short_url passed!")


def test_trendyol_url_forces_turkish_storefront():
    url = (
        "https://www.trendyol.com/icollagen/kolajen-ve-prebiyotik-tablet-"
        "p-752356123?boutiqueId=61&utm_source=test"
    )
    response = Mock()
    response.status_code = 200
    response.headers = {}
    response.text = """
        <html><head>
          <meta property="og:title" content="icollagen Kolajen ve Prebiyotik Tablet">
          <meta property="product:price:amount" content="350,00">
          <meta property="og:image" content="https://cdn.example.com/product.jpg">
        </head></html>
    """
    response.raise_for_status.return_value = None

    with (
        patch("app.parser.is_public_product_url", return_value=True),
        patch("app.parser.requests.get", return_value=response) as get,
    ):
        parsed = parse_product_url(url)

    requested_url = get.call_args.args[0]
    assert "countryCode=TR" in requested_url
    assert "language=tr" in requested_url
    assert "storefrontId=1" in requested_url
    assert parsed.title == "icollagen Kolajen ve Prebiyotik Tablet"
    assert parsed.price == 350.0


def test_url_normalization_and_slug_title_fallback():
    url = normalize_product_url(
        "trendyol.com/icollagen/kolajen-ve-prebiyotik-tablet-p-752356123"
        "?merchantId=1&utm_source=test"
    )
    assert url == (
        "https://www.trendyol.com/icollagen/kolajen-ve-prebiyotik-tablet-"
        "p-752356123?merchantId=1"
    )
    assert title_from_product_url(url) == "Kolajen Ve Prebiyotik Tablet"


def test_private_network_product_url_is_rejected():
    parsed = parse_product_url("http://127.0.0.1:8000/admin")
    assert parsed.title is None
    assert parsed.price is None
    assert parsed.confidence == 0


def test_detect_source():
    from app.parser import detect_source
    assert detect_source("https://www.gratis.com/urun-url") == "gratis"
    assert detect_source("https://rossmann.com.tr/urun") == "rossmann"
    assert detect_source("https://www.supplementler.com/product") == "supplementler"
    assert detect_source("https://proteinocean.com/urun") == "proteinocean"
    assert detect_source("https://www.vatanbilgisayar.com/urun") == "vatanbilgisayar"
    assert detect_source("https://www.itopya.com/urun") == "itopya"
    assert detect_source("https://www.karaca.com/urun") == "karaca"
    assert detect_source("https://www.lcwaikiki.com/urun") == "lcwaikiki"
    assert detect_source("https://www.defacto.com.tr/urun") == "defacto"
    assert detect_source("https://www.mediamarkt.com.tr/urun") == "mediamarkt"
    assert detect_source("https://www.teknosa.com/urun") == "teknosa"
    assert detect_source("https://www.zara.com/urun") == "zara"
    assert detect_source("https://www.migros.com.tr/urun") == "migros"
    assert detect_source("https://www.boyner.com.tr/urun") == "boyner"
    assert detect_source("https://www.koton.com/urun") == "koton"
    assert detect_source("https://www.mavi.com/urun") == "mavi"
    print("test_detect_source passed!")


def test_extract_extra_info():
    from app.parser import extract_extra_info
    from bs4 import BeautifulSoup
    
    # Test supplement parsing
    info1 = extract_extra_info("Hardline Whey 3g Pro 120 Servis Çilekli", "supplementler")
    assert info1.get("servings") == 120, f"Failed: {info1}"
    assert info1.get("category") == "supplement", f"Failed: {info1}"

    info2 = extract_extra_info("Protein Ocean Creatine 60 Ölçek", "proteinocean")
    assert info2.get("servings") == 60, f"Failed: {info2}"
    assert info2.get("category") == "supplement", f"Failed: {info2}"

    # Test supplement parsing from HTML soup (Supplementler)
    soup_supp = BeautifulSoup('<li><span class="pp-sm-title">Porsiyon Sayısı</span><span>:</span><span class="pp-sm-desc spec-service-size">66</span></li>', 'html.parser')
    info_soup1 = extract_extra_info("Supplementler Whey Protein 2000 Gr", "supplementler", soup_supp)
    assert info_soup1.get("servings") == 66, f"Failed: {info_soup1}"

    # Test supplement parsing from HTML soup (Proteinocean)
    soup_ocean = BeautifulSoup('<div>1.6kg | ( 64 servis )</div>', 'html.parser')
    info_soup2 = extract_extra_info("Proteinocean Whey Protein", "proteinocean", soup_ocean)
    assert info_soup2.get("servings") == 64, f"Failed: {info_soup2}"

    # Test supplement parsing estimation from weight fallback (when title has weight but no explicit servings & soup is empty)
    info_est1 = extract_extra_info("Hardline Whey 3 Matrix 2300 Gr - Whey Protein", "supplementler", None)
    # 2300g / 30g serving size = ~77 servings
    assert info_est1.get("servings") == 77, f"Failed: {info_est1}"

    info_est2 = extract_extra_info("Multipower %100 Creatine 500g", "proteinocean", None)
    # 500g / 5g serving size = 100 servings
    assert info_est2.get("servings") == 100, f"Failed: {info_est2}"

    # Test PC component compatibility parsing
    info3 = extract_extra_info("MSI PRO B650-P WIFI AM5 DDR5 Anakart", "vatanbilgisayar")
    assert info3.get("socket") == "AM5", f"Failed: {info3}"
    assert info3.get("ram_type") == "DDR5", f"Failed: {info3}"
    assert "Ryzen" in info3.get("compatibility_info", ""), f"Failed: {info3}"

    info4 = extract_extra_info("ASUS Prime H610M-K LGA1700 DDR4", "itopya")
    assert info4.get("socket") == "LGA1700", f"Failed: {info4}"
    assert info4.get("ram_type") == "DDR4", f"Failed: {info4}"

    print("test_extract_extra_info passed!")


def test_discount_authenticity():
    from app.main import calculate_discount_authenticity
    
    # Case 1: No history, has original price > current
    p1 = {
        "original_price": 1000.0,
        "price_history": [{"price": 800.0}],
    }
    # Current price is 800 (derived from last of price_history)
    res1 = calculate_discount_authenticity(p1)
    assert res1["status"] == "pending", f"Failed: {res1}"
    assert res1["discount_percent"] == 20, f"Failed: {res1}"
    assert res1["badge_color"] == "blue", f"Failed: {res1}"

    # Case 2: Authentic discount (current price is lower than all previous prices)
    p2 = {
        "price_history": [
            {"price": 120.0},
            {"price": 115.0},
            {"price": 95.0}  # current price is 95.0
        ]
    }
    res2 = calculate_discount_authenticity(p2)
    assert res2["status"] == "authentic", f"Failed: {res2}"
    assert res2["badge_color"] == "green", f"Failed: {res2}"

    # Case 3: Fake/Suspicious discount (store claims discount but price is near mean)
    p3 = {
        "original_price": 150.0,
        "price_history": [
            {"price": 98.0},
            {"price": 102.0},
            {"price": 100.0} # current price 100.0
        ]
    }
    res3 = calculate_discount_authenticity(p3)
    assert res3["status"] == "fake", f"Failed: {res3}"
    assert res3["badge_color"] == "red", f"Failed: {res3}"

    # Case 4: Price manipulation (inflated then deflated)
    p4 = {
        "price_history": [
            {"price": 100.0},
            {"price": 150.0}, # inflated
            {"price": 110.0}  # current price 110.0
        ]
    }
    res4 = calculate_discount_authenticity(p4)
    assert res4["status"] == "manipulated", f"Failed: {res4}"
    assert res4["badge_color"] == "yellow", f"Failed: {res4}"

    print("test_discount_authenticity passed!")


if __name__ == "__main__":
    test_translate_deep_link()
    test_resolve_short_url()
    test_detect_source()
    test_extract_extra_info()
    test_discount_authenticity()
    print("All tests passed successfully!")
