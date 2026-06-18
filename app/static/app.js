/**
 * Almadan — Minimal Frontend
 * Tek sorumluluk: Ara / Barkod Tarat / Sonuçları Göster / Takip Et
 */

/* ── Yardımcılar ──────────────────────────────────────────────── */

const currency = new Intl.NumberFormat("tr-TR", {
  style: "currency", currency: "TRY", maximumFractionDigits: 2,
});

function fmt(price) {
  const n = parseFloat(price);
  return isNaN(n) ? "—" : currency.format(n);
}

function toast(msg, duration = 2800) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), duration);
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── State ────────────────────────────────────────────────────── */

const state = {
  watchlist: JSON.parse(localStorage.getItem("almadan_watchlist") || "[]"),
  lastResults: [],
  lastQuery: "",
};

function saveWatchlist() {
  localStorage.setItem("almadan_watchlist", JSON.stringify(state.watchlist));
}

/* ── View Router ──────────────────────────────────────────────── */

function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  const el = document.getElementById("view-" + name);
  if (el) el.classList.add("active");
  if (name === "tracking")  renderTracking();
  if (name === "bulletins") loadStores();
  if (name === "savings")   renderSavings();
}

document.querySelectorAll("[data-view]").forEach(btn => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

/* ── Arama ────────────────────────────────────────────────────── */

const searchInput = document.getElementById("searchInput");
const searchBtn   = document.getElementById("searchBtn");
const resultsArea = document.getElementById("resultsArea");

async function runSearch(query) {
  query = query.trim();
  if (!query) return;
  state.lastQuery = query;

  showResults({ loading: true });

  try {
    // Link mi, ürün adı mı?
    const isUrl = /^https?:\/\//i.test(query);
    let endpoint, payload;

    if (isUrl) {
      endpoint = "/api/track";
      payload  = { url: query };
    } else {
      // Link değil: yine de ürün adıyla dene
      endpoint = "/api/search";
      payload  = { query, category: "general" };
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Sunucu hatası (${res.status})`);
    }

    const data = await res.json();
    state.lastResults = data.results || (data.title ? [data] : []);
    showResults({ data, query });

  } catch (err) {
    showResults({ error: err.message, query });
  }
}

searchBtn.addEventListener("click", () => runSearch(searchInput.value));
searchInput.addEventListener("keydown", e => {
  if (e.key === "Enter") runSearch(searchInput.value);
});

/* ── Sonuç Renderer ───────────────────────────────────────────── */

function showResults({ loading, data, error, query, barcodeTitle }) {
  resultsArea.style.display = "block";
  resultsArea.scrollIntoView({ behavior: "smooth", block: "start" });

  if (loading) {
    resultsArea.innerHTML = `
      <div class="results-area">
        <div class="loading-row">
          <span class="spinner"></span>
          <span>Fiyatlar taranıyor…</span>
        </div>
      </div>`;
    return;
  }

  if (error) {
    resultsArea.innerHTML = `
      <div class="result-msg error">
        <strong>Hata:</strong> ${esc(error)}<br>
        <small style="margin-top:6px;display:block;">Ürün linkini doğrudan yapıştırmayı deneyin.</small>
      </div>`;
    return;
  }

  // Barkod "found: false" durumu
  if (data && data.found === false) {
    resultsArea.innerHTML = `
      <div class="result-msg error">
        <strong>${esc(data.barcode_title ? `"${data.barcode_title}" —` : "")} Güvenilir eşleşme bulunamadı.</strong><br>
        ${esc(data.message || "Lütfen ürün linkini yapıştırın.")}
      </div>`;
    return;
  }

  const results = data?.results ?? state.lastResults;

  if (!results.length) {
    resultsArea.innerHTML = `
      <div class="result-msg info">
        "<strong>${esc(query || state.lastQuery)}</strong>" için sonuç bulunamadı.
        Farklı bir arama terimi deneyin ya da ürün linkini yapıştırın.
      </div>`;
    return;
  }

  const barcodeInfo = barcodeTitle
    ? `<span style="margin-left:8px;" class="match-badge">Barkod: ${esc(barcodeTitle)}</span>`
    : "";

  const cards = results.map(r => {
    const price = r.price ?? r.current_price ?? r.price_value;
    const img   = r.image_url || r.image || "";
    const store = r.store || r.source || "";
    const title = r.title || r.name || "";
    const url   = r.url || r.product_url || "#";
    const score = r._match_score ? `<div class="card-score">Eşleşme: ${(r._match_score * 100).toFixed(0)}%</div>` : "";

    const imgEl = img
      ? `<img src="${esc(img)}" alt="${esc(title)}" loading="lazy" onerror="this.parentNode.innerHTML='<div class=card-no-img>📦</div>'">`
      : `<div class="card-no-img">📦</div>`;

    return `
      <a class="product-card" href="${esc(url)}" target="_blank" rel="noopener"
         data-title="${esc(title)}" data-price="${esc(price ?? "")}" data-store="${esc(store)}" data-url="${esc(url)}">
        ${imgEl}
        <div class="card-store">${esc(store)}</div>
        <div class="card-title">${esc(title)}</div>
        <div class="card-price">${price != null ? fmt(price) : "Fiyat yok"}</div>
        ${score}
        <button class="btn-sm" style="margin-top:4px;" onclick="addToWatchlist(event, this)">+ Takibe Al</button>
      </a>`;
  }).join("");

  resultsArea.innerHTML = `
    <div class="results-header">
      <span class="results-title">${results.length} sonuç${barcodeInfo}</span>
      <span class="results-meta">${esc(query || state.lastQuery)}</span>
    </div>
    <div class="product-grid">${cards}</div>`;
}

/* ── Takip ────────────────────────────────────────────────────── */

function addToWatchlist(event, btn) {
  event.preventDefault();
  event.stopPropagation();
  const card  = btn.closest(".product-card");
  const item  = {
    id:    Date.now(),
    title: card.dataset.title,
    price: parseFloat(card.dataset.price) || null,
    store: card.dataset.store,
    url:   card.dataset.url,
    addedAt: new Date().toISOString(),
  };
  if (state.watchlist.some(w => w.url === item.url && w.title === item.title)) {
    toast("Zaten takip listesinde.");
    return;
  }
  state.watchlist.unshift(item);
  saveWatchlist();
  toast("Takip listesine eklendi ✓");
  btn.textContent = "✓ Eklendi";
  btn.disabled = true;
}

function removeFromWatchlist(id) {
  state.watchlist = state.watchlist.filter(w => w.id !== id);
  saveWatchlist();
  renderTracking();
}

/* ── Hatırlatıcı Hesaplama (saf, sıfır API) ─────────────────── */

function calcReminderDates(lastPurchaseDate, reorderDays, remindBeforeDays) {
  const purchase     = new Date(lastPurchaseDate);
  const endDate      = new Date(purchase);
  endDate.setDate(endDate.getDate() + Number(reorderDays));

  const reminderDate = new Date(endDate);
  reminderDate.setDate(reminderDate.getDate() - Number(remindBeforeDays));

  const today     = new Date();
  today.setHours(0, 0, 0, 0);
  const daysLeft  = Math.round((endDate - today) / 86400000);

  const fmtDate = d => d.toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" });

  return {
    endDateStr:      fmtDate(endDate),
    reminderDateStr: fmtDate(reminderDate),
    daysLeft,
  };
}

function onReminderInput(itemId) {
  const form       = document.getElementById(`rform-${itemId}`);
  const resultEl   = document.getElementById(`rresult-${itemId}`);
  const dateInput  = form.querySelector(".r-date");
  const daysInput  = form.querySelector(".r-days");
  const beforeInput= form.querySelector(".r-before");

  if (!dateInput.value || !daysInput.value) { resultEl.classList.remove("show"); return; }

  const { endDateStr, daysLeft } = calcReminderDates(
    dateInput.value, daysInput.value, beforeInput.value || 5
  );

  resultEl.textContent = daysLeft >= 0
    ? `📅 Ürün yaklaşık ${endDateStr} tarihinde biter — ${daysLeft} gün kaldı.`
    : `⚠️ Tahmini bitiş tarihi (${endDateStr}) geçti.`;
  resultEl.classList.add("show");
}

async function saveReminder(itemId) {
  const form        = document.getElementById(`rform-${itemId}`);
  const item        = state.watchlist.find(w => w.id === itemId);
  const dateInput   = form.querySelector(".r-date");
  const daysInput   = form.querySelector(".r-days");
  const beforeInput = form.querySelector(".r-before");
  const saveBtn     = form.querySelector(".btn-reminder-save");

  if (!dateInput.value || !daysInput.value) { toast("Tarih ve periyot alanlarını doldur."); return; }

  saveBtn.disabled = true;
  saveBtn.textContent = "Kaydediliyor…";

  try {
    const res = await fetch("/api/reminders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_url:        item.url,
        product_title:      item.title,
        last_purchase_date: dateInput.value,
        reorder_days:       Number(daysInput.value),
        remind_before_days: Number(beforeInput.value || 5),
      }),
    });

    if (res.status === 401) { toast("Hatırlatıcı için giriş yapman gerekiyor."); return; }
    if (!res.ok) throw new Error(await res.text());

    toast("Hatırlatıcı kaydedildi ✓");
    form.classList.remove("open");
    saveBtn.textContent = "✓ Kaydedildi";
  } catch {
    toast("Kaydedilemedi — giriş yapmadan yerel olarak tutuldu.");
    // Giriş yoksa locale kaydet
    const local = JSON.parse(localStorage.getItem("almadan_reminders") || "[]");
    local.push({
      itemId, url: item.url, title: item.title,
      lastPurchaseDate: dateInput.value,
      reorderDays: Number(daysInput.value),
      remindBeforeDays: Number(beforeInput.value || 5),
      savedAt: new Date().toISOString(),
    });
    localStorage.setItem("almadan_reminders", JSON.stringify(local));
    saveBtn.textContent = "✓ Yerel kaydedildi";
  } finally {
    saveBtn.disabled = false;
  }
}

function toggleReminderForm(itemId) {
  const form = document.getElementById(`rform-${itemId}`);
  form.classList.toggle("open");
}

function renderTracking() {
  const list = document.getElementById("trackingList");
  if (!list) return;
  if (!state.watchlist.length) {
    list.innerHTML = `<p class="empty-state">Henüz takip edilen ürün yok.<br>Arama sonuçlarında "Takibe Al" butonunu kullan.</p>`;
    return;
  }
  list.innerHTML = state.watchlist.map(w => `
    <div class="tracking-item" style="flex-direction:column;align-items:stretch;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div class="tracking-info">
          <div class="tracking-name">${esc(w.title)}</div>
          <div class="tracking-price">${w.store ? esc(w.store) + " · " : ""}${w.price != null ? fmt(w.price) : "Fiyat yok"}</div>
        </div>
        <a class="btn-sm" href="${esc(w.url)}" target="_blank" rel="noopener" style="white-space:nowrap;">Görüntüle</a>
        <button class="btn-danger-sm" onclick="removeFromWatchlist(${w.id})">Kaldır</button>
      </div>

      <button class="reminder-toggle" onclick="toggleReminderForm(${w.id})">
        ⏰ Hatırlatıcı kur
      </button>

      <div class="reminder-form" id="rform-${w.id}">
        <div class="reminder-row">
          <div class="reminder-field">
            <label>Son Satın Alma Tarihi</label>
            <input class="r-date" type="date" oninput="onReminderInput(${w.id})">
          </div>
          <div class="reminder-field">
            <label>Tekrar Alma Periyodu (gün)</label>
            <input class="r-days" type="number" min="1" max="365" placeholder="30" oninput="onReminderInput(${w.id})">
          </div>
          <div class="reminder-field" style="max-width:110px;">
            <label>Kaç gün önce</label>
            <input class="r-before" type="number" min="0" max="30" placeholder="5" oninput="onReminderInput(${w.id})">
          </div>
        </div>
        <div class="reminder-result" id="rresult-${w.id}"></div>
        <button class="btn-reminder-save" onclick="saveReminder(${w.id})" style="margin-top:8px;">
          Hatırlatıcıyı Kaydet
        </button>
      </div>
    </div>`).join("");
}

/* ── Tasarruf özeti ───────────────────────────────────────────── */

function renderSavings() {
  const total   = document.getElementById("savTotal");
  const tracked = document.getElementById("savTracked");
  const buy     = document.getElementById("savBuy");
  if (!total) return;
  // İleride /api/dashboard/savings'ten çekilecek; şimdilik yerel
  tracked.textContent = state.watchlist.length;
  total.textContent   = "₺0";
  buy.textContent     = "0";
}

/* ── Barkod Tarayıcı ─────────────────────────────────────────── */

const barcodeToggleBtn = document.getElementById("barcodeToggleBtn");
const stopScanBtn      = document.getElementById("stopScanBtn");
const scannerWrapper   = document.getElementById("scannerWrapper");
const scanStatus       = document.getElementById("scanStatus");

let scanner = null;

async function startScanner() {
  scannerWrapper.style.display = "block";
  scanStatus.textContent = "Kamera başlatılıyor…";

  if (scanner) {
    try { await scanner.stop(); } catch (_) {}
    scanner = null;
  }

  scanner = new Html5Qrcode("html5QrCodeReader");

  try {
    await scanner.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: { width: 240, height: 160 } },
      async code => {
        scanStatus.textContent = `Barkod okundu: ${code}`;
        await scanner.stop().catch(() => {});
        scanner = null;
        scannerWrapper.style.display = "none";
        await lookupBarcode(code);
      },
      () => {} // hata yoksay
    );
    scanStatus.textContent = "Kamerayı barkoda doğrultun…";
  } catch (err) {
    scanStatus.textContent = "Kamera açılamadı: " + err.message;
  }
}

async function stopScanner() {
  if (scanner) {
    try { await scanner.stop(); } catch (_) {}
    scanner = null;
  }
  scannerWrapper.style.display = "none";
}

barcodeToggleBtn.addEventListener("click", () => {
  if (scannerWrapper.style.display === "none" || !scannerWrapper.style.display) {
    startScanner();
  } else {
    stopScanner();
  }
});

stopScanBtn.addEventListener("click", stopScanner);

/* ── Barkod → API ─────────────────────────────────────────────── */

async function lookupBarcode(code) {
  toast(`Barkod sorgulanıyor: ${code}…`);
  showResults({ loading: true });

  try {
    const res  = await fetch(`/api/barcode/${encodeURIComponent(code)}`);
    const data = await res.json();

    if (!res.ok || data.found === false) {
      showResults({
        data,
        query: code,
        barcodeTitle: data.barcode_title || null,
      });
      return;
    }

    state.lastResults = data.results || [];
    showResults({
      data,
      query: data.search_query || code,
      barcodeTitle: data.title,
    });
  } catch (err) {
    showResults({ error: err.message, query: code });
  }
}

/* ── Mağaza Bültenleri ────────────────────────────────────────── */

const STORE_EMOJIS = {
  market: "🛒", fashion: "👗", beauty: "💄", home: "🏠",
};

// Takip durumunu hafızada tut (API çağrısı olmadan anında toggle)
const storeFollowState = {};

async function loadStores() {
  const list = document.getElementById("storeList");
  if (!list) return;

  try {
    const res  = await fetch("/api/stores");
    const data = await res.json();
    const stores = data.stores || [];

    if (!stores.length) {
      list.innerHTML = `<p class="empty-state">Henüz mağaza eklenmemiş.</p>`;
      return;
    }

    // Kategoriye göre grupla
    const groups = {};
    stores.forEach(s => {
      const cat = s.category || "other";
      (groups[cat] = groups[cat] || []).push(s);
      storeFollowState[s.slug] = s.followed;
    });

    const CAT_LABELS = { market: "Marketler", fashion: "Moda", beauty: "Güzellik & Kozmetik", home: "Ev & Yaşam" };
    const catOrder   = ["market", "fashion", "beauty", "home"];

    let html = "";
    catOrder.forEach(cat => {
      if (!groups[cat]?.length) return;
      html += `<div class="store-section-title">${CAT_LABELS[cat] || cat}</div>`;
      html += `<div class="store-grid">`;
      html += groups[cat].map(s => renderStoreCard(s)).join("");
      html += `</div>`;
    });

    list.innerHTML = html;
  } catch {
    list.innerHTML = `<p class="empty-state">Mağazalar yüklenemedi. Tekrar dene.</p>`;
  }
}

function renderStoreCard(s) {
  const followed = storeFollowState[s.slug];
  const emoji    = STORE_EMOJIS[s.category] || "🏪";
  return `
    <div class="store-card ${followed ? "followed" : ""}" id="scard-${s.slug}">
      <div class="store-card-header">
        <span class="store-emoji">${emoji}</span>
        <div>
          <div class="store-name">${esc(s.name)}</div>
          <div class="store-cat">${esc(s.category)}</div>
        </div>
      </div>
      ${s.publication_note ? `<div class="store-note">📅 ${esc(s.publication_note)}</div>` : ""}
      <button
        class="btn-follow ${followed ? "active" : ""}"
        onclick="toggleFollow('${s.slug}', '${esc(s.name)}')"
        id="sfbtn-${s.slug}"
      >${followed ? "✓ Takip Ediliyor" : "+ Takibe Al"}</button>
    </div>`;
}

async function toggleFollow(slug, name) {
  const btn  = document.getElementById(`sfbtn-${slug}`);
  const card = document.getElementById(`scard-${slug}`);
  const isFollowed = storeFollowState[slug];

  // Anında UI güncelle (optimistic)
  storeFollowState[slug] = !isFollowed;
  btn.textContent  = isFollowed ? "+ Takibe Al" : "✓ Takip Ediliyor";
  btn.classList.toggle("active", !isFollowed);
  card.classList.toggle("followed", !isFollowed);

  try {
    const method = isFollowed ? "DELETE" : "POST";
    const res    = await fetch(`/api/stores/${slug}/follow`, { method });
    if (res.status === 401) {
      toast("Takip için giriş yapman gerekiyor.");
      // Geri al
      storeFollowState[slug] = isFollowed;
      btn.textContent  = isFollowed ? "✓ Takip Ediliyor" : "+ Takibe Al";
      btn.classList.toggle("active", isFollowed);
      card.classList.toggle("followed", isFollowed);
      return;
    }
    toast(isFollowed ? `${name} takipten çıkarıldı.` : `${name} takibe alındı ✓`);
  } catch {
    toast("Bağlantı hatası, tekrar dene.");
  }
}

/* ── "Link nasıl kopyalanır?" Pop-up ─────────────────────────── */

const linkHelpOverlay = document.getElementById("linkHelpOverlay");

function openLinkHelp() {
  linkHelpOverlay.classList.add("open");
  document.getElementById("linkHelpClose").focus();
}

function closeLinkHelp() {
  linkHelpOverlay.classList.remove("open");
}

document.getElementById("linkHelpBtn").addEventListener("click", openLinkHelp);
document.getElementById("linkHelpClose").addEventListener("click", closeLinkHelp);

// Overlay'e (arka plan) tıklayınca kapat
linkHelpOverlay.addEventListener("click", e => {
  if (e.target === linkHelpOverlay) closeLinkHelp();
});

// ESC tuşuyla kapat
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && linkHelpOverlay.classList.contains("open")) closeLinkHelp();
});

/* ── Hesap butonu (basit) ─────────────────────────────────────── */

document.getElementById("accountBtn")?.addEventListener("click", () => {
  toast("Hesap özelliği yakında.");
});
document.getElementById("notifBtn")?.addEventListener("click", () => {
  toast("Bildirimler yakında.");
});

/* ── Service Worker ───────────────────────────────────────────── */

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/sw.js").catch(() => {});
}

/* ── Init ─────────────────────────────────────────────────────── */

showView("search");
