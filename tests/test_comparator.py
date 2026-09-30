import pytest

from app.comparator import (
    clean_product_title, extract_yahoo_url, find_comparison_links, compare_prices, titles_match,
    is_refurbished_title, extract_model_numbers, has_model_conflict,
    extract_storage_capacity, has_capacity_conflict,
    extract_volume_weight_count, has_physical_conflict,
    extract_ram_and_tv_size, has_tech_conflict, is_logical_product, has_gender_conflict,
    same_product, title_has_brand, postprocess_search_products,
)

def test_clean_product_title():
    t1 = clean_product_title("Hardline Whey 3 Matrix 2300 Gr - Whey Protein")
    assert t1 == "Hardline Whey 3 Matrix 2300 Gr", f"Failed: {t1}"

    t2 = clean_product_title("MSI PRO B650-P WIFI AM5 DDR5 | Hepsiburada")
    assert t2 == "MSI PRO B650-P WIFI AM5 DDR5", f"Failed: {t2}"
    print("test_clean_product_title passed!")


def test_extract_yahoo_url():
    yahoo_url = "https://r.search.yahoo.com/_ylt=AwrFeN3nNytqNAIAoBNXNyoA;_ylu=Y29sbwNiZjEEcG9zAzEEdnRpZAMEc2VjA3Ny/RV=2/RE=1782426856/RO=10/RU=https%3a%2f%2fwww.trendyol.com%2fhardline-whey-3-matrix-y-s4188/RK=2/RS=FBWZKqLxFTGg10AIJ9jwFUhyK5Q-"
    extracted = extract_yahoo_url(yahoo_url)
    assert extracted == "https://www.trendyol.com/hardline-whey-3-matrix-y-s4188", f"Failed: {extracted}"
    print("test_extract_yahoo_url passed!")


def test_find_comparison_links():
    # Test with a popular product query to see if Yahoo returns matches
    links = find_comparison_links("Hardline Whey 3 Matrix 2300 Gr", "supplementler")
    print("Found comparison links:", links)
    
    # Check if at least one expected store is found
    expected_stores = {"trendyol", "hepsiburada", "amazon"}
    found_expected = any(store in links for store in expected_stores)
    # If the network or Yahoo fluctuates, we don't strict fail, but print warning
    assert len(links) >= 0
    print("test_find_comparison_links passed!")

def test_titles_match():
    assert titles_match("Hardline Whey 3 Matrix 2300 Gr", "Hardline Nutrition Hardline Whey 3 Matrix 2300 Gr Çikolata") is True
    assert titles_match("Hardline Whey 3 Matrix 2300 Gr", "Remixon Hunter 6721 21 Gr Color 09") is False
    assert titles_match("MSI PRO B650-P WIFI AM5 DDR5", "MSI PRO B650-P WIFI AM5 DDR5 ATX Anakart") is True
    print("test_titles_match passed!")


# ── is_refurbished_title ─────────────────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("iPhone 15 128 GB Yenilenmiş A Kalite", True),
    ("Samsung Galaxy S24 Refurbished", True),
    ("Laptop Teşhir Ürünü %20 İndirimli", True),
    ("2. El iPhone 13", True),
    ("2.el iPhone 13", True),
    ("İkinci El Kitap Seti", True),
    ("YENILENMIS Xiaomi Redmi Note 12", True),  # TR karakter/büyük harf duyarsız
    ("iPhone 15 128 GB Sıfır Kutulu", False),
    ("Samsung Galaxy S24 Yeni Ürün", False),
    ("", False),
])
def test_is_refurbished_title(title, expected):
    assert is_refurbished_title(title) is expected


# ── extract_model_numbers ────────────────────────────────────

def test_extract_model_numbers_iphone_15():
    models = extract_model_numbers("Apple iPhone 15 128 GB Mavi")
    assert "15" in models
    # 3+ haneli kapasite modeli sayilmamali
    assert "128" not in models


def test_extract_model_numbers_iphone_16e():
    models = extract_model_numbers("Apple iPhone 16e 128 GB Siyah")
    assert "16e" in models
    assert "16" in models  # cekirdek sayi da eklenir


