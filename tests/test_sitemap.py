"""scripts/generate_sitemap.py'nin urettigi XML'in gecerli oldugunu dogrular.
Gercek ag istegi yapmaz -- build_sitemap() saf Python, mevcut ALL_STORES_MAP /
get_seo_price_terms veri yapilarindan uretiliyor.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_sitemap import build_sitemap  # noqa: E402


def test_sitemap_xml_is_well_formed():
    xml_str = build_sitemap()
    root = ET.fromstring(xml_str)  # ParseError firlatirsa test basarisiz olur
    assert root is not None


def test_sitemap_contains_static_pages():
    xml_str = build_sitemap()
    assert "https://www.almadan.app/index.html" in xml_str
    assert "https://www.almadan.app/hakkinda" in xml_str


def test_sitemap_urls_are_well_formed_and_non_empty():
    xml_str = build_sitemap()
    root = ET.fromstring(xml_str)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = root.findall("sm:url", ns)
    assert len(urls) > 0
    for url_el in urls:
        loc = url_el.find("sm:loc", ns)
        assert loc is not None
        assert loc.text.startswith("https://www.almadan.app/")
