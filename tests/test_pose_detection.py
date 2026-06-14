import unittest
import base64
from io import BytesIO
from PIL import Image
from app.main import PoseRequest, detect_pose

class PoseDetectionTests(unittest.TestCase):
    def test_detect_pose_fallback_default(self) -> None:
        # Create a simple 50x50 white image base64
        img = Image.new("RGB", (50, 50), color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        payload = PoseRequest(image_base64=f"data:image/png;base64,{img_str}")
        
        # Call the endpoint handler function directly
        result = detect_pose(payload)
        
        # Verify structure
        self.assertIn("success", result)
        self.assertIn("shoulder_left", result)
        self.assertIn("shoulder_right", result)
        self.assertIn("tilt_angle", result)
        self.assertIn("body_width", result)
        self.assertIn("neck_anchor", result)
        self.assertIn("source", result)
        
        # Since it is a solid white image, it should fallback to defaults or NumPy fallback
        self.assertFalse(result["success"])
        self.assertEqual(result["source"], "default_fallback")
        self.assertEqual(result["shoulder_left"], [0.25, 0.4])
        self.assertEqual(result["shoulder_right"], [0.75, 0.4])

    def test_detect_pose_invalid_base64(self) -> None:
        from fastapi import HTTPException
        payload = PoseRequest(image_base64="invalid_base64_data")
        with self.assertRaises(HTTPException):
            detect_pose(payload)

if __name__ == "__main__":
    unittest.main()
