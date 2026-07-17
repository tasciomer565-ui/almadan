"""_scrape_jsonld_itemlist icin regresyon testi -- strict=False JSON parse
duzeltmesi (bazi magazalar, orn. madamecoco, JSON-LD icine kacissiz kontrol
karakteri (ham newline/tab) gomuyor; Python'un varsayilan strict modu bu
yuzden tum bloğu reddediyordu). Gercek ag istegi yapilmaz, requests.get mock'lanir.
"""
from unittest.mock import patch, MagicMock

from app.comparator import _scrape_jsonld_itemlist


def _fake_response(html: str):
    resp = MagicMock()
    resp.ok = True
    resp.text = html
    return resp


def test_scrape_jsonld_itemlist_with_unescaped_control_char():
    # JSON-LD script icinde ham bir newline (kacissiz kontrol karakteri)
    # iceriyor -- standart json.loads (strict=True) bunu reddeder.
    raw_json_ld = (
        '{"@type": "ItemList", "itemListElement": [\n'
        '  {"item": {"name": "Test Ürün\nİkinci Satır", "url": "https://example.com/p/1", '
        '"image": "https://example.com/img.jpg", "offers": {"price": "199.90"}}}\n'
        ']}'
    )
    html = f"""
    <html><body>
    <script type="application/ld+json">{raw_json_ld}</script>
    </body></html>
    """

    with patch("app.scraping_proxy.proxy_enabled", return_value=False), \
         patch("app.comparator.requests.get", return_value=_fake_response(html)):
        results = _scrape_jsonld_itemlist("https://example.com/liste", "madamecoco")

    assert len(results) == 1
    assert results[0]["price"] == 199.90
    assert results[0]["source"] == "madamecoco"
    assert results[0]["verified"] is True
    assert "Test Ürün" in results[0]["title"]


def test_scrape_jsonld_itemlist_no_jsonld_returns_empty_or_heuristic():
    html = "<html><body><div>no jsonld here</div></body></html>"
    with patch("app.scraping_proxy.proxy_enabled", return_value=False), \
         patch("app.comparator.requests.get", return_value=_fake_response(html)):
        results = _scrape_jsonld_itemlist("https://example.com/liste", "example")
    assert results == []


def test_scrape_jsonld_itemlist_network_failure_returns_empty():
    with patch("app.scraping_proxy.proxy_enabled", return_value=False), \
         patch("app.comparator.requests.get", side_effect=Exception("network down")):
        results = _scrape_jsonld_itemlist("https://example.com/liste", "example")
    assert results == []
