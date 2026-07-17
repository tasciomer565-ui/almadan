"""
app.js / app.min.js ve index.html / index.min.html senkronizasyon kontrolu.

Onemli proje kurali (bu oturumda defalarca dogrulandi): bu projede
"*.min.*" dosyalar GERCEKTEN minify edilmis DEGIL -- app.min.js, app.js'in
birebir (byte-byte) kopyasi olacak sekilde elle senkron tutuluyor (Vercel
rewrite'lari /index.html ve / rotalarini index.min.html'e yonlendiriyor,
ama JS/CSS dosyalari tarayiciya dogrudan /static/app.min.js olarak
gidiyor). Gecmiste bu ikisi birbirinden sapinca (once app.js duzeltilip
app.min.js unutulunca) canliya yansimayan sessiz bug'lar olustu -- bu
script tam olarak o senaryoyu yakalamak icin var.

Kullanim:
    python scripts/check_js_sync.py
    (Fark varsa exit code 1 doner, diff'i yazdirir.)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "public" / "static"

# (kaynak, "min" kopyasi) -- ikisi birebir ayni olmali
PAIRS = [
    (STATIC / "app.js", STATIC / "app.min.js"),
    (STATIC / "index.html", STATIC / "index.min.html"),
]


def check_pair(src: Path, dup: Path) -> bool:
    if not src.exists() or not dup.exists():
        print(f"[SKIP] {src.name} veya {dup.name} bulunamadi")
        return True

    src_bytes = src.read_bytes()
    dup_bytes = dup.read_bytes()

    if src_bytes == dup_bytes:
        print(f"[OK]   {src.name} == {dup.name} (birebir ayni)")
        return True

    print(f"[FAIL] {src.name} != {dup.name} -- senkron degil!")
    # Ilk farkli satiri bulup goster (hizli teshis icin)
    src_lines = src_bytes.decode("utf-8", errors="replace").splitlines()
    dup_lines = dup_bytes.decode("utf-8", errors="replace").splitlines()
    for i, (a, b) in enumerate(zip(src_lines, dup_lines)):
        if a != b:
            print(f"       ilk fark satir {i + 1}:")
            print(f"       {src.name}: {a[:120]}")
            print(f"       {dup.name}: {b[:120]}")
            break
    else:
        print(f"       dosya uzunluklari farkli ({len(src_lines)} vs {len(dup_lines)} satir)")
    return False


def main() -> int:
    ok = True
    for src, dup in PAIRS:
        if not check_pair(src, dup):
            ok = False
    if not ok:
        print("\nSonuc: FAIL -- min kopyalarini kaynaktan yeniden kopyalayin (cp app.js app.min.js).")
        return 1
    print("\nSonuc: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
