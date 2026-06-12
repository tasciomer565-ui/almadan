import sys
import unittest
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
                self.assertIn(label, ["En Ucuz", "En Yüksek İndirim", "Hızlı Kargo", "En İyi Puan", "Önerilen", "Birim Fiyat Avantajı", "Şüpheli Fiyat", "Önerilen Alternatif"])
                
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    unittest.main()