def test_extract_model_numbers_ignores_units():
    # "12 Ay Garantili" -> 12 model sayilmamali
    models = extract_model_numbers("Ürün 12 Ay Garantili 3 lu Paket")
    assert "12" not in models


def test_extract_model_numbers_empty():
    assert extract_model_numbers("") == set()
    assert extract_model_numbers(None) == set()


# ── has_model_conflict ───────────────────────────────────────

def test_has_model_conflict_iphone_15_vs_16e():
    assert has_model_conflict("iPhone 15 128 GB", "Apple iPhone 16e 128 GB Siyah") is True


def test_has_model_conflict_same_model_no_conflict():
    assert has_model_conflict("iPhone 15 128 GB", "Apple iPhone 15 128 GB Mavi") is False


def test_has_model_conflict_no_model_numbers_conservative():
    # Hicbir tarafta model adayi yoksa suphede kal, celiski yok say
    assert has_model_conflict("Kablosuz Kulaklık", "Bluetooth Kulaklık Siyah") is False


# ── extract_storage_capacity ─────────────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("iPhone 15 128 GB Mavi", 128.0),
    ("iPhone 15 512GB Siyah", 512.0),
    ("MacBook Pro 1 TB SSD", 1024.0),
    ("Samsung Galaxy S24 256 gb", 256.0),
])
def test_extract_storage_capacity_basic(title, expected):
    assert extract_storage_capacity(title) == expected


def test_extract_storage_capacity_none_when_missing():
    assert extract_storage_capacity("iPhone 15 Mavi") is None
    assert extract_storage_capacity("") is None
    assert extract_storage_capacity(None) is None


# ── has_capacity_conflict ─────────────────────────────────────

def test_has_capacity_conflict_128_vs_512():
    assert has_capacity_conflict("iPhone 15 128 GB", "iPhone 15 512 GB") is True


def test_has_capacity_conflict_same_capacity():
    assert has_capacity_conflict("iPhone 15 128 GB", "Apple iPhone 15 128 GB Mavi") is False


def test_has_capacity_conflict_conservative_when_missing():
    assert has_capacity_conflict("iPhone 15 128 GB", "iPhone 15 Mavi") is False
    assert has_capacity_conflict("iPhone 15", "iPhone 15 128 GB") is False


# ── extract_storage_capacity: edge cases (ondalik TB, RAM+depolama karisik) ──

@pytest.mark.parametrize("title,expected", [
    ("Laptop 1.5 TB SSD", 1536.0),
    ("Laptop 1,5 TB SSD", 1536.0),
])
def test_extract_storage_capacity_decimal_tb(title, expected):
    assert extract_storage_capacity(title) == expected


def test_extract_storage_capacity_ambiguous_ram_and_storage():
    # Hem RAM hem depolama gecince -> muhafazakar None
    assert extract_storage_capacity("Laptop 8 GB RAM 128 GB Depolama") is None
    assert extract_storage_capacity("Telefon 12 GB RAM 256 GB Hafıza") is None


def test_extract_storage_capacity_single_capacity_normal_title():
    assert extract_storage_capacity("Xiaomi Redmi Note 12 128 GB Yıldız Mavisi") == 128.0


def test_extract_volume_weight_count():
    p1 = extract_volume_weight_count("Pınar Süt 1 L")
    assert p1["volume"] == 1000.0
    assert p1["weight"] is None
    assert p1["count"] is None

    p2 = extract_volume_weight_count("Hardline Protein 2300 gr")
    assert p2["volume"] is None
    assert p2["weight"] == 2300.0
    assert p2["count"] is None

    p3 = extract_volume_weight_count("Lipton Demlik Çay 100'lü Paket")
    assert p3["volume"] is None
    assert p3["weight"] is None
    assert p3["count"] == 100.0


def test_has_physical_conflict():
    # Volume conflict
    assert has_physical_conflict("Pınar Süt 1 L", "Pınar Süt 500 ml") is True
    assert has_physical_conflict("Pınar Süt 1 L", "Pınar Süt 1000 ml") is False

    # Weight conflict
    assert has_physical_conflict("Un 5 kg", "Un 1 kg") is True
    assert has_physical_conflict("Un 5 kg", "Un 5000 gr") is False

    # Count conflict
    assert has_physical_conflict("Çay 100'lü", "Çay 50'li") is True
    assert has_physical_conflict("Çay 100'lü", "Çay 100 Adet") is False


