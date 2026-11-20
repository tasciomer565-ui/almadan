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
    position: fixed; top: 20px; right: 20px; background: #ffffff; color: #141715; border: 1px solid #e6e4dd;
    padding: 16px 18px; border-radius: 14px; z-index: 999999; box-shadow: 0 14px 36px rgba(20,23,21,0.16);
    font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, sans-serif; max-width: 310px;
  `;
  const priceText = cheapestAlt.price.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  div.innerHTML = `
    <div style="font-weight: 800; color: #1b5e3f; font-size: 13px; margin-bottom: 6px;">Almadan Fiyat Uyarısı</div>
    <div style="font-size: 13px; line-height: 1.45; margin-bottom: 12px; color: #141715;">Bu ürünü <b>${cheapestAlt.source}</b> üzerinde <b style="color: #1b5e3f;">₺${priceText}</b> fiyatıyla bulduk.</div>
    <div style="display: flex; gap: 8px;">
      <button id="almadan-popup-close" style="background: #faf9f6; color: #5e6460; border: 1px solid #e6e4dd; border-radius: 8px; padding: 7px 12px; cursor: pointer; font-weight: 600;">Kapat</button>
      <a href="${cheapestAlt.url}" target="_blank" rel="noopener" style="background: #1b5e3f; color: #ffffff; text-decoration: none; border-radius: 8px; padding: 7px 14px; font-weight: 700;">Mağazaya Git</a>
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
