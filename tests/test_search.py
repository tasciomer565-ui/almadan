import sys
import unittest
from unittest.mock import patch
from app.comparator import search_products_by_name

class TestSearchByName(unittest.TestCase):
    def test_search_structure_and_labels(self):
        # We search for a popular product
        query = "Hardline Whey 3 Matrix 2300 Gr"
        print(f"Running test search for query: '{query}'...")
        results = search_products_by_name(query)
        
        # Verify result is a list and has at most 5 results
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) <= 5)
        
        # Verify schema of each result item
        for item in results:
            self.assertIn("title", item)
            self.assertIn("price", item)
            self.assertIn("original_price", item)
            self.assertIn("image_url", item)
            self.assertIn("source", item)
            self.assertIn("url", item)
            self.assertIn("labels", item)
            self.assertIn("extra_info", item)
            
            # Check price is positive
            self.assertGreater(item["price"], 0)
            
            # Check labels is a list and contains valid tags
            self.assertIsInstance(item["labels"], list)
            self.assertTrue(len(item["labels"]) >= 1)
            for label in item["labels"]:
                self.assertIn(label, ["En Ucuz", "En Yüksek İndirim", "Hızlı Kargo", "En İyi Puan", "Önerilen", "Birim Fiyat Avantajı", "Şüpheli Fiyat", "Önerilen Alternatif", "Birim Fiyat Riski", "Sistem, lokal rezonans verisi kullanıyor", "Lokal Fallback"])
                
        print(f"Search successfully returned {len(results)} items.")
        if results:
            print("First item labels:", results[0]["labels"])
            print("First item price:", results[0]["price"])

    def test_search_fallback_on_bogus_query(self):
        # Search for a query that won't match anything
        results = search_products_by_name("xyzabcqwerty")
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # Verify that all returned items are fallback recommendations
        for item in results:
            self.assertIn("Önerilen Alternatif", item["labels"])
            self.assertTrue(item["extra_info"].get("fallback"))

    @patch("app.comparator.search_n11_direct")
    @patch("app.search_orchestrator.fetch_aol_urls_for_sites")
    def test_unit_price_risk_labeling(self, mock_fetch_urls, mock_n11):
        mock_fetch_urls.return_value = []
        mock_n11.return_value = (
            [
                {
                    "title": "Süt 1 L",
                    "price": 20.0,
                    "original_price": None,
                    "image_url": None,
                    "source": "n11",
                    "url": "https://www.n11.com/urun/sut-1l",
                    "labels": ["Önerilen"],
                    "extra_info": {"out_of_stock": False},
                },
                {
                    "title": "Süt 200 ml",
                    "price": 10.0,
                    "original_price": None,
                    "image_url": None,
                    "source": "n11",
                    "url": "https://www.n11.com/urun/sut-200ml",
                    "labels": ["Önerilen"],
                    "extra_info": {"out_of_stock": False},
                },
            ],
            "süt",
        )
        results = search_products_by_name("süt")
        item_200 = next(item for item in results if "200 ml" in item["title"])
        self.assertIn("Birim Fiyat Riski", item_200["labels"])
        self.assertNotIn("Önerilen", item_200["labels"])

    def test_search_local_geographic_resonance(self):
        # Search with coordinates and hybrid mode
        results = search_products_by_name("süt", lat=41.0082, lon=28.9784, mode="hybrid")
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # Verify that geographic fields are present
        for item in results:
            self.assertIn("delivery_type", item)
            self.assertIn("delivery_time", item)
            self.assertIn("delivery_cost", item)
            if item["delivery_type"] == "local":
                self.assertIsNotNone(item["distance_km"])
                self.assertIsNotNone(item["latitude"])
                self.assertIsNotNone(item["longitude"])
                self.assertTrue("Dakika" in item["delivery_time"])


if __name__ == "__main__":
    from unittest.mock import patch
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    unittest.main()