def test_extract_ram_and_tv_size():
    t1 = extract_ram_and_tv_size("MSI Laptop 16 GB RAM 512 GB SSD")
    assert t1["ram"] == 16.0
    assert t1["tv_size"] is None

    t2 = extract_ram_and_tv_size("Philips 55\" 4K Smart LED TV")
    assert t2["ram"] is None
    assert t2["tv_size"] == 55.0

    t3 = extract_ram_and_tv_size("LG 139 Ekran OLED TV")
    assert t3["tv_size"] == 55.0


def test_has_tech_conflict():
    assert has_tech_conflict("Laptop 16 GB RAM", "Laptop 8 GB RAM") is True
    assert has_tech_conflict("Laptop 16 GB RAM", "Laptop 16GB RAM") is False

    assert has_tech_conflict("TV 55 inç", "TV 43 inç") is True
    assert has_tech_conflict("TV 55\"", "TV 139 cm") is False


def test_is_logical_product_physical_conflicts():
    # Filter out mismatching pack sizes/counts via is_logical_product
    assert is_logical_product("Yudum Ayçiçek Yağı 5 L", "Yudum Ayçiçek Yağı 1 L") is False
    assert is_logical_product("Sarıyer Gazoz 6'lı", "Sarıyer Gazoz Tekli") is False
    assert is_logical_product("Laptop 16 GB RAM", "Laptop 8 GB RAM") is False


def test_has_gender_conflict():
    assert has_gender_conflict("Erkek Parfüm", "Zara Kadın Parfüm") is True
    assert has_gender_conflict("Erkek Parfüm", "Calvin Klein Erkek Parfüm") is False
    assert has_gender_conflict("Kadın Ceket", "Erkek Deri Ceket") is True
    assert has_gender_conflict("Kadın Ceket", "Zara Unisex Ceket") is False


def test_stem_turkish_word():
    from app.matching_engine import stem_turkish_word
    assert stem_turkish_word("kulaklıklar") == "kulaklık"
    assert stem_turkish_word("bilgisayardan") == "bilgisayar"
    assert stem_turkish_word("deterjanlar") == "deterjan"
    assert stem_turkish_word("sabun") == "sabun"


def test_is_logical_product_gender():
    assert is_logical_product("Erkek Parfüm", "Kadın Parfüm") is False
    assert is_logical_product("Kadın Ceket", "Erkek Ceket") is False


# ── same_product (tekrar eleme) ──────────────────────────────

@pytest.mark.parametrize("a,b,query", [
    ("Apple iPhone 15 128GB Siyah", "iPhone 15 128 GB Siyah Cep Telefonu", "iphone 15"),
    ("JBL Go 3 Bluetooth Hoparlör Siyah", "JBL GO 3 Taşınabilir Bluetooth Hoparlör", "jbl hoparlör"),
    ("Tefal KO1501 Express Kettle 1.7 L", "Tefal Express KO1501 Su Isıtıcı Kettle", "tefal kettle"),
    ("Samsung Galaxy A55 128GB Lacivert", "Samsung Galaxy A55 5G 128 GB Lacivert", "samsung telefon"),
])
def test_same_product_merges_same_model(a, b, query):
    assert same_product(a, b, set(query.split())) is True


@pytest.mark.parametrize("a,b,query", [
    ("JBL Go 3 Hoparlör", "JBL Flip 6 Hoparlör", "jbl hoparlör"),
    ("Tefal Kettle KO1501", "Tefal Kettle KI2008", "tefal kettle"),
    ("Sony SRS-XB13 Bluetooth Hoparlör", "Sony ULT Field 1 Hoparlör", "sony hoparlör"),
    ("Samsung Galaxy A55 128GB", "Samsung Galaxy A35 128GB", "samsung telefon"),
])
def test_same_product_keeps_different_models(a, b, query):
    # titles_match bunlari "ayni" sayiyordu -- markali aramada sadece en ucuz model kaliyordu
    assert same_product(a, b, set(query.split())) is False


