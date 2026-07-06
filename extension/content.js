// Almadan Tarayıcı Eklentisi - Content Script
// 2026-07-06: domain, selector'lar ve CORS/CSRF entegrasyonu güncellendi.

const ALMADAN_API_URL = "https://www.almadan.app/api/find-alternatives";

function extractProductInfo() {
  let title = "";
  let price = 0;
  const host = window.location.hostname;

  if (host.includes("trendyol.com")) {
    const titleEl = document.querySelector("h1.product-title") || document.querySelector("h1");
    const priceEl = document.querySelector("[class*='price-current-price']");
    if (titleEl) title = titleEl.innerText;
    if (priceEl) price = parseFloat(priceEl.innerText.replace(" TL", "").replace(/\./g, "").replace(",", "."));
  } else if (host.includes("hepsiburada.com")) {
    const titleEl = document.querySelector("h1");
    const priceEl = document.querySelector("[data-test-id='price-current-price']");
    if (titleEl) title = titleEl.innerText;
    if (priceEl) price = parseFloat(priceEl.innerText.replace(/\./g, "").replace(",", "."));
  } else if (host.includes("amazon.com.tr")) {
    const titleEl = document.querySelector("#productTitle");
    const priceEl = document.querySelector(".a-price .a-offscreen");
    if (titleEl) title = titleEl.innerText;
    if (priceEl) price = parseFloat(priceEl.innerText.replace("TL", "").replace(/\s/g, "").replace(/\./g, "").replace(",", "."));
  }

  return { title: title.trim(), price };
}

function showAlmadanPopup(cheapestAlt) {
  if (document.getElementById("almadan-popup")) return;
  const div = document.createElement("div");
  div.id = "almadan-popup";
  div.style.cssText = `
    position: fixed; top: 20px; right: 20px; background: #121412; color: #fff; border: 1px solid #287a50;
    padding: 16px; border-radius: 12px; z-index: 999999; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    font-family: sans-serif; max-width: 300px;
  `;
  const priceText = cheapestAlt.price.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  div.innerHTML = `
    <div style="font-weight: bold; color: #c8d94a; margin-bottom: 8px;">🛒 Almadan Uyarıyor!</div>
    <div style="font-size: 13px; margin-bottom: 12px;">Bu ürünü <b>${cheapestAlt.source}</b> üzerinden <b style="color: #00e676;">₺${priceText}</b> fiyatına alabilirsiniz!</div>
    <div style="display: flex; gap: 8px;">
      <button id="almadan-popup-close" style="background: transparent; color: #888; border: 1px solid #444; border-radius: 6px; padding: 6px 12px; cursor: pointer;">Kapat</button>
      <a href="${cheapestAlt.url}" target="_blank" rel="noopener" style="background: #287a50; color: #fff; text-decoration: none; border-radius: 6px; padding: 6px 12px; font-weight: bold;">Oraya Git</a>
    </div>
  `;
  document.body.appendChild(div);
  document.getElementById("almadan-popup-close").addEventListener("click", () => div.remove());
}

setTimeout(async () => {
  const { title, price } = extractProductInfo();
  if (!title || price <= 0) return;
  try {
    const response = await fetch(ALMADAN_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, original_url: window.location.href }),
    });
    if (!response.ok) return;
    const data = await response.json();
    const alts = (data.alternatives || []).filter((a) => a.price > 0);
    if (!alts.length) return;
    const cheapest = alts.reduce((min, p) => (p.price < min.price ? p : min), alts[0]);
    if (cheapest.price < price) {
      showAlmadanPopup(cheapest);
    }
  } catch (e) {
    console.log("Almadan eklentisi API'ye bağlanamadı:", e);
  }
}, 3000);
