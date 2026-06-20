// Almadan Tarayıcı Eklentisi - Content Script

const ALMADAN_API_URL = "https://almadan.vercel.app/api/find-alternatives"; // Canlıya çıkınca asıl domain eklenecek.

function extractProductInfo() {
  let title = "";
  let price = 0;
  const host = window.location.hostname;

  if (host.includes("trendyol.com")) {
    const titleEl = document.querySelector("h1.pr-new-br span");
    const priceEl = document.querySelector(".prc-dsc");
    if (titleEl) title = titleEl.innerText;
    if (priceEl) price = parseFloat(priceEl.innerText.replace(" TL", "").replace(".", "").replace(",", "."));
  } else if (host.includes("hepsiburada.com")) {
    const titleEl = document.querySelector("h1#product-name");
    const priceEl = document.querySelector("[data-test-id='price-current-price']");
    if (titleEl) title = titleEl.innerText;
    if (priceEl) price = parseFloat(priceEl.innerText.replace(".", "").replace(",", "."));
  } else if (host.includes("amazon.com.tr")) {
    const titleEl = document.querySelector("#productTitle");
    const priceEl = document.querySelector(".a-price .a-offscreen");
    if (titleEl) title = titleEl.innerText;
    if (priceEl) price = parseFloat(priceEl.innerText.replace("TL", "").replace(/\s/g, "").replace(".", "").replace(",", "."));
  }

  return { title, price };
}

function showAlmadanPopup(cheapestAlt) {
  const div = document.createElement("div");
  div.style.cssText = `
    position: fixed; top: 20px; right: 20px; background: #121412; color: #fff; border: 1px solid #287a50; 
    padding: 16px; border-radius: 12px; z-index: 999999; box-shadow: 0 10px 30px rgba(0,0,0,0.5); font-family: sans-serif;
  `;
  div.innerHTML = `
    <div style="font-weight: bold; color: #00e676; margin-bottom: 8px;">🛒 Almadan Uyarıyor!</div>
    <div style="font-size: 13px; margin-bottom: 12px;">Bu ürünü <b>${cheapestAlt.source}</b> üzerinden <b style="color: #00e676;">₺${cheapestAlt.price.toFixed(2)}</b> fiyatına alabilirsiniz!</div>
    <div style="display: flex; gap: 8px;">
      <button onclick="this.parentElement.parentElement.remove()" style="background: transparent; color: #888; border: 1px solid #444; border-radius: 6px; padding: 6px 12px; cursor: pointer;">Kapat</button>
      <a href="${cheapestAlt.url}" target="_blank" style="background: #287a50; color: #fff; text-decoration: none; border-radius: 6px; padding: 6px 12px; font-weight: bold;">Oraya Git</a>
    </div>
  `;
  document.body.appendChild(div);
}

setTimeout(async () => {
  const { title, price } = extractProductInfo();
  if (title && price > 0) {
    try {
      const response = await fetch(ALMADAN_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title, original_url: window.location.href })
      });
      const data = await response.json();
      if (data.alternatives && data.alternatives.length > 0) {
        const cheapest = data.alternatives.reduce((min, p) => p.price < min.price ? p : min, data.alternatives[0]);
        if (cheapest.price < price) {
          showAlmadanPopup(cheapest);
        }
      }
    } catch (e) {
      console.log("Almadan eklentisi apiye bağlanamadı:", e);
    }
  }
}, 3000); // Sayfa yüklendikten 3 saniye sonra tarama yapar
