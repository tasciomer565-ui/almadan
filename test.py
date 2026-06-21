from app.parser import safe_product_get
import re, json

resp = safe_product_get("https://www.trendyol.com/momordica/daily-shake-ara-ogun-tozu-200-gr-kakao-tozu-protein-inulin-9-vitamin-5-mineral-p-735955635")
print("STATUS:", resp.status_code)
m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', resp.text)
if m:
    print("MATCHED FIRST REGEX")
else:
    print("FIRST REGEX FAILED")
    m2 = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});?</script>', resp.text, re.DOTALL)
    if m2:
        print("MATCHED SECOND REGEX")
    else:
        print("SECOND REGEX FAILED")
        m3 = re.search(r'window\.__INITIAL_STATE__=(.*?})</script>', resp.text, re.DOTALL)
        if m3:
            print("MATCHED THIRD REGEX")
        else:
            print("ALL REGEX FAILED")
