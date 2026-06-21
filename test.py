from app.parser import safe_product_get
import json

resp = safe_product_get("https://www.trendyol.com/momordica/daily-shake-ara-ogun-tozu-200-gr-kakao-tozu-protein-inulin-9-vitamin-5-mineral-p-735955635")
print("STATUS:", resp.status_code)

found = False
if resp.status_code == 200:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")
    for script in soup.find_all("script"):
        script_text = script.string or ""
        if "window.__INITIAL_STATE__=" in script_text:
            try:
                json_str = script_text.split("window.__INITIAL_STATE__=")[1]
                # Try to split by the next known variable or script end
                if ";window.__SEARCH_APP_INITIAL_STATE__=" in json_str:
                    json_str = json_str.split(";window.__SEARCH_APP_INITIAL_STATE__=")[0]
                elif ";window.__" in json_str:
                    json_str = json_str.split(";window.__")[0]
                else:
                    json_str = json_str.rsplit(";", 1)[0]
                
                state = json.loads(json_str.strip())
                merchants = state.get("product", {}).get("productDetails", {}).get("otherMerchants", [])
                print("Merchants found:", len(merchants))
                for m in merchants:
                    print("-", m.get("merchant", {}).get("name"), "Price:", m.get("price", {}).get("discountedPrice", {}).get("value"))
                found = True
                break
            except Exception as e:
                print("JSON Error:", e)

if not found:
    print("Not found in any script!")
