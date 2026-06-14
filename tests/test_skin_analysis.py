import unittest
import base64
from io import BytesIO
from PIL import Image
from app.main import SkinRequest, CosmeticColorRequest, analyze_skin, analyze_cosmetic_color

class SkinAnalysisTests(unittest.TestCase):
    def test_analyze_skin_fallback_default(self) -> None:
        # Create a simple 50x50 white image base64
        img = Image.new("RGB", (50, 50), color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        payload = SkinRequest(image_base64=f"data:image/png;base64,{img_str}")
        result = analyze_skin(payload)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["skin_type"], "light")  # White has high luminance -> light skin
        self.assertEqual(result["undertone"], "Cool (Soğuk)")
        self.assertEqual(result["source"], "numpy_fallback")

    def test_analyze_cosmetic_color_light_pembe(self) -> None:
        payload = CosmeticColorRequest(skin_type="light", undertone="Cool (Soğuk)", query="pembe allık")
        result = analyze_cosmetic_color(payload)
        
        self.assertTrue(result["success"])
        self.assertIn("HOLOGRAFİK ANALİZ RAPORU", result["comment"])
        self.assertIn("rezonansı yakaladı", result["comment"])

    def test_analyze_cosmetic_color_light_turuncu(self) -> None:
        payload = CosmeticColorRequest(skin_type="light", undertone="Cool (Soğuk)", query="turuncu ruj")
        result = analyze_cosmetic_color(payload)
        
        self.assertTrue(result["success"])
        self.assertIn("GRAVİTASYONEL ALAN UYARISI", result["comment"])
        self.assertIn("kuantum frekansının çakıştığını gösteriyor", result["comment"])

if __name__ == "__main__":
    unittest.main()
