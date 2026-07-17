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
