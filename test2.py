import sys
from app.scraping_proxy import proxy_get

url = "https://www.trendyol.com/momordica/daily-shake-ara-ogun-tozu-200-gr-kakao-tozu-protein-inulin-9-vitamin-5-mineral-p-735955635"
html = proxy_get(url, render_js=False)

if not html:
    print("PROXY GET FAILED")
    sys.exit(1)

with open("test_trendyol.html", "w", encoding="utf-8") as f:
    f.write(html)
print("SAVED TO test_trendyol.html")
