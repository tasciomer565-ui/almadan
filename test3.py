import json
from bs4 import BeautifulSoup

with open("test_trendyol.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")
for script in soup.find_all("script"):
    script_text = script.string or ""
    if "window.__INITIAL_STATE__=" in script_text:
        print("FOUND INITIAL STATE SCRIPT. Length:", len(script_text))
        try:
            json_str = script_text.split("window.__INITIAL_STATE__=")[1]
            if ";window.__SEARCH_APP_INITIAL_STATE__=" in json_str:
                json_str = json_str.split(";window.__SEARCH_APP_INITIAL_STATE__=")[0]
            elif ";window.__" in json_str:
                json_str = json_str.split(";window.__")[0]
            else:
                json_str = json_str.rsplit(";", 1)[0]
            
            print("Extracted json_str length:", len(json_str))
            state = json.loads(json_str.strip())
            merchants = state.get("product", {}).get("productDetails", {}).get("otherMerchants", [])
            print("Merchants found:", len(merchants))
            for m in merchants:
                print("-", m.get("merchant", {}).get("name"), m.get("price", {}).get("discountedPrice", {}).get("value"))
        except Exception as e:
            print("ERROR parsing:", e)
            print("First 100 chars:", json_str[:100])
            print("Last 100 chars:", json_str[-100:])
        break
