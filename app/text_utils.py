"""
text_utils.py — Unified text normalization utilities.
"""

TR_TRANSLATE_MAP = str.maketrans(
    "şğıöüçâîŞĞİÖÜÇIı",
    "sgioucaisgioucii"
)

def normalize_turkish(text: str) -> str:
    """
    Standardizes Turkish characters to their basic Latin equivalents
    and converts the string to lowercase.
    """
    if not text:
        return ""
    return text.translate(TR_TRANSLATE_MAP).lower()


def fix_mojibake(text: str) -> str:
    """
    UTF-8 baytlarının yanlışlıkla Latin-1/cp1252 olarak okunup tekrar
    UTF-8'e kodlanmasıyla oluşan bozuk metni ("TÃ¼rkiye" -> "Türkiye")
    onarır. Bazı kazıyıcı kaynaklarda (ör. n11) ara katmanlarda oluşan
    çift kodlama sonucu ortaya çıkıyor.

    Güvenli: metin zaten doğruysa (tipik olarak latin-1'e sığmayan
    karakterler içerdiği için) round-trip başarısız olur ve metin
    değişmeden döner.
    """
    if not text:
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if fixed != text and "�" not in fixed:
        return fixed
    return text
