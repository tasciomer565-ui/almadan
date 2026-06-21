import json
from bs4 import BeautifulSoup

with open("test_trendyol.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")
for script in soup.find_all("script"):
    if script.get("type") == "application/json" or script.get("id") in {"__NEXT_DATA__", "__NUXT_DATA__"}:
        print("Found JSON script! ID:", script.get("id"), "Type:", script.get("type"))
        raw = script.string or script.get_text(strip=True)
        print("Length:", len(raw))
        try:
            data = json.loads(raw)
            # Find anything related to otherMerchants
            if "props" in data:
                print("Has props")
            elif "otherMerchants" in str(data):
                print("Has otherMerchants somewhere!")
        except:
            pass
