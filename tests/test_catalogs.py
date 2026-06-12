import unittest
from unittest.mock import Mock

from app.catalogs import (
    CatalogSource,
    catalog_matches_product,
    extract_catalog_items,
    fetch_catalog,
)


class CatalogTests(unittest.TestCase):
    def test_extract_catalog_items_removes_duplicates(self):
        html = """
        <html>
          <body>
            <h2>Yudum Aycicek Yagi 5 L</h2>
            <h2>Yudum Aycicek Yagi 5 L</h2>
            <div class="product-name">Filiz Makarna 500 g</div>
          </body>
        </html>
        """

        self.assertEqual(
            extract_catalog_items(html),
            ["Yudum Aycicek Yagi 5 L", "Filiz Makarna 500 g"],
        )

    def test_fetch_catalog_builds_stable_fingerprint(self):
        source = CatalogSource(
            "test",
            "Test Katalog",
            "https://example.com/catalog",
            ("yag",),
        )
        response = Mock()
        response.url = source.url
        response.text = "<h2>Yudum Aycicek Yagi 5 L</h2>"
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response

        first = fetch_catalog(source, session=session)
        second = fetch_catalog(source, session=session)

        self.assertTrue(first["ok"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(first["items"], ["Yudum Aycicek Yagi 5 L"])

    def test_catalog_matches_product_by_title_words(self):
        snapshot = {
            "items": ["Yudum Aycicek Yagi 5 L"],
            "keywords": ["yag"],
        }

        self.assertTrue(
            catalog_matches_product(snapshot, "Yudum Aycicek Yagi 5 L Pet")
        )
        self.assertFalse(
            catalog_matches_product(snapshot, "Kablosuz Oyuncu Mouse")
        )


if __name__ == "__main__":
    unittest.main()