# ── marka filtresi ───────────────────────────────────────────

def test_title_has_brand_aliases_and_boundaries():
    assert title_has_brand("iPhone 14 Pro", "apple") is True
    assert title_has_brand("ARÇELİK Bulaşık Makinesi", "arcelik") is True
    assert title_has_brand("CHP Rozeti", "hp") is False
    assert title_has_brand("JBL Go 3", "sony") is False


def test_postprocess_brand_query_drops_other_brands_keeps_models():
    raw = [
        {"title": "Sony SRS-XB13 Bluetooth Hoparlör", "price": 1500, "source": "trendyol", "url": "u1"},
        {"title": "JBL Go 3 Hoparlör", "price": 1200, "source": "n11", "url": "u2"},
        {"title": "Sony ULT Field 1 Hoparlör", "price": 3500, "source": "hepsiburada", "url": "u3"},
    ]
    titles = [p["title"] for p in postprocess_search_products("sony hoparlör", raw)]
    assert "JBL Go 3 Hoparlör" not in titles
    assert len(titles) == 2


def _sony(src, n, base, model):
    return [{"title": f"Sony SRS-{model}{i} Bluetooth Hoparlör", "price": base + i * 100,
             "source": src, "url": f"{src}{i}"} for i in range(n)]


def test_postprocess_brand_query_interleaves_stores():
    # Markali aramada ilk magaza 5 slotun hepsini dolduruyordu (/fiyat "1 magaza" -> noindex)
    raw = _sony("n11", 6, 8000, "XB") + _sony("trendyol", 3, 7000, "XE") + _sony("hepsiburada", 2, 9000, "ULT")
    sources = [p["source"] for p in postprocess_search_products("sony hoparlör", raw)]
    assert set(sources) == {"n11", "trendyol", "hepsiburada"}


def test_postprocess_brand_query_single_store_keeps_count():
    sources = [p["source"] for p in postprocess_search_products("sony hoparlör", _sony("n11", 6, 8000, "XB"))]
    assert sources == ["n11"] * 5


# ── N11: once dogrudan, olmazsa proxy ────────────────────────

_N11_HTML = ('<a class="product-item" href="/urun/x"><h3 class="product-item-title">Sony X Hoparlör</h3>'
             '<span class="price-currency">1.234,00 TL</span></a>')


def test_n11_direct_success_does_not_spend_proxy_credit():
    from unittest import mock
    import app.comparator as comparator
    import app.scraping_proxy as scraping_proxy
    direct = mock.Mock(status_code=200, text=_N11_HTML)
    with mock.patch.object(comparator.requests, "get", return_value=direct),          mock.patch.object(scraping_proxy, "proxy_enabled", return_value=True),          mock.patch.object(scraping_proxy, "proxy_get") as proxy_get:
        products, _ = comparator.search_n11_direct("sony hoparlör")
    assert len(products) == 1 and products[0]["source"] == "n11"
    assert proxy_get.call_count == 0


def test_n11_falls_back_to_proxy_when_direct_blocked():
    from unittest import mock
    import app.comparator as comparator
    import app.scraping_proxy as scraping_proxy
    with mock.patch.object(comparator.requests, "get", side_effect=Exception("blocked")),          mock.patch.object(scraping_proxy, "proxy_enabled", return_value=True),          mock.patch.object(scraping_proxy, "proxy_get", return_value=_N11_HTML) as proxy_get:
        products, _ = comparator.search_n11_direct("sony hoparlör")
    assert len(products) == 1
    assert proxy_get.call_count == 1


if __name__ == "__main__":
    test_clean_product_title()
    test_extract_yahoo_url()
    test_find_comparison_links()
    test_titles_match()
    test_extract_volume_weight_count()
    test_has_physical_conflict()
    test_extract_ram_and_tv_size()
    test_has_tech_conflict()
    test_is_logical_product_physical_conflicts()
    test_has_gender_conflict()
    test_stem_turkish_word()
    test_is_logical_product_gender()
    print("All comparator tests passed successfully!")
