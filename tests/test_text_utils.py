from app.text_utils import normalize_turkish

def test_normalize_turkish_empty():
    assert normalize_turkish("") == ""
    assert normalize_turkish(None) == ""

def test_normalize_turkish_lowercase():
    assert normalize_turkish("şeker") == "seker"
    assert normalize_turkish("ılık") == "ilik"
    assert normalize_turkish("gözlük") == "gozluk"
    assert normalize_turkish("çorba") == "corba"
    assert normalize_turkish("yağmur") == "yagmur"
    assert normalize_turkish("üzüm") == "uzum"

def test_normalize_turkish_uppercase():
    assert normalize_turkish("ŞEKER") == "seker"
    assert normalize_turkish("ILIK") == "ilik"
    assert normalize_turkish("GÖZLÜK") == "gozluk"
    assert normalize_turkish("ÇORBA") == "corba"
    assert normalize_turkish("YAĞMUR") == "yagmur"
    assert normalize_turkish("ÜZÜM") == "uzum"
    assert normalize_turkish("İSTANBUL") == "istanbul"

def test_normalize_turkish_circumflex():
    assert normalize_turkish("kâğıt") == "kagit"
    assert normalize_turkish("millî") == "milli"
    assert normalize_turkish("Lâle") == "lale"
