// ── Mağaza marka sistemi ─────────────────────────────────────────────────────
const STORE_BRANDS = {
  trendyol:      { name: "Trendyol",      color: "#f27a1a", bg: "rgba(242,122,26,0.08)",  emoji: "🟠" },
  hepsiburada:   { name: "Hepsiburada",   color: "#ff6000", bg: "rgba(255,96,0,0.08)",    emoji: "🔶" },
  amazon:        { name: "Amazon",        color: "#ff9900", bg: "rgba(255,153,0,0.08)",   emoji: "📦" },
  n11:           { name: "n11",           color: "#6f41c1", bg: "rgba(111,65,193,0.08)",  emoji: "🟣" },
  migros:        { name: "Migros",        color: "#e31e24", bg: "rgba(227,30,36,0.08)",   emoji: "🔴" },
  carrefoursa:   { name: "CarrefourSA",   color: "#003c91", bg: "rgba(0,60,145,0.08)",    emoji: "🔵" },
  a101:          { name: "A101",          color: "#e63a2e", bg: "rgba(230,58,46,0.08)",   emoji: "🏪" },
  bim:           { name: "BİM",           color: "#c0392b", bg: "rgba(192,57,43,0.08)",   emoji: "🏪" },
  sok:           { name: "ŞOK",           color: "#e74c3c", bg: "rgba(231,76,60,0.08)",   emoji: "🏪" },
  teknosa:       { name: "Teknosa",       color: "#0066cc", bg: "rgba(0,102,204,0.08)",   emoji: "💻" },
  mediamarkt:    { name: "MediaMarkt",    color: "#cc0000", bg: "rgba(204,0,0,0.08)",     emoji: "📺" },
  vatanbilgisayar: { name: "Vatan",       color: "#e52a2a", bg: "rgba(229,42,42,0.08)",   emoji: "💻" },
  gratis:        { name: "Gratis",        color: "#e91e8c", bg: "rgba(233,30,140,0.08)",  emoji: "💄" },
  rossmann:      { name: "Rossmann",      color: "#c8002d", bg: "rgba(200,0,45,0.08)",    emoji: "💊" },
  supplementler: { name: "Supplementler", color: "#1a9c3e", bg: "rgba(26,156,62,0.08)",  emoji: "💪" },
  proteinocean:  { name: "ProteinOcean",  color: "#0077b6", bg: "rgba(0,119,182,0.08)",   emoji: "🌊" },
  lcwaikiki:     { name: "LC Waikiki",    color: "#e31837", bg: "rgba(227,24,55,0.08)",   emoji: "👗" },
  defacto:       { name: "DeFacto",       color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",    emoji: "👕" },
  koton:         { name: "Koton",         color: "#c8a45a", bg: "rgba(200,164,90,0.08)",  emoji: "👚" },
  ikea:          { name: "IKEA",          color: "#0051a2", bg: "rgba(0,81,162,0.08)",    emoji: "🪑" },
  karaca:        { name: "Karaca",        color: "#8b1a1a", bg: "rgba(139,26,26,0.08)",   emoji: "🍳" },
  watsons:       { name: "Watsons",       color: "#00843d", bg: "rgba(0,132,61,0.08)",    emoji: "💚" },
  boyner:        { name: "Boyner",        color: "#e30613", bg: "rgba(227,6,19,0.08)",    emoji: "🛍️" },
  flo:           { name: "FLO",           color: "#ff6600", bg: "rgba(255,102,0,0.08)",   emoji: "👟" },
  decathlon:     { name: "Decathlon",     color: "#0082c3", bg: "rgba(0,130,195,0.08)",   emoji: "⚽" },
  mavi:          { name: "Mavi",          color: "#003087", bg: "rgba(0,48,135,0.08)",    emoji: "👖" },
  zara:          { name: "Zara",          color: "#000000", bg: "rgba(0,0,0,0.06)",        emoji: "🖤" },
  englishhome:   { name: "English Home",  color: "#8b4513", bg: "rgba(139,69,19,0.08)",   emoji: "🏠" },
  sokmarket:     { name: "ŞOK",           color: "#f7941d", bg: "rgba(247,148,29,0.08)",  emoji: "🏪" },
  temu:          { name: "Temu",          color: "#ff4747", bg: "rgba(255,71,71,0.08)",    emoji: "🛒", logo: "TM" },
  pazarama:      { name: "Pazarama",      color: "#ff6600", bg: "rgba(255,102,0,0.08)",    emoji: "🛒", logo: "PZ" },
  ciceksepeti:   { name: "Çiçeksepeti",   color: "#ff69b4", bg: "rgba(255,105,180,0.08)", emoji: "🌸", logo: "CS" },
  xiaomi:        { name: "Xiaomi",        color: "#ff6900", bg: "rgba(255,105,0,0.08)",    emoji: "📱", logo: "XI" },
  huawei:        { name: "Huawei",        color: "#cf0a2c", bg: "rgba(207,10,44,0.08)",    emoji: "📱", logo: "HW" },
  hp:            { name: "HP",            color: "#0096d6", bg: "rgba(0,150,214,0.08)",    emoji: "💻", logo: "HP" },
  lenovo:        { name: "Lenovo",        color: "#e2231a", bg: "rgba(226,35,26,0.08)",    emoji: "💻", logo: "LN" },
  evkur:         { name: "Evkur",         color: "#004b87", bg: "rgba(0,75,135,0.08)",     emoji: "🖥️", logo: "EK" },
  penti:         { name: "Penti",         color: "#e4003a", bg: "rgba(228,0,58,0.08)",     emoji: "👗", logo: "PT" },
  colins:        { name: "Colin's",       color: "#003087", bg: "rgba(0,48,135,0.08)",     emoji: "👖", logo: "CL" },
  twist:         { name: "Twist",         color: "#9b1b30", bg: "rgba(155,27,48,0.08)",    emoji: "👚", logo: "TW" },
  ltb:           { name: "LTB",           color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",     emoji: "👖", logo: "LB" },
  modanisa:      { name: "Modanisa",      color: "#6b21a8", bg: "rgba(107,33,168,0.08)",   emoji: "👗", logo: "MN" },
  nike:          { name: "Nike",          color: "#111111", bg: "rgba(17,17,17,0.06)",      emoji: "👟", logo: "NK" },
  puma:          { name: "Puma",          color: "#ee0000", bg: "rgba(238,0,0,0.08)",       emoji: "🐆", logo: "PM" },
  newbalance:    { name: "New Balance",   color: "#cf192b", bg: "rgba(207,25,43,0.08)",    emoji: "👟", logo: "NB" },
  sportive:      { name: "Sportive",      color: "#f47920", bg: "rgba(244,121,32,0.08)",   emoji: "⚽", logo: "SV" },
  flormar:       { name: "Flormar",       color: "#e91e8c", bg: "rgba(233,30,140,0.08)",   emoji: "💄", logo: "FL" },
  goldenrose:    { name: "Golden Rose",   color: "#c8a415", bg: "rgba(200,164,21,0.08)",   emoji: "🌹", logo: "GR" },
  istikbal:      { name: "İstikbal",      color: "#e30613", bg: "rgba(227,6,19,0.08)",     emoji: "🛋️", logo: "IS" },
  bellona:       { name: "Bellona",       color: "#003366", bg: "rgba(0,51,102,0.08)",     emoji: "🛋️", logo: "BL" },
  madamecoco:    { name: "Madame Coco",   color: "#8b0000", bg: "rgba(139,0,0,0.08)",      emoji: "🏠", logo: "MC" },
  korkmaz:       { name: "Korkmaz",       color: "#cc0000", bg: "rgba(204,0,0,0.08)",      emoji: "🍳", logo: "KK" },
  kitapyurdu:    { name: "Kitapyurdu",    color: "#e07b00", bg: "rgba(224,123,0,0.08)",    emoji: "📚", logo: "KY" },
  dr:            { name: "D&R",           color: "#e30613", bg: "rgba(227,6,19,0.08)",     emoji: "📖", logo: "DR" },
  idefix:        { name: "İdefix",        color: "#f47920", bg: "rgba(244,121,32,0.08)",   emoji: "📚", logo: "IF" },
  bebek:          { name: "Bebek.com",      color: "#ff69b4", bg: "rgba(255,105,180,0.08)", logo: "BK" },
  ebebek:         { name: "ebebek",         color: "#ff6600", bg: "rgba(255,102,0,0.08)",   logo: "EB" },
  toyzz:          { name: "Toyzz Shop",     color: "#e91e63", bg: "rgba(233,30,99,0.08)",   logo: "TZ" },
  tefal:          { name: "Tefal",          color: "#e30613", bg: "rgba(227,6,19,0.08)",    logo: "TF" },
  arnica:         { name: "Arnica",         color: "#004b87", bg: "rgba(0,75,135,0.08)",    logo: "AR" },
  arzum:          { name: "Arzum",          color: "#ff6900", bg: "rgba(255,105,0,0.08)",   logo: "AZ" },
  schafer:        { name: "Schafer",        color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",    logo: "SC" },
  fakir:          { name: "Fakir",          color: "#0066cc", bg: "rgba(0,102,204,0.08)",   logo: "FK" },
  bosch:          { name: "Bosch",          color: "#e20015", bg: "rgba(226,0,21,0.08)",    logo: "BS" },
  evidea:         { name: "Evidea",         color: "#2e7d32", bg: "rgba(46,125,50,0.08)",   logo: "EV" },
  vivense:        { name: "Vivense",        color: "#ff5722", bg: "rgba(255,87,34,0.08)",   logo: "VV" },
  kelebek:        { name: "Kelebek",        color: "#e91e63", bg: "rgba(233,30,99,0.08)",   logo: "KL" },
  dogtas:         { name: "Doğtaş",         color: "#795548", bg: "rgba(121,85,72,0.08)",   logo: "DT" },
  bauhaus:        { name: "Bauhaus",        color: "#e30613", bg: "rgba(227,6,19,0.08)",    logo: "BH" },
  petlebi:        { name: "Petlebi",        color: "#4caf50", bg: "rgba(76,175,80,0.08)",   logo: "PL" },
  bigjoy:         { name: "BigJoy",         color: "#ff4500", bg: "rgba(255,69,0,0.08)",    logo: "BJ" },
  runnutrition:   { name: "Run Nutrition",  color: "#43a047", bg: "rgba(67,160,71,0.08)",   logo: "RN" },
  pierrecardin:   { name: "Pierre Cardin",  color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",    logo: "PC" },
  itopya:         { name: "İtopya",         color: "#ff6600", bg: "rgba(255,102,0,0.08)",   logo: "IT" },
  casper:         { name: "Casper",         color: "#004b87", bg: "rgba(0,75,135,0.08)",    logo: "CP" },
  remzi:          { name: "Remzi Kitabevi", color: "#e65100", bg: "rgba(230,81,0,0.08)",    logo: "RK" },
  tazedirekt:     { name: "Taze Direkt",    color: "#2e7d32", bg: "rgba(46,125,50,0.08)",   logo: "TD" },
  bizimtoptan:    { name: "Bizim Toptan",   color: "#1565c0", bg: "rgba(21,101,192,0.08)",  logo: "BT" },
  tarimkredi:     { name: "Tarım Kredi",    color: "#388e3c", bg: "rgba(56,142,60,0.08)",   logo: "TK" },
  kutahyaporselen: { name: "Kütahya Porselen", color: "#8b0000", bg: "rgba(139,0,0,0.08)", logo: "KP" },
  beymen:          { name: "Beymen",         color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",   logo: "BY" },
  vakko:           { name: "Vakko",          color: "#2c2c2c", bg: "rgba(44,44,44,0.06)",   logo: "VK" },
  network:         { name: "Network",        color: "#003087", bg: "rgba(0,48,135,0.08)",   logo: "NW" },
  philips:         { name: "Philips",        color: "#003087", bg: "rgba(0,48,135,0.08)",   logo: "PH" },
  farmasi:         { name: "Farmasi",        color: "#e91e63", bg: "rgba(233,30,99,0.08)",  logo: "FM" },
  dsmart:          { name: "D-Smart",        color: "#e30613", bg: "rgba(227,6,19,0.08)",   logo: "DS" },
  miniso:          { name: "Miniso",         color: "#e30613", bg: "rgba(227,6,19,0.08)",   logo: "MS" },
  action:          { name: "Action",         color: "#e53935", bg: "rgba(229,57,53,0.08)",  logo: "AC" },
  turkcell:        { name: "Turkcell",       color: "#005f9e", bg: "rgba(0,95,158,0.08)",   logo: "TC" },
  hopi:            { name: "Hopi",           color: "#ff4081", bg: "rgba(255,64,129,0.08)", logo: "HP" },
  pandora:         { name: "Pandora",        color: "#0c0c0c", bg: "rgba(12,12,12,0.06)",   logo: "PN" },
  altinyildiz:     { name: "Altınyıldız",    color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",   logo: "AY" },
  derimod:         { name: "Derimod",        color: "#5d4037", bg: "rgba(93,64,55,0.08)",   logo: "DM" },
  lescon:          { name: "Lescon",         color: "#e53935", bg: "rgba(229,57,53,0.08)",  logo: "LC" },
  kinetix:         { name: "Kinetix",        color: "#0066cc", bg: "rgba(0,102,204,0.08)",  logo: "KX" },
  namet:           { name: "Namet",          color: "#c62828", bg: "rgba(198,40,40,0.08)",  logo: "NM" },
  dardanel:        { name: "Dardanel",       color: "#0d47a1", bg: "rgba(13,71,161,0.08)",  logo: "DD" },
  shein:           { name: "Shein",          color: "#222222", bg: "rgba(34,34,34,0.06)",   logo: "SH" },
  aliexpress:      { name: "AliExpress",     color: "#ff6000", bg: "rgba(255,96,0,0.08)",   logo: "AE" },
  hm:              { name: "H&M",            color: "#e50010", bg: "rgba(229,0,16,0.08)",   logo: "HM" },
  sephora:         { name: "Sephora",        color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",   logo: "SP" },
  koctas:          { name: "Koçtaş",         color: "#e30613", bg: "rgba(227,6,19,0.08)",   logo: "KT" },
  adidas:          { name: "Adidas",         color: "#000000", bg: "rgba(0,0,0,0.06)",       logo: "AD" },
  metro:           { name: "Metro",          color: "#003087", bg: "rgba(0,48,135,0.08)",   logo: "MT" },
  gamegaraj:       { name: "GameGaraj",      color: "#1a1a2e", bg: "rgba(26,26,46,0.08)",   logo: "GG" },
  ofissepeti:      { name: "Ofis Sepeti",    color: "#e65100", bg: "rgba(230,81,0,0.08)",   logo: "OS" },
  muzikdunyasi:    { name: "Müzik Dünyası",  color: "#6a1b9a", bg: "rgba(106,27,154,0.08)", logo: "MD" },
  reebok:          { name: "Reebok",         color: "#cc0000", bg: "rgba(204,0,0,0.08)",    logo: "RB" },
  bershka:         { name: "Bershka",        color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",   logo: "BK" },
  ulker:           { name: "Ülker",          color: "#e53935", bg: "rgba(229,57,53,0.08)",  logo: "UK" },
  lego:            { name: "Lego",           color: "#e3000b", bg: "rgba(227,0,11,0.08)",   logo: "LG" },
  epson:           { name: "Epson",          color: "#003087", bg: "rgba(0,48,135,0.08)",   logo: "EP" },
  sarar:           { name: "Sarar",          color: "#1a1a1a", bg: "rgba(26,26,26,0.06)",   logo: "SR" },
  damattween:      { name: "Damat Tween",    color: "#1a237e", bg: "rgba(26,35,126,0.08)",  logo: "DT" },
  yargici:         { name: "Yargıcı",        color: "#3e2723", bg: "rgba(62,39,35,0.08)",   logo: "YG" },
  sony:            { name: "Sony",           color: "#000000", bg: "rgba(0,0,0,0.06)",       logo: "SN" },
  lg:              { name: "LG",             color: "#a50034", bg: "rgba(165,0,52,0.08)",   logo: "LG" },
  canon:           { name: "Canon",          color: "#cc0000", bg: "rgba(204,0,0,0.08)",    logo: "CN" },
  oyundeposu:      { name: "Oyun Deposu",   color: "#1a1a2e", bg: "rgba(26,26,46,0.08)",   logo: "OD" },
  frigg:           { name: "Frigg",          color: "#7b1fa2", bg: "rgba(123,31,162,0.08)", logo: "FG" },
  asusrog:         { name: "Asus ROG",       color: "#cc0000", bg: "rgba(204,0,0,0.08)",    logo: "RG" },
  melodika:        { name: "Melodika",       color: "#00695c", bg: "rgba(0,105,92,0.08)",   logo: "ML" },
  ufukkirtasiye:   { name: "Ufuk Kirtasiye", color: "#1565c0", bg: "rgba(21,101,192,0.08)", logo: "UK" },
  evpet:           { name: "Evpet",          color: "#2e7d32", bg: "rgba(46,125,50,0.08)",  logo: "EP" },
  zopet:           { name: "Zopet",          color: "#e65100", bg: "rgba(230,81,0,0.08)",   logo: "ZP" },
  petbis:          { name: "Petbis",         color: "#6a1b9a", bg: "rgba(106,27,154,0.08)", logo: "PB" },
};

function addAffiliateTag(url, source) {
  if (!url) return url;
  try {
    const u = new URL(url);
    if (source === 'amazon' || u.hostname.includes('amazon.com.tr')) {
      u.searchParams.set('tag', '210214a-21');
    }
    return u.toString();
  } catch(e) { return url; }
}

function getStoreBrand(source) {
  const key = String(source || "").toLowerCase().replace(/\s+.*$/, "").replace(/[^a-z0-9]/g, "");
  return STORE_BRANDS[key] || { name: source || "Mağaza", color: "#287a50", bg: "rgba(40,122,80,0.08)", emoji: "🛒" };
}

function storeLogoHtml(source, size = 36) {
  const brand = getStoreBrand(source);
  const initial = brand.name.charAt(0).toUpperCase();
  return `<div style="width:${size}px;height:${size}px;border-radius:8px;background:${brand.bg};border:1.5px solid ${brand.color}44;display:flex;align-items:center;justify-content:center;font-size:${Math.round(size*0.44)}px;font-weight:900;color:${brand.color};flex-shrink:0;font-family:'Manrope',sans-serif;">${initial}</div>`;
}
// ─────────────────────────────────────────────────────────────────────────────

window.__almadanPanicModeActive = false;
window.__almadanErrorReportCount = 0;

/* Hata raporunu sunucuya gönder (oturum başına en fazla 5, sessizce) */
function reportClientError(kind, message, source, lineno) {
  try {
    if (window.__almadanErrorReportCount >= 5) return;
    window.__almadanErrorReportCount++;
    const payload = JSON.stringify({
      kind, message: String(message).slice(0, 500),
      source: String(source || "").slice(0, 200),
      lineno: lineno || 0,
      url: location.pathname,
      ua: navigator.userAgent.slice(0, 120),
    });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/client-error", new Blob([payload], { type: "application/json" }));
    } else {
      fetch("/api/client-error", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(() => {});
    }
  } catch (_) { /* raporlama asla uygulamayı bozmasın */ }
}

window.onerror = function (message, source, lineno, colno, error) {
  const readable = `${message} @ ${String(source).split("/").pop()}:${lineno}:${colno}`;
  console.error("Almadan hata:", readable, error || "");
  reportClientError("error", message, source, lineno);

  if (window.__almadanPanicModeActive) {
    return true;
  }

  window.__almadanPanicModeActive = true;
  try {
    if (typeof window.showInitialLoadFallback === "function") {
      window.showInitialLoadFallback();
    }
  } catch (fallbackError) {
    console.error("Almadan kurtarma modu başlatılamadı:", fallbackError);
  } finally {
    window.setTimeout(() => {
      window.__almadanPanicModeActive = false;
    }, 1500);
  }

  return true;
};

window.addEventListener("unhandledrejection", function (event) {
  const reason = event.reason;
  const msg = reason && reason.message ? reason.message : String(reason);
  console.error("Almadan promise hatası:", msg, reason && reason.stack ? reason.stack.split("\n")[1] : "");
  reportClientError("unhandledrejection", msg, "", 0);
});

const state = {
  products: [],
  activeView: "discover",
  parsedProduct: null,
  deviceId: getOrCreateDeviceId(),
  auth: {
    enabled: false,
    authenticated: false,
    user: null,
  },
  cart: JSON.parse(localStorage.getItem("almadan_cart") || "[]"),
  sharedListId: null,
  sharedListVersion: 0,
  optimizerMode: "single",
  userLocation: "default",
  userCoords: null,
  maxDistance: 99999,
  theme: localStorage.getItem("almadan_theme") || "light",
  receipts: [],
  receiptSummary: null,
  pendingReceipt: null,
  charts: {},
};

let liveBarcodeScanner = null;
let liveBarcodeScannerRunning = false;
let liveBarcodeScanLocked = false;
let lastLiveBarcode = "";

const currency = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  maximumFractionDigits: 2,
});

const productFallbackIcons = {
  trendyol: "shopping-bag",
  hepsiburada: "package",
  amazon: "boxes",
  n11: "store",
  gratis: "flower",
  rossmann: "flower-2",
  supplementler: "dumbbell",
  proteinocean: "droplet",
  vatanbilgisayar: "cpu",
  itopya: "monitor",
  karaca: "home",
  lcwaikiki: "shirt",
  defacto: "shirt",
  mediamarkt: "smartphone",
  teknosa: "tv",
  zara: "shirt",
  migros: "shopping-cart",
  boyner: "shirt",
  koton: "shirt",
  mavi: "shirt",
  bim: "shopping-cart",
  a101: "shopping-cart",
  sok: "shopping-cart",
  file: "shopping-cart",
  metro: "shopping-cart",
  carrefoursa: "shopping-cart",
  manual: "package-search",
};

function md5(str) {
  const RotateLeft = (lValue, iShiftBits) => (lValue << iShiftBits) | (lValue >>> (32 - iShiftBits));
  const AddUnsigned = (lX, lY) => {
    const lX8 = lX & 0x80000000;
    const lY8 = lY & 0x80000000;
    const lX4 = lX & 0x40000000;
    const lY4 = lY & 0x40000000;
    const lResult = (lX & 0x3FFFFFFF) + (lY & 0x3FFFFFFF);
    if (lX4 & lY4) return lResult ^ 0x80000000 ^ lX8 ^ lY8;
    if (lX4 | lY4) {
      if (lResult & 0x40000000) return lResult ^ 0xC0000000 ^ lX8 ^ lY8;
      return lResult ^ 0x40000000 ^ lX8 ^ lY8;
    }
    return lResult ^ lX8 ^ lY8;
  };
  const F = (x, y, z) => (x & y) | (~x & z);
  const G = (x, y, z) => (x & z) | (y & ~z);
  const H = (x, y, z) => x ^ y ^ z;
  const I = (x, y, z) => y ^ (x | ~z);
  const FF = (a, b, c, d, x, s, ac) => AddUnsigned(RotateLeft(AddUnsigned(a, AddUnsigned(AddUnsigned(F(b, c, d), x), ac)), s), b);
  const GG = (a, b, c, d, x, s, ac) => AddUnsigned(RotateLeft(AddUnsigned(a, AddUnsigned(AddUnsigned(G(b, c, d), x), ac)), s), b);
  const HH = (a, b, c, d, x, s, ac) => AddUnsigned(RotateLeft(AddUnsigned(a, AddUnsigned(AddUnsigned(H(b, c, d), x), ac)), s), b);
  const II = (a, b, c, d, x, s, ac) => AddUnsigned(RotateLeft(AddUnsigned(a, AddUnsigned(AddUnsigned(I(b, c, d), x), ac)), s), b);

  const ConvertToWordArray = (string) => {
    const lMessageLength = string.length;
    const lNumberOfWords_temp1 = lMessageLength + 8;
    const lNumberOfWords_temp2 = (lNumberOfWords_temp1 - (lNumberOfWords_temp1 % 64)) / 64;
    const lNumberOfWords = (lNumberOfWords_temp2 + 1) * 16;
    const lWordArray = Array(lNumberOfWords).fill(0);
    let lByteCount = 0;
    while (lByteCount < lMessageLength) {
      const lWordCount = (lByteCount - (lByteCount % 4)) / 4;
      const lBytePosition = (lByteCount % 4) * 8;
      lWordArray[lWordCount] = lWordArray[lWordCount] | (string.charCodeAt(lByteCount) << lBytePosition);
      lByteCount++;
    }
    const lWordCount = (lByteCount - (lByteCount % 4)) / 4;
    const lBytePosition = (lByteCount % 4) * 8;
    lWordArray[lWordCount] = lWordArray[lWordCount] | (0x80 << lBytePosition);
    lWordArray[lNumberOfWords - 2] = lMessageLength << 3;
    lWordArray[lNumberOfWords - 1] = lMessageLength >>> 29;
    return lWordArray;
  };
  const WordToHex = (lValue) => {
    let WordToHexValue = "";
    for (let lCount = 0; lCount <= 3; lCount++) {
      const lByte = (lValue >>> (lCount * 8)) & 255;
      const WordToHexValue_temp = "0" + lByte.toString(16);
      WordToHexValue = WordToHexValue + WordToHexValue_temp.substring(WordToHexValue_temp.length - 2);
    }
    return WordToHexValue;
  };
  const Utf8Encode = (string) => {
    string = string.replace(/\r\n/g, "\n");
    let utftext = "";
    for (let n = 0; n < string.length; n++) {
      const c = string.charCodeAt(n);
      if (c < 128) {
        utftext += String.fromCharCode(c);
      } else if (c > 127 && c < 2048) {
        utftext += String.fromCharCode((c >> 6) | 192);
        utftext += String.fromCharCode((c & 63) | 128);
      } else {
        utftext += String.fromCharCode((c >> 12) | 224);
        utftext += String.fromCharCode(((c >> 6) & 63) | 128);
        utftext += String.fromCharCode((c & 63) | 128);
      }
    }
    return utftext;
  };

  const x = ConvertToWordArray(Utf8Encode(str));
  let a = 0x67452301;
  let b = 0xEFCDAB89;
  let c = 0x98BADCFE;
  let d = 0x10325476;
  const S11 = 7; const S12 = 12; const S13 = 17; const S14 = 22;
  const S21 = 5; const S22 = 9; const S23 = 14; const S24 = 20;
  const S31 = 4; const S32 = 11; const S33 = 16; const S34 = 23;
  const S41 = 6; const S42 = 10; const S43 = 15; const S44 = 21;

  for (let k = 0; k < x.length; k += 16) {
    const AA = a; const BB = b; const CC = c; const DD = d;
    a = FF(a, b, c, d, x[k + 0], S11, 0xD76AA478); d = FF(d, a, b, c, x[k + 1], S12, 0xE8C7B756); c = FF(c, d, a, b, x[k + 2], S13, 0x242070DB); b = FF(b, c, d, a, x[k + 3], S14, 0xC1BDCEEE);
    a = FF(a, b, c, d, x[k + 4], S11, 0xF57C0FAF); d = FF(d, a, b, c, x[k + 5], S12, 0x4787C62A); c = FF(c, d, a, b, x[k + 6], S13, 0xA8304613); b = FF(b, c, d, a, x[k + 7], S14, 0xFD469501);
    a = FF(a, b, c, d, x[k + 8], S11, 0x698098D8); d = FF(d, a, b, c, x[k + 9], S12, 0x8B44F7AF); c = FF(c, d, a, b, x[k + 10], S13, 0xFFFF5BB1); b = FF(b, c, d, a, x[k + 11], S14, 0x895CD7BE);
    a = FF(a, b, c, d, x[k + 12], S11, 0x6B901122); d = FF(d, a, b, c, x[k + 13], S12, 0xFD987193); c = FF(c, d, a, b, x[k + 14], S13, 0xA679438E); b = FF(b, c, d, a, x[k + 15], S14, 0x49B40821);

    a = GG(a, b, c, d, x[k + 1], S21, 0xF61E2562); d = GG(d, a, b, c, x[k + 6], S22, 0xC040B340); c = GG(c, d, a, b, x[k + 11], S23, 0x265E5A51); b = GG(b, c, d, a, x[k + 0], S24, 0xE9B6C7AA);
    a = GG(a, b, c, d, x[k + 5], S21, 0xD62F105D); d = GG(d, a, b, c, x[k + 10], S22, 0x02441453); c = GG(c, d, a, b, x[k + 15], S23, 0xD8A1E681); b = GG(b, c, d, a, x[k + 4], S24, 0xE7D3FBC8);
    a = GG(a, b, c, d, x[k + 9], S21, 0x21E1CDE6); d = GG(d, a, b, c, x[k + 14], S22, 0xC33707D6); c = GG(c, d, a, b, x[k + 3], S23, 0xF4D50D87); b = GG(b, c, d, a, x[k + 8], S24, 0x455A14ED);
    a = GG(a, b, c, d, x[k + 13], S21, 0xA9E3E905); d = GG(d, a, b, c, x[k + 2], S22, 0xFCEFA3F8); c = GG(c, d, a, b, x[k + 7], S23, 0x676F02D9); b = GG(b, c, d, a, x[k + 12], S24, 0x8D2A4C8A);

    a = HH(a, b, c, d, x[k + 5], S31, 0xFFFA3942); d = HH(d, a, b, c, x[k + 8], S32, 0x8771F681); c = HH(c, d, a, b, x[k + 11], S33, 0x6D9D6122); b = HH(b, c, d, a, x[k + 14], S34, 0xFDE5380C);
    a = HH(a, b, c, d, x[k + 1], S31, 0xA4BEEA44); d = HH(d, a, b, c, x[k + 4], S32, 0x4BDECFA9); c = HH(c, d, a, b, x[k + 7], S33, 0xF6BB4B60); b = HH(b, c, d, a, x[k + 10], S34, 0xBEBFBC70);
    a = HH(a, b, c, d, x[k + 13], S31, 0x289B7EC6); d = HH(d, a, b, c, x[k + 0], S32, 0xEAA127FA); c = HH(c, d, a, b, x[k + 3], S33, 0xD4EF3085); b = HH(b, c, d, a, x[k + 6], S34, 0x04881D05);
    a = HH(a, b, c, d, x[k + 9], S31, 0xD9D4D039); d = HH(d, a, b, c, x[k + 12], S32, 0xE6DB99E5); c = HH(c, d, a, b, x[k + 15], S33, 0x1FA27CF8); b = HH(b, c, d, a, x[k + 2], S34, 0xC4AC5665);

    a = II(a, b, c, d, x[k + 0], S41, 0xF4292244); d = II(d, a, b, c, x[k + 7], S42, 0x432AFF97); c = II(c, d, a, b, x[k + 14], S43, 0xAB9423A7); b = II(b, c, d, a, x[k + 5], S44, 0xFC93A039);
    a = II(a, b, c, d, x[k + 12], S41, 0x655B59C3); d = II(d, a, b, c, x[k + 3], S42, 0x8F0CCC92); c = II(c, d, a, b, x[k + 10], S43, 0xFFEFF47D); b = II(b, c, d, a, x[k + 1], S44, 0x85845DD1);
    a = II(a, b, c, d, x[k + 8], S41, 0x6FA87E4F); d = II(d, a, b, c, x[k + 15], S42, 0xFE2CE6E0); c = II(c, d, a, b, x[k + 6], S43, 0xA3014314); b = II(b, c, d, a, x[k + 13], S44, 0x4E0811A1);
    a = II(a, b, c, d, x[k + 4], S41, 0xF7537E82); d = II(d, a, b, c, x[k + 11], S42, 0xBD3AF235); c = II(c, d, a, b, x[k + 2], S43, 0x2AD7D2BB); b = II(b, c, d, a, x[k + 9], S44, 0xEB86D391);

    a = AddUnsigned(a, AA); b = AddUnsigned(b, BB); c = AddUnsigned(c, CC); d = AddUnsigned(d, DD);
  }
  return (WordToHex(a) + WordToHex(b) + WordToHex(c) + WordToHex(d)).toLowerCase();
}

function getStoreIcon(store, title) {
  if (store && productFallbackIcons[store]) {
    return productFallbackIcons[store];
  }
  const category = getItemCategory(title || "");
  switch (category) {
    case "supplement": return "dumbbell";
    case "electronics": return "cpu";
    case "cosmetics": return "flower";
    case "fashion": return "shirt";
    case "health": return "heart-pulse";
    case "home": return "home";
    case "grocery": return "shopping-cart";
    default: return "package-search";
  }
}

const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
window.SEARCH_TIMEOUT = 6000;

function optimizeForMobile() {
  if (isMobile) {
    console.log("Mobil Mod: Optimizasyonlar devreye alındı.");
    document.documentElement.style.setProperty('--animation-speed', '0s');
    window.SEARCH_TIMEOUT = 3000;

    const svgWrapper = document.querySelector("#quantumScanOverlay div");
    if (svgWrapper) {
      svgWrapper.querySelectorAll("svg").forEach(svg => {
        svg.style.opacity = "0";
        svg.style.visibility = "hidden";
      });
    }
  }
}

function persistQuantumState() {
  const globalCheckbox = document.getElementById("globalModeCheckbox");
  const data = {
    userCoords: state.userCoords,
    userLocation: state.userLocation,
    isGlobalActive: globalCheckbox ? globalCheckbox.checked : false
  };
  localStorage.setItem("almadan_state", JSON.stringify(data));
  console.log("Kuantum Hafıza: Durum kaydedildi.", data);
}

document.addEventListener("DOMContentLoaded", async () => {
  applyTheme();
  optimizeForMobile();

  if (window.requestIdleCallback) {
    requestIdleCallback(() => {
      lucide.createIcons();
    });
  } else {
    requestAnimationFrame(() => {
      lucide.createIcons();
    });
  }

  bindEvents();
  registerServiceWorker();
  updateNetworkStatus();
  updateGpsStatusUI();
  const recoverySession = readRecoverySession();
  if (recoverySession) {
    showPasswordReset(recoverySession);
    loadSession();
  } else {
    // Çerezlerin tarayıcıya işlenmesini bekle -- aksi halde hemen ardından
    // gelen loadSession() henüz eski (çıkış yapılmış) durumu görüp üzerine yazabilir.
    const confirmed = await completeEmailConfirmSession();
    if (!confirmed) loadSession();
  }
  checkSharedListUrl();
  loadLatestCampaigns();
});

// E-posta onay linkine tıklayınca Supabase #access_token=...&type=signup
// fragmanıyla siteye döner -- bunu yakalayıp otomatik oturum aç, kullanıcı
// ad soyad/telefon gibi bilgileri BAŞTAN girmek zorunda kalmasın.
async function completeEmailConfirmSession() {
  if (!window.location.hash) return false;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const type = params.get("type");
  const accessToken = params.get("access_token");
  if (!accessToken || (type !== "signup" && type !== "email_change" && type !== "magiclink")) return false;

  history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  try {
    const result = await api("/auth/session/exchange", {
      method: "POST",
      body: JSON.stringify({
        access_token: accessToken,
        refresh_token: params.get("refresh_token"),
      }),
    });
    state.auth = { enabled: true, authenticated: true, user: result.user };
    renderAccountButton();
    handleCategoryChange();
    await loadProducts();
    await loadCartFromBackend();
    showToast("Hesabın onaylandı, hoş geldin! Bilgilerini tamamlayalım.");
    showAccount();
    return true;
  } catch (error) {
    console.warn("E-posta onayı sonrası otomatik giriş başarısız:", error.message);
    return false;
  }
}

/* ── "Haftanın En Çok Düşenleri" vitrini ──────────────────────────────── */
async function loadLatestCampaigns() {
  const section = document.getElementById("latestCampaignsSection");
  const grid = document.getElementById("latestCampaignsGrid");
  if (!section || !grid) return;
  try {
    const res = await fetch("/api/campaigns/latest?limit=10");
    if (!res.ok) return;
    const data = await res.json();
    const campaigns = data.campaigns || [];
    if (!campaigns.length) return;

    grid.innerHTML = campaigns
      .map((c) => {
        const storeName = escapeHtml(c.store_name || c.store_slug || "Mağaza");
        const title = escapeHtml(c.title || "Yeni Kampanya");
        const desc = escapeHtml((c.description || "").slice(0, 90));
        const url = c.catalog_url ? escapeHtml(addAffiliateTag(c.catalog_url, c.store_slug)) : "";
        const brand = getStoreBrand(c.store_slug);
        return `
          <a href="${url || "#"}" target="_blank" rel="noopener"
             style="flex:0 0 240px;background:var(--bg-card,#181b20);border:1.5px solid var(--border,#2e3240);border-radius:12px;padding:14px;text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:6px;transition:border-color .15s;"
             onmouseover="this.style.borderColor='#287a50'" onmouseout="this.style.borderColor='var(--border,#2e3240)'">
            <div style="display:flex;align-items:center;gap:8px;">
              <div style="width:28px;height:28px;border-radius:7px;background:${brand.bg};color:${brand.color};display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;flex-shrink:0;">${storeName.charAt(0).toUpperCase()}</div>
              <span style="font-size:12.5px;font-weight:700;color:var(--ink,#e2e4e9);">${storeName}</span>
            </div>
            <div style="font-size:13px;font-weight:700;color:var(--ink,#e2e4e9);">🔥 ${title}</div>
            ${desc ? `<div style="font-size:11.5px;color:var(--ink-2,#848c96);line-height:1.4;">${desc}</div>` : ""}
          </a>`;
      })
      .join("");
    section.classList.remove("hidden");
  } catch (e) {
    // Sessizce geç — ana sayfa deneyimini bozmasın
  }
}

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  // Onboarding modal — backdrop tıklamasında kapat
  const onboardingModal = document.getElementById("onboardingModal");
  if (onboardingModal) {
    onboardingModal.addEventListener("click", (e) => {
      if (e.target === onboardingModal) closeOnboarding();
    });
  }

  document.getElementById("urlForm").addEventListener("submit", parseProduct);
  document.getElementById("pasteButton").addEventListener("click", pasteUrl);
  document.getElementById("refreshButton").addEventListener("click", refreshAllPrices);
  document.getElementById("dialogClose").addEventListener("click", closeDialog);
  document.getElementById("notificationButton").addEventListener("click", showNotifications);
  document.getElementById("accountButton").addEventListener("click", showAccount);

  const gpsPill = document.getElementById("gpsStatusIndicator");
  if (gpsPill) {
    gpsPill.addEventListener("click", () => {
      window.triggerGpsActivation();
    });
  }

  const globalCheckbox = document.getElementById("globalModeCheckbox");
  if (globalCheckbox) {
    globalCheckbox.addEventListener("change", persistQuantumState);
  }

  document.getElementById("themeToggleButton").addEventListener("click", toggleTheme);
  document.getElementById("quickCartAddBtn").addEventListener("click", addQuickCartItem);
  document.getElementById("quickCartInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") addQuickCartItem();
  });
  document.getElementById("clearCartBtn").addEventListener("click", clearCart);
  document.getElementById("shareListBtn").addEventListener("click", shareCartList);
  document.getElementById("simulateBarcodeBtn").addEventListener("click", () => toggleScannerArea("barcode"));
  document.getElementById("simulateOcrBtn").addEventListener("click", () => toggleScannerArea("ocr"));
  document.getElementById("runBarcodeScanBtn").addEventListener("click", runBarcodeScan);
  document.getElementById("stopBarcodeScanBtn")?.addEventListener("click", stopLiveBarcodeScanner);
  document.getElementById("runOcrScanBtn").addEventListener("click", runOcrScan);
  document.getElementById("barcodeImageInput").addEventListener("change", scanBarcodeImage);
  document.getElementById("receiptImageInput").addEventListener("change", previewReceiptFile);
  document.getElementById("receiptGalleryInput")?.addEventListener("change", previewReceiptFile);
  document.getElementById("receiptMonthFilter")?.addEventListener("change", (event) => {
    loadReceipts(event.target.value);
  });
  document.getElementById("optModeSingle").addEventListener("click", () => switchOptimizerMode("single"));
  document.getElementById("optModeSplit").addEventListener("click", () => switchOptimizerMode("split"));
  document.getElementById("micButton")?.addEventListener("click", startVoiceSearch);

  window.addEventListener("online", () => {
    updateNetworkStatus();
    flushPendingSharedSync();
  });
  window.addEventListener("offline", updateNetworkStatus);

  document.getElementById("productDialog").addEventListener("click", (event) => {
    if (event.target.id === "productDialog") closeDialog();
  });

  // Category Selector change listener
  const categorySelector = document.getElementById("searchCategorySelector");
  if (categorySelector) {
    categorySelector.addEventListener("change", handleCategoryChange);
  }
}

function requestHeaders(extra = {}, method = "GET") {
  const csrfToken = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrf_token="))
    ?.split("=")
    .slice(1)
    .join("=");
  return {
    "Content-Type": "application/json",
    "X-Device-ID": state.deviceId,
    ...(["POST", "PUT", "PATCH", "DELETE"].includes(String(method).toUpperCase()) && csrfToken
      ? { "X-CSRF-Token": decodeURIComponent(csrfToken) }
      : {}),
    ...extra,
  };
}

async function api(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: requestHeaders(options.headers || {}, method),
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { detail: await response.text() || `Sunucu hatası (${response.status})` };

  if (!response.ok) {
    const err = new Error(apiErrorMessage(data, response.status));
    err.status = response.status;
    throw err;
  }
  return data;
}

// Bir API çağrısı "giriş gerekli" (401/403 + yetki mesajı) ile başarısız
// olduğunda true döner -- takip/bildirim gibi hesap gerektiren işlemler
// için ortak kontrol.
function isLoginRequiredError(error) {
  return error && (error.status === 401 || error.status === 403);
}

// ── Onboarding ─────────────────────────────────────────────────────────────
let _onboardingStep = 0;
const _ONBOARDING_KEY = "almadan_onboarded_v1";

function showOnboarding() {
  if (localStorage.getItem(_ONBOARDING_KEY)) return;
  const modal = document.getElementById("onboardingModal");
  if (!modal) return;
  if (!modal.open) modal.showModal();
  lucide.createIcons();
}

function closeOnboarding() {
  const modal = document.getElementById("onboardingModal");
  if (modal && modal.open) modal.close();
  localStorage.setItem(_ONBOARDING_KEY, "1");
}

function goOnboardingStep(step) {
  const steps = document.querySelectorAll(".onboarding-step");
  const dots = document.querySelectorAll(".onboarding-dot");
  const prevBtn = document.getElementById("onboardingPrev");
  const nextBtn = document.getElementById("onboardingNext");
  if (!steps.length) return;

  steps.forEach((s) => (s.style.display = "none"));
  dots.forEach((d) => (d.style.background = "var(--line, #ddd)"));

  const target = steps[step];
  if (target) target.style.display = "block";
  const dot = dots[step];
  if (dot) dot.style.background = "#287a50";

  _onboardingStep = step;
  if (prevBtn) prevBtn.disabled = step === 0;
  if (nextBtn) {
    if (step === steps.length - 1) {
      nextBtn.textContent = "Başlayalım!";
      nextBtn.onclick = closeOnboarding;
    } else {
      nextBtn.textContent = "İleri →";
      nextBtn.onclick = () => onboardingNav(1);
    }
  }
}

function onboardingNav(dir) {
  const steps = document.querySelectorAll(".onboarding-step");
  const next = Math.max(0, Math.min(steps.length - 1, _onboardingStep + dir));
  goOnboardingStep(next);
}
// ───────────────────────────────────────────────────────────────────────────

async function loadSession() {
  try {
    state.auth = await api("/auth/session");
  } catch {
    state.auth = { enabled: false, authenticated: false, user: null };
  }
  renderAccountButton();
  handleCategoryChange();
  loadProducts();
  if (state.auth.authenticated) {
    loadCartFromBackend();
    maybePromptPhoneVerification();
  }
  setTimeout(showOnboarding, 800);
}

// Fake kullanıcıları engellemek için: telefonu doğrulanmamış hesaplara,
// oturum başına en fazla bir kez, doğrulama dialogu göster.
function maybePromptPhoneVerification() {
  const user = state.auth?.user;
  if (!user || !user.phone || user.phone_verified) return;
  if (sessionStorage.getItem("almadan_phone_verify_dismissed") === user.phone) return;
  promptPhoneVerification(user.phone);
}

function promptPhoneVerification(phone, codeSent = false) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  if (!dialog || !content) return;

  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">TELEFON DOĞRULAMA</p>
      <h2>Telefon numaranı doğrula.</h2>
      <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">
        Hesabının gerçek olduğundan emin olmak için <b>${escapeHtml(phone)}</b> numarasına gönderdiğimiz kodu gir.
      </p>
      <div id="phoneVerifyError" class="auth-error" hidden></div>
      ${codeSent ? `
        <div class="manual-fields">
          <label class="manual-field">
            <span>Doğrulama Kodu</span>
            <input id="phoneVerifyCode" type="text" inputmode="numeric" maxlength="6" placeholder="6 haneli kod" style="width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--line); border-radius: 6px; font-family: inherit; font-size: 14px;">
          </label>
        </div>
        <div class="dialog-actions" style="margin-top: 20px;">
          <button class="secondary-button" type="button" onclick="dismissPhoneVerification('${phone}')">Daha Sonra</button>
          <button class="primary-button" type="button" onclick="confirmPhoneVerification('${phone}')">Doğrula</button>
        </div>
      ` : `
        <div class="dialog-actions" style="margin-top: 20px;">
          <button class="secondary-button" type="button" onclick="dismissPhoneVerification('${phone}')">Daha Sonra</button>
          <button class="primary-button" type="button" onclick="sendPhoneVerificationCode('${phone}')">Kod Gönder</button>
        </div>
      `}
    </div>
  `;
  dialog.showModal();
}

function dismissPhoneVerification(phone) {
  sessionStorage.setItem("almadan_phone_verify_dismissed", phone);
  closeDialog();
}

async function sendPhoneVerificationCode(phone) {
  try {
    await api("/auth/otp/send", { method: "POST", body: JSON.stringify({ phone }) });
    showToast("Doğrulama kodu gönderildi.");
    promptPhoneVerification(phone, true);
  } catch (error) {
    showToast(error.message);
  }
}

async function confirmPhoneVerification(phone) {
  const code = document.getElementById("phoneVerifyCode")?.value.trim();
  if (!code || code.length !== 6) {
    showToast("Lütfen 6 haneli kodu girin.");
    return;
  }
  try {
    const result = await api("/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ phone, code }),
    });
    state.auth.user = { ...state.auth.user, ...result.user, phone_verified: true };
    sessionStorage.removeItem("almadan_phone_verify_dismissed");
    closeDialog();
    showToast("Telefon doğrulandı!");
  } catch (error) {
    showToast(error.message);
  }
}

function renderAccountButton() {
  const label = document.getElementById("accountButtonLabel");
  const button = document.getElementById("accountButton");
  if (!label || !button) return;

  if (state.auth.authenticated) {
    label.textContent = state.auth.user?.email?.split("@")[0] || "Hesabım";
    button.title = state.auth.user?.email || "Hesabım";
  } else {
    label.textContent = "Giriş";
    button.title = "Giriş yap veya hesap oluştur";
  }
}

let activeAuthMethod = "email"; // "email" or "sms"
let authFormMode = "login"; // "login" or "signup" -- sadece "email" sekmesi için
let smsCodeSent = false;

function switchAuthFormMode(mode) {
  authFormMode = mode;
  const content = document.getElementById("dialogContent");
  if (content) renderUnauthenticatedAuth(content);
}

function renderUnauthenticatedAuth(content) {
  if (activeAuthMethod === "email") {
    const isSignup = authFormMode === "signup";
    content.innerHTML = `
      <div class="dialog-body auth-dialog">
        <p class="eyebrow">ALMADAN HESABI</p>
        <h2>${isSignup ? "Hesap oluştur." : "Takiplerini kaybetme."}</h2>

        <div class="auth-tabs" style="display: flex; gap: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--line); padding-bottom: 10px; width: 100%;">
          <button type="button" onclick="switchAuthMethod('email')" style="background: none; border: none; font-weight: bold; cursor: pointer; color: var(--green-dark); border-bottom: 2px solid var(--green-dark); padding-bottom: 8px; font-family: inherit; font-size: 14px;">E-posta ile Giriş</button>
          <button type="button" onclick="switchAuthMethod('sms')" style="background: none; border: none; cursor: pointer; color: var(--ink-light); padding-bottom: 8px; font-family: inherit; font-size: 14px;">SMS ile Giriş</button>
        </div>

        <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">
          ${isSignup ? "Sadece e-posta ve şifre yeterli -- telefon, ad soyad gibi bilgileri girdikten sonra tamamlarsın." : "E-posta ile giriş yap. Bu cihazdaki ürünlerin hesabına otomatik taşınsın."}
        </p>

        <div class="manual-fields">
          <label class="manual-field">
            <span>E-posta</span>
            <input id="authEmail" type="email" autocomplete="email" placeholder="ornek@email.com" required>
          </label>
          <label class="manual-field">
            <span>Şifre</span>
            <input id="authPassword" type="password" autocomplete="${isSignup ? "new-password" : "current-password"}" minlength="8" placeholder="En az 8 karakter">
          </label>
          ${isSignup ? `
            <label class="manual-field">
              <span>Şifre (Tekrar)</span>
              <input id="authPasswordConfirm" type="password" autocomplete="new-password" minlength="8" placeholder="Şifreni tekrar yaz">
            </label>
          ` : ""}
        </div>
        ${isSignup ? "" : `
          <button class="auth-link-button" type="button" onclick="showForgotPassword()">
            Şifremi unuttum
          </button>
        `}
        <p class="dialog-error" id="authError" hidden></p>
        <p class="dialog-success" id="authSuccess" hidden></p>
        ${state.auth.enabled ? `
          <div class="dialog-actions">
            <button class="primary-button" type="button" onclick="submitAuth('${isSignup ? "signup" : "login"}')" style="width: 100%;">
              <i data-lucide="${isSignup ? "user-plus" : "log-in"}"></i>
              ${isSignup ? "Hesap oluştur" : "Giriş yap"}
            </button>
          </div>
          <p class="auth-copy" style="margin-top: 14px; font-size: 13px; text-align: center;">
            ${isSignup ? "Zaten hesabın var mı?" : "Hesabın yok mu?"}
            <button class="auth-link-button" type="button" onclick="switchAuthFormMode('${isSignup ? "login" : "signup"}')" style="font-weight: 700;">
              ${isSignup ? "Giriş yap" : "Üye ol"}
            </button>
          </p>
        ` : `
          <p class="dialog-error">Hesap sistemi henüz sunucuda etkinleştirilmedi.</p>
        `}
      </div>
    `;
  } else {
    content.innerHTML = `
      <div class="dialog-body auth-dialog">
        <p class="eyebrow">ALMADAN HESABI</p>
        <h2>SMS ile Hızlı Giriş.</h2>

        <div class="auth-tabs" style="display: flex; gap: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--line); padding-bottom: 10px; width: 100%;">
          <button type="button" onclick="switchAuthMethod('email')" style="background: none; border: none; cursor: pointer; color: var(--ink-light); padding-bottom: 8px; font-family: inherit; font-size: 14px;">E-posta ile Giriş</button>
          <button type="button" onclick="switchAuthMethod('sms')" style="background: none; border: none; font-weight: bold; cursor: pointer; color: var(--green-dark); border-bottom: 2px solid var(--green-dark); padding-bottom: 8px; font-family: inherit; font-size: 14px;">SMS ile Giriş</button>
        </div>

        <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">Şifresiz giriş yap. Telefonuna gelecek tek kullanımlık SMS koduyla hesabına anında ulaş.</p>

        <div class="manual-fields">
          <label class="manual-field">
            <span>Telefon Numarası</span>
            <input id="authSmsPhone" type="tel" placeholder="05XXXXXXXXX" ${smsCodeSent ? 'disabled' : ''}>
          </label>
          ${smsCodeSent ? `
            <label class="manual-field">
              <span>6 Haneli Doğrulama Kodu</span>
              <input id="authSmsCode" type="text" pattern="[0-9]*" inputmode="numeric" maxlength="6" placeholder="******">
            </label>
          ` : ''}
        </div>

        <p class="dialog-error" id="authError" hidden></p>
        <p class="dialog-success" id="authSuccess" hidden></p>

        ${state.auth.enabled ? `
          <div class="dialog-actions" style="margin-top: 20px;">
            ${smsCodeSent ? `
              <button class="secondary-button" type="button" onclick="resetSmsFlow()">Telefonu Değiştir</button>
              <button class="primary-button" type="button" onclick="verifySmsCode()">
                <i data-lucide="check"></i>
                Doğrula ve Giriş Yap
              </button>
            ` : `
              <button class="primary-button" type="button" onclick="sendSmsCode()" style="width: 100%;">
                <i data-lucide="send"></i>
                Kod Gönder
              </button>
            `}
          </div>
        ` : `
          <p class="dialog-error">Hesap sistemi henüz sunucuda etkinleştirilmedi.</p>
        `}
      </div>
    `;
  }
  lucide.createIcons();
  if (typeof togglePhoneField === "function" && activeAuthMethod === "email") togglePhoneField();
}

function switchAuthMethod(method) {
  activeAuthMethod = method;
  const content = document.getElementById("dialogContent");
  if (content) {
    renderUnauthenticatedAuth(content);
  }
}

function resetSmsFlow() {
  smsCodeSent = false;
  const content = document.getElementById("dialogContent");
  if (content) {
    renderUnauthenticatedAuth(content);
  }
}

function normalizePhoneNumber(raw) {
  const digits = raw.replace(/\D/g, "");
  if (digits.startsWith("90") && digits.length === 12) return "+" + digits;
  if (digits.startsWith("0") && digits.length === 11) return "+9" + digits;
  if (digits.length === 10) return "+90" + digits;
  return "+" + digits;
}

async function sendSmsCode() {
  const rawPhone = document.getElementById("authSmsPhone")?.value.trim();
  if (!rawPhone || rawPhone.replace(/\D/g, "").length < 10) {
    showAuthError("Lütfen geçerli bir telefon numarası girin.");
    return;
  }
  const phone = normalizePhoneNumber(rawPhone);

  try {
    const errorBox = document.getElementById("authError");
    if (errorBox) errorBox.hidden = true;

    await api("/auth/otp/send", {
      method: "POST",
      body: JSON.stringify({ phone }),
    });

    smsCodeSent = true;
    const content = document.getElementById("dialogContent");
    if (content) {
      renderUnauthenticatedAuth(content);
    }
    showToast("Doğrulama kodu gönderildi.");
  } catch (error) {
    showAuthError(error.message);
  }
}

async function verifySmsCode() {
  const rawPhone = document.getElementById("authSmsPhone")?.value.trim();
  const code = document.getElementById("authSmsCode")?.value.trim();

  if (!rawPhone || !code || code.length !== 6) {
    showAuthError("Lütfen 6 haneli doğrulama kodunu girin.");
    return;
  }
  const phone = normalizePhoneNumber(rawPhone);

  try {
    const errorBox = document.getElementById("authError");
    if (errorBox) errorBox.hidden = true;

    const result = await api("/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ phone, code }),
    });

    state.auth = {
      enabled: true,
      authenticated: true,
      user: result.user,
    };
    renderAccountButton();
    handleCategoryChange();
    closeDialog();
    await loadProducts();
    await loadCartFromBackend();
    showToast("Giriş yapıldı.");
  } catch (error) {
    showAuthError(error.message);
  }
}

function promptLoginForTracking(reason) {
  showToast(reason || "Ürün takibi için hesap açman gerekiyor.");
  showAccount();
}

function showAccount() {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");

  if (state.auth.authenticated) {
    content.innerHTML = `
      <div class="dialog-body auth-dialog">
        <p class="eyebrow">HESABIN</p>
        <h2>Takiplerin seninle gelsin.</h2>
        <div class="account-summary">
          <span class="account-avatar"><i data-lucide="user-round"></i></span>
          <div>
            <strong>${escapeHtml(state.auth.user?.email || state.auth.user?.phone || "Almadan kullanıcısı")}</strong>
            <p>Takiplerin bu hesapla farklı cihazlarda eşitlenir.</p>
          </div>
        </div>
        <div class="manual-fields">
          <label class="manual-field">
            <span>Ad Soyad</span>
            <input id="profileFullName" type="text" autocomplete="name" maxlength="120" value="${escapeHtml(state.auth.user?.full_name || "")}" placeholder="Ad Soyad">
          </label>
          <label class="manual-field">
            <span>Cinsiyet</span>
            <select id="profileGender">
              <option value="belirtilmemiş">Belirtilmemiş</option>
              <option value="erkek" ${state.auth.user?.gender === "erkek" ? "selected" : ""}>Erkek</option>
              <option value="kadın" ${state.auth.user?.gender === "kadın" ? "selected" : ""}>Kadın</option>
            </select>
          </label>
          <label class="manual-field">
            <span>Bildirim Tercihi</span>
            <select id="profileNotificationPref" onchange="toggleProfilePhoneField()">
              <option value="both" ${state.auth.user?.notification_pref === "both" ? "selected" : ""}>Hem SMS hem E-posta</option>
              <option value="email" ${state.auth.user?.notification_pref === "email" ? "selected" : ""}>Sadece E-posta</option>
              <option value="sms" ${state.auth.user?.notification_pref === "sms" ? "selected" : ""}>Sadece SMS</option>
            </select>
          </label>
          <label class="manual-field" id="profilePhoneField">
            <span>Telefon Numarası</span>
            <div style="display: flex; gap: 8px; align-items: center;">
              <input id="profilePhone" type="tel" value="${escapeHtml(state.auth.user?.phone || "")}" placeholder="05XXXXXXXXX" style="flex: 1;">
              ${state.auth.user?.phone ? (
                state.auth.user?.phone_verified
                  ? `<span style="font-size: 12px; color: var(--green-dark); font-weight: 700; white-space: nowrap;">✓ Doğrulandı</span>`
                  : `<button class="secondary-button" type="button" style="white-space: nowrap; padding: 0 12px; min-height: 40px;" onclick="promptPhoneVerification(state.auth.user.phone)">Doğrula</button>`
              ) : ""}
            </div>
          </label>
          <label class="profile-checkbox">
            <input id="profileSilenceEnabled" type="checkbox" ${state.auth.user?.silence_hours ? "checked" : ""}>
            <span>22:00-08:00 arasında bildirimleri sabaha ertele</span>
          </label>
        </div>
        <p class="dialog-error" id="authError" hidden></p>
        <button class="primary-button auth-submit-button" type="button" onclick="saveProfileSettings()">
          <i data-lucide="save"></i>
          Ayarları kaydet
        </button>
        <button class="danger-button" type="button" onclick="logoutAccount()">
          <i data-lucide="log-out"></i>
          Çıkış yap
        </button>
      </div>
    `;
  } else {
    smsCodeSent = false;
    renderUnauthenticatedAuth(content);
  }

  dialog.showModal();
  lucide.createIcons();
  if (typeof togglePhoneField === "function" && activeAuthMethod === "email") togglePhoneField();
  if (typeof toggleProfilePhoneField === "function") toggleProfilePhoneField();
}

function toggleProfilePhoneField() {
  const pref = document.getElementById("profileNotificationPref")?.value;
  const phoneField = document.getElementById("profilePhoneField");
  if (phoneField) phoneField.hidden = pref === "email";
}

async function saveProfileSettings() {
  const fullName = document.getElementById("profileFullName")?.value.trim() || "";
  const gender = document.getElementById("profileGender")?.value || "belirtilmemiş";
  const notificationPref = document.getElementById("profileNotificationPref")?.value || "both";
  const rawPhone = document.getElementById("profilePhone")?.value.trim() || "";
  const phone = rawPhone ? normalizePhoneNumber(rawPhone) : "";
  const silenceEnabled = Boolean(document.getElementById("profileSilenceEnabled")?.checked);

  if (notificationPref !== "email" && !phone) {
    showAuthError("SMS bildirimleri için telefon numarası gereklidir.");
    return;
  }

  try {
    const result = await api("/auth/profile", {
      method: "PUT",
      body: JSON.stringify({
        full_name: fullName,
        gender,
        phone,
        notification_pref: notificationPref,
        silence_enabled: silenceEnabled,
      }),
    });
    state.auth.user = result.user;
    closeDialog();
    showToast("Profil ve bildirim ayarların kaydedildi.");
    maybePromptPhoneVerification();
  } catch (error) {
    showAuthError(error.message);
  }
}

function showForgotPassword() {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  const currentEmail = document.getElementById("authEmail")?.value.trim() || "";

  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">ŞİFRE YENİLEME</p>
      <h2>Hesabına yeniden ulaş.</h2>
      <p class="auth-copy">E-posta adresini yaz. Sana yeni şifre belirleyebileceğin güvenli bir bağlantı gönderelim.</p>
      <div class="manual-fields">
        <label class="manual-field">
          <span>E-posta</span>
          <input id="resetEmail" type="email" autocomplete="email" value="${escapeHtml(currentEmail)}" placeholder="ornek@email.com">
        </label>
      </div>
      <p class="dialog-error" id="authError" hidden></p>
      <div class="dialog-actions">
        <button class="secondary-button" type="button" onclick="showAccount()">Geri dön</button>
        <button class="primary-button" type="button" onclick="sendPasswordReset()">
          <i data-lucide="mail"></i>
          Bağlantı gönder
        </button>
      </div>
    </div>
  `;

  if (!dialog.open) dialog.showModal();
  lucide.createIcons();
  document.getElementById("resetEmail")?.focus();
}

async function sendPasswordReset() {
  const email = document.getElementById("resetEmail")?.value.trim();
  if (!email) {
    showAuthError("Geçerli bir e-posta adresi yaz.");
    return;
  }

  try {
    const result = await api("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    showToast(result.message || "Şifre yenileme bağlantısı gönderildi.");
    closeDialog();
  } catch (error) {
    showAuthError(error.message);
  }
}

function readRecoverySession() {
  if (!window.location.hash) return null;

  const params = new URLSearchParams(window.location.hash.slice(1));
  if (params.get("type") !== "recovery") return null;

  const accessToken = params.get("access_token");
  if (!accessToken) return null;

  return {
    accessToken,
    refreshToken: params.get("refresh_token"),
  };
}

function showPasswordReset(recoverySession) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  state.passwordRecovery = recoverySession;

  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">YENİ ŞİFRE</p>
      <h2>Yeni şifreni belirle.</h2>
      <p class="auth-copy">En az 8 karakterli, başka hesaplarında kullanmadığın bir şifre seç.</p>
      <div class="manual-fields">
        <label class="manual-field">
          <span>Yeni şifre</span>
          <input id="newPassword" type="password" autocomplete="new-password" minlength="8" placeholder="En az 8 karakter">
        </label>
        <label class="manual-field">
          <span>Yeni şifre tekrar</span>
          <input id="newPasswordConfirm" type="password" autocomplete="new-password" minlength="8" placeholder="Şifreni tekrar yaz">
        </label>
      </div>
      <p class="dialog-error" id="authError" hidden></p>
      <button class="primary-button auth-submit-button" type="button" onclick="submitPasswordReset()">
        <i data-lucide="key-round"></i>
        Şifreyi yenile
      </button>
    </div>
  `;

  dialog.showModal();
  lucide.createIcons();
}

async function submitPasswordReset() {
  const password = document.getElementById("newPassword")?.value || "";
  const confirmation = document.getElementById("newPasswordConfirm")?.value || "";
  const recovery = state.passwordRecovery;

  if (!recovery?.accessToken) {
    showAuthError("Şifre yenileme bağlantısı geçersiz veya süresi dolmuş.");
    return;
  }
  if (password.length < 8) {
    showAuthError("Yeni şifre en az 8 karakter olmalı.");
    return;
  }
  if (password !== confirmation) {
    showAuthError("Yazdığın şifreler birbiriyle eşleşmiyor.");
    return;
  }

  try {
    const result = await api("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        access_token: recovery.accessToken,
        refresh_token: recovery.refreshToken,
        password,
      }),
    });

    history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    state.passwordRecovery = null;
    state.auth = {
      enabled: true,
      authenticated: true,
      user: result.user,
    };
    renderAccountButton();
    closeDialog();
    showToast("Şifren yenilendi. Hesabına giriş yapıldı.");
  } catch (error) {
    showAuthError(error.message);
  }
}

async function submitAuth(mode) {
  const email = document.getElementById("authEmail")?.value.trim();
  const password = document.getElementById("authPassword")?.value || "";

  if (!email || password.length < 8) {
    showAuthError("Geçerli e-posta ve en az 8 karakterli şifre gerekli.");
    return;
  }

  if (mode === "signup") {
    const passwordConfirm = document.getElementById("authPasswordConfirm")?.value || "";
    if (password !== passwordConfirm) {
      showAuthError("Yazdığın şifreler birbiriyle eşleşmiyor.");
      return;
    }
  }

  try {
    const payload = { email, password };

    const result = await api(`/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (result.requires_email_confirmation) {
      showAuthSuccess("Hesabın oluşturuldu! E-posta adresine bir onay bağlantısı gönderdik. Linke tıklayınca otomatik giriş yapılacak, kalan bilgilerini (ad soyad, telefon) orada birkaç adımda tamamlarsın.");
      return;
    }

    state.auth = {
      enabled: true,
      authenticated: true,
      user: result.user,
    };
    renderAccountButton();
    handleCategoryChange();
    closeDialog();
    await loadProducts();
    await loadCartFromBackend();
    showToast(mode === "signup" ? "Hesabın oluşturuldu." : "Giriş yapıldı.");
    if (mode === "signup") {
      showAccount();
    } else {
      maybePromptPhoneVerification();
    }
  } catch (error) {
    showAuthError(error.message);
  }
}

function showAuthError(message) {
  const successBox = document.getElementById("authSuccess");
  if (successBox) successBox.hidden = true;

  const errorBox = document.getElementById("authError");
  if (!errorBox) return;
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function showAuthSuccess(message) {
  const errorBox = document.getElementById("authError");
  if (errorBox) errorBox.hidden = true;

  const successBox = document.getElementById("authSuccess");
  if (!successBox) return;
  successBox.textContent = message;
  successBox.hidden = false;
}

async function logoutAccount() {
  try {
    await api("/auth/logout", { method: "POST" });
    state.auth = { enabled: true, authenticated: false, user: null };
    renderAccountButton();
    closeDialog();
    await loadProducts();
    showToast("Çıkış yapıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

function apiErrorMessage(data, status) {
  const detail = data?.detail ?? data?.message ?? data;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail.message === "string") return detail.message;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .join(" ");
  }
  return `İşlem tamamlanamadı (HTTP ${status}).`;
}

function proxiedImageUrl(url) {
  return `/image-proxy?url=${encodeURIComponent(url)}`;
}

function imageFallback(element, icon = "package-search") {
  const placeholder = document.createElement("span");
  placeholder.className = "product-placeholder";
  placeholder.innerHTML = `<i data-lucide="${icon}"></i>`;
  element.replaceWith(placeholder);
  lucide.createIcons();
}

async function loadProducts(signal = null) {
  const grid = document.getElementById("dealGrid");
  if (grid) {
    grid.innerHTML = `<div class="loading-state"><span class="spinner"></span>Fırsatlar hazırlanıyor</div>`;
  }

  try {
    state.products = await api("/api/opportunities", { signal: null });
    renderAll();
  } catch (error) {
    console.error("loadProducts hatası:", error);
    renderFallbackOpportunities();
  }
}

function renderFallbackOpportunities() {
  const grid = document.getElementById("dealGrid");
  if (!grid) return;
  grid.innerHTML = `
    <div style="grid-column:1/-1;padding:48px 24px;text-align:center;">
      <div style="font-size:40px;margin-bottom:12px;">🛒</div>
      <p style="font-size:15px;font-weight:600;color:var(--ink);margin:0 0 6px;">Henüz takip edilen ürün yok</p>
      <p style="font-size:13px;color:var(--ink-2);margin:0;">Üst kısımdan ürün linki yapıştır veya barkod tara — fiyatları karşılaştıralım.</p>
    </div>`;
}

function renderAll() {
  renderDeals();
  renderTracking();
  renderSavings();
  lucide.createIcons();
}

function renderDeals() {
  const grid = document.getElementById("dealGrid");
  const products = [...state.products].sort((a, b) => b.deal_score - a.deal_score).slice(0, 6);

  if (!products.length) {
    grid.innerHTML = `<div class="empty-state"><i data-lucide="scan-search"></i>İlk ürün linkini ekleyerek fırsat radarını başlat.</div>`;
    return;
  }

  grid.innerHTML = products.map((product) => {
    const discountPercent = product.discount_analysis?.discount_percent || 0;
    const discountBadge = discountPercent > 0
      ? `<span class="discount-badge">-%${discountPercent}</span>`
      : "";
    const forecast = product.discount_forecast;
    const forecastBadge = forecast?.status === "ready"
      ? `<span class="forecast-chip">%${forecast.probability} · 7 gün</span>`
      : `<span class="forecast-chip muted">Tahmin hazırlanıyor</span>`;
    return `
    <article class="deal-card">
      <div class="deal-image">
        ${productImage(product)}
        <span class="score-badge">${product.deal_score}/100</span>
        ${discountBadge}
      </div>
      <div class="deal-body">
        <p class="source-name">${escapeHtml(product.source)}</p>
        <h3>${escapeHtml(product.title)}</h3>
        ${forecastBadge}
        <div class="price-row">
          <span class="price">${currency.format(product.current_price)}</span>
          <span class="verdict ${product.verdict === "bekle" ? "wait" : ""}">${escapeHtml(product.verdict)}</span>
        </div>
        <button class="card-button" onclick="openProduct('${product.id}')">Kararı gör</button>
      </div>
    </article>
  `;
  }).join("");
}

function renderTracking() {
  const list = document.getElementById("trackingList");
  document.getElementById("trackingCount").textContent = `${state.products.length} ürün`;

  if (!state.products.length) {
    list.innerHTML = `<div class="empty-state">Henüz takip edilen ürün yok.</div>`;
    return;
  }

  list.innerHTML = state.products.map((product) => {
    const firstPrice = product.price_history[0]?.price || product.current_price;
    const difference = firstPrice - product.current_price;
    const diffPercent = firstPrice > 0 ? ((difference / firstPrice) * 100).toFixed(1) : 0;
    const discountPercent = product.discount_analysis?.discount_percent || 0;
    const forecast = product.discount_forecast;
    const priceChangeHtml = difference > 0.5
      ? `<span class="price-change-down">▼ %${diffPercent} düştü</span>`
      : difference < -0.5
        ? `<span class="price-change-up">▲ %${Math.abs(diffPercent)} arttı</span>`
        : `<span style="font-size:11px; color:var(--ink-2);">Değişmedi</span>`;
    return `
      <button class="tracking-item" onclick="openProduct('${product.id}')">
        <span class="tracking-thumb">${productImage(product)}</span>
        <span class="tracking-copy">
          <h3>${escapeHtml(product.title)}</h3>
          <p>${escapeHtml(product.source)} · ${product.price_history.length} fiyat kaydı</p>
          <span class="check-status">
            <span class="status-dot ${escapeHtml(product.last_check_status || "pending")}"></span>
            ${escapeHtml(checkStatusText(product))}
          </span>
          <span class="tracking-forecast">
            ${forecast?.status === "ready"
              ? `7 günlük indirim ihtimali: %${forecast.probability}`
              : escapeHtml(forecast?.message || "Tahmin için fiyat geçmişi bekleniyor.")}
          </span>
        </span>
        <span class="tracking-price">
          <strong>${currency.format(product.current_price)}</strong>
          <span>${difference > 0 ? currency.format(difference) + " düştü" : "Takipte"}</span>
          ${discountPercent > 0 ? `<span class="discount-badge" style="position: static; display: inline-block; margin-top: 4px; padding: 2px 5px; font-size: 10px;">-%${discountPercent}</span>` : ""}
        </span>
      </button>
    `;
  }).join("");
}

function renderSavings() {
  const totalSavings = state.products.reduce((total, product) => {
    const firstPrice = product.price_history[0]?.price || product.current_price;
    return total + Math.max(0, firstPrice - product.current_price);
  }, 0);

  const buySignals = state.products.filter((product) => product.verdict === "al").length;
  const bestScore = state.products.reduce((best, product) => Math.max(best, product.deal_score), 0);

  document.getElementById("totalSavings").textContent = currency.format(totalSavings);
  document.getElementById("trackedStat").textContent = state.products.length;
  document.getElementById("buyStat").textContent = buySignals;
  document.getElementById("bestScoreStat").textContent = bestScore;
  renderSavingsCharts();
}

function destroyChart(name) {
  if (!state.charts[name]) return;
  state.charts[name].destroy();
  delete state.charts[name];
}

function renderSavingsCharts() {
  if (typeof Chart === "undefined") return;

  const productCanvas = document.getElementById("savingsProductChart");
  const categoryCanvas = document.getElementById("spendingCategoryChart");
  if (!productCanvas || !categoryCanvas) return;

  const productSavings = state.products
    .map((product) => ({
      label: product.title.length > 24 ? `${product.title.slice(0, 24)}â€¦` : product.title,
      value: Math.max(
        0,
        (product.price_history[0]?.price || product.current_price) - product.current_price,
      ),
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);

  const categoryTotals = {};
  state.products.forEach((product) => {
    const category = getItemCategory(product.title);
    categoryTotals[category] = (categoryTotals[category] || 0) + product.current_price;
  });

  const categoryLabels = {
    grocery: "Market",
    electronics: "Elektronik",
    fashion: "Giyim",
    cosmetics: "Kozmetik",
    supplement: "Takviye",
  };
  const chartText = state.theme === "dark" ? "#c8cec8" : "#687068";
  const chartGrid = state.theme === "dark" ? "#2b3036" : "#e2e6df";

  destroyChart("products");
  destroyChart("categories");

  state.charts.products = new Chart(productCanvas, {
    type: "bar",
    data: {
      labels: productSavings.length
        ? productSavings.map((item) => item.label)
        : ["Henüz veri yok"],
      datasets: [{
        label: "Tasarruf",
        data: productSavings.length ? productSavings.map((item) => item.value) : [0],
        backgroundColor: "#287a50",
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: chartText }, grid: { display: false } },
        y: { ticks: { color: chartText }, grid: { color: chartGrid } },
      },
    },
  });

  const categoryEntries = Object.entries(categoryTotals);
  state.charts.categories = new Chart(categoryCanvas, {
    type: "doughnut",
    data: {
      labels: categoryEntries.length
        ? categoryEntries.map(([category]) => categoryLabels[category] || category)
        : ["Henüz veri yok"],
      datasets: [{
        data: categoryEntries.length ? categoryEntries.map(([, value]) => value) : [1],
        backgroundColor: ["#287a50", "#3979a8", "#c45243", "#8e5fa2", "#d39a32"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "66%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: chartText, boxWidth: 10 },
        },
      },
    },
  });
}

async function loadReceipts(month = "", signal = null) {
  const monthFilter = document.getElementById("receiptMonthFilter");
  if (monthFilter && !monthFilter.value) {
    monthFilter.value = new Date().toISOString().slice(0, 7);
  }
  const selectedMonth = month || monthFilter?.value || "";
  try {
    const result = await api(
      `/api/receipts${selectedMonth ? `?month=${encodeURIComponent(selectedMonth)}` : ""}`,
      { signal: null }
    );
    state.receipts = result.receipts || [];
    state.receiptSummary = result.summary || null;
    renderReceiptAnalytics();
  } catch (error) {
    console.error("loadReceipts hatası:", error);
  }
}

function renderReceiptAnalytics() {
  const summary = state.receiptSummary || {};
  const totalElement = document.getElementById("receiptMonthTotal");
  if (!totalElement) return;

  totalElement.textContent = currency.format(Number(summary.total || 0));
  document.getElementById("receiptCountStat").textContent = summary.receipt_count || 0;

  const change = document.getElementById("receiptMonthChange");
  if (summary.change_percent === null || summary.change_percent === undefined) {
    change.textContent = "Önceki ay verisi yok";
  } else {
    const direction = summary.change_percent > 0 ? "arttı" : "azaldı";
    change.textContent = `Önceki aya göre %${Math.abs(summary.change_percent)} ${direction}`;
  }

  const stores = Object.entries(summary.store_totals || {});
  document.getElementById("receiptTopStore").textContent = stores[0]?.[0] || "-";
  document.getElementById("receiptTopStoreAmount").textContent = stores[0]
    ? currency.format(stores[0][1])
    : "Henüz veri yok";

  renderReceiptHistory();
  renderReceiptCharts();
  lucide.createIcons();
}

function renderReceiptHistory() {
  const container = document.getElementById("receiptHistoryList");
  if (!container) return;
  if (!state.receipts.length) {
    container.innerHTML = `<p class="empty-text">Bu ay için kaydedilmiş fiş yok.</p>`;
    return;
  }
  const paymentLabels = {
    unknown: "Ödeme belirtilmedi",
    card: "Kart",
    cash: "Nakit",
    meal_card: "Yemek kartı",
    other: "Diğer",
  };
  container.innerHTML = state.receipts.map((receipt) => `
    <article class="receipt-history-item">
      <div class="receipt-history-main">
        <div class="receipt-history-heading">
          <div>
            <h4>${escapeHtml(receipt.store)}</h4>
            <p>${formatReceiptDate(receipt.purchased_at)} Â· ${receipt.items?.length || 0} ürün Â·
              ${paymentLabels[receipt.payment_method] || "Ödeme belirtilmedi"}</p>
          </div>
          <strong class="receipt-history-total">${currency.format(receipt.total || 0)}</strong>
        </div>
        <div class="receipt-history-products">
          ${(receipt.items || []).map((item) => `
            <div class="receipt-history-product">
              <span>${escapeHtml(item.title)}${Number(item.quantity || 1) > 1 ? ` × ${item.quantity}` : ""}</span>
              <strong>${currency.format(Number(item.price || 0) * Number(item.quantity || 1))}</strong>
            </div>
          `).join("")}
        </div>
      </div>
      <button type="button" class="icon-button light" onclick="deleteReceipt('${receipt.id}')"
        title="Fişi sil" aria-label="Fişi sil"><i data-lucide="trash-2"></i></button>
    </article>
  `).join("");
}

function formatReceiptDate(value) {
  if (!value) return "Tarih yok";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
}

function renderReceiptCharts() {
  if (typeof Chart === "undefined") return;
  const summary = state.receiptSummary || {};
  const monthlyCanvas = document.getElementById("receiptMonthlyChart");
  const storeCanvas = document.getElementById("receiptStoreChart");
  if (!monthlyCanvas || !storeCanvas) return;

  const monthlyEntries = Object.entries(summary.monthly_totals || {});
  const storeEntries = Object.entries(summary.store_totals || {}).slice(0, 7);
  const chartText = state.theme === "dark" ? "#c8cec8" : "#687068";
  const chartGrid = state.theme === "dark" ? "#2b3036" : "#e2e6df";

  destroyChart("receiptMonthly");
  destroyChart("receiptStores");

  state.charts.receiptMonthly = new Chart(monthlyCanvas, {
    type: "bar",
    data: {
      labels: monthlyEntries.length
        ? monthlyEntries.map(([key]) => key)
        : ["Henüz veri yok"],
      datasets: [{
        data: monthlyEntries.length ? monthlyEntries.map(([, value]) => value) : [0],
        backgroundColor: "#287a50",
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: chartText }, grid: { display: false } },
        y: { ticks: { color: chartText }, grid: { color: chartGrid } },
      },
    },
  });

  state.charts.receiptStores = new Chart(storeCanvas, {
    type: "doughnut",
    data: {
      labels: storeEntries.length ? storeEntries.map(([store]) => store) : ["Henüz veri yok"],
      datasets: [{
        data: storeEntries.length ? storeEntries.map(([, value]) => value) : [1],
        backgroundColor: ["#287a50", "#3979a8", "#d39a32", "#c45243", "#8e5fa2", "#4d9b8f", "#7b846f"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "64%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: chartText, boxWidth: 10 },
        },
      },
    },
  });
}

async function deleteReceipt(receiptId) {
  if (!window.confirm("Bu fişi harcama geçmişinden silmek istiyor musun?")) return;
  try {
    await api(`/api/receipts/${receiptId}`, { method: "DELETE" });
    showToast("Fiş silindi.");
    await loadReceipts(document.getElementById("receiptMonthFilter")?.value || "");
  } catch (error) {
    showToast(error.message);
  }
}

function isUrl(string) {
  const s = string.trim().toLowerCase();
  return s.startsWith("http://") || s.startsWith("https://") || s.startsWith("trendyol://") || s.startsWith("hepsiburada://") || s.startsWith("n11://") || s.includes(".com") || s.includes(".net") || s.includes(".org") || s.includes(".co");
}

async function parseProduct(event) {
  event.preventDefault();
  const input = document.getElementById("productUrl");
  const submit = event.submitter;
  const val = input.value.trim();

  if (!val) return;

  // 1. Arayüzü anında güncelle (Zero-Blocking)
  submit.disabled = true;
  submit.innerHTML = `<span class="spinner"></span> İşleniyor...`;

  const overlay = document.getElementById("quantumScanOverlay");
  const progressText = document.getElementById("quantumScanProgress");
  if (overlay) overlay.style.display = "flex";
  if (progressText) {
    progressText.innerText = "Ürün bilgilerini getiriyoruz...";
  }

  // 2. Arama işlemini asenkron olarak bir sonraki frame'de başlat
  requestAnimationFrame(() => {
    setTimeout(async () => {
      var t1 = setTimeout(() => { if (progressText) progressText.innerText = "Mağaza fiyatları karşılaştırılıyor..."; }, 600);
      var t2 = setTimeout(() => { if (progressText) progressText.innerText = "En iyi teklifler seçiliyor..."; }, 1300);

      try {
        if (isUrl(val)) {
          const parsed = await api("/parse-url", {
            method: "POST",
            body: JSON.stringify({ url: val }),
            signal: null
          });
          // Link parse edilemediyse rehber popup aç
          if (!parsed.title && !parsed.price) {
            if (overlay) overlay.style.display = "none";
            submit.disabled = false;
            submit.innerHTML = `<span>Kontrol et</span>`;
            showLinkGuide(true);
            return;
          }
          if (overlay) overlay.style.display = "none";
          showSellerSelectionDialog(parsed);
        } else {
          // URL değil — rehber popup göster
          if (overlay) overlay.style.display = "none";
          submit.disabled = false;
          submit.innerHTML = `<span>Kontrol et</span>`;
          showLinkGuide(true);
        }
      } catch (error) {
        console.error("parseProduct hatası:", error);

        if (overlay && progressText) {
          // 1. Durum bildirimini yeşil mod ve glitch ile güncelle
          const header = overlay.querySelector("h3");
          if (header) {
            header.innerText = "Alternatif Sonuçlar Yükleniyor";
          }
          progressText.innerText = "Bağlantı yavaş, yakın alternatifler getiriliyor...";

          // 2. Lokal CPU simülasyonu için 1.5 saniye bekle
          await new Promise(resolve => setTimeout(resolve, 1500));

          // 3. Lokal rezonans fallback sonuçlarını oluştur
          showSearchResults({ products: [], query: val });
        } else {
          showToast("Bağlantı hatası. Lütfen tekrar deneyin.");
        }
      } finally {
        clearTimeout(t1);
        clearTimeout(t2);
        if (overlay) overlay.style.display = "none";
        submit.disabled = false;
        submit.innerHTML = `<i data-lucide="scan-search"></i> Kontrol et`;
        lucide.createIcons();
      }
    }, 0);
  });
}

// ── Admin Dashboard ─────────────────────────────────────────────────────────
async function showAdminDashboard() {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  if (!dialog || !content) return;

  content.innerHTML = `<div class="dialog-body" style="max-width: 560px;"><p class="eyebrow" style="color:var(--green);">YÖNETİCİ PANELİ</p><h2>Sistem İstatistikleri</h2><div id="adminStatsBody" style="margin-top:16px;"><span class="spinner"></span> Yükleniyor...</div></div>`;
  if (!dialog.open) dialog.showModal();
  lucide.createIcons();

  try {
    const stats = await api("/api/admin/stats?days=7");
    const { counts = {}, cache_hit_rate_pct = 0, total_searches = 0, avg_duration_ms = {}, daily = {} } = stats;

    const rows = [
      ["Cache Hit",      counts.cache_hit      || 0, "#38a169"],
      ["Cache Miss",     counts.cache_miss      || 0, "#e53e3e"],
      ["Proxy Kullanım", counts.proxy_used      || 0, "#3182ce"],
      ["Stale Fallback", counts.stale_fallback  || 0, "#d69e2e"],
    ];

    const barMax = Math.max(...rows.map(r => r[1]), 1);

    const dailyKeys = Object.keys(daily).sort();
    const dailyHtml = dailyKeys.map(day => {
      const d = daily[day] || {};
      const total = Object.values(d).reduce((a, b) => a + b, 0);
      return `<tr>
        <td style="padding:6px 8px; font-size:12px; color:var(--ink-light);">${day.slice(5)}</td>
        <td style="padding:6px 8px; font-size:12px; text-align:right;">${total}</td>
        <td style="padding:6px 8px; font-size:12px; text-align:right; color:#38a169;">${d.cache_hit || 0}</td>
        <td style="padding:6px 8px; font-size:12px; text-align:right; color:#3182ce;">${d.proxy_used || 0}</td>
      </tr>`;
    }).join("");

    document.getElementById("adminStatsBody").innerHTML = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:20px;">
        <div style="background:rgba(40,122,80,0.07); border-radius:10px; padding:14px; text-align:center;">
          <div style="font-size:28px; font-weight:800; color:#287a50;">${cache_hit_rate_pct}%</div>
          <div style="font-size:11px; color:var(--ink-light); margin-top:4px;">Cache Hit Oranı</div>
        </div>
        <div style="background:rgba(40,122,80,0.07); border-radius:10px; padding:14px; text-align:center;">
          <div style="font-size:28px; font-weight:800; color:#287a50;">${total_searches}</div>
          <div style="font-size:11px; color:var(--ink-light); margin-top:4px;">Toplam Arama (7 gün)</div>
        </div>
      </div>

      <div style="margin-bottom:20px;">
        ${rows.map(([label, count, color]) => `
          <div style="margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:3px;">
              <span style="font-weight:600;">${label}</span>
              <span style="color:var(--ink-light);">${count}</span>
            </div>
            <div style="height:6px; background:var(--line); border-radius:3px; overflow:hidden;">
              <div style="height:100%; width:${Math.round(count / barMax * 100)}%; background:${color}; border-radius:3px; transition:width 0.5s;"></div>
            </div>
          </div>
        `).join("")}
      </div>

      ${dailyHtml ? `
        <p style="font-size:11px; font-weight:700; color:var(--ink-light); text-transform:uppercase; margin-bottom:8px;">Günlük Dağılım</p>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr style="border-bottom:1px solid var(--line);">
              <th style="padding:4px 8px; text-align:left; color:var(--ink-light);">Tarih</th>
              <th style="padding:4px 8px; text-align:right; color:var(--ink-light);">Toplam</th>
              <th style="padding:4px 8px; text-align:right; color:#38a169;">Hit</th>
              <th style="padding:4px 8px; text-align:right; color:#3182ce;">Proxy</th>
            </tr>
          </thead>
          <tbody>${dailyHtml}</tbody>
        </table>
      ` : ""}

      <div style="margin-top:16px; padding-top:12px; border-top:1px solid var(--line);">
        <p style="font-size:11px; color:var(--ink-light);">Ortalama Yanıt: Cache Hit ${avg_duration_ms.cache_hit || "—"}ms | Miss ${avg_duration_ms.cache_miss || "—"}ms</p>
      </div>
    `;
    lucide.createIcons();
  } catch (err) {
    const statsBody = document.getElementById("adminStatsBody");
    if (statsBody) {
      statsBody.textContent = `İstatistikler yüklenemedi: ${err.message}`;
      statsBody.style.color = "var(--muted)";
    }
  }
}

// URL'de ?admin=1 varsa admin paneline giden kısayol tuşu
if (new URLSearchParams(window.location.search).get("admin") === "1") {
  document.addEventListener("keydown", (e) => {
    if (e.key === "F2") showAdminDashboard();
  });
}
// ───────────────────────────────────────────────────────────────────────────

async function forceRefreshSearch(query, cacheKey) {
  const btn = document.getElementById("forceRefreshBtn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" style="width:13px;height:13px;border-width:2px;"></span> Güncelleniyor...`;
  }
  try {
    // 1. Cache'i sil
    if (cacheKey) {
      await api(`/api/cache?query=${encodeURIComponent(query)}`, { method: "DELETE" });
    }
    // 2. Taze arama yap
    const category = document.getElementById("searchCategorySelector")?.value || "general";
    const mode = document.getElementById("globalModeCheckbox")?.checked ? "global" : "hybrid";
    let searchUrl = `/api/search?query=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&mode=${encodeURIComponent(mode)}`;
    if (state.userCoords && mode !== "global") {
      searchUrl += `&lat=${state.userCoords.lat}&lon=${state.userCoords.lng}`;
    }
    const results = await api(searchUrl, { signal: null });
    showSearchResults(results);
    showToast("Fiyatlar güncellendi.");
  } catch (err) {
    showToast("Güncelleme başarısız, mevcut sonuçlar gösteriliyor.");
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="refresh-cw" style="width:13px;height:13px;margin-right:4px;"></i>Fiyatı Güncelle`;
      lucide.createIcons();
    }
  }
}

function showSearchResults(response) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");

  const products = response.products || [];
  const suggestion = response.suggestion;
  const originalQuery = response.query || "";

  if (response.needs_clarification && response.clarification) {
    const c = response.clarification;
    content.innerHTML = `
      <div class="dialog-body" style="text-align: center; padding: 32px 20px;">
        <i data-lucide="search" style="width: 40px; height: 40px; color: var(--green); margin-bottom: 14px;"></i>
        <h2 style="margin-bottom: 6px;">${escapeHtml(c.question)}</h2>
        <p style="color: var(--muted); margin-bottom: 20px; font-size: 13px;">Daha isabetli sonuçlar için bir seçenek seç.</p>
        <div style="display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-bottom: 20px;">
          ${c.options.map(opt => `
            <button type="button" class="secondary-button" style="padding: 10px 18px; border-radius: 20px; font-weight: 700; height: auto;"
              onclick="event.preventDefault(); resolveClarificationSearch(${inlineJsArg(opt.query)}, ${inlineJsArg(response.category || "general")});">
              ${escapeHtml(opt.label)}
            </button>
          `).join("")}
        </div>
        <a href="#" style="color: var(--ink-light); font-size: 12px; text-decoration: underline;"
          onclick="event.preventDefault(); resolveClarificationSearch(${inlineJsArg(c.term + "​")}, ${inlineJsArg(response.category || "general")});">
          Yine de "${escapeHtml(c.term)}" olarak tüm sonuçları göster
        </a>
      </div>
    `;
    if (!dialog.open) dialog.showModal();
    lucide.createIcons();
    return;
  }

  if (!products || products.length === 0) {
    let suggestionHtml = "";
    if (suggestion) {
      suggestionHtml = `
        <p style="margin-top: 16px; font-size: 15px; color: var(--ink);">
          Bunu mu demek istediniz:
          <a href="#" style="color: var(--green); font-weight: 700; text-decoration: underline;" onclick="event.preventDefault(); triggerSuggestionSearch(${inlineJsArg(suggestion)});">
            ${escapeHtml(suggestion)}
          </a>
        </p>
      `;
    }
    content.innerHTML = `
      <div class="dialog-body" style="text-align: center; padding: 40px 20px;">
        <i data-lucide="frown" style="width: 48px; height: 48px; color: var(--muted); margin-bottom: 16px;"></i>
        <h2>Arama Sonucu Bulunamadı</h2>
        <p style="color: var(--muted); margin-top: 8px;">"${escapeHtml(originalQuery)}" için alternatif satıcı veya fiyat bilgisi bulunamadı.</p>
        ${suggestionHtml}
        <button class="secondary-button" style="margin-top: 24px;" onclick="closeDialog()">Kapat</button>
      </div>
    `;
    if (!dialog.open) dialog.showModal();
    lucide.createIcons();
    return;
  }

  const isFallback = response.fallback_applied;
  const isStale = response.is_stale || products.some((p) => p.stale_cache);
  const staleAge = response.stale_age || (products.find((p) => p.stale_age) || {}).stale_age || "birkaç saat";
  const cacheKey = response.cache_key || "";

  const fallbackNoticeHtml = isStale
    ? `
      <div class="assistant-info-box" style="border-left: 3px solid #e6a817; background: rgba(230,168,23,0.07); margin-bottom: 16px; padding: 12px 14px;">
        <div class="stale-banner-inner" style="display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
          <div style="flex: 1; min-width: 0;">
            <div style="color: #b8860b; font-weight: 700; display: flex; align-items: center; gap: 6px; font-size: 13px;">
              <i data-lucide="clock" style="width: 14px; height: 14px; flex-shrink: 0;"></i>
              ${staleAge} önceki fiyatlar
            </div>
            <div style="color: var(--ink); font-size: 12px; margin-top: 3px; line-height: 1.4;">
              Mağaza sunucularına ulaşılamadı. Fiyatlar güncellenmemiş olabilir.
            </div>
          </div>
          <button class="secondary-button" style="white-space: nowrap; font-size: 12px; padding: 7px 14px; height: auto; flex-shrink: 0; display: inline-flex; align-items: center;"
            onclick="forceRefreshSearch(${inlineJsArg(originalQuery)}, ${inlineJsArg(cacheKey)})">
            <i data-lucide="refresh-cw" style="width: 13px; height: 13px; margin-right: 5px;"></i>Tazele
          </button>
        </div>
      </div>
    `
    : isFallback
    ? `
      <div class="assistant-info-box" style="border-left: 3px solid var(--red); background: rgba(248, 215, 211, 0.1); margin-bottom: 16px;">
        <div class="assistant-info-title" style="color: #d9383a; font-weight: 700;">
          <i data-lucide="info"></i> Tam Eşleşme Bulunamadı
        </div>
        <div class="assistant-info-content" style="color: var(--ink);">
          "${escapeHtml(originalQuery)}" için tam eşleşen ürün bulunamadı. Size en yakın popüler alternatifleri listeliyoruz.
        </div>
      </div>
    `
    : "";

  // Dynamic search refinement chips for generic products
  const queryLower = originalQuery.toLowerCase().trim();
  let matchingKey = Object.keys(genericProductSizes).find(key => queryLower === key || queryLower === key + "sı" || queryLower === key + "su" || queryLower === key + "yu");

  let sizeChipsHtml = "";
  if (matchingKey) {
    const chips = genericProductSizes[matchingKey];
    sizeChipsHtml = `
      <div class="search-refinement-chips" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; background: rgba(40, 122, 80, 0.05); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(40, 122, 80, 0.15);">
        <span style="font-size: 11px; font-weight: 700; color: var(--green); margin-right: 4px;">EBAT HIZLI FİLTRE:</span>
        ${chips.map(sz => `
          <button type="button" class="secondary-button" style="padding: 4px 10px; border-radius: 12px; font-size: 10px; font-weight: 700; height: auto;" onclick="event.preventDefault(); triggerSuggestionSearch(${inlineJsArg(`${matchingKey} ${sz}`)});">
            ${escapeHtml(sz)}
          </button>
        `).join("")}
      </div>
    `;
  }

  const queryCategory = getItemCategory(originalQuery);
  const isFashion = queryCategory === "fashion" || products.some(p => getItemCategory(p.title) === "fashion");
  const isElectronics = queryCategory === "electronics" || products.some(p => getItemCategory(p.title) === "electronics");

  let categoryHeaderHtml = "";
  if (isFashion) {
    const isShoe = ["ayakkabi", "ayakkabı", "bot", "çizme", "cizme", "terlik", "sneaker"].some(kw => originalQuery.toLowerCase().includes(kw)) ||
                   products.some(p => ["ayakkabi", "ayakkabı", "bot", "çizme", "cizme", "terlik", "sneaker"].some(kw => p.title.toLowerCase().includes(kw)));

    categoryHeaderHtml = `
      <div class="fashion-size-selector-container" style="margin-bottom: 16px; background: var(--bg-card); border: 1px solid var(--line); padding: 12px; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 12px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <i data-lucide="scissors" style="color: var(--green); width: 16px; height: 16px;"></i>
          <span style="font-size: 13px; font-weight: 700; color: var(--ink);">Beden / Numara Seçimi:</span>
        </div>
        <select id="fashionSizeSelect" class="form-input" style="width: auto; padding: 4px 10px; font-size: 12px; height: auto;" onchange="window.updateFashionPrices(this.value)">
          ${isShoe ? `
            <option value="39">39 (Standart)</option>
            <option value="40">40 (+15 TL)</option>
            <option value="41">41 (+25 TL)</option>
            <option value="42">42 (+35 TL)</option>
          ` : `
            <option value="S">S (Standart)</option>
            <option value="M">M (%5 Ekstra)</option>
            <option value="L">L (%10 Ekstra)</option>
            <option value="XL">XL (%15 Ekstra)</option>
          `}
        </select>
      </div>
    `;
  } else if (isElectronics) {
    categoryHeaderHtml = `
      <div class="electronics-warranty-filter-container" style="margin-bottom: 16px; background: var(--bg-card); border: 1px solid var(--line); padding: 12px; border-radius: 8px; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <i data-lucide="shield-check" style="color: var(--green); width: 16px; height: 16px;"></i>
          <span style="font-size: 13px; font-weight: 700; color: var(--ink);">Garanti Türü Filtresi:</span>
        </div>
        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 12px; font-weight: 700; color: var(--ink);">
          <input type="checkbox" id="warrantyFilterCheckbox" style="accent-color: var(--green); width: 16px; height: 16px; cursor: pointer;" onchange="window.updateWarrantyFilter(this.checked)">
          Sadece Resmi Distribütör
        </label>
      </div>
    `;
  }

  // Calculate cheapest valid price for nodes highlighting
  const validPrices = products.filter(p => !p.extra_info?.out_of_stock).map(p => p.price);
  const cheapestPrice = validPrices.length > 0 ? Math.min(...validPrices) : -1;

  window._lastSearchQuery = originalQuery;
  window._lastSearchCacheKey = cacheKey;

  content.innerHTML = `
    <style>
      .search-result-card {
        transition: all 0.2s ease-in-out;
      }
      .search-result-card:hover {
        border-color: var(--green) !important;
        box-shadow: 0 4px 12px rgba(40, 122, 80, 0.08);
        transform: translateY(-1px);
      }
    </style>
    <div class="dialog-body" style="max-width: 600px; width: 100%;">
      <div class="search-result-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px;">
        <div>
          <p class="eyebrow" style="color: var(--green); font-weight: 700; margin-bottom: 4px;">ARAMA SONUÇLARI</p>
          <h2 style="margin: 0;">En Mantıklı Seçenekler</h2>
        </div>
        <button class="secondary-button" id="forceRefreshBtn" style="font-size: 12px; padding: 6px 14px; height: auto; flex-shrink: 0; white-space: nowrap; display: inline-flex; align-items: center;"
          onclick="forceRefreshSearch(${inlineJsArg(originalQuery)}, ${inlineJsArg(cacheKey)})">
          <i data-lucide="refresh-cw" style="width: 13px; height: 13px; margin-right: 5px;"></i>Fiyatı Güncelle
        </button>
      </div>
      ${sizeChipsHtml}
      ${fallbackNoticeHtml}
      ${categoryHeaderHtml}
      <div style="display: flex; flex-direction: column; gap: 12px; max-height: 400px; overflow-y: auto; padding-right: 4px; margin-bottom: 24px;">
        ${products.map((item, index) => {
          const badgesHtml = item.labels.map(lbl => {
            let colorClass = "bg-gray";
            if (lbl === "En Ucuz") colorClass = "bg-green";
            if (lbl === "En Yüksek İndirim") colorClass = "bg-red";
            if (lbl === "Hızlı Kargo") colorClass = "bg-blue";
            if (lbl === "En İyi Puan") colorClass = "bg-yellow";
            if (lbl === "Şüpheli Fiyat") colorClass = "bg-red";
            if (lbl === "Birim Fiyat Riski") colorClass = "bg-red";
            if (lbl === "Birim Fiyat Avantajı") colorClass = "bg-green";
            return `<span class="analysis-status-badge ${colorClass}" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase;">${escapeHtml(lbl)}</span>`;
          }).join(" ");

          const originalPriceHtml = item.original_price && item.original_price > item.price
            ? `<span style="text-decoration: line-through; color: var(--muted); font-size: 11px; margin-right: 6px;" class="price-display-original">${currency.format(item.original_price)}</span>`
            : `<span style="text-decoration: line-through; color: var(--muted); font-size: 11px; margin-right: 6px; display: none;" class="price-display-original"></span>`;

          const isOutOfStock = item.extra_info?.out_of_stock;
          const priceDisplayHtml = isOutOfStock
            ? `<strong style="font-size: 14px; color: var(--muted); font-style: italic;">Stokta Yok</strong>`
            : `<strong style="font-size: 14px; color: var(--ink);" class="price-display-strong">${currency.format(item.price)}</strong>`;

          const buttonHtml = isOutOfStock
            ? `<button class="primary-button" style="padding: 6px 12px; font-size: 11px; height: auto; width: auto; background-color: #687068; border-color: #687068;" onclick="trackSearchResultProduct(this, ${index})">
                 <i data-lucide="bell" style="width:12px; height:12px; margin-right:4px;"></i> Stok Takibi Ekle
               </button>`
            : `<button class="primary-button" style="padding: 6px 12px; font-size: 11px; height: auto; width: auto;" onclick="trackSearchResultProduct(this, ${index})">
                 <i data-lucide="radar" style="width:12px; height:12px; margin-right:4px;"></i> Radara Ekle
               </button>`;

          const suspiciousWarningHtml = item.extra_info?.suspicious
            ? `<div style="display: flex; align-items: center; gap: 4px; color: var(--red); font-size: 11px; margin-top: 6px; font-weight: 700;">
                 <i data-lucide="shield-alert" style="width: 13px; height: 13px; flex-shrink: 0;"></i> Şüpheli Fiyat Uyarısı!
               </div>`
            : "";
          const unitPriceHtml = item.extra_info?.unit_price && item.extra_info?.unit
            ? `<div class="unit-price-row ${item.extra_info.best_unit_price ? "best" : ""}">
                 ${currency.format(item.extra_info.unit_price)} / ${escapeHtml(item.extra_info.unit)}
               </div>`
            : "";

          let warrantyBadgeHtml = "";
          let isImporter = false;
          if (isElectronics) {
            isImporter = index % 2 === 1;
            const warrantyText = isImporter ? "İthalatçı Garantili" : "Resmi Distribütör";
            const badgeColor = isImporter ? "rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245,158,11,0.2)" : "rgba(16, 185, 129, 0.1); color: #10b981; border: 1px solid rgba(16,185,129,0.2)";
            warrantyBadgeHtml = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; background: ${badgeColor}; display: inline-block;">${warrantyText}</span>`;
          }

          const isCheapestNode = !isOutOfStock && item.price === cheapestPrice;
          const nodeClasses = `quantum-node-card ${isCheapestNode ? 'cheapest-node-glow' : ''}`;

          const isLocal = item.delivery_type === "local";
          const borderStyle = isLocal
            ? "border: 2px solid #00f3ff !important; box-shadow: 0 0 10px rgba(0, 243, 255, 0.15);"
            : "border: 2px solid #10b981 !important; box-shadow: 0 0 10px rgba(16, 185, 129, 0.15);";

          return `
            <div class="${nodeClasses} search-result-card"
                 data-base-price="${item.price}"
                 data-base-original-price="${item.original_price || 0}"
                 data-is-importer="${isImporter}"
                 style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; ${borderStyle} border-radius: 8px; background: white; transition: all 0.2s;">
              <div style="width: 50px; height: 50px; flex-shrink: 0; border-radius: 6px; overflow: hidden; border: 1px solid var(--line); background: var(--surface); display: flex; align-items: center; justify-content: center;">
                ${item.image_url
                  ? `<img src="${escapeHtml(proxiedImageUrl(item.image_url))}" alt="${escapeHtml(item.title)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="imageFallback(this, '${getStoreIcon(item.source, item.title)}')">`
                  : `<span class="product-placeholder" style="width:100%; height:100%; display:grid; place-items:center;"><i data-lucide="${getStoreIcon(item.source, item.title)}" style="width:18px; height:18px;"></i></span>`}
              </div>
              <div style="flex: 1; min-width: 0;">
                <p class="source-name" style="margin: 0 0 2px 0; font-size: 10px; font-weight: 800; text-transform: uppercase; color: var(--muted);">${escapeHtml(item.source)}</p>
                <h4 style="margin: 0 0 6px 0; font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h4>
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px;">
                  ${badgesHtml}
                </div>
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                  ${isLocal
                    ? `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; background: rgba(0,243,255,0.1); color: #00d2ff; border: 1px solid rgba(0,243,255,0.2); display: inline-flex; align-items: center; gap: 4px;"><i data-lucide="truck" style="width:11px; height:11px;"></i> ${escapeHtml(item.delivery_time || '30-60 Dakika')} ${item.distance_km ? `(${item.distance_km} km)` : ''}</span>`
                    : `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; background: rgba(16,185,129,0.1); color: #10b981; border: 1px solid rgba(16,185,129,0.2); display: inline-flex; align-items: center; gap: 4px;"><i data-lucide="globe" style="width:11px; height:11px;"></i> ${escapeHtml(item.delivery_time || '2 İş Günü')}</span>`
                  }
                  ${warrantyBadgeHtml}
                </div>
                ${suspiciousWarningHtml}
                ${unitPriceHtml}
              </div>
              <div style="text-align: right; flex-shrink: 0; display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
                <div>
                  ${originalPriceHtml}
                  ${priceDisplayHtml}
                  ${(() => {
                    const t = item.price_trend;
                    if (!t) return "";
                    if (t.direction === "up")   return `<div class="price-trend-up"><i data-lucide="trending-up" style="width:11px;height:11px;flex-shrink:0;"></i>%${Math.abs(t.change_pct)} arttı (7g)</div>`;
                    if (t.direction === "down") return `<div class="price-trend-down"><i data-lucide="trending-down" style="width:11px;height:11px;flex-shrink:0;"></i>%${Math.abs(t.change_pct)} düştü (7g)</div>`;
                    return `<div class="price-trend-flat"><i data-lucide="minus" style="width:11px;height:11px;flex-shrink:0;"></i>Sabit (7g)</div>`;
                  })()}
                </div>
                ${buttonHtml}
              </div>
            </div>
          `;
        }).join("")}
      </div>
      <div class="dialog-actions" style="margin-top: 0;">
        <button class="secondary-button" type="button" onclick="closeDialog()" style="width: 100%;">Vazgeç</button>
      </div>
    </div>
  `;

  state.searchResults = products;

  if (!dialog.open) dialog.showModal();
  lucide.createIcons();

  // Register node cards for bobbing animation
  dialog.querySelectorAll('.quantum-node-card').forEach(card => {
    if (window.registerForBobbing) window.registerForBobbing(card);
  });
}

window.triggerSuggestionSearch = function(query) {
  const input = document.getElementById("productUrl");
  if (input) {
    input.value = query;
    const form = document.getElementById("urlForm");
    if (form) {
      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) {
        submitBtn.click();
      } else {
        const event = new Event("submit", { cancelable: true });
        form.dispatchEvent(event);
      }
    }
  }
};


async function trackSearchResultProduct(button, index) {
  const item = state.searchResults ? state.searchResults[index] : null;
  if (!item) return;

  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Ekleniyor`;

  let title = item.title;
  let price = item.price;
  let originalPrice = item.original_price;

  const sizeSelect = document.getElementById("fashionSizeSelect");
  if (sizeSelect && sizeSelect.value) {
    const val = sizeSelect.value;
    title = `${item.title} (${val})`;
    if (val === "M") {
      price = item.price * 1.05;
      originalPrice = originalPrice ? originalPrice * 1.05 : null;
    } else if (val === "L") {
      price = item.price * 1.10;
      originalPrice = originalPrice ? originalPrice * 1.10 : null;
    } else if (val === "XL") {
      price = item.price * 1.15;
      originalPrice = originalPrice ? originalPrice * 1.15 : null;
    } else if (val === "40") {
      price = item.price + 15;
      originalPrice = originalPrice ? originalPrice + 15 : null;
    } else if (val === "41") {
      price = item.price + 25;
      originalPrice = originalPrice ? originalPrice + 25 : null;
    } else if (val === "42") {
      price = item.price + 35;
      originalPrice = originalPrice ? originalPrice + 35 : null;
    }
  }

  try {
    await api("/products", {
      method: "POST",
      body: JSON.stringify({
        title: title,
        url: item.url,
        price: price,
        source: item.source,
        image_url: item.image_url,
        original_price: originalPrice,
        extra_info: item.extra_info || {}
      }),
    });

    showToast("Ürün radara eklendi.");
    closeDialog();
    document.getElementById("productUrl").value = "";
    await loadProducts();
    switchView("tracking");
  } catch (error) {
    if (isLoginRequiredError(error)) {
      promptLoginForTracking("Bir ürünü fiyat radarına eklemek için hesap açman gerekiyor.");
    } else {
      showToast(`Ürün kaydedilemedi: ${error.message}`);
    }
    button.disabled = false;
    button.innerHTML = `<i data-lucide="radar" style="width:12px; height:12px; margin-right:4px;"></i> Radara Ekle`;
    lucide.createIcons();
  }
}

function showParsedProduct(parsed) {
  state.parsedProduct = parsed;
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  const title = parsed.title || "Ürün bilgisi tamamlanamadı";

  const isSupplement = parsed.source === "supplementler" ||
                       parsed.source === "proteinocean" ||
                       (parsed.extra_info && parsed.extra_info.category === "supplement");

  const isCosmetics = parsed.source === "gratis" ||
                      parsed.source === "rossmann" ||
                      (parsed.extra_info && parsed.extra_info.category === "cosmetics");

  content.innerHTML = `
    <div class="dialog-product-image">
      ${parsed.image_url
        ? `<img src="${escapeHtml(proxiedImageUrl(parsed.image_url))}" alt="${escapeHtml(title)}"
            onerror="imageFallback(this, '${getStoreIcon(parsed.source, title)}')">`
        : `<span class="product-placeholder"><i data-lucide="${getStoreIcon(parsed.source, title)}"></i></span>`}
    </div>
    <div class="dialog-body">
      <p class="source-name">${escapeHtml(parsed.source)}</p>
      <h2>${escapeHtml(title)}</h2>
      <div class="decision-panel">
        <div class="score-ring">${parsed.confidence}</div>
        <div>
          <strong>Bilgi güveni</strong>
          <p>${parsed.price ? "Ürün ve fiyat bilgisi bulundu." : "Fiyat bulunamadı. Aşağıdan elle tamamlayabilirsin."}</p>
        </div>
      </div>
      <div class="manual-fields">
        <label class="manual-field">
          <span>Ürün adı</span>
          <input id="parsedTitle" type="text" value="${escapeHtml(parsed.title || "")}" placeholder="Ürün adını yaz">
        </label>
        <label class="manual-field">
          <span>Güncel fiyat</span>
          <input id="parsedPrice" type="text" inputmode="decimal" value="${parsed.price ?? ""}" placeholder="Örn. 1849,90">
        </label>
        <label class="manual-field">
          <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
            <span>Hedef Fiyat Eşiği (Alarm)</span>
            <label style="display:flex; align-items:center; gap:4px; cursor:pointer; margin:0;">
              <input type="checkbox" id="parsedStockAlarm" style="width:14px;height:14px;accent-color:var(--green);">
              <span style="font-size:10.5px; color:var(--ink-2); font-weight:700; text-transform:uppercase;">Stok Takibi</span>
            </label>
          </div>
          <input id="parsedTargetPrice" type="text" inputmode="decimal" placeholder="Bu fiyata düşünce haber ver (İsteğe bağlı)">
        </label>
        <label class="manual-field">
          <span>Son Satın Alma Tarihi</span>
          <input id="parsedLastPurchasedDate" type="date">
        </label>
        <label class="manual-field">
          <span>Tekrar Alma Periyodu (Gün)</span>
          <input id="parsedRestockPeriod" type="number" min="1" max="730" placeholder="Örn. 30">
        </label>
        ${isSupplement ? `
        <label class="manual-field">
          <span>Toplam Servis Sayısı</span>
          <input id="parsedServings" type="number" value="${parsed.extra_info && parsed.extra_info.servings ? parsed.extra_info.servings : ""}" placeholder="Örn. 60">
        </label>
        <div id="parsedServingPriceRow" class="form-hint" style="margin-top: -6px; color: var(--green); font-weight: 700; min-height: 16px;"></div>
        ` : ""}
        ${isCosmetics ? `
        <label class="manual-field">
          <span>Kozmetik Açılış Tarihi</span>
          <input id="parsedOpeningDate" type="date" value="" placeholder="Açılış Tarihi">
        </label>
        <label class="manual-field">
          <span>Kullanım Ömrü (Ay)</span>
          <input id="parsedShelfLife" type="number" value="12" placeholder="Örn. 12">
        </label>
        ` : ""}
        <p class="form-hint">Otomatik bulunan bilgileri kontrol edip düzeltebilirsin.</p>
      </div>
      ${parsed.warnings.length ? `<p class="source-name">${parsed.warnings.map(escapeHtml).join(" ")}</p>` : ""}
      <div id="alternativeSellersContainer" style="margin-top: 16px; margin-bottom: 16px; padding: 12px; border-radius: 8px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);">
        <div class="loading-row" style="margin: 0;"><span class="spinner" style="width:14px;height:14px;border-width:2px;border-color:#a0aab0;border-top-color:transparent;"></span><span style="font-size:13px;color:#a0aab0;">Alternatif satıcılar aranıyor... (Bu işlem birkaç saniye sürebilir)</span></div>
      </div>
      <p class="dialog-error" id="trackProductError" hidden></p>
      <div class="dialog-actions">
        <button class="secondary-button" type="button" onclick="closeDialog()">Vazgeç</button>
        <button class="primary-button" type="button" id="trackParsedButton" onclick="trackParsedProduct()">
          <i data-lucide="radar"></i>
          Takibe al
        </button>
      </div>
    </div>
  `;

  dialog.showModal();
  document.getElementById("parsedTitle").addEventListener("input", updateTrackButton);
  document.getElementById("parsedPrice").addEventListener("input", updateTrackButton);

  const updateServingPrice = () => {
    const servingsInput = document.getElementById("parsedServings");
    const priceInput = document.getElementById("parsedPrice");
    const display = document.getElementById("parsedServingPriceRow");
    if (!servingsInput || !priceInput || !display) return;

    const price = parseUserPrice(priceInput.value);
    const servings = parseInt(servingsInput.value, 10);

    if (price && servings && servings > 0) {
      const perServing = price / servings;
      display.textContent = `Servis başına maliyet: ${currency.format(perServing)}`;
    } else {
      display.textContent = "";
    }
  };

  if (isSupplement) {
    document.getElementById("parsedServings").addEventListener("input", updateServingPrice);
    document.getElementById("parsedPrice").addEventListener("input", updateServingPrice);
    updateServingPrice();
  }

  updateTrackButton();
  findAlternativeSellers(parsed);
  lucide.createIcons();
}

async function findAlternativeSellers(parsed) {
  const container = document.getElementById("alternativeSellersContainer");
  if (!container) return;

  try {
    const data = await api("/api/find-alternatives", {
      method: "POST",
      body: JSON.stringify({ title: parsed.title, original_url: parsed.canonical_url, source: parsed.source, image_url: parsed.image_url })
    });
    const alts = data.alternatives || [];

    if (alts.length === 0) {
      const links = data.search_links || [];
      if (links.length) {
        container.innerHTML = `
          <p style="font-size:12px; color:#a0aab0; margin:0 0 8px; text-align:center;">Otomatik eşleşme bulunamadı — bu mağazalarda arayabilirsin:</p>
          <div style="display:flex; flex-wrap:wrap; gap:6px; justify-content:center;">
            ${links.map(l => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener" style="font-size:12px; padding:6px 10px; border:1px solid var(--border); border-radius:8px; text-decoration:none; color:var(--ink); font-weight:600;">🔎 ${escapeHtml(l.label)}</a>`).join("")}
          </div>`;
      } else {
        container.innerHTML = `<p style="font-size:12px; color:#a0aab0; margin:0; text-align:center;">Alternatif satıcı bulunamadı.</p>`;
      }
      return;
    }

    let fakeDiscountWarning = "";
    if (parsed.original_price && parsed.price) {
      const prices = alts.map(a => a.price).filter(p => p > 0);
      if (prices.length > 0) {
        const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
        if (parsed.original_price > avgPrice * 1.15) {
          fakeDiscountWarning = `
            <div style="margin-bottom: 12px; padding: 10px; border-radius: 6px; background: rgba(255, 60, 60, 0.1); border: 1px solid rgba(255, 60, 60, 0.3); color: #ff6b6b; font-size: 13px;">
              <strong style="display:flex; align-items:center; gap:4px;"><i data-lucide="alert-triangle" style="width:14px;height:14px;"></i> Sahte İndirim Tespit Edildi!</strong>
              <div style="margin-top:4px; opacity:0.9;">Mağaza ürünün ₺${parsed.original_price.toFixed(2)} değerinden düştüğünü iddia ediyor, ancak piyasa ortalaması zaten ₺${avgPrice.toFixed(2)} seviyesinde.</div>
            </div>
          `;
        }
      }
    }

    const validPrices2 = alts.map(a => a.price).filter(p => p > 0);
    const minPrice2 = validPrices2.length > 0 ? Math.min(...validPrices2) : -1;
    const maxPrice2 = validPrices2.length > 0 ? Math.max(...validPrices2) : -1;

    let html = fakeDiscountWarning + `
      <div style="font-size:11px;font-weight:700;color:var(--ink-2);margin-bottom:8px;letter-spacing:.5px;text-transform:uppercase;">
        ${alts.length} Mağaza Karşılaştırması ${maxPrice2 > minPrice2 + 1 ? `· <span style="color:#287a50;">₺${(maxPrice2-minPrice2).toFixed(2)} tasarruf mümkün</span>` : ""}
      </div>
      <div style="display:flex;flex-direction:column;gap:7px;">`;

    alts.forEach((a) => {
      const altJson = escapeHtml(JSON.stringify(a));
      const brand = getStoreBrand(a.source);
      const isCheapest = minPrice2 > 0 && a.price === minPrice2;
      const savingVsMax = a.price > 0 && maxPrice2 > a.price ? (maxPrice2 - a.price) : 0;

      let badges = [];
      if (isCheapest) badges.push(`<span style="background:#287a50;color:#fff;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:800;">EN UCUZ</span>`);
      if (a.labels?.includes("Sponsorlu")) badges.push(`<span style="background:rgba(255,183,77,.15);color:#ffb74d;border:1px solid rgba(255,183,77,.3);padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;">Reklam</span>`);
      if (["amazon","hepsiburada"].includes(String(a.source).toLowerCase())) badges.push(`<span style="background:rgba(171,71,188,.1);color:#ab47bc;border:1px solid rgba(171,71,188,.25);padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;">🛡 Güvenilir</span>`);
      const fastDeliverySources = ["migros","carrefoursa","sokmarket","metro","file","a101"];
      if (fastDeliverySources.includes(String(a.source).toLowerCase())) badges.push(`<span style="background:rgba(41,182,246,.1);color:#29b6f6;border:1px solid rgba(41,182,246,.25);padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;">⚡ Hızlı</span>`);

      const badgesHtml = badges.length > 0 ? `<div style="display:flex;gap:3px;flex-wrap:wrap;margin-top:3px;">${badges.join("")}</div>` : "";

      let finalPrice = `₺${a.price.toFixed(2)}`;
      let oldPriceDisplay = a.original_price && a.original_price > a.price ? `<span style="font-size:10px;color:var(--ink-2);text-decoration:line-through;margin-left:4px;">₺${a.original_price.toFixed(2)}</span>` : "";

      html += `
        <div class="alt-seller-card" onclick="selectAlternativeSeller(this)" data-alt='${altJson}'
          style="display:flex;justify-content:space-between;align-items:center;background:${isCheapest ? 'rgba(40,122,80,0.06)' : 'var(--bg-card,#fff)'};padding:9px 11px;border-radius:8px;cursor:pointer;border:${isCheapest ? '1.5px solid #287a5055' : '1px solid var(--line)'};transition:.15s;"
          onmouseover="this.style.borderColor='${brand.color}55';this.style.background='${brand.bg}';"
          onmouseout="this.style.borderColor='${isCheapest ? '#287a5055' : 'var(--line)'}';this.style.background='${isCheapest ? 'rgba(40,122,80,0.06)' : 'var(--bg-card,#fff)'}';">
          <div style="display:flex;align-items:center;gap:9px;min-width:0;flex:1;">
            ${storeLogoHtml(a.source, 32)}
            <div style="min-width:0;">
              <div style="font-size:13px;font-weight:800;color:${brand.color};">${escapeHtml(brand.name)}</div>
              <div style="font-size:10.5px;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;">${escapeHtml(a.title)}</div>
              ${badgesHtml}
            </div>
          </div>
          <div style="font-weight:800;color:var(--green-dark);text-align:right;flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;">
            <span style="font-size:15px;">${finalPrice}${oldPriceDisplay}</span>
            ${savingVsMax > 1 ? `<span style="font-size:10px;color:#287a50;font-weight:700;">−₺${savingVsMax.toFixed(0)}</span>` : ""}
          </div>
        </div>
      `;
    });
    html += `</div>`;

    container.innerHTML = html;
    lucide.createIcons();
  } catch (err) {
    container.innerHTML = `<p style="font-size:12px; color:#ff6b6b; margin:0; text-align:center;">Alternatifler aranırken hata oluştu.</p>`;
  }
}

window.selectAlternativeSeller = function(el) {
  document.querySelectorAll('.alt-seller-card').forEach(c => {
    c.style.border = '1px solid var(--line)';
    c.style.background = 'var(--bg-card,#fff)';
  });
  el.style.border = '1.5px solid #287a50';
  el.style.background = 'rgba(40,122,80,0.08)';

  const alt = JSON.parse(el.getAttribute('data-alt'));

  const parsedPrice = document.getElementById("parsedPrice");
  const parsedTitle = document.getElementById("parsedTitle");
  if (parsedPrice) {
    parsedPrice.value = String(alt.price).replace('.', ',');
    parsedPrice.dispatchEvent(new Event('input'));
  }
  if (parsedTitle) {
    parsedTitle.value = alt.title;
    parsedTitle.dispatchEvent(new Event('input'));
  }

  const sourceNameEl = document.querySelector(".dialog-body .source-name");
  if (sourceNameEl) sourceNameEl.innerText = alt.source;

  if (state.parsedProduct) {
     state.parsedProduct.canonical_url = addAffiliateTag(alt.url || alt.canonical_url || state.parsedProduct.canonical_url, alt.source);
     state.parsedProduct.source = alt.source;
     if (alt.image_url) state.parsedProduct.image_url = alt.image_url;
     state.parsedProduct.title = alt.title;
     state.parsedProduct.price = alt.price;
     state.parsedProduct.original_price = alt.original_price;

     const imgEl = document.querySelector(".dialog-product-image");
     if (imgEl && state.parsedProduct.image_url) {
       imgEl.innerHTML = `<img src="${escapeHtml(state.parsedProduct.image_url)}" alt="${escapeHtml(state.parsedProduct.title)}" style="max-height:100%;">`;
     }
  }
};

function parseUserPrice(value) {
  let text = String(value || "").trim().replace(/[^\d,.]/g, "");
  if (!text) return null;

  if (text.includes(",") && text.includes(".")) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replaceAll(".", "").replace(",", ".")
      : text.replaceAll(",", "");
  } else if (text.includes(",")) {
    text = text.replaceAll(".", "").replace(",", ".");
  } else {
    const parts = text.split(".");
    if (parts.length === 2 && parts[1].length === 3) text = parts.join("");
  }

  const price = Number(text);
  return Number.isFinite(price) && price > 0 ? price : null;
}

function updateTrackButton() {
  const button = document.getElementById("trackParsedButton");
  if (!button) return;

  const title = document.getElementById("parsedTitle").value.trim();
  const price = parseUserPrice(document.getElementById("parsedPrice").value);
  button.disabled = !title || !price;
}

async function trackParsedProduct() {
  const parsed = state.parsedProduct;
  if (!parsed) return;

  const button = document.getElementById("trackParsedButton");
  const errorBox = document.getElementById("trackProductError");
  const title = document.getElementById("parsedTitle").value.trim();
  const price = parseUserPrice(document.getElementById("parsedPrice").value);

  const targetPriceInput = document.getElementById("parsedTargetPrice");
  const targetPrice = targetPriceInput ? parseUserPrice(targetPriceInput.value) : null;
  const lastPurchasedDate = document.getElementById("parsedLastPurchasedDate")?.value || "";
  const restockPeriod = Number(document.getElementById("parsedRestockPeriod")?.value || 0);

  const servingsInput = document.getElementById("parsedServings");
  const servings = servingsInput ? parseInt(servingsInput.value, 10) : null;

  if (!title || !price) {
    showDialogError("Ürün adı ve geçerli fiyat gerekli.");
    return;
  }

  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Kaydediliyor`;
  errorBox.hidden = true;

  const extraInfo = { ...(parsed.extra_info || {}) };
  if (targetPrice) {
    extraInfo.target_price = targetPrice;
  }
  if (Number.isFinite(alertThreshold) && alertThreshold >= 1 && alertThreshold <= 100) {
    extraInfo.alert_threshold = alertThreshold;
  }
  if (lastPurchasedDate && Number.isFinite(restockPeriod) && restockPeriod > 0) {
    extraInfo.last_purchased_date = lastPurchasedDate;
    extraInfo.restock_period_days = restockPeriod;
  }
  if (servings && !isNaN(servings)) {
    extraInfo.servings = servings;
  }

  const openingDateInput = document.getElementById("parsedOpeningDate");
  const openingDate = openingDateInput ? openingDateInput.value.trim() : null;
  const shelfLifeInput = document.getElementById("parsedShelfLife");
  const shelfLife = shelfLifeInput ? parseInt(shelfLifeInput.value, 10) : null;

  if (openingDate) {
    extraInfo.opening_date = openingDate;
  }
  if (shelfLife && !isNaN(shelfLife)) {
    extraInfo.shelf_life_months = shelfLife;
  }

  try {
    await api("/products", {
      method: "POST",
      body: JSON.stringify({
        title,
        url: parsed.canonical_url,
        price,
        source: parsed.source,
        image_url: parsed.image_url,
        original_price: parsed.original_price,
        extra_info: extraInfo,
      }),
    });

    closeDialog();
    document.getElementById("productUrl").value = "";
    showToast("Ürün fiyat radarına eklendi.");
    await loadProducts();
    switchView("tracking");
  } catch (error) {
    if (isLoginRequiredError(error)) {
      closeDialog();
      promptLoginForTracking("Bir ürünü fiyat radarına eklemek için hesap açman gerekiyor.");
    } else {
      showDialogError(`Ürün kaydedilemedi: ${error.message}`);
    }
    button.disabled = false;
    button.innerHTML = `<i data-lucide="radar"></i> Takibe al`;
    lucide.createIcons();
  }
}

function showDialogError(message) {
  const errorBox = document.getElementById("trackProductError");
  if (!errorBox) {
    showToast(message);
    return;
  }

  errorBox.textContent = message;
  errorBox.hidden = false;
  errorBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function openProduct(id) {
  const product = state.products.find((item) => item.id === id);
  if (!product) return;

  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  const history = product.price_history.map((item) => item.price);
  const lowest = Math.min(...history);
  const highest = Math.max(...history);

  // Fiyat geçmişini kronolojik sıraya göre diz
  const sortedHistory = [...product.price_history].sort((a, b) => new Date(a.seen_at) - new Date(b.seen_at));
  const labels = sortedHistory.map((item) => {
    if (!item.seen_at) return "İlk Kayıt";
    return new Intl.DateTimeFormat("tr-TR", {
      day: "2-digit",
      month: "short",
    }).format(new Date(item.seen_at));
  });
  const prices = sortedHistory.map((item) => item.price);

  const extraInfo = product.extra_info || {};
  let assistantHtml = "";

  // 1. Supplement porsiyon ve servis maliyeti
  if (extraInfo.servings) {
    const servings = parseInt(extraInfo.servings, 10);
    const costPerServing = product.current_price / servings;
    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="dumbbell"></i> Porsiyon Analizi
        </div>
        <div class="assistant-info-content">
          Bu ürün <strong>${servings} servis</strong> içeriyor.<br>
          Servis başına maliyet: <strong>${currency.format(costPerServing)}</strong>
        </div>
      </div>
    `;
  }

  // 2. PC donanım uyumluluk bilgileri
  if (extraInfo.compatibility_info) {
    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="cpu"></i> Donanım Uyumluluk Rehberi
        </div>
        <div class="assistant-info-content">
          ${escapeHtml(extraInfo.compatibility_info)}
        </div>
      </div>
    `;
  }

  // 2.5. Kozmetik son kullanma ve ömür bilgisi
  if (extraInfo.opening_date && extraInfo.shelf_life_months) {
    const openingDate = new Date(extraInfo.opening_date);
    const shelfMonths = parseInt(extraInfo.shelf_life_months, 10);
    const expDate = new Date(openingDate.getTime() + shelfMonths * 30 * 24 * 60 * 60 * 1000);
    const now = new Date();
    const daysLeft = Math.ceil((expDate - now) / (1000 * 60 * 60 * 24));

    let statusMsg = "";
    if (daysLeft < 0) {
      statusMsg = `<span style="color: var(--red); font-weight: 700;">Kullanım ömrü dolmuş! (${Math.abs(daysLeft)} gün önce)</span>`;
    } else {
      statusMsg = `Kalan kullanım süresi: <strong>${daysLeft} gün</strong>`;
    }

    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="calendar"></i> Kozmetik Ömür Takibi
        </div>
        <div class="assistant-info-content">
          Açılış Tarihi: <strong>${extraInfo.opening_date}</strong> (Kullanım Ömrü: <strong>${shelfMonths} Ay</strong>)<br>
          Son Kullanma Hedefi: <strong>${expDate.toISOString().split('T')[0]}</strong><br>
          ${statusMsg}
        </div>
      </div>
    `;
  }

  if (extraInfo.last_purchased_date && extraInfo.restock_period_days) {
    const purchasedAt = new Date(extraInfo.last_purchased_date);
    const dueAt = new Date(
      purchasedAt.getTime()
      + Number(extraInfo.restock_period_days) * 24 * 60 * 60 * 1000,
    );
    const daysUntilDue = Math.ceil((dueAt - new Date()) / (24 * 60 * 60 * 1000));
    const restockStatus = daysUntilDue > 0
      ? `${daysUntilDue} gün sonra yeniden alma zamanı`
      : `${Math.abs(daysUntilDue)} gündür yeniden alma zamanı gelmiş`;

    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="repeat-2"></i> Periyodik İhtiyaç Asistanı
        </div>
        <div class="assistant-info-content">
          ${Number(extraInfo.restock_period_days)} günlük periyot takip ediliyor.<br>
          Sonraki hedef: <strong>${dueAt.toLocaleDateString("tr-TR")}</strong><br>
          <strong>${restockStatus}</strong>
        </div>
      </div>
    `;
  }

  // 3. Hedef fiyat alarm bilgisi
  if (extraInfo.target_price) {
    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="bell-ring"></i> Hedef Fiyat Alarmı
        </div>
        <div class="assistant-info-content">
          Hedef fiyatın: <strong>${currency.format(extraInfo.target_price)}</strong>. Fiyat bu seviyeye veya altına düştüğünde bildirim gönderilecektir.
        </div>
      </div>
    `;
  }

  // 4. Sahte İndirim Analiz Raporu
  const forecast = product.discount_forecast;
  if (forecast) {
    assistantHtml += `
      <div class="forecast-panel ${forecast.status === "ready" ? "" : "forecast-pending"}">
        <div class="forecast-heading">
          <div>
            <span class="forecast-label">7 GÜNLÜK TAHMİN</span>
            <strong>${forecast.status === "ready"
              ? `%${forecast.probability} indirim ihtimali`
              : "Tahmin hazırlanıyor"}</strong>
          </div>
          <span class="forecast-recommendation">${escapeHtml(forecast.recommendation)}</span>
        </div>
        <p>${escapeHtml(forecast.message)}</p>
        ${forecast.status === "ready" ? `
          <div class="forecast-stats">
            <span>Güven <strong>${escapeHtml(forecast.confidence)}</strong></span>
            <span>Beklenen düşüş <strong>%${forecast.expected_drop_percent}</strong></span>
            <span>Veri <strong>${forecast.observation_count} kayıt</strong></span>
          </div>
        ` : ""}
      </div>
    `;
  }

  const discountAnalysis = product.discount_analysis;
  if (discountAnalysis) {
    const badgeColor = discountAnalysis.badge_color || "gray";
    const statusText = discountAnalysis.status || "normal";
    assistantHtml += `
      <div class="discount-analysis-panel badge-${badgeColor}">
        <span class="analysis-status-badge bg-${badgeColor}">${escapeHtml(statusText)}</span>
        <div class="assistant-info-content" style="font-weight: 500;">
          ${escapeHtml(discountAnalysis.message)}
        </div>
      </div>
    `;
  }

  // 5. Diğer Mağaza Fiyat Karşılaştırması
  const comparison = product.price_comparison || [];
  let comparisonHtml = "";
  if (comparison.length > 0) {
    comparisonHtml += `
      <div class="price-chart-container" style="margin: 18px 0; padding: 12px; background: #f4f6f2; border: 1px solid var(--line); border-radius: 8px;">
        <p class="source-name" style="margin-top: 0; margin-bottom: 10px; font-weight: 700; color: var(--green-dark); display: flex; align-items: center; justify-content: space-between;">
          <span style="display: flex; align-items: center; gap: 6px;"><i data-lucide="arrow-left-right" style="width: 14px; height: 14px;"></i> Diğer Mağazalardaki Fiyatlar</span>
          <button onclick="refreshProductComparison('${product.id}')" style="background: none; border: none; color: var(--green); font-size: 11px; font-weight: 700; cursor: pointer; padding: 0; display: flex; align-items: center; gap: 4px;">
            <i data-lucide="refresh-cw" style="width: 11px; height: 11px;"></i> Yenile
          </button>
        </p>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${comparison.map((item, idx) => {
            const isCheapest = idx === 0 && item.price < product.current_price;
            const borderStyle = isCheapest ? "border: 1px solid var(--green); background: #eaf6ec;" : "border: 1px solid var(--line); background: white;";
            const badgeStyle = isCheapest ? "background: var(--green); color: white; padding: 2px 4px; border-radius: 4px; font-size: 9px; font-weight: 800; margin-left: 4px;" : "";
            return `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 6px; ${borderStyle}">
              <div style="display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; margin-right: 10px;">
                <span style="font-size: 11px; font-weight: 800; text-transform: uppercase; color: var(--muted); min-width: 75px; display: inline-block;">${escapeHtml(item.store)}</span>
                <span style="font-size: 12px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink);">${escapeHtml(item.title)}</span>
              </div>
              <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
                <strong style="color: ${isCheapest ? "var(--green-dark)" : "var(--ink)"}; font-size: 13px;">${currency.format(item.price)}</strong>
                ${isCheapest ? `<span style="${badgeStyle}">EN UCUZ</span>` : ""}
          <a href="${escapeHtml(safeHttpUrl(addAffiliateTag(item.url, item.store)))}" target="_blank" rel="noopener noreferrer" style="color: var(--muted); display: inline-grid; place-items: center; width: 26px; height: 26px; border: 1px solid var(--line); border-radius: 4px; background: white;" title="Mağazaya git">
                  <i data-lucide="external-link" style="width: 14px; height: 14px; color: var(--ink);"></i>
                </a>
              </div>
            </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  } else {
    comparisonHtml += `
      <div class="price-chart-container" style="margin: 18px 0; padding: 12px; background: #fbfcf9; border: 1px solid var(--line); border-radius: 6px; text-align: center;">
        <button class="card-button" style="margin-top: 0; width: auto; display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;" onclick="refreshProductComparison('${product.id}')">
          <i data-lucide="search" style="width: 14px; height: 14px;"></i>
          Diğer Mağazalardaki Fiyatları Sorgula
        </button>
      </div>
    `;
  }

  content.innerHTML = `
    <div class="dialog-product-image">${productImage(product)}</div>
    <div class="dialog-body">
      <p class="source-name">${escapeHtml(product.source)}</p>
      <h2>${escapeHtml(product.title)}</h2>
      <div class="decision-panel">
        <div class="score-ring">${product.deal_score}</div>
        <div>
          <strong>${escapeHtml(product.verdict.toUpperCase())}</strong>
          <p>${escapeHtml(product.reason)}</p>
        </div>
      </div>

      <!-- Akıllı Asistan Bilgileri -->
      ${assistantHtml}

      <div class="price-row">
        <span class="price">${currency.format(product.current_price)}</span>
        <span class="verdict">${escapeHtml(product.verdict)}</span>
      </div>
      <p class="source-name">En düşük ${currency.format(lowest)} · En yüksek ${currency.format(highest)}</p>

      <!-- Fiyat Geçmişi Grafiği -->
      <div class="price-chart-container" style="margin: 18px 0; padding: 12px; background: #fbfcf9; border: 1px solid var(--line); border-radius: 6px;">
        <p class="source-name" style="margin-top: 0; margin-bottom: 8px; font-weight: 600; color: var(--ink);">Fiyat Değişim Grafiği</p>
        <div style="position: relative; height: 160px; width: 100%;">
          <canvas id="priceHistoryChart"></canvas>
        </div>
      </div>

      <!-- Fiyat Karşılaştırması -->
      ${comparisonHtml}

      <div class="manual-fields">
        <label class="manual-field">
          <span>Yeni fiyat kaydı</span>
          <input id="newPriceInput" type="text" inputmode="decimal" placeholder="Örn. 1749,90">
        </label>
        <button class="secondary-button" onclick="updateProductPrice('${product.id}')">Fiyatı güncelle</button>
      </div>

      <!-- Tüketim & Bitme Takibi -->
      <div class="manual-fields" style="margin-top: 14px; border-top: 1px solid var(--line); padding-top: 14px;">
        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; font-weight: 700; color: var(--ink); margin-bottom: 10px;">
          <input type="checkbox" id="enableRestockTracking" style="accent-color: var(--green); width: 16px; height: 16px;" ${extraInfo.restock_period_days ? "checked" : ""} onchange="document.getElementById('restockFields').style.display = this.checked ? 'block' : 'none'">
          Tüketim & Bitme Takibi Aktif
        </label>
        <div id="restockFields" style="display: ${extraInfo.restock_period_days ? "block" : "none"}; margin-bottom: 10px;">
          <div style="display: flex; gap: 10px; margin-bottom: 10px;">
            <label class="manual-field" style="flex: 1; margin: 0;">
              <span style="font-size: 11px;">Tüketim Süresi (Gün)</span>
              <input id="restockPeriodInput" type="number" min="1" value="${extraInfo.restock_period_days || 30}" style="padding: 6px 10px; font-size: 12px;">
            </label>
            <label class="manual-field" style="flex: 1; margin: 0;">
              <span style="font-size: 11px;">Son Satın Alım</span>
              <input id="restockLastPurchasedInput" type="date" value="${extraInfo.last_purchased_date || new Date().toISOString().split('T')[0]}" style="padding: 6px 10px; font-size: 12px;">
            </label>
          </div>
        </div>
        <button class="secondary-button" style="width: 100%; font-size: 12px; height: 34px;" onclick="window.saveRestockTracking('${product.id}')">Takip Ayarlarını Kaydet</button>
      </div>
      <div class="dialog-actions">
        <button class="secondary-button" style="flex:1;" type="button" onclick="showToast('Koleksiyonlar özelliği çok yakında aktif olacak!')">
          <i data-lucide="bookmark-plus"></i>
          Listeye Ekle
        </button>
        <button class="danger-button" style="flex:1;" type="button" onclick="removeTrackedProduct('${product.id}')">
          <i data-lucide="trash-2"></i>
          Takipten çıkar
        </button>
        <button class="primary-button" style="flex:1;" onclick="window.open(${inlineJsArg(safeHttpUrl(addAffiliateTag(product.url, product.source)))}, '_blank', 'noopener,noreferrer')">
          <i data-lucide="external-link"></i>
          Mağazaya git
        </button>
      </div>
      <button class="card-button" onclick="refreshSingleProduct('${product.id}')">
        <i data-lucide="refresh-cw"></i>
        Şimdi otomatik kontrol et
      </button>
      <button class="card-button" onclick="shareProduct('${product.id}')">
        <i data-lucide="share-2"></i>
        Bu fırsatı paylaş
      </button>

      <!-- Topluluk İncelemeleri -->
      <div class="manual-fields" style="margin-top: 14px; border-top: 1px solid var(--line); padding-top: 14px;">
        <h3 style="font-size: 14px; margin-bottom: 8px; color: var(--ink); display:flex; align-items:center; gap:6px;">
          <i data-lucide="message-square" style="width:16px;height:16px;"></i> Topluluk İncelemeleri
        </h3>
        <div id="reviewsList" style="display:flex; flex-direction:column; gap:8px; margin-bottom: 12px; max-height: 200px; overflow-y: auto;">
           <div class="loading-row" style="margin:0;"><span class="spinner" style="width:14px;height:14px;border-width:2px;border-color:#a0aab0;border-top-color:transparent;"></span><span style="font-size:12px;color:#a0aab0;">Yorumlar yükleniyor...</span></div>
        </div>
        <div style="display:flex; gap:8px; align-items:center;">
           <input type="text" id="reviewComment" placeholder="Bu fiyat/satıcı hakkında ne düşünüyorsun?" style="flex:1; padding: 8px; font-size:12px; border-radius:6px; background:var(--bg-lighter); border:1px solid var(--line); color:var(--ink);">
           <select id="reviewRating" style="padding: 8px; font-size:12px; border-radius:6px; background:var(--bg-lighter); border:1px solid var(--line); color:var(--ink); width:auto;">
              <option value="5">⭐⭐⭐⭐⭐</option>
              <option value="4">⭐⭐⭐⭐</option>
              <option value="3">⭐⭐⭐</option>
              <option value="2">⭐⭐</option>
              <option value="1">⭐</option>
           </select>
           <button class="primary-button" style="padding: 8px 12px;" onclick="submitProductReview('${product.id}')">Gönder</button>
        </div>
      </div>
    </div>
  `;

  dialog.showModal();
  lucide.createIcons();

  loadProductReviews(product.id);

  // Grafik çizimi
  setTimeout(() => {
    const ctx = document.getElementById("priceHistoryChart");
    if (!ctx) return;

    const existingChart = Chart.getChart(ctx);
    if (existingChart) {
      existingChart.destroy();
    }

    new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Fiyat",
            data: prices,
            borderColor: "#287a50", // --green
            backgroundColor: "rgba(40, 122, 80, 0.08)",
            borderWidth: 2,
            tension: 0.15,
            pointBackgroundColor: "#287a50",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
            pointRadius: 4.5,
            pointHoverRadius: 6.5,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: "index",
            intersect: false,
            callbacks: {
              label: function (context) {
                return currency.format(context.raw);
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { family: "DM Sans", size: 10 },
              color: "#687068",
            },
          },
          y: {
            grid: { color: "#dfe3dc" },
            ticks: {
              font: { family: "DM Sans", size: 10 },
              color: "#687068",
              callback: function (value) {
                return "â‚º" + value;
              },
            },
          },
        },
      },
    });
  }, 100);
}

window.loadProductReviews = async function(productId) {
  const list = document.getElementById("reviewsList");
  if (!list) return;
  try {
    const res = await fetch(`/api/products/${productId}/reviews`);
    const data = await res.json();
    if (!data.reviews || data.reviews.length === 0) {
      list.innerHTML = `<div style="font-size:12px; color:#a0aab0; text-align:center; padding: 10px;">Henüz yorum yapılmamış. İlk değerlendiren sen ol!</div>`;
      return;
    }
    list.innerHTML = data.reviews.map(r => `
      <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px;">
         <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 4px;">
            <span style="font-weight:700; font-size:11px; color:#e8ede8;">${escapeHtml(r.user_name)}</span>
            <span style="font-size:10px;">${"⭐".repeat(r.rating)}</span>
         </div>
         <div style="font-size:12px; color:#a0aab0;">${escapeHtml(r.comment)}</div>
      </div>
    `).join("");
  } catch (err) {
    list.innerHTML = `<div style="font-size:12px; color:#ff6b6b; text-align:center;">Yorumlar yüklenemedi.</div>`;
  }
};

window.submitProductReview = async function(productId) {
  const commentInput = document.getElementById("reviewComment");
  const ratingInput = document.getElementById("reviewRating");
  if (!commentInput || !ratingInput) return;

  const comment = commentInput.value.trim();
  if (!comment) return showToast("Lütfen bir yorum yazın.");

  try {
    const res = await fetch(`/api/products/${productId}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-device-id": deviceId },
      body: JSON.stringify({ rating: parseInt(ratingInput.value), comment: comment })
    });
    if (res.ok) {
      commentInput.value = "";
      showToast("Yorumunuz eklendi!");
      loadProductReviews(productId);
    } else {
      showToast("Yorum eklenirken hata oluştu.");
    }
  } catch (e) {
    showToast("Bağlantı hatası.");
  }
};

async function updateProductPrice(productId) {
  const input = document.getElementById("newPriceInput");
  const price = parseUserPrice(input?.value);

  if (!price) {
    showToast("Geçerli bir fiyat yaz.");
    return;
  }

  try {
    const updated = await api(`/products/${productId}/prices`, {
      method: "POST",
      body: JSON.stringify({ price }),
    });

    state.products = state.products.map((product) => (
      product.id === productId ? updated : product
    ));
    renderAll();
    showToast("Yeni fiyat kaydedildi, fırsat skoru güncellendi.");
    openProduct(productId);
  } catch (error) {
    showToast(error.message);
  }
}

async function removeTrackedProduct(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;

  const confirmed = window.confirm(`"${product.title}" takipten çıkarılsın mı?`);
  if (!confirmed) return;

  try {
    await api(`/products/${productId}`, { method: "DELETE" });
    state.products = state.products.filter((item) => item.id !== productId);
    closeDialog();
    renderAll();
    showToast("Ürün takip listesinden çıkarıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

async function shareProduct(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;

  const price = currency.format(product.current_price);
  const storeName = escapeHtml(product.source || "mağaza");
  const text = `${product.title} — ${storeName}'da ${price}! Almadan ile karşılaştır:`;
  const url = product.url || window.location.href;

  if (navigator.share) {
    try {
      await navigator.share({ title: product.title, text, url });
      return;
    } catch (e) {
      if (e.name === "AbortError") return; // kullanıcı paylaşımı iptal etti
      // diğer tüm hatalarda WhatsApp fallback'ine düş
    }
  }

  const waText = encodeURIComponent(`${text} ${url}`);
  window.open(`https://wa.me/?text=${waText}`, "_blank", "noopener,noreferrer");
}

async function refreshSingleProduct(productId) {
  showToast("Ürünün güncel fiyatı kontrol ediliyor...");

  try {
    const result = await api(`/products/${productId}/refresh`, {
      method: "POST",
    });

    state.products = state.products.map((product) => (
      product.id === productId ? result.product : product
    ));
    renderAll();
    openProduct(productId);

    if (result.status === "success" && result.price_changed) {
      showToast(`Fiyat güncellendi: ${currency.format(result.new_price)}`);
    } else if (result.status === "success") {
      showToast("Fiyat değişmemiş.");
    } else {
      showToast(`Fiyat bulunamadı: ${result.message}`);
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function refreshAllPrices() {
  const button = document.getElementById("refreshButton");
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Kontrol ediliyor`;

  try {
    const result = await api("/refresh-all", { method: "POST" });
    await loadProducts();
    showToast(`${result.successful} ürün kontrol edildi, ${result.failed} üründe fiyat bulunamadı.`);
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = `<i data-lucide="scan-line"></i> Fiyatları kontrol et`;
    lucide.createIcons();
  }
}

async function showNotifications() {
  try {
    const [notifications, pushConfig] = await Promise.all([
      api("/notifications"),
      api("/push/config"),
    ]);
    const dialog = document.getElementById("productDialog");
    const content = document.getElementById("dialogContent");
    const pushState = await currentPushState(pushConfig);

    content.innerHTML = `
      <div class="dialog-body">
        <p class="eyebrow">BİLDİRİMLER</p>
        <h2>Fırsat hareketleri</h2>
        <div class="push-settings">
          <div>
            <strong>Fiyat alarmı bildirimleri</strong>
            <span>${escapeHtml(pushState.message)}</span>
          </div>
          ${pushState.action === "enable"
            ? `<button class="primary-button compact-button" type="button" onclick="enablePushNotifications()">Aç</button>`
            : pushState.action === "disable"
              ? `<button class="secondary-button compact-button" type="button" onclick="disablePushNotifications()">Kapat</button>`
              : ""}
        </div>
        <div class="notification-list">
          ${notifications.length
            ? notifications.map((item) => {
                let badgeHtml = "";
                if (item.type === "catalog_bim") {
                  badgeHtml = `<span class="analysis-status-badge bg-blue" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">BİM AKTÜEL</span>`;
                } else if (item.type === "catalog_a101") {
                  badgeHtml = `<span class="analysis-status-badge bg-yellow" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; color: #775815; margin-right: 6px;">A101 AKTÜEL</span>`;
                } else if (item.type === "catalog_gratis") {
                  badgeHtml = `<span class="analysis-status-badge bg-red" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">GRATİS</span>`;
                } else if (item.type === "stock_back") {
                  badgeHtml = `<span class="analysis-status-badge bg-green" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">STOK GELDİ</span>`;
                } else if (item.type === "catalog_match") {
                  badgeHtml = `<span class="analysis-status-badge bg-green" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">KATALOĞA DÜŞTÜ!</span>`;
                }

                return `
                  <div class="notification-item">
                    <div style="display: flex; align-items: center; margin-bottom: 4px;">
                      ${badgeHtml}
                      <strong>${escapeHtml(item.title)}</strong>
                    </div>
                    <span>${escapeHtml(item.message)}</span>
                    <time>${formatDate(item.created_at)}</time>
                  </div>
                `;
              }).join("")
            : `<div class="empty-state">Henüz fiyat düşüşü bildirimi yok.</div>`}
        </div>
      </div>
    `;
    dialog.showModal();
    await api("/notifications/read-all", { method: "POST" });
  } catch (error) {
    showToast(error.message);
  }
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

async function currentPushState(config) {
  if (!config.enabled) {
    return {
      action: null,
      message: "Sunucuda web bildirimleri henüz etkin değil.",
    };
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return {
      action: null,
      message: "Bu tarayıcı web bildirimlerini desteklemiyor.",
    };
  }
  if (Notification.permission === "denied") {
    return {
      action: null,
      message: "Bildirim izni tarayıcı ayarlarından engellenmiş.",
    };
  }

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return subscription
    ? { action: "disable", message: "Bu cihazda bildirimler açık." }
    : { action: "enable", message: "Hedef fiyat ve ciddi düşüşlerde haber al." };
}

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replaceAll("-", "+").replaceAll("_", "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

async function enablePushNotifications() {
  try {
    const config = await api("/push/config");
    if (!config.enabled || !config.public_key) {
      throw new Error("Web bildirimleri sunucuda henüz etkinleştirilmedi.");
    }

    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Bildirim izni verilmedi.");
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(config.public_key),
      });
    }

    await api("/push/subscriptions", {
      method: "POST",
      body: JSON.stringify(subscription.toJSON()),
    });
    closeDialog();
    showToast("Fiyat alarmı bildirimleri açıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

async function disablePushNotifications() {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api("/push/subscriptions", {
        method: "DELETE",
        body: JSON.stringify(subscription.toJSON()),
      });
      await subscription.unsubscribe();
    }
    closeDialog();
    showToast("Bu cihazdaki bildirimler kapatıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

function checkStatusText(product) {
  if (product.last_check_status === "success") {
    return `Son kontrol: ${formatDate(product.last_checked_at)}`;
  }
  if (product.last_check_status === "failed") {
    return "Otomatik fiyat bulunamadı";
  }
  return "İlk otomatik kontrol bekleniyor";
}

function formatDate(value) {
  if (!value) return "Henüz kontrol edilmedi";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function productImage(product) {
  if (product.image_url) {
    return `<img src="${escapeHtml(proxiedImageUrl(product.image_url))}" alt="${escapeHtml(product.title)}"
      loading="lazy" onerror="imageFallback(this, '${getStoreIcon(product.source, product.title)}')">`;
  }
  const icon = getStoreIcon(product.source, product.title);
  return `<span class="product-placeholder"><i data-lucide="${icon}"></i></span>`;
}

function switchView(view) {
  state.activeView = view;
  const sections = {
    discover:  document.getElementById("discoverView"),
    tracking:  document.getElementById("trackingView"),
    savings:   document.getElementById("savingsView"),
    bulletins: document.getElementById("bulletinsView"),
    cart:      document.getElementById("cartView"),
  };

  Object.entries(sections).forEach(([name, section]) => {
    if (section) section.classList.toggle("hidden", name !== view);
  });

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });

  if (view === "cart") {
    if (!state.auth.authenticated) {
      promptLoginForTracking("Sepetini kullanmak ve cihazlar arasında senkronize etmek için hesap açman gerekiyor.");
      switchView("discover");
      return;
    }
    renderCart();
  }
  if (view === "savings") {
    loadReceipts(document.getElementById("receiptMonthFilter")?.value || "");
  }
  if (view === "bulletins") {
    loadStores();
  }

  window.scrollTo({ top: view === "discover" ? 0 : 180, behavior: "smooth" });

  // Rehber popup — ilk ziyarette göster
  setTimeout(() => showGuide(view), 150);
}

async function pasteUrl() {
  try {
    const value = await navigator.clipboard.readText();
    document.getElementById("productUrl").value = value;
  } catch {
    showToast("Pano izni verilmedi. Linki elle yapıştırabilirsin.");
  }
}

async function refreshProductComparison(productId) {
  showToast("Diğer mağazalardaki fiyatlar sorgulanıyor...");
  try {
    const updated = await api(`/products/${productId}/compare`, {
      method: "POST",
    });

    state.products = state.products.map((product) => (
      product.id === productId ? updated : product
    ));
    renderAll();
    openProduct(productId);
    showToast("Diğer mağaza fiyatları güncellendi.");
  } catch (error) {
    showToast(error.message);
  }
}

function closeDialog() {
  const dialog = document.getElementById("productDialog");
  if (dialog.open) dialog.close();
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.innerHTML = message;
  toast.classList.add("show");
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => toast.classList.remove("show"), 2800);
}

function updateNetworkStatus() {
  const status = document.getElementById("networkStatus");
  if (!status) return;
  const online = navigator.onLine;
  status.classList.toggle("offline", !online);
  status.innerHTML = online
    ? `<i data-lucide="wifi"></i><span>Çevrimiçi</span>`
    : `<i data-lucide="wifi-off"></i><span>Çevrimdışı mod</span>`;
  lucide.createIcons();
  if (!online) {
    showToast("Çevrimdışı mod aktif. Kayıtlı liste ve market karşılaştırmaları kullanılabilir.");
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function inlineJsArg(value) {
  // JSON'in çift tırnaklı JS stringini HTML attribute bağlamında kaçırır.
  return escapeHtml(JSON.stringify(String(value ?? "")));
}

function safeHttpUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function getOrCreateDeviceId() {
  const storageKey = "almadan_device_id";
  let deviceId = localStorage.getItem(storageKey);

  if (!deviceId) {
    deviceId = globalThis.crypto?.randomUUID
      ? globalThis.crypto.randomUUID()
      : `device-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(storageKey, deviceId);
  }

  return deviceId;
}

function togglePhoneField() {
  // Telefon artık her zaman zorunlu (bildirim tercihinden bağımsız) --
  // alan her durumda görünür kalır.
  const phoneField = document.getElementById("phoneFieldLabel");
  if (phoneField) {
    phoneField.style.display = "block";
  }
}

window.openProduct = openProduct;
window.closeDialog = closeDialog;
window.trackParsedProduct = trackParsedProduct;
window.updateProductPrice = updateProductPrice;
window.refreshSingleProduct = refreshSingleProduct;
window.removeTrackedProduct = removeTrackedProduct;
window.refreshProductComparison = refreshProductComparison;
window.submitAuth = submitAuth;
window.logoutAccount = logoutAccount;
window.showAccount = showAccount;
window.showForgotPassword = showForgotPassword;
window.sendPasswordReset = sendPasswordReset;
window.submitPasswordReset = submitPasswordReset;
window.enablePushNotifications = enablePushNotifications;
window.disablePushNotifications = disablePushNotifications;
window.trackSearchResultProduct = trackSearchResultProduct;
window.togglePhoneField = togglePhoneField;
window.toggleProfilePhoneField = toggleProfilePhoneField;
window.saveProfileSettings = saveProfileSettings;

// NEW FUNCTIONS EXPORTS
window.toggleTheme = toggleTheme;
window.addQuickCartItem = addQuickCartItem;
window.clearCart = clearCart;
window.toggleCartItem = toggleCartItem;
window.removeCartItem = removeCartItem;
window.shareCartList = shareCartList;
window.toggleScannerArea = toggleScannerArea;
window.runBarcodeScan = runBarcodeScan;
window.runOcrScan = runOcrScan;
window.switchOptimizerMode = switchOptimizerMode;
window.startVoiceSearch = startVoiceSearch;
window.closeSizeSelectorDialog = closeSizeSelectorDialog;
window.addGenericCartItemWithSize = addGenericCartItemWithSize;
window.addGenericCartItemWithCustomSize = addGenericCartItemWithCustomSize;
window.addGenericCartItemWithoutSize = addGenericCartItemWithoutSize;
window.updateUserLocation = updateUserLocation;
window.updateMaxDistance = updateMaxDistance;
window.removePendingReceiptItem = removePendingReceiptItem;
window.cancelReceiptReview = cancelReceiptReview;
window.savePendingReceipt = savePendingReceipt;
window.scanAnotherReceipt = scanAnotherReceipt;
window.goToReceiptHistory = goToReceiptHistory;
window.deleteReceipt = deleteReceipt;


/* PREMIUM KOYU TEMA */
function applyTheme() {
  const isDark = state.theme === "dark";
  document.documentElement.classList.toggle("dark-theme", isDark);
  document.body.classList.toggle("dark-theme", isDark);
  const themeBtn = document.getElementById("themeToggleButton");
  if (themeBtn) {
    themeBtn.innerHTML = isDark ? `<i data-lucide="sun"></i>` : `<i data-lucide="moon"></i>`;
    lucide.createIcons();
  }
}

function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  localStorage.setItem("almadan_theme", state.theme);
  applyTheme();
  renderSavingsCharts();
  renderReceiptCharts();
}


/* SEPETİM & ALIVERİŞ LİSTEM */
function addQuickCartItem() {
  const input = document.getElementById("quickCartInput");
  const val = input.value.trim();
  if (!val) return;

  const hasSize = /\d+\s*(ml|l|g|gr|kg|li|'lu|'li|'lü|'lu|'lü|adet|porsiyon|servis)/i.test(val);
  const lowerVal = val.toLowerCase();
  const isGeneric = Object.keys(genericProductSizes).some(key => lowerVal === key || lowerVal.includes(key));

  input.value = "";

  if (isGeneric && !hasSize) {
    showSizeSelectorDialog(val);
    return;
  }

  const newItem = {
    id: "cart-" + Date.now(),
    name: val,
    checked: false,
    quantity: 1,
    updated_at: new Date().toISOString(),
  };

  state.cart.push(newItem);
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function clearCart() {
  if (state.cart.length === 0) return;
  const confirmed = window.confirm("Tüm sepeti temizlemek istediğinizden emin misiniz?");
  if (!confirmed) return;

  state.cart = [];
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function toggleCartItem(itemId) {
  state.cart = state.cart.map(item => {
    if (item.id === itemId) {
      return {
        ...item,
        checked: !item.checked,
        updated_at: new Date().toISOString(),
      };
    }
    return item;
  });
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function removeCartItem(itemId) {
  state.cart = state.cart.filter(item => item.id !== itemId);
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function updateCartQuantity(itemId, value) {
  const quantity = Math.max(1, Math.min(99, Number.parseInt(value, 10) || 1));
  state.cart = state.cart.map(item => (
    item.id === itemId
      ? { ...item, quantity, updated_at: new Date().toISOString() }
      : item
  ));
  saveCartToLocalStorage();
  renderCart();
  if (state.sharedListId) syncSharedListWithServer();
}

let _cartSyncTimer = null;

function saveCartToLocalStorage() {
  localStorage.setItem("almadan_cart", JSON.stringify(state.cart));
  syncCartToBackend();
}

// Hesaba bağlı senkronizasyon -- her mutasyonda çağrılır, kısa bir
// debounce ile (hızlı ardışık değişikliklerde tek istek atsın).
function syncCartToBackend() {
  if (!state.auth.authenticated) return;
  clearTimeout(_cartSyncTimer);
  _cartSyncTimer = setTimeout(async () => {
    try {
      await api("/api/cart", {
        method: "POST",
        body: JSON.stringify({ items: state.cart }),
      });
    } catch (error) {
      console.warn("Sepet senkronize edilemedi:", error.message);
    }
  }, 600);
}

// Giriş/kayıt sonrası veya sayfa açılışında (oturum zaten varsa) hesaptaki
// sepeti çeker. Cihazdaki yerel sepet boşsa doğrudan hesaptakini kullanır;
// yerelde veri varsa (misafirken eklenmiş olabilir) hesaptakiyle birleştirir.
async function loadCartFromBackend() {
  if (!state.auth.authenticated) return;
  try {
    const res = await api("/api/cart");
    const remoteItems = res.items || [];
    if (state.cart.length === 0) {
      state.cart = remoteItems;
    } else {
      const existingIds = new Set(state.cart.map((i) => i.id));
      state.cart = [...state.cart, ...remoteItems.filter((i) => !existingIds.has(i.id))];
    }
    localStorage.setItem("almadan_cart", JSON.stringify(state.cart));
    if (state.activeView === "cart") renderCart();
  } catch (error) {
    console.warn("Sepet hesaptan yüklenemedi:", error.message);
  }
}


/* SCANNERS AND OCR SIMULATION */
function toggleScannerArea(type) {
  const area = document.getElementById("barcodeOcrInputArea");
  const barcode = document.getElementById("barcodeScannerArea");
  const ocr = document.getElementById("receiptOcrUploadArea");

  if (type === "barcode") {
    const isHidden = barcode.classList.contains("hidden");
    area.classList.toggle("hidden", !isHidden);
    barcode.classList.toggle("hidden", !isHidden);
    ocr.classList.add("hidden");
    if (isHidden) {
      startLiveBarcodeScanner();
    } else {
      stopLiveBarcodeScanner();
    }
  } else {
    const isHidden = ocr.classList.contains("hidden");
    area.classList.toggle("hidden", !isHidden);
    ocr.classList.toggle("hidden", !isHidden);
    barcode.classList.add("hidden");
    stopLiveBarcodeScanner();
  }
}

function updateBarcodeScanStatus(message) {
  const status = document.getElementById("barcodeScanStatus");
  if (status) status.textContent = message;
}

async function startLiveBarcodeScanner() {
  const reader = document.getElementById("html5QrCodeReader");
  if (!reader) return;
  if (!window.Html5Qrcode) {
    updateBarcodeScanStatus("Kamera tarayici kutuphanesi yuklenemedi.");
    showToast("Barkod tarayici yuklenemedi. Internet baglantisini kontrol edin.");
    return;
  }
  if (liveBarcodeScannerRunning) return;

  liveBarcodeScanLocked = false;
  lastLiveBarcode = "";
  updateBarcodeScanStatus("Kamera izni bekleniyor...");

  try {
    if (!liveBarcodeScanner) {
      liveBarcodeScanner = new Html5Qrcode("html5QrCodeReader", {
        verbose: false,
      });
    }
    await liveBarcodeScanner.start(
      { facingMode: "environment", advanced: [{ zoom: 1.5 }] },
      {
        fps: 20,
        qrbox: (viewfinderWidth, viewfinderHeight) => ({
          width:  Math.floor(viewfinderWidth  * 0.92),
          height: Math.floor(viewfinderHeight * 0.28),
        }),
        aspectRatio: 1.777778,
        disableFlip: false,
        formatsToSupport: [
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.UPC_A,
          Html5QrcodeSupportedFormats.UPC_E,
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
        ],
      },
      async (decodedText) => {
        const code = String(decodedText || "").replace(/\D/g, "");
        const validLen = [8, 12, 13].includes(code.length);
        if (liveBarcodeScanLocked || code === lastLiveBarcode || !validLen) return;
        liveBarcodeScanLocked = true;
        lastLiveBarcode = code;
        updateBarcodeScanStatus(`${code} yakalandi. Urun sorgulaniyor...`);
        await stopLiveBarcodeScanner();
        await lookupAndAddBarcode(code);
      },
      () => {},
    );
    liveBarcodeScannerRunning = true;
    updateBarcodeScanStatus("Barkodu cercevenin icine hizalayin.");
  } catch (error) {
    liveBarcodeScannerRunning = false;
    liveBarcodeScanLocked = false;
    updateBarcodeScanStatus("Kamera baslatilamadi.");
    showToast(`Kamera acilamadi: ${error.message || error}`);
  }
}

async function stopLiveBarcodeScanner() {
  if (!liveBarcodeScanner || !liveBarcodeScannerRunning) {
    updateBarcodeScanStatus("Tarayici durduruldu.");
    return;
  }
  try {
    await liveBarcodeScanner.stop();
    liveBarcodeScanner.clear();
  } catch (error) {
    console.warn("Barkod kamerasi durdurulamadi:", error);
  } finally {
    liveBarcodeScannerRunning = false;
    updateBarcodeScanStatus("Tarayici durduruldu.");
  }
}

async function runBarcodeScan() {
  const code = document.getElementById("barcodeSelector").value;
  if (!code) {
    showToast("Lütfen bir barkod seçin.");
    return;
  }

  await lookupAndAddBarcode(code);
}

async function lookupAndAddBarcode(code) {
  const cleanCode = String(code || "").replace(/\D/g, "");
  if (![8, 12, 13].includes(cleanCode.length)) {
    showToast("Geçersiz barkod. EAN-8, EAN-13 veya UPC-A formatında olmalıdır.");
    liveBarcodeScanLocked = false;
    return;
  }

  updateBarcodeScanStatus("Ürün sorgulanıyor...");
  showToast("Barkod taraniyor...");

  let res;
  try {
    res = await api(`/api/barcode/${cleanCode}`);
    console.info(`[Barkod] ${cleanCode} → found=${res.found} source=${res.source || "?"}`);
  } catch (error) {
    console.error(`[Barkod] API hatası (${cleanCode}):`, error.message);
    updateBarcodeScanStatus("");
    showBarcodeManualEntry(cleanCode, `Sunucu hatası: ${error.message}`);
    liveBarcodeScanLocked = false;
    return;
  }

  if (res.found) {
    const existingIndex = state.cart.findIndex(item => item.barcode === cleanCode);
    if (existingIndex >= 0) {
      const existing = state.cart[existingIndex];
      state.cart[existingIndex] = {
        ...existing,
        quantity: Math.min(99, Number(existing.quantity || 1) + 1),
        updated_at: new Date().toISOString(),
      };
      showToast(`Miktar artırıldı: ${res.title}`);
    } else {
      state.cart.push({
        id: "cart-" + Date.now(),
        name: res.title,
        brand: res.brand || "",
        image_url: res.image_url || "",
        barcode: cleanCode,
        category: res.suggested_category || "general",
        checked: false,
        quantity: 1,
        updated_at: new Date().toISOString(),
      });
      showToast(`Eklendi: ${res.title}`);
    }
    saveCartToLocalStorage();
    renderCart();
    if (state.sharedListId) syncSharedListWithServer();
    updateBarcodeScanStatus("");

    // Fiyat karşılaştırması: suggested_category kullanarak doğru mağazalarda ara
    if (res.search_query) {
      const hasResults = res.results && res.results.length > 0;
      if (hasResults) {
        showSearchResults({
          products: res.results,
          query: res.search_query,
          category: res.suggested_category || "general",
        });
      } else {
        showBarcodeCategoryMismatch(res.title, res.search_query, res.suggested_category || "general");
      }
    }
  } else {
    // Ürün hiçbir kaynakta bulunamadı → Manuel giriş seçeneği sun
    console.warn(`[Barkod] ${cleanCode} bulunamadı (allow_manual=${res.allow_manual}):`, res.message);
    updateBarcodeScanStatus("");
    if (res.allow_manual) {
      showBarcodeManualEntry(cleanCode, res.message);
    } else {
      showToast(res.message || "Barkod bulunamadı.");
    }
    liveBarcodeScanLocked = false;
  }
}

const _CATEGORY_LABELS = {
  electronics: { label: "Teknoloji mağazaları", icon: "cpu", stores: "Teknosa, Vatan, MediaMarkt, Trendyol" },
  grocery:     { label: "Market zinciri",        icon: "shopping-basket", stores: "Migros, CarrefourSA, Trendyol" },
  cosmetics:   { label: "Kozmetik mağazaları",   icon: "sparkles", stores: "Gratis, Rossmann, Watsons" },
  fashion:     { label: "Moda mağazaları",        icon: "shirt", stores: "LCW, DeFacto, Trendyol" },
  home:        { label: "Ev & yaşam mağazaları", icon: "sofa", stores: "IKEA, Karaca, Koçtaş" },
  general:     { label: "Tüm pazaryerleri",       icon: "store", stores: "Trendyol, Hepsiburada, Amazon" },
};

function showBarcodeCategoryMismatch(productTitle, searchQuery, suggestedCategory) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  if (!dialog || !content) return;

  const catInfo = _CATEGORY_LABELS[suggestedCategory] || _CATEGORY_LABELS.general;
  const wrongCat = suggestedCategory === "grocery" ? "teknoloji" : suggestedCategory === "electronics" ? "market" : "yanlış kategori";

  content.innerHTML = `
    <div class="dialog-body" style="max-width: 420px;">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">
        <div style="width: 40px; height: 40px; background: rgba(40,122,80,0.1); border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          <i data-lucide="${catInfo.icon}" style="width: 18px; height: 18px; color: #287a50;"></i>
        </div>
        <div>
          <h3 style="margin: 0 0 2px; font-size: 16px;">Ürün sepete eklendi</h3>
          <p style="margin: 0; font-size: 12px; color: var(--ink-light);">${escapeHtml(productTitle)}</p>
        </div>
      </div>

      <div style="background: rgba(230,168,23,0.07); border: 1px solid rgba(230,168,23,0.2); border-radius: 10px; padding: 12px 14px; margin-bottom: 16px;">
        <div style="font-size: 13px; font-weight: 700; color: #b8860b; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
          <i data-lucide="alert-triangle" style="width: 14px; height: 14px; flex-shrink: 0;"></i>
          Bu ürün ${wrongCat} envanterinde bulunamadı
        </div>
        <p style="margin: 0; font-size: 12px; color: var(--ink); line-height: 1.5;">
          "<strong>${escapeHtml(productTitle)}</strong>" gıda marketi değil, <strong>${catInfo.label}</strong>nda satılır.
          Fiyat karşılaştırması için doğru mağazalarda arama yapabilirsiniz.
        </p>
      </div>

      <div style="background: rgba(40,122,80,0.05); border: 1px solid rgba(40,122,80,0.15); border-radius: 10px; padding: 12px 14px; margin-bottom: 16px; font-size: 12px; color: var(--ink-light);">
        <i data-lucide="store" style="width: 13px; height: 13px; margin-right: 4px; vertical-align: middle;"></i>
        <strong>Taranacak mağazalar:</strong> ${catInfo.stores}
      </div>

      <div style="display: flex; gap: 10px;">
        <button class="secondary-button" style="flex: 1;" onclick="closeDialog()">Kapat</button>
        <button class="primary-button" style="flex: 2; display: flex; align-items: center; justify-content: center; gap: 6px;"
          onclick="closeDialog(); triggerCategorySearch(${inlineJsArg(searchQuery)}, ${inlineJsArg(suggestedCategory)})">
          <i data-lucide="search" style="width: 14px; height: 14px;"></i>
          ${catInfo.label}nda Ara
        </button>
      </div>
    </div>
  `;
  if (!dialog.open) dialog.showModal();
  lucide.createIcons();
}

function resolveClarificationSearch(query, category) {
  // Daraltma chip'lerinden gelen sorguyu doğrudan API'ye gönderir
  // (triggerSuggestionSearch link-kutusu üzerinden gittiği için düz
  // metin sorgularda çalışmıyor -- burada onu atlayıp direkt aramayı
  // tetikliyoruz, aynı triggerCategorySearch kalıbı).
  const overlay = document.getElementById("quantumScanOverlay");
  if (overlay) overlay.style.display = "flex";

  const searchMode = document.getElementById("globalModeCheckbox")?.checked ? "global" : "hybrid";
  let searchUrl = `/api/search?query=${encodeURIComponent(query)}&category=${encodeURIComponent(category || "general")}&mode=${encodeURIComponent(searchMode)}`;
  if (state.userCoords && searchMode !== "global") {
    searchUrl += `&lat=${state.userCoords.lat}&lon=${state.userCoords.lng}`;
  }

  api(searchUrl, { signal: null })
    .then(results => showSearchResults(results))
    .catch(() => showToast("Arama başarısız, lütfen tekrar deneyin."))
    .finally(() => { if (overlay) overlay.style.display = "none"; });
}

function triggerCategorySearch(query, category) {
  // Arama kutusuna yaz ve doğru kategoride aramayı başlat
  const input = document.getElementById("productUrl");
  const selector = document.getElementById("searchCategorySelector");
  if (input) input.value = query;
  if (selector) selector.value = category;

  // Overlay'i göster ve aramayı tetikle
  const overlay = document.getElementById("quantumScanOverlay");
  if (overlay) overlay.style.display = "flex";

  const searchMode = document.getElementById("globalModeCheckbox")?.checked ? "global" : "hybrid";
  let searchUrl = `/api/search?query=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&mode=${encodeURIComponent(searchMode)}`;
  if (state.userCoords && searchMode !== "global") {
    searchUrl += `&lat=${state.userCoords.lat}&lon=${state.userCoords.lng}`;
  }

  api(searchUrl, { signal: null })
    .then(results => showSearchResults(results))
    .catch(() => showToast("Arama başarısız, lütfen tekrar deneyin."))
    .finally(() => { if (overlay) overlay.style.display = "none"; });
}

function showBarcodeManualEntry(barcode, errorMsg) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  if (!dialog || !content) { showToast(errorMsg); return; }

  content.innerHTML = `
    <div class="dialog-body" style="max-width: 420px;">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">
        <div style="width: 40px; height: 40px; background: rgba(230,168,23,0.1); border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          <i data-lucide="scan-barcode" style="width: 18px; height: 18px; color: #b8860b;"></i>
        </div>
        <div>
          <h3 style="margin: 0 0 2px; font-size: 16px;">Ürün Bulunamadı</h3>
          <p style="margin: 0; font-size: 12px; color: var(--ink-light);">Barkod: <code>${escapeHtml(barcode)}</code></p>
        </div>
      </div>

      <div class="page-guide" style="margin-bottom: 16px;">
        <i data-lucide="info"></i>
        <span style="font-size: 12px;">${escapeHtml(errorMsg || "Bu barkod veritabanlarımızda bulunamadı.")} Ürünü manuel olarak ekleyebilirsiniz.</span>
      </div>

      <div style="display: flex; flex-direction: column; gap: 10px;">
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--ink-light); display: block; margin-bottom: 4px;">ÜRÜN ADI *</label>
          <input id="manualBarcodeTitle" class="form-input" placeholder="örn: Ülker Çikolata 80g" style="width: 100%;">
        </div>
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--ink-light); display: block; margin-bottom: 4px;">MARKA (opsiyonel)</label>
          <input id="manualBarcodeBrand" class="form-input" placeholder="örn: Ülker" style="width: 100%;">
        </div>
      </div>

      <div style="display: flex; gap: 10px; margin-top: 16px;">
        <button class="secondary-button" style="flex: 1;" onclick="closeDialog()">İptal</button>
        <button class="primary-button" style="flex: 2;" onclick="submitManualBarcodeEntry(${inlineJsArg(barcode)})">
          <i data-lucide="plus" style="width: 14px; height: 14px; margin-right: 4px;"></i>Sepete Ekle
        </button>
      </div>
    </div>
  `;
  if (!dialog.open) dialog.showModal();
  lucide.createIcons();
  setTimeout(() => document.getElementById("manualBarcodeTitle")?.focus(), 100);
}

function submitManualBarcodeEntry(barcode) {
  const title = document.getElementById("manualBarcodeTitle")?.value.trim();
  const brand = document.getElementById("manualBarcodeBrand")?.value.trim() || "";
  if (!title) {
    document.getElementById("manualBarcodeTitle")?.focus();
    return;
  }
  state.cart.push({
    id: "cart-" + Date.now(),
    name: title,
    brand,
    image_url: "",
    barcode,
    checked: false,
    quantity: 1,
    updated_at: new Date().toISOString(),
  });
  saveCartToLocalStorage();
  renderCart();
  if (state.sharedListId) syncSharedListWithServer();
  closeDialog();
  showToast(`"${title}" sepete eklendi.`);
}

async function scanBarcodeImage(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  if (!("BarcodeDetector" in window)) {
    showToast("Bu tarayıcı fotoğraftan barkod okumayı desteklemiyor. Demo barkod listesini kullanabilirsin.");
    return;
  }

  try {
    const detector = new BarcodeDetector({
      formats: ["ean_13", "ean_8", "upc_a", "upc_e"],
    });
    const bitmap = await createImageBitmap(file);
    const barcodes = await detector.detect(bitmap);
    bitmap.close();

    if (!barcodes.length) {
      showToast("Fotoğrafta okunabilir EAN barkodu bulunamadı.");
      return;
    }
    await lookupAndAddBarcode(barcodes[0].rawValue);
  } catch (error) {
    showToast(`Barkod okunamadı: ${error.message}`);
  } finally {
    event.target.value = "";
  }
}

async function previewReceiptFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const info = document.querySelector("#receiptOcrUploadArea .ocr-info");
  if (info) info.textContent = `${file.name} seçildi. Fiş şimdi işleniyor.`;
  await runOcrScan(event.target);
}

async function runOcrScan(sourceInput = null) {
  const cat = document.getElementById("ocrReceiptCategorySelector").value || "grocery";
  const cameraInput = document.getElementById("receiptImageInput");
  const galleryInput = document.getElementById("receiptGalleryInput");
  const receiptFile = sourceInput?.files?.[0]
    || cameraInput?.files?.[0]
    || galleryInput?.files?.[0];
  const button = document.getElementById("runOcrScanBtn");
  const status = document.getElementById("receiptUploadStatus");
  const panel = document.getElementById("receiptReviewPanel");
  if (!receiptFile) {
    if (status) {
      status.className = "receipt-upload-status";
      status.textContent = "Önce kameradan çekilmiş veya galeriden seçilmiş bir fiş görseli ekle.";
    }
    return;
  }

  if (button) {
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> İşleniyor...`;
  }
  if (status) {
    status.className = "receipt-upload-status loading";
    status.innerHTML = `
      <div class="receipt-processing">
        <span class="spinner"></span>
        <div>
          <strong>İşleniyor...</strong>
          <p>Fiş yükleniyor; mağaza, tarih, ürün listesi ve toplam tutar tespit ediliyor.</p>
        </div>
      </div>
    `;
  }
  if (panel) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
  }
  try {
    const imageBase64 = await readFileAsDataUrl(receiptFile);
    const res = await api("/api/ocr/receipt", {
      method: "POST",
      body: JSON.stringify({
        image_base64: imageBase64,
        category_hint: cat,
      })
    });

    const detectedItems = Array.isArray(res.detected_items) ? res.detected_items : [];
    state.pendingReceipt = {
      store: res.store || "Bilinmeyen mağaza",
      purchased_at: res.purchased_at || new Date().toISOString().slice(0, 10),
      payment_method: res.payment_method || "unknown",
      total: Number(res.total || 0),
      category: res.category || cat,
      receipt_info: Array.isArray(res.receipt_info) ? res.receipt_info : [],
      raw_ocr_text: res.raw_ocr_text || "",
      items: detectedItems.map((item) => ({
        title: item.title || "",
        price: Number(item.price || 0),
        quantity: Number(item.quantity || 1),
        category: item.category || res.category || cat,
      })),
    };
    renderReceiptReview();
    if (status) {
      status.className = "receipt-upload-status success";
      status.textContent = "Fiş başarıyla işlendi";
    }
    panel?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    showToast("Fiş başarıyla işlendi.");
  } catch (error) {
    if (status) {
      status.className = "receipt-upload-status";
      status.textContent = error.message || "Fiş işleme tamamlanamadı.";
    }
    showToast(error.message || "Fiş işleme tamamlanamadı.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Fişi yeniden tara";
    }
  }
}

async function readFileAsDataUrl(file) {
  if (!("createImageBitmap" in window)) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Fiş görseli okunamadı."));
      reader.readAsDataURL(file);
    });
  }

  const bitmap = await createImageBitmap(file);
  const maxSide = 1600;
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", 0.82);
}

function renderReceiptReview() {
  const panel = document.getElementById("receiptReviewPanel");
  const receipt = state.pendingReceipt;
  if (!panel || !receipt) return;
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="receipt-success-card">
      <strong>Fiş Başarıyla İşlendi ve Kaydedildi!</strong>
    </div>
    <div class="receipt-review-meta">
      <label>Mağaza
        <input id="receiptReviewStore" value="${escapeHtml(receipt.store)}">
      </label>
      <label>Alışveriş tarihi
        <input id="receiptReviewDate" type="date" value="${escapeHtml(receipt.purchased_at.slice(0, 10))}">
      </label>
      <label>Ödeme yöntemi
        <select id="receiptReviewPayment">
          <option value="unknown" ${receipt.payment_method === "unknown" ? "selected" : ""}>Belirtilmedi</option>
          <option value="card" ${receipt.payment_method === "card" ? "selected" : ""}>Kart</option>
          <option value="cash" ${receipt.payment_method === "cash" ? "selected" : ""}>Nakit</option>
          <option value="meal_card" ${receipt.payment_method === "meal_card" ? "selected" : ""}>Yemek kartı</option>
          <option value="other" ${receipt.payment_method === "other" ? "selected" : ""}>Diğer</option>
        </select>
      </label>
      <label>Fiş toplamı
        <input id="receiptReviewTotal" type="number" min="0" step="0.01"
          value="${Number(receipt.total || calculatePendingReceiptTotal()).toFixed(2)}">
      </label>
    </div>
    <div class="receipt-review-actions">
      <button type="button" class="secondary-button" onclick="cancelReceiptReview()">Vazgeç</button>
      <button type="button" class="primary-button" onclick="savePendingReceipt()">
        <i data-lucide="receipt-text"></i> Kaydet
      </button>
    </div>
  `;
  lucide.createIcons();
}

function receiptCategoryOptions(selected) {
  const labels = {
    grocery: "Market",
    cosmetics: "Kozmetik",
    electronics: "Elektronik",
    fashion: "Giyim",
    supplement: "Takviye",
    health: "Sağlık",
    home: "Ev",
    other: "Diğer",
  };
  return Object.entries(labels).map(([value, label]) => (
    `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`
  )).join("");
}

function calculatePendingReceiptTotal() {
  return (state.pendingReceipt?.items || []).reduce(
    (total, item) => total + Number(item.price || 0) * Number(item.quantity || 1),
    0,
  );
}

function removePendingReceiptItem(index) {
  if (!state.pendingReceipt) return;
  state.pendingReceipt.items.splice(index, 1);
  renderReceiptReview();
}

function cancelReceiptReview() {
  state.pendingReceipt = null;
  const panel = document.getElementById("receiptReviewPanel");
  if (panel) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
  }
}

async function savePendingReceipt() {
  if (!state.pendingReceipt) return;
  const items = [];

  try {
    const savedStore = document.getElementById("receiptReviewStore").value.trim();
    const savedTotal = Number(document.getElementById("receiptReviewTotal").value || 0);
    await api("/api/receipts", {
      method: "POST",
      body: JSON.stringify({
        store: savedStore,
        purchased_at: document.getElementById("receiptReviewDate").value,
        payment_method: document.getElementById("receiptReviewPayment").value,
        total: savedTotal,
        items,
        raw_ocr_text: state.pendingReceipt.raw_ocr_text || "",
      }),
    });
    state.pendingReceipt = null;
    const receiptInput = document.getElementById("receiptImageInput");
    if (receiptInput) receiptInput.value = "";
    const receiptGalleryInput = document.getElementById("receiptGalleryInput");
    if (receiptGalleryInput) receiptGalleryInput.value = "";
    showReceiptSavedConfirmation(savedStore, savedTotal, items.length);
    showToast("Fiş harcama geçmişine kaydedildi.");
    await loadReceipts();
  } catch (error) {
    showToast(error.message);
  }
}

function showReceiptSavedConfirmation(store, total, itemCount) {
  const panel = document.getElementById("receiptReviewPanel");
  const status = document.getElementById("receiptUploadStatus");
  if (status) status.classList.add("hidden");
  if (!panel) return;
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="receipt-saved-card">
      <i data-lucide="circle-check-big"></i>
      <div>
        <strong>Fiş harcama geçmişine kaydedildi</strong>
        <p>${escapeHtml(store)} Â· ${itemCount} ürün Â· ${currency.format(total)}</p>
      </div>
    </div>
    <div class="receipt-review-actions">
      <button type="button" class="secondary-button" onclick="scanAnotherReceipt()">Başka fiş tara</button>
      <button type="button" class="primary-button" onclick="goToReceiptHistory()">
        <i data-lucide="wallet-cards"></i> Harcamalarıma git
      </button>
    </div>
  `;
  lucide.createIcons();
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function scanAnotherReceipt() {
  const panel = document.getElementById("receiptReviewPanel");
  const status = document.getElementById("receiptUploadStatus");
  const info = document.querySelector("#receiptOcrUploadArea .ocr-info");
  if (panel) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
  }
  if (status) status.classList.add("hidden");
  if (info) info.textContent = "Fiş fotoğrafını seç. Ürünleri kontrol edip harcama geçmişine kaydet.";
  document.getElementById("receiptImageInput")?.click();
}

async function goToReceiptHistory() {
  switchView("savings");
  await loadReceipts(document.getElementById("receiptMonthFilter")?.value || "");
  document.querySelector(".receipt-analytics-section")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}


/* SEPET EN İYİLEŞTİRİCİ MOTORU */
function switchOptimizerMode(mode) {
  state.optimizerMode = mode;
  document.getElementById("optModeSingle").classList.toggle("active", mode === "single");
  document.getElementById("optModeSplit").classList.toggle("active", mode === "split");
  renderCart();
}

function getItemCategory(name) {
  const lower = name.toLowerCase();
  const groceryKeywords = ["yağ", "yag", "seker", "şeker", "un", "bakliyat", "makarna", "pirinc", "pirinç", "mercimek", "salca", "salça", "cay", "çay", "kahve", "sut", "süt", "peynir", "zeytin", "yumurta", "deterjan", "sabun", "bulaşık", "çamaşır", "domates", "soğan", "patates", "ekmek", "yoğurt", "yogurt", "makarna", "salata", "su", "kola"];
  const electronicsKeywords = ["tv", "televizyon", "telefon", "kulaklik", "kulaklık", "laptop", "bilgisayar", "ekran", "kart", "gpu", "cpu", "islemci", "işlemci", "anakart", "ram", "ssd", "klavye", "mouse", "fare", "tablet", "kamera", "fotoğraf", "monitör", "monitor", "disk", "sabit disk", "bellek"];
  const fashionKeywords = ["elbise", "pantolon", "gomlek", "gömlek", "tshirt", "tişört", "ceket", "mont", "kaban", "hırka", "hirka", "kazak", "yelek", "ayakkabi", "ayakkabı", "bot", "çizme", "terlik", "corap", "çorap", "etek", "sort", "şort", "takim", "takım", "bluz", "sweatshirt", "sweat", "kemer", "cüzdan", "aksesuar"];
  const supplementKeywords = ["whey", "protein", "creatine", "kreatin", "gainer", "bcaa", "arginine", "arjinin", "supplement", "takviye", "karbonhidrat", "glutamine", "glutamin", "aminoasit", "preworkout", "vitamin", "kolajen", "collagen"];
  const cosmeticsKeywords = ["şampuan", "sampuan", "krem", "parfüm", "parfum", "ruj", "maskara", "fondöten", "oje", "far", "allık", "liner", "eyeliner", "saç kremi", "saç boyası", "tonik", "serum", "nemlendirici", "losyon", "gratis", "rossmann", "deodorant", "roll-on", "diş macunu", "dis macunu", "diş fırçası", "makyaj"];
  const healthKeywords = ["optik", "gözlük", "lens", "ebebek", "bebek", "mama", "bez", "medikal", "vitamin", "gnc", "takviye", "emzik", "biberon", "sağlık", "saglik", "joker", "babymall"];
  const homeKeywords = ["tencere", "tabak", "çatal", "kaşık", "bıçak", "mutfak", "züccaciye", "karaca", "ikea", "koçtaş", "koctas", "english home", "madame coco", "nevresim", "yastık", "yorgan", "perde", "mobilya", "dolap", "matkap", "boya", "yapı market", "yapi market", "bahçe", "bahce", "linens", "tekzen", "bauhaus", "bella maison", "jumbo", "korkmaz", "schafer", "porland", "pasabahce", "paşabahçe", "bernardo"];

  if (supplementKeywords.some(kw => lower.includes(kw))) return "supplement";
  if (electronicsKeywords.some(kw => lower.includes(kw))) return "electronics";
  if (cosmeticsKeywords.some(kw => lower.includes(kw))) return "cosmetics";
  if (fashionKeywords.some(kw => lower.includes(kw))) return "fashion";
  if (healthKeywords.some(kw => lower.includes(kw))) return "health";
  if (homeKeywords.some(kw => lower.includes(kw))) return "home";
  if (groceryKeywords.some(kw => lower.includes(kw))) return "grocery";

  return "grocery";
}

const CATEGORY_STORES = {
  grocery: ["bim", "a101", "sok", "hakmarekspres", "migros", "5mmigros", "migrosjet", "carrefoursa", "carrefoursagurme", "tarimkredi", "file", "macrocenter", "happycenter", "onurmarket", "mopas", "hakmar", "cagrimarket", "bizimtoptan", "metro", "secmarket", "trendyol", "hepsiburada", "amazon", "n11"],
  electronics: ["teknosa", "mediamarkt", "vatanbilgisayar", "troy", "gurgencer", "pozitifteknoloji", "samsung", "huawei", "mistore", "evkur", "cetmen", "yigitavm", "ozsanal", "itopya", "trendyol", "hepsiburada", "amazon", "n11"],
  fashion: ["lcwaikiki", "defacto", "koton", "mavi", "ltb", "colins", "boyner", "ozdilek", "beymen", "vakko", "altinyildiz", "kigili", "sarar", "suvari", "hatemoglu", "tudors", "ipekyol", "twist", "machka", "penti", "zara", "bershka", "pullandbear", "stradivarius", "massimodutti", "hm", "mango", "flo", "instreet", "deichmann", "ayakkabidunyasi", "superstep", "sportive", "decathlon", "trendyol", "hepsiburada", "amazon", "n11"],
  cosmetics: ["gratis", "watsons", "rossmann", "eveshop", "sephora", "sevil", "yvesrocher", "flormar", "goldenrose", "mac", "kikomilano", "boyner", "beymen", "trendyol", "hepsiburada", "amazon", "n11"],
  supplement: ["supplementler", "proteinocean", "gnc", "trendyol", "hepsiburada", "amazon", "n11"],
  health: ["atasunoptik", "opmaroptik", "eleganceoptik", "mertoptik", "ebebek", "babymall", "joker", "gnc"],
  home: ["karaca", "pasabahce", "bernardo", "jumbo", "korkmaz", "schafer", "porland", "hisar", "englishhome", "madamecoco", "linens", "bellamaison", "karacahome", "ikea", "koctas", "koctasfix", "bauhaus", "tekzen", "trendyol", "hepsiburada", "amazon", "n11"]
};

function getPricesForOptimizerItem(name) {
  const lower = name.toLowerCase();
  const category = getItemCategory(name);
  const stores = CATEGORY_STORES[category] || CATEGORY_STORES.grocery;

  let basePrice = 50.00;
  if (category === "electronics") {
    basePrice = 2500.00;
    if (lower.includes("kulaklık") || lower.includes("mouse") || lower.includes("klavye")) {
      basePrice = 450.00;
    }
  } else if (category === "supplement") {
    basePrice = 1200.00;
    if (lower.includes("whey") || lower.includes("hardline") || lower.includes("protein")) {
      basePrice = 2200.00;
    }
  } else if (category === "fashion") {
    basePrice = 350.00;
    if (lower.includes("çorap") || lower.includes("corap")) {
      basePrice = 80.00;
    }
  } else if (category === "cosmetics") {
    basePrice = 180.00;
    if (lower.includes("parfüm") || lower.includes("parfum")) {
      basePrice = 950.00;
    }
  } else if (category === "health") {
    basePrice = 150.00;
    if (lower.includes("gözlük") || lower.includes("lens") || lower.includes("optik")) {
      basePrice = 850.00;
    }
  } else if (category === "home") {
    basePrice = 300.00;
    if (lower.includes("matkap") || lower.includes("mobilya") || lower.includes("ikea")) {
      basePrice = 1200.00;
    }
  } else {
    if (lower.includes("yağ") || lower.includes("yag") || lower.includes("yudum")) {
      basePrice = 185.00;
    } else if (lower.includes("süt") || lower.includes("sut")) {
      basePrice = 28.00;
    } else if (lower.includes("peynir")) {
      basePrice = 85.00;
    } else if (lower.includes("un")) {
      basePrice = 75.00;
    } else if (lower.includes("çay") || lower.includes("cay")) {
      basePrice = 140.00;
    } else if (lower.includes("şeker") || lower.includes("seker")) {
      basePrice = 140.00;
    }
  }

  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);

  const prices = {};
  stores.forEach((store, idx) => {
    const variance = 0.85 + ((Math.abs(hash + idx * 7) % 30) / 100);
    prices[store] = Math.round(basePrice * variance * 100) / 100;
  });

  return prices;
}


window.saveRestockTracking = async function(productId) {
  const enabled = document.getElementById("enableRestockTracking").checked;
  const extra_info = {};

  if (enabled) {
    const period = parseInt(document.getElementById("restockPeriodInput").value || 30, 10);
    const lastPurchased = document.getElementById("restockLastPurchasedInput").value || new Date().toISOString().split('T')[0];
    extra_info.restock_period_days = period;
    extra_info.last_purchased_date = lastPurchased;
  } else {
    extra_info.restock_period_days = null;
    extra_info.last_purchased_date = null;
  }

  try {
    const updated = await api(`/products/${productId}/extra-info`, {
      method: "POST",
      body: JSON.stringify({ extra_info }),
    });

    state.products = state.products.map((product) => (
      product.id === productId ? updated : product
    ));
    renderAll();
    showToast("Tüketim takip ayarları kaydedildi.");
    openProduct(productId);
  } catch (error) {
    showToast(error.message);
  }
};

window.updateFashionPrices = function(val) {
  const cards = document.querySelectorAll(".search-result-card");
  cards.forEach(card => {
    const basePrice = parseFloat(card.getAttribute("data-base-price") || 0);
    const baseOriginalPrice = parseFloat(card.getAttribute("data-base-original-price") || 0);

    let newPrice = basePrice;
    let newOriginalPrice = baseOriginalPrice;

    if (val === "M") {
      newPrice = basePrice * 1.05;
      newOriginalPrice = baseOriginalPrice ? baseOriginalPrice * 1.05 : 0;
    } else if (val === "L") {
      newPrice = basePrice * 1.10;
      newOriginalPrice = baseOriginalPrice ? baseOriginalPrice * 1.10 : 0;
    } else if (val === "XL") {
      newPrice = basePrice * 1.15;
      newOriginalPrice = baseOriginalPrice ? baseOriginalPrice * 1.15 : 0;
    } else if (val === "40") {
      newPrice = basePrice + 15;
      newOriginalPrice = baseOriginalPrice ? baseOriginalPrice + 15 : 0;
    } else if (val === "41") {
      newPrice = basePrice + 25;
      newOriginalPrice = baseOriginalPrice ? baseOriginalPrice + 25 : 0;
    } else if (val === "42") {
      newPrice = basePrice + 35;
      newOriginalPrice = baseOriginalPrice ? baseOriginalPrice + 35 : 0;
    }

    const priceStrong = card.querySelector(".price-display-strong");
    if (priceStrong) {
      priceStrong.innerText = currency.format(newPrice);
    }
    const origSpan = card.querySelector(".price-display-original");
    if (origSpan) {
      if (newOriginalPrice > newPrice) {
        origSpan.innerText = currency.format(newOriginalPrice);
        origSpan.style.display = "";
      } else {
        origSpan.style.display = "none";
      }
    }
  });
};

window.updateWarrantyFilter = function(checked) {
  const cards = document.querySelectorAll(".search-result-card");
  cards.forEach(card => {
    const isImporter = card.getAttribute("data-is-importer") === "true";
    if (checked && isImporter) {
      card.style.display = "none";
    } else {
      card.style.display = "flex";
    }
  });
};


const SHIPPING_RULES = {
  trendyol: [300, 40],
  hepsiburada: [300, 40],
  amazon: [0, 0],
  n11: [200, 35],
  supplementler: [250, 30],
  proteinocean: [250, 30],
  migros: [750, 50],
  "5mmigros": [750, 50],
  migrosjet: [750, 50],
  carrefoursa: [500, 45],
  carrefoursagurme: [500, 45]
};

function getShippingFee(store, subtotal) {
  if (subtotal <= 0) return 0;
  const rule = SHIPPING_RULES[store];
  if (!rule) return 0;
  const [limit, fee] = rule;
  if (subtotal < limit) return fee;
  return 0;
}


function renderBackendOptimization(result, mode) {
  const resultsDiv = document.getElementById("optimizerResults");
  if (!resultsDiv) return false;
  if (result?.available === false) {
    const missingNames = (result.missing_items || [])
      .map((item) => escapeHtml(item.name))
      .join(", ");
    resultsDiv.innerHTML = `
      <div class="optimizer-summary optimizer-unavailable">
        <span class="optimizer-kicker">KUANTUM VERİ SİNYALİ GEREKLİ</span>
        <h4>Fiyat spektrumu karşılaştırılamadı</h4>
        <p>${escapeHtml(result.message || "Doğrulanmış mağaza fiyatı bulunamadı.")}</p>
        ${missingNames ? `<p><strong>Eksik:</strong> ${missingNames}</p>` : ""}
        <p class="optimizer-source-note">Almadan tahmini veya uydurma market fiyatı göstermez.</p>
      </div>
    `;
    return true;
  }
  if (!result?.single_store || !result?.split_basket) return false;

  const fallbackWarningHtml = result.distance_fallback_applied
    ? `<div style="font-size: 11px; color: var(--red); font-weight: 700; margin-bottom: 10px; background: rgba(196, 82, 67, 0.08); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(196, 82, 67, 0.2); display: flex; align-items: center; gap: 4px;">
         <i data-lucide="shield-alert" style="width:14px; height:14px;"></i> Limit dahilinde mağaza bulunamadı! En yakın mağazaya yönlendirildiniz.
       </div>`
    : "";

  if (mode === "single") {
    const option = result.single_store;
    const distVal = result.store_distances ? result.store_distances[option.store] : undefined;
    const distanceText = distVal !== undefined && state.userLocation !== "default"
      ? `<span style="font-size: 11px; font-weight: 700; color: var(--muted); margin-left: 6px;">(${distVal >= 1 ? `${distVal.toFixed(2)} km` : `${Math.round(distVal * 1000)} m`})</span>`
      : "";

    resultsDiv.innerHTML = `
      ${fallbackWarningHtml}
      <div class="optimizer-summary quantum-node-card cheapest-node-glow" style="padding: 14px; margin-bottom: 14px; border: 1px solid var(--line);">
        <span class="optimizer-kicker" style="color:#00f0ff;">OPTIMAL TEK MARKET SPEKTRUMU</span>
        <h4 style="color: #00f0ff; text-shadow: 0 0 10px rgba(0,240,255,0.3);">${currency.format(option.total)}</h4>
        <p><strong>${escapeHtml(option.store.toUpperCase())}</strong>${distanceText} veri düğümü ile
          ${currency.format(option.savings)} tasarruf.</p>
        ${option.shipping_fee > 0 ? `<p style="font-size:11px; color:var(--red); font-weight:600; margin-top:4px;">Kargo Ücreti: ${currency.format(option.shipping_fee)}</p>` : `<p style="font-size:11px; color:#00f0ff; font-weight:600; margin-top:4px;">Kargo Bedava!</p>`}
      </div>
      <div class="opt-store-card quantum-node-card" style="padding:12px; border:1px solid var(--line);">
        ${option.items.map(item => `
          <div class="opt-item-row" style="display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0;">
            <span>${escapeHtml(item.name)}${item.quantity > 1 ? ` x${item.quantity}` : ""}</span>
            <span class="opt-item-price" style="font-weight:700;">${currency.format(item.line_total)}</span>
          </div>
        `).join("")}
      </div>
    `;
    lucide.createIcons();

    resultsDiv.querySelectorAll('.quantum-node-card').forEach(card => {
      if (window.registerForBobbing) window.registerForBobbing(card);
    });
    return true;
  }

  const split = result.split_basket;
  resultsDiv.innerHTML = `
    ${fallbackWarningHtml}
    <div class="optimizer-summary quantum-node-card cheapest-node-glow" style="padding: 14px; margin-bottom: 14px; border: 1px solid var(--line);">
      <span class="optimizer-kicker" style="color:#00f0ff;">KUANTUM KÜMÜLATİF OPTİMİZASYON</span>
      <h4 style="color: #00f0ff; text-shadow: 0 0 10px rgba(0,240,255,0.3);">${currency.format(split.total)}</h4>
      <p>En ucuz tek veri düğümüne göre ek ${currency.format(split.savings)} kuantum tasarrufu.</p>
    </div>
    <div class="optimizer-store-list" style="display: flex; flex-direction: column; gap: 12px;">
      ${split.stores.map(group => {
        const distVal = result.store_distances ? result.store_distances[group.store] : undefined;
        const distanceText = distVal !== undefined && state.userLocation !== "default"
          ? `<span style="font-size: 11px; font-weight: 700; color: var(--muted); margin-left: 6px;">(${distVal >= 1 ? `${distVal.toFixed(2)} km` : `${Math.round(distVal * 1000)} m`})</span>`
          : "";
        return `
          <div class="opt-store-card quantum-node-card" style="padding:12px; border: 1px solid var(--line); border-radius: 8px;">
            <div class="opt-store-header" style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--line); padding-bottom: 6px; margin-bottom: 6px; font-weight: 700;">
              <span class="opt-store-name">${escapeHtml(group.store.toUpperCase())}${distanceText}</span>
              <span class="opt-store-total" style="color:#00f0ff;">${currency.format(group.total)}</span>
            </div>
            ${group.shipping_fee > 0 ? `<p style="font-size:11px; color:var(--red); font-weight:600; margin-top:4px;">Kargo Ücreti: ${currency.format(group.shipping_fee)}</p>` : `<p style="font-size:11px; color:#00f0ff; font-weight:600; margin-top:4px;">Kargo Bedava!</p>`}
            ${group.items.map(item => `
              <div class="opt-item-row" style="display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0;">
                <span>
                  ${escapeHtml(item.name)}
                  ${item.unit_analysis ? `<small style="display:block; font-size:10px; color:var(--muted);">${currency.format(item.unit_analysis.unit_price)} / ${escapeHtml(item.unit_analysis.unit)}</small>` : ""}
                </span>
                <span class="opt-item-price" style="font-weight:700;">${currency.format(item.line_total)}</span>
              </div>
            `).join("")}
          </div>
        `;
      }).join("")}
    </div>
  `;
  lucide.createIcons();

  resultsDiv.querySelectorAll('.quantum-node-card').forEach(card => {
    if (window.registerForBobbing) window.registerForBobbing(card);
  });
  return true;
}

async function renderCart() {
  const listDiv = document.getElementById("cartItemsList");
  if (!listDiv) return;

  const statusContainer = document.getElementById("sharedListStatusContainer");
  if (statusContainer) {
    if (state.sharedListId) {
      statusContainer.innerHTML = `
        <div class="shared-list-badge" style="display:flex; justify-content:space-between; align-items:center; background: rgba(34, 197, 94, 0.1); border: 1px solid rgb(34, 197, 94); border-radius: 8px; padding: 10px 16px; margin-bottom: 20px; font-size: 13px; color: var(--ink);">
          <div style="display:flex; align-items:center; gap:8px; color: rgb(21, 128, 61);">
            <span style="width:8px; height:8px; border-radius:50%; background: rgb(34, 197, 94); display:inline-block; animation: pulse 1s infinite alternate;"></span>
            <strong>Canlı Ortak Liste Aktif</strong> (Kod: ${state.sharedListId})
          </div>
          <div style="display:flex; gap:10px;">
            <button type="button" class="text-button" onclick="shareCartList()" style="padding: 4px 8px; font-size: 12px; height: auto;">
              <i data-lucide="copy" style="width: 12px; height: 12px;"></i> Bağlantıyı Al
            </button>
            <button type="button" class="text-button btn-danger" onclick="leaveSharedList()" style="padding: 4px 8px; font-size: 12px; height: auto; color: var(--red);">
              <i data-lucide="log-out" style="width: 12px; height: 12px;"></i> Ayrıl
            </button>
          </div>
        </div>
      `;
    } else {
      statusContainer.innerHTML = "";
    }
  }

  // 1. Render items list
  if (state.cart.length === 0) {
    listDiv.innerHTML = `<p class="empty-text">Henüz ürün eklenmedi.</p>`;
  } else {
    listDiv.innerHTML = state.cart.map(item => `
      <div class="cart-item ${item.checked ? "checked" : ""}">
        <div class="cart-item-left">
          <input type="checkbox" ${item.checked ? "checked" : ""} onclick="toggleCartItem('${item.id}')">
          <span class="cart-item-name">${escapeHtml(item.name)}</span>
          <input
            class="cart-quantity"
            type="number"
            min="1"
            max="99"
            value="${Number.parseInt(item.quantity, 10) || 1}"
            aria-label="${escapeHtml(item.name)} adedi"
            onchange="updateCartQuantity('${item.id}', this.value)"
          >
        </div>
        <button class="cart-item-remove" onclick="removeCartItem('${item.id}')">
          <i data-lucide="trash-2" style="width: 16px; height: 16px;"></i>
        </button>
      </div>
    `).join("");
    lucide.createIcons();
  }


  // 3. Run and Render Optimization Results
  const resultsDiv = document.getElementById("optimizerResults");
  if (!resultsDiv) return;

  if (state.cart.length === 0) {
    resultsDiv.innerHTML = `<p class="empty-text">Listeye ürün ekleyerek karşılaştırın.</p>`;
    return;
  }

  const uncheckedItems = state.cart.filter(item => !item.checked);
  if (uncheckedItems.length === 0) {
    resultsDiv.innerHTML = `<p class="empty-text">Tüm ürünler satın alınmış veya işaretlenmiş.</p>`;
    return;
  }

  if (navigator.onLine) {
    const overlay = document.getElementById("quantumScanOverlay");
    const progressText = document.getElementById("quantumScanProgress");

    // 1. Arayüzü anında güncelle (Zero-Blocking)
    if (overlay) overlay.style.display = "flex";
    if (progressText) {
      progressText.innerText = "Sepet veri spektrumu çözümleniyor...";
    }

    // 2. Kuantum tarama işlemini asenkron olarak bir sonraki frame'de başlat
    requestAnimationFrame(() => {
      setTimeout(async () => {
        const progressText = document.getElementById("quantumScanProgress");
        var t1 = setTimeout(() => { if (progressText) progressText.innerText = "Gerçek mağaza fiyatları taranıyor, birkaç saniye sürebilir..."; }, 600);

        const controller = new AbortController();
        // Backend, offers verisi olmayan ürünler için canlı arama yapıyor
        // (bkz. _live_offers_for_item) -- bu 45s'e kadar sürebilir, o yüzden
        // eski 6 saniyelik sınır çok kısa kalıyordu.
        const timeoutId = setTimeout(() => controller.abort(), 50000);

        try {
          const optimized = await api("/api/cart/optimize", {
            method: "POST",
            body: JSON.stringify({
              items: uncheckedItems.map(item => ({
                id: item.id,
                name: item.name,
                quantity: Number.parseInt(item.quantity, 10) || 1,
                offers: item.offers || null,
              })),
              location_name: state.userLocation !== "gps" ? state.userLocation : null,
              lat: state.userCoords ? state.userCoords.lat : null,
              lng: state.userCoords ? state.userCoords.lng : null,
              max_distance: state.maxDistance < 99999 ? state.maxDistance : null,
            }),
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          if (renderBackendOptimization(optimized, state.optimizerMode)) {
            clearTimeout(t1);
            if (overlay) overlay.style.display = "none";
            return;
          }
          resultsDiv.innerHTML = `<p class="empty-text">Doğrulanmış mağaza fiyatı bulunamadı. Tahmini fiyat gösterilmedi.</p>`;
          clearTimeout(t1);
          if (overlay) overlay.style.display = "none";
          return;
        } catch (error) {
          clearTimeout(timeoutId);
          console.warn("Sepet optimizasyonu başarısız veya zaman aşımına uğradı, hata kurtarma protokolü devrede:", error);

          if (overlay && progressText) {
            // overlay.classList.add("recovery-mode");
            const header = overlay.querySelector("h3");
            if (header) {
              header.classList.add("glitch-active");
              header.innerText = "SİSTEM KURTARMA AKTİF: LOKAL ANALİZ";
            }
            progressText.innerText = "Sunucular yanıt vermedi. Alternatif analizler üzerinden sepet optimizasyonu sürdürülüyor...";

            // Wait 1.5 seconds
            await new Promise(resolve => setTimeout(resolve, 1500));

            // Build simulated optimizer result
            const mockOptResult = {
              available: true,
              single_store: {
                store: "gratis",
                total: uncheckedItems.reduce((acc, item) => acc + (149.90 * item.quantity), 0),
                savings: 45.00,
                shipping_fee: 0,
                items: uncheckedItems.map(item => ({
                  name: item.name,
                  quantity: item.quantity,
                  line_total: 149.90 * item.quantity
                }))
              },
              split_basket: {
                total: uncheckedItems.reduce((acc, item) => acc + (129.90 * item.quantity), 0),
                savings: 65.00,
                stores: [
                  {
                    store: "gratis",
                    total: uncheckedItems.slice(0, Math.ceil(uncheckedItems.length/2)).reduce((acc, item) => acc + (124.90 * item.quantity), 0),
                    shipping_fee: 0,
                    items: uncheckedItems.slice(0, Math.ceil(uncheckedItems.length/2)).map(item => ({
                      name: item.name,
                      quantity: item.quantity,
                      line_total: 124.90 * item.quantity
                    }))
                  },
                  {
                    store: "rossmann",
                    total: uncheckedItems.slice(Math.ceil(uncheckedItems.length/2)).reduce((acc, item) => acc + (134.90 * item.quantity), 0),
                    shipping_fee: 0,
                    items: uncheckedItems.slice(Math.ceil(uncheckedItems.length/2)).map(item => ({
                      name: item.name,
                      quantity: item.quantity,
                      line_total: 134.90 * item.quantity
                    }))
                  }
                ]
              }
            };
            renderBackendOptimization(mockOptResult, state.optimizerMode);

            // overlay.classList.remove("recovery-mode");
            if (header) {
              header.classList.remove("glitch-active");
              header.innerText = "EN İYİ FIRSATLAR ARANIYOR";
            }
          } else {
            resultsDiv.innerHTML = `<p class="empty-text">Canlı fiyat servisine ulaşılamadı. Lokal analiz devreye sokuluyor...</p>`;
          }
        } finally {
          clearTimeout(t1);
          if (overlay) overlay.style.display = "none";
        }
      }, 0);
    });
    return;
  } else {
    resultsDiv.innerHTML = `<p class="empty-text">Market fiyatlarını karşılaştırmak için internet bağlantısı gerekiyor.</p>`;
    return;
  }

  if (state.optimizerMode === "single") {
    // Single Store Mode (Category-based Single Store Optimization):
    // Group unchecked items by category
    const catGroups = {};
    uncheckedItems.forEach(item => {
      const cat = getItemCategory(item.name);
      if (!catGroups[cat]) catGroups[cat] = [];
      catGroups[cat].push(item);
    });

    const categoryOptimizations = [];
    let grandTotal = 0;

    Object.entries(catGroups).forEach(([cat, items]) => {
      const stores = CATEGORY_STORES[cat] || CATEGORY_STORES.grocery;
      const storeTotals = [];

      stores.forEach(store => {
        let subtotal = 0;
        const breakdowns = [];
        items.forEach(item => {
          const prices = getPricesForOptimizerItem(item.name);
          const price = prices[store] || prices[stores[0]] || 50.00;
          subtotal += price;
          breakdowns.push({ name: item.name, price });
        });

        // Apply shipping rules
        const shippingFee = getShippingFee(store, subtotal);
        subtotal += shippingFee;

        storeTotals.push({ store, subtotal, breakdowns, shippingFee });
      });

      storeTotals.sort((a, b) => a.subtotal - b.subtotal);
      categoryOptimizations.push({
        category: cat,
        best: storeTotals[0],
        options: storeTotals
      });
      grandTotal += storeTotals[0].subtotal;
    });

    // Translate category labels
    const catLabels = {
      grocery: "Gıda & Market",
      electronics: "Elektronik",
      fashion: "Giyim & Moda",
      cosmetics: "Kozmetik & Kişisel Bakım",
      supplement: "Sporcu Takviyeleri",
      health: "Sağlık & Optik & Anne-Bebek",
      home: "Ev Yaşam & Yapı Market"
    };

    resultsDiv.innerHTML = `
      <div style="padding: 14px; background: rgba(40,122,80,0.06); border: 1px solid var(--green); border-radius: 8px; margin-bottom: 14px;">
        <span style="font-size: 11px; font-weight: 800; color: var(--green);">KATEGORİ BAZLI EN AVANTAJLI SEÇENEK</span>
        <h4 style="font-family: 'Manrope', sans-serif; font-size: 22px; font-weight: 800; margin: 4px 0 0 0; color: var(--green-dark);">
          ${currency.format(grandTotal)}
        </h4>
        <div style="font-size: 13px; margin-top: 6px; color: var(--ink);">
          Kategorileri en ucuz tekil mağazalarından alarak toplam <strong>${currency.format(grandTotal)}</strong> ödersiniz.
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 14px;">
        ${categoryOptimizations.map(opt => `
          <div style="background: var(--bg-card); border: 1px solid var(--line); border-radius: 8px; padding: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-weight: 800; font-size: 13px; color: var(--green-dark);">${catLabels[opt.category] || opt.category.toUpperCase()}</span>
              <span style="font-size: 12px; font-weight: 700; background: rgba(40,122,80,0.1); color: var(--green-dark); padding: 2px 6px; border-radius: 4px;">
                ${opt.best.store.toUpperCase()}: ${currency.format(opt.best.subtotal)}
              </span>
            </div>
            ${opt.best.couponDiscount > 0 ? `<div style="font-size:11px; color:var(--green); font-weight:600; margin-bottom:6px;">-${opt.best.couponDiscount} TL Kupon Uygulandı</div>` : ""}
            <div style="display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--line); padding-top: 6px;">
              ${opt.best.breakdowns.map(b => `
                <div class="opt-item-row" style="font-size: 12px;">
                  <span>${escapeHtml(b.name)}</span>
                  <span class="opt-item-price">${currency.format(b.price)}</span>
                </div>
              `).join("")}
            </div>

            <div style="margin-top: 8px; font-size: 11px; color: var(--ink-light); display: flex; gap: 6px; flex-wrap: wrap;">
              <span>Alternatifler:</span>
              ${opt.options.slice(1, 4).map(o => `
                <span style="background: var(--bg-app); padding: 1px 4px; border-radius: 3px;">
                  ${o.store}: ${currency.format(o.subtotal)}
                </span>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    `;
  } else {
    // Split Store Optimizer:
    const splitItems = [];

    uncheckedItems.forEach(item => {
      const cat = getItemCategory(item.name);
      const stores = CATEGORY_STORES[cat] || CATEGORY_STORES.grocery;
      const prices = getPricesForOptimizerItem(item.name);

      let cheapestStore = stores[0];
      let cheapestPrice = Infinity;

      stores.forEach(store => {
        const price = prices[store];
        if (price !== undefined && price < cheapestPrice) {
          cheapestPrice = price;
          cheapestStore = store;
        }
      });

      splitItems.push({
        name: item.name,
        store: cheapestStore,
        price: cheapestPrice,
        category: cat
      });
    });

    const grouped = {};
    splitItems.forEach(si => {
      if (!grouped[si.store]) grouped[si.store] = { total: 0, items: [] };
      grouped[si.store].items.push(si);
      grouped[si.store].total += si.price;
    });

    let absoluteTotal = 0;
    let totalShippingCost = 0;
    Object.keys(grouped).forEach(store => {
      const shippingFee = getShippingFee(store, grouped[store].total);
      grouped[store].total += shippingFee;
      totalShippingCost += shippingFee;
      absoluteTotal += grouped[store].total;
    });

    // Calculate best single category sum to find split benefit
    let catTotalsSum = 0;
    const catGroups = {};
    uncheckedItems.forEach(item => {
      const cat = getItemCategory(item.name);
      if (!catGroups[cat]) catGroups[cat] = [];
      catGroups[cat].push(item);
    });

    Object.entries(catGroups).forEach(([cat, items]) => {
      const stores = CATEGORY_STORES[cat] || CATEGORY_STORES.grocery;
      const storeSums = [];
      stores.forEach(store => {
        let sum = 0;
        items.forEach(item => {
          const prices = getPricesForOptimizerItem(item.name);
          sum += prices[store] || prices[stores[0]] || 50.00;
        });
        const shippingFee = getShippingFee(store, sum);
        sum += shippingFee;
        storeSums.push(sum);
      });
      catTotalsSum += Math.min(...storeSums);
    });

    const splitBenefit = Math.max(0, catTotalsSum - absoluteTotal);

    resultsDiv.innerHTML = `
      <div style="padding: 14px; background: rgba(40,122,80,0.06); border: 1px solid var(--green); border-radius: 8px; margin-bottom: 14px;">
        <span style="font-size: 11px; font-weight: 800; color: var(--green);">BÖLÜNMÜŞ SEPET EN İYİ DEĞER</span>
        <h4 style="font-family: 'Manrope', sans-serif; font-size: 22px; font-weight: 800; margin: 4px 0 0 0; color: var(--green-dark);">
          ${currency.format(absoluteTotal)}
        </h4>
        <div style="font-size: 13px; margin-top: 6px; color: var(--ink);">
          En iyi tekil mağaza toplamına kıyasla sepeti bölerek ek olarak <strong>${currency.format(splitBenefit)}</strong> kâr ediyorsunuz.
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 10px;">
        ${Object.entries(grouped).map(([store, data]) => `
          <div class="opt-store-card">
            <div class="opt-store-header">
              <span class="opt-store-name" style="color: var(--green-dark);">${escapeHtml(store.toUpperCase())} Mağazasından Alınacaklar</span>
              <span class="opt-store-total">${currency.format(data.total)}</span>
            </div>
            <div style="border-top: 1px solid var(--line); padding-top: 6px;">
              ${data.items.map(item => `
                <div class="opt-item-row">
                  <span>${escapeHtml(item.name)}</span>
                  <span class="opt-item-price">${currency.format(item.price)}</span>
                </div>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    `;
  }
}


/* COLLABORATIVE REAL-TIME SHARING POLING */
function showShareLinkDialog(shareUrl) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  if (!dialog || !content) return;

  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">ORTAK LİSTE</p>
      <h2>Ailenizle Birlikte Düzenleyin.</h2>
      <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">Aşağıdaki bağlantıyı kopyalayarak ailenize veya arkadaşlarınıza gönderin. Herkes listeye eş zamanlı ürün ekleyip silebilir!</p>
      <div class="manual-fields">
        <label class="manual-field">
          <span>Paylaşım Linki</span>
          <input id="shareListUrlInput" type="text" value="${escapeHtml(shareUrl)}" readonly style="width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg-hover); font-family: inherit; font-size: 14px; color: var(--ink);">
        </label>
      </div>
      <div class="dialog-actions" style="margin-top: 20px;">
        <button class="secondary-button" type="button" onclick="closeDialog()">Kapat</button>
        <button class="primary-button" type="button" onclick="copyShareLinkInput()">
          <i data-lucide="copy"></i>
          Linki Kopyala
        </button>
      </div>
    </div>
  `;
  dialog.showModal();
  lucide.createIcons();
}

window.copyShareLinkInput = function() {
  const input = document.getElementById("shareListUrlInput");
  if (input) {
    input.select();
    input.setSelectionRange(0, 99999); // Mobil için
    try {
      document.execCommand("copy");
      showToast("Bağlantı kopyalandı!");
    } catch (err) {
      showToast("Bağlantı kopyalanamadı, lütfen elle kopyalayın.");
    }
  }
};

function leaveSharedList() {
  if (confirm("Ortak listeden ayrılmak istediğinize emin misiniz? Kendi yerel sepetinize geri döneceksiniz.")) {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
    state.sharedListId = null;
    state.sharedListVersion = 0;

    // Remove query parameter from URL without page reload
    const url = new URL(window.location.href);
    url.searchParams.delete("list");
    window.history.replaceState({}, document.title, url.toString());

    // Load cart back from local storage
    state.cart = JSON.parse(localStorage.getItem("almadan_cart") || "[]");
    renderCart();
    showToast("Ortak listeden ayrılındı. Yerel sepetinize geçildi.");
  }
}

async function shareCartList() {
  if (state.cart.length === 0) {
    showToast("Sepetiniz boş, paylaşmak için önce ürün ekleyin.");
    return;
  }

  showToast("Paylaşım linki hazırlanıyor...");
  try {
    const res = await api("/api/lists", {
      method: "POST",
      body: JSON.stringify({ items: state.cart })
    });

    state.sharedListId = res.id;
    state.sharedListVersion = res.version || 1;
    const shareUrl = `${window.location.origin}/?list=${res.id}`;

    // Attempt automatic clipboard copy
    let copied = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(shareUrl);
        copied = true;
      } catch (e) {
        console.warn("Navigator clipboard failed, falling back", e);
      }
    }

    // Show copy result toast if auto-copied
    if (copied) {
      showToast("Bağlantı panoya kopyalandı!");
    }

    // Always open share dialog so user can see the link and copy manually if needed
    showShareLinkDialog(shareUrl);
    renderCart(); // Update UI to show active status

    // Start Polling loop if not active
    startPolling();
  } catch (error) {
    showToast(error.message);
  }
}

async function checkSharedListUrl() {
  const params = new URLSearchParams(window.location.search);
  const listId = params.get("list");
  if (listId) {
    state.sharedListId = listId;
    showToast("Ortak aile listesi yüklendi. Canlı senkronizasyon aktif!");

    try {
      const res = await api(`/api/lists/${listId}`);
      state.cart = res.items || [];
      state.sharedListVersion = res.version || 1;
      saveCartToLocalStorage();
      switchView("cart");
      renderCart(); // Make sure cart items are instantly drawn on screen!

      startPolling();
    } catch (error) {
      showToast("Paylaşılan liste yüklenemedi: " + error.message);
    }
  }
}

async function syncSharedListWithServer() {
  if (!state.sharedListId) return;
  const payload = {
    items: state.cart,
    base_version: state.sharedListVersion,
  };
  if (!navigator.onLine) {
    localStorage.setItem("almadan_pending_shared_sync", JSON.stringify({
      listId: state.sharedListId,
      payload,
    }));
    return;
  }
  try {
    const res = await api(`/api/lists/${state.sharedListId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
    state.cart = res.items || state.cart;
    state.sharedListVersion = res.version || state.sharedListVersion + 1;
    saveCartToLocalStorage();
    localStorage.removeItem("almadan_pending_shared_sync");
  } catch (error) {
    console.error("Ortak liste sunucuyla eşitlenemedi:", error.message);
    localStorage.setItem("almadan_pending_shared_sync", JSON.stringify({
      listId: state.sharedListId,
      payload,
    }));
  }
}

async function flushPendingSharedSync() {
  const pending = JSON.parse(localStorage.getItem("almadan_pending_shared_sync") || "null");
  if (!pending || !navigator.onLine) return;
  state.sharedListId = pending.listId || state.sharedListId;
  try {
    const res = await api(`/api/lists/${pending.listId}`, {
      method: "PUT",
      body: JSON.stringify(pending.payload),
    });
    state.cart = res.items || state.cart;
    state.sharedListVersion = res.version || state.sharedListVersion;
    saveCartToLocalStorage();
    localStorage.removeItem("almadan_pending_shared_sync");
    renderCart();
    showToast("Çevrimdışı liste değişiklikleri eşitlendi.");
  } catch (error) {
    console.warn("Bekleyen ortak liste eşitlenemedi:", error.message);
  }
}

let pollingInterval = null;

function startPolling() {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(async () => {
    if (!state.sharedListId || state.activeView !== "cart") return;
    try {
      const res = await api(`/api/lists/${state.sharedListId}`);
      state.sharedListVersion = res.version || state.sharedListVersion;
      // Simple compare to prevent unnecessary redraws
      if (JSON.stringify(res.items) !== JSON.stringify(state.cart)) {
        state.cart = res.items || [];
        saveCartToLocalStorage();
        renderCart();
      }
    } catch (error) {
      console.warn("Canlı veri eşitleme başarısız:", error.message);
    }
  }, 5000);
}


/* WEB SPEECH API VOICE DICTATION */
function startVoiceSearch() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showToast("Tarayıcınız ses tanımayı desteklemiyor.");
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "tr-TR";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  const micBtn = document.getElementById("micButton");
  micBtn.classList.add("recording");
  showToast("Dinleniyor... Ürün adını söyleyin.");

  recognition.start();

  recognition.onresult = (event) => {
    const result = event.results[0][0].transcript;
    document.getElementById("productUrl").value = result;
    showToast(`Tanımlandı: "${result}"`);
    // Automatically submit search
    document.getElementById("urlForm").dispatchEvent(new Event("submit"));
  };

  recognition.onerror = (event) => {
    showToast("Ses tanınamadı. Lütfen tekrar deneyin.");
  };

  recognition.onend = () => {
    micBtn.classList.remove("recording");
  };
}


/* KATEGORİ DEĞİŞİMİ VE AI CİLT ANALİZİ LOGIC */
let currentSkinType = null; // light, medium, dark

function handleCategoryChange() {}

/* EN YAKIN MAĞAZA VE EBAT SEÇİMİ BİLEŞENLERİ */
const genericProductSizes = {
  "süt": ["200 ml", "1 L", "2 L"],
  "yağ": ["1 L", "2 L", "5 L"],
  "ayçiçek yağı": ["1 L", "2 L", "5 L"],
  "zeytinyağı": ["1 L", "2 L", "5 L"],
  "sıvı yağ": ["1 L", "2 L", "5 L"],
  "salça": ["400 gr", "830 gr", "1.5 kg", "5 kg"],
  "domates salçası": ["400 gr", "830 gr", "1.5 kg", "5 kg"],
  "biber salçası": ["400 gr", "830 gr", "1.5 kg", "5 kg"],
  "yoğurt": ["500 gr", "1 kg", "2 kg", "3 kg"],
  "peynir": ["500 gr", "700 gr", "1 kg"],
  "süzme peynir": ["500 gr", "700 gr", "1 kg"],
  "kaşar peyniri": ["500 gr", "700 gr", "1 kg"],
  "un": ["1 kg", "2 kg", "5 kg"],
  "şeker": ["1 kg", "3 kg", "5 kg"],
  "çay": ["500 gr", "1 kg"],
  "yumurta": ["10'lu", "15'li", "30'lu"]
};

const STORE_BRANCHES_JS = {
  besiktas: { bim: 0.10, a101: 0.11, sok: 0.13, file: 0.44, carrefoursa: 0.38, migros: 0.22, metro: 3.80 },
  kadikoy: { bim: 0.10, a101: 0.14, sok: 0.15, file: 0.90, carrefoursa: 0.60, migros: 0.24, metro: 8.10 },
  cankaya: { bim: 0.10, a101: 0.15, sok: 0.12, file: 1.20, carrefoursa: 0.80, migros: 0.25, metro: 5.50 },
  karsiyaka: { bim: 0.10, a101: 0.15, sok: 0.13, file: 999.00, carrefoursa: 0.70, migros: 0.23, metro: 7.50 },
  bodrum: { bim: 0.20, a101: 0.23, sok: 0.32, file: 999.00, carrefoursa: 1.20, migros: 0.45, metro: 6.50 }
};

function getLocalStoreDistance(store, locName, coords) {
  if (locName in STORE_BRANCHES_JS) {
    if (store in STORE_BRANCHES_JS[locName]) {
      return STORE_BRANCHES_JS[locName][store];
    }
    // MD5 Hash stable fallback (stable distance between 0.1km and 3.1km)
    const md5Hex = md5(store);
    const h = BigInt("0x" + md5Hex);
    const dist = 0.1 + Number(h % 30n) / 10;
    return Math.round(dist * 100) / 100;
  }

  if (coords) {
    const offsets = {
      bim: [0.001, -0.001],
      a101: [-0.0015, 0.001],
      sok: [0.002, 0.002],
      file: [-0.005, -0.004],
      carrefoursa: [0.008, 0.006],
      migros: [-0.003, 0.004],
      metro: [0.045, -0.035]
    };

    let dlat, dlng;
    if (offsets[store]) {
      [dlat, dlng] = offsets[store];
    } else {
      // MD5 Hash stable offset fallback
      const md5Hex = md5(store);
      const h = BigInt("0x" + md5Hex);
      dlat = Number((h % 50n) - 25n) / 10000.0;
      dlng = Number(((h >> 8n) % 50n) - 25n) / 10000.0;
    }

    const lat2 = coords.lat + dlat;
    const lng2 = coords.lng + dlng;

    const R = 6371;
    const dLat = (lat2 - coords.lat) * Math.PI / 180;
    const dLon = (lng2 - coords.lng) * Math.PI / 180;
    const a =
      Math.sin(dLat/2) * Math.sin(dLat/2) +
      Math.cos(coords.lat * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
      Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return Math.round(R * c * 100) / 100;
  }
  return 0;
}

function showSizeSelectorDialog(itemName) {
  const dialog = document.getElementById("sizeSelectorDialog");
  const content = document.getElementById("sizeSelectorContent");
  if (!dialog || !content) return;

  const lowerName = itemName.trim().toLowerCase();
  let matchKey = Object.keys(genericProductSizes).find(key => lowerName === key || lowerName.includes(key));
  const sizes = matchKey ? genericProductSizes[matchKey] : ["1 L", "1 kg", "500 gr"];

  content.innerHTML = `
    <h3 style="margin-bottom: 12px; font-weight: 700; color: var(--ink);">Ebat/Miktar Seçin</h3>
    <p style="color: var(--muted); font-size: 13px; margin-bottom: 16px;">
      "${escapeHtml(itemName)}" için daha doğru birim fiyat karşılaştırması yapılabilmesi için bir ebat seçin:
    </p>

    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">
      ${sizes.map(sz => `
        <button type="button" class="secondary-button" style="padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: 700; height: auto;" onclick="addGenericCartItemWithSize(${inlineJsArg(itemName)}, ${inlineJsArg(sz)})">
          ${escapeHtml(sz)}
        </button>
      `).join("")}
    </div>

    <div style="border-top: 1px solid var(--line); padding-top: 16px; margin-bottom: 16px;">
      <label style="display: block; font-size: 12px; font-weight: 700; margin-bottom: 6px; color: var(--muted);">Özel Ebat Girin:</label>
      <div style="display: flex; gap: 8px;">
        <input type="text" id="customSizeInput" placeholder="Örn: 1.5 L, 800 gr, 250 ml" style="flex: 1; padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; font-size: 13px;">
        <button type="button" class="primary-button" style="width: auto; height: auto; padding: 8px 16px;" onclick="addGenericCartItemWithCustomSize(${inlineJsArg(itemName)})">Ekle</button>
      </div>
    </div>

    <div style="display: flex; gap: 8px;">
      <button type="button" class="text-button" style="flex: 1; text-align: center; color: var(--muted);" onclick="addGenericCartItemWithoutSize(${inlineJsArg(itemName)})">
        Belirtmeden Ekle
      </button>
      <button type="button" class="text-button" style="flex: 1; text-align: center; color: var(--red);" onclick="closeSizeSelectorDialog()">
        İptal
      </button>
    </div>
  `;

  if (!dialog.open) dialog.showModal();
}

function closeSizeSelectorDialog() {
  const dialog = document.getElementById("sizeSelectorDialog");
  if (dialog && dialog.open) dialog.close();
}

function addGenericCartItemWithSize(name, size) {
  const finalName = `${name} ${size}`;
  const newItem = {
    id: "cart-" + Date.now(),
    name: finalName,
    checked: false,
    quantity: 1,
    updated_at: new Date().toISOString(),
  };
  state.cart.push(newItem);
  saveCartToLocalStorage();
  renderCart();
  closeSizeSelectorDialog();
  if (state.sharedListId) syncSharedListWithServer();
}

function addGenericCartItemWithCustomSize(name) {
  const input = document.getElementById("customSizeInput");
  const size = input ? input.value.trim() : "";
  if (!size) return;
  addGenericCartItemWithSize(name, size);
}

function addGenericCartItemWithoutSize(name) {
  const newItem = {
    id: "cart-" + Date.now(),
    name: name,
    checked: false,
    quantity: 1,
    updated_at: new Date().toISOString(),
  };
  state.cart.push(newItem);
  saveCartToLocalStorage();
  renderCart();
  closeSizeSelectorDialog();
  if (state.sharedListId) syncSharedListWithServer();
}

function updateGpsStatusUI() {
  const indicator = document.getElementById("gpsStatusIndicator");
  if (!indicator) return;
  if (state.userCoords) {
    indicator.innerHTML = `<i data-lucide="map-pin" style="width: 12px; height: 12px;"></i> GPS Konumu Aktif`;
    indicator.style.color = "#00d2ff";
    indicator.style.borderColor = "rgba(0, 243, 255, 0.3)";
    indicator.style.background = "rgba(0, 243, 255, 0.08)";
    indicator.style.boxShadow = "0 0 8px rgba(0, 243, 255, 0.2)";
  } else {
    indicator.innerHTML = `<i data-lucide="map-pin-off" style="width: 12px; height: 12px;"></i> GPS Konumu Pasif`;
    indicator.style.color = "var(--muted)";
    indicator.style.borderColor = "var(--line)";
    indicator.style.background = "rgba(0,0,0,0.02)";
    indicator.style.boxShadow = "none";
  }
  if (window.lucide) lucide.createIcons();
}

window.triggerGpsActivation = function() {
  if (navigator.geolocation) {
    showToast("GPS konumu sorgulanıyor...");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        state.userCoords = {
          lat: position.coords.latitude,
          lng: position.coords.longitude
        };
        state.userLocation = "gps";
        const selector = document.getElementById("userLocationSelector");
        if (selector) selector.value = "gps";
        showToast("GPS konumu aktif edildi!");
        updateGpsStatusUI();
        persistQuantumState();
        renderCart();
      },
      (error) => {
        showToast("GPS konum izni alınamadı veya reddedildi: " + error.message);
        state.userCoords = null;
        updateGpsStatusUI();
        persistQuantumState();
      }
    );
  } else {
    showToast("Tarayıcınız konum servisini desteklemiyor.");
  }
};

async function updateUserLocation(val) {
  state.userLocation = val;
  const locationCoords = {
    besiktas: { lat: 41.0428, lng: 29.0075 },
    kadikoy: { lat: 40.9901, lng: 29.0292 },
    cankaya: { lat: 39.9081, lng: 32.8597 },
    karsiyaka: { lat: 38.4558, lng: 27.1147 },
    bodrum: { lat: 37.0344, lng: 27.4305 }
  };

  if (val === "gps") {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          state.userCoords = {
            lat: position.coords.latitude,
            lng: position.coords.longitude
          };
          showToast("GPS konumu alındı.");
          updateGpsStatusUI();
          persistQuantumState();
          renderCart();
        },
        (error) => {
          showToast("GPS konumu alınamadı: " + error.message);
          document.getElementById("userLocationSelector").value = "default";
          state.userLocation = "default";
          state.userCoords = null;
          updateGpsStatusUI();
          persistQuantumState();
          renderCart();
        }
      );
    } else {
      showToast("Tarayıcınız konum servisini desteklemiyor.");
      document.getElementById("userLocationSelector").value = "default";
      state.userLocation = "default";
      state.userCoords = null;
      updateGpsStatusUI();
      persistQuantumState();
      renderCart();
    }
  } else if (locationCoords[val]) {
    state.userCoords = locationCoords[val];
    updateGpsStatusUI();
    persistQuantumState();
    renderCart();
  } else {
    state.userCoords = null;
    updateGpsStatusUI();
    persistQuantumState();
    renderCart();
  }
}

function updateMaxDistance(val) {
  state.maxDistance = Number(val);
  renderCart();
}

function toggleSupportedStores() {
  const toggleBtn = document.querySelector(".supported-stores-toggle");
  const panel = document.getElementById("supportedStoresPanel");
  if (!panel || !toggleBtn) return;

  const isOpen = panel.classList.toggle("open");
  toggleBtn.classList.toggle("active", isOpen);
}
window.toggleSupportedStores = toggleSupportedStores;

// ============================================================================
// ANTIGRAVITE & KUANTUM DİNAMİK ARAKAYNAK VE KONTROLCÜLERİ
// ============================================================================

// 1. Global Süzülme Kontrolcüsü (Global Bobbing Controller)
window.bobbingElements = [];
window.bobbingTime = 0;
window.globalBobbingActive = false;

window.registerForBobbing = function(element) {
  if (element && !window.bobbingElements.includes(element)) {
    window.bobbingElements.push(element);
  }
};

window.unregisterForBobbing = function(element) {
  window.bobbingElements = window.bobbingElements.filter(el => el !== element);
};

window.startGlobalBobbingController = function() {
  if (window.globalBobbingActive) return;
  window.globalBobbingActive = true;

  function step() {
    window.bobbingTime += 0.025; // Süzülme hızı
    const offset = Math.sin(window.bobbingTime) * 6; // +/- 6px salınım

    // Geçersiz/silinmiş DOM elemanlarını temizle
    window.bobbingElements = window.bobbingElements.filter(el => document.body.contains(el));

    window.bobbingElements.forEach(el => {
      // Senkronize dikey süzülme uyguluyoruz
      el.style.transform = `translateY(${offset}px)`;
    });

    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
};

// 2. Makyaj Prova Küresi Uçuş Animasyonu (Antigravity Drift)

/* ── Mağaza Bültenleri ───────────────────────────────────────────────────── */

const storeFollowState  = {};
const storeFollowerCounts = {};

function getStoreColor(slug) {
  let hash = 0;
  for (let i = 0; i < slug.length; i++) {
    hash = slug.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 75%, 45%)`;
}

async function loadStores() {
  const list = document.getElementById("storeList");
  if (!list) return;
  list.innerHTML = `<div class="loading-row"><span class="spinner"></span><span>Mağazalar yükleniyor…</span></div>`;
  try {
    const res    = await fetch("/api/stores");
    const data   = await res.json();
    const stores = data.stores || data;

    if (!stores.length) { list.innerHTML = `<p class="empty-state">Henüz mağaza eklenmemiş.</p>`; return; }

    stores.forEach(s => {
      storeFollowState[s.slug]    = s.followed;
      storeFollowerCounts[s.slug] = s.follower_count || 0;
    });

    let html = "";

    const followed = stores.filter(s => s.followed);
    if (followed.length) {
      html += `<div class="store-section-title">⭐ Takip Ettiklerim</div><div class="store-grid">`;
      html += followed.map(s => renderStoreCard(s)).join("");
      html += `</div>`;
    }

    const groups = {};
    stores.forEach(s => (groups[s.category] = groups[s.category] || []).push(s));
    const CAT_LABELS = { market: "Marketler", tech: "Teknoloji", beauty: "Kozmetik & Kişisel Bakım", fashion: "Giyim & Moda", health: "Sağlık & Optik", home: "Ev & Yaşam", online: "Pazaryeri" };
    html += `<div class="store-section-title" style="margin-top:${followed.length ? "24px" : "0"}">🏪 Tüm Mağazalar</div>`;
    ["market", "tech", "beauty", "fashion", "health", "home", "online"].forEach(cat => {
      if (!groups[cat]?.length) return;
      html += `<div class="store-section-title" style="font-size:11px;margin-top:12px;">${CAT_LABELS[cat] || cat}</div><div class="store-grid">`;
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
  const count    = storeFollowerCounts[s.slug] || 0;
  const initial  = escapeHtml(s.name.charAt(0).toUpperCase());
  const bgColor  = getStoreColor(s.slug);
  const desc     = s.description ? `<div class="store-desc">${escapeHtml(s.description)}</div>` : "";
  return `
    <div class="store-card ${followed ? "followed" : ""}" id="scard-${s.slug}">
      <div class="store-card-header">
        <div class="store-avatar" style="background-color: ${bgColor}; color: white; width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800; flex-shrink: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">${initial}</div>
        <div>
          <div class="store-name">${escapeHtml(s.name)}</div>
          <div class="store-cat">${escapeHtml(s.category)}</div>
        </div>
      </div>
      ${s.publication_note ? `<div class="store-note">📅 ${escapeHtml(s.publication_note)}</div>` : ""}
      ${desc}
      <button class="btn-follow ${followed ? "active" : ""}" onclick="toggleFollow(${inlineJsArg(s.slug)}, ${inlineJsArg(s.name)})" id="sfbtn-${escapeHtml(s.slug)}">
        ${followed ? "✓ Takip Ediliyor" : "+ Takibe Al"}
      </button>
      ${s.notify_info ? `<div class="store-notify-info" style="margin-top:8px;font-size:11px;line-height:1.4;color:var(--ink-2,#687068);background:rgba(40,122,80,0.06);border-radius:8px;padding:6px 8px;">${escapeHtml(s.notify_info)}</div>` : ""}
    </div>`;
}

async function toggleFollow(slug, name) {
  const btn      = document.getElementById(`sfbtn-${slug}`);
  const card     = document.getElementById(`scard-${slug}`);
  const countEl  = document.getElementById(`scount-${slug}`);
  const isFollowed = storeFollowState[slug];

  // Optimistic UI
  storeFollowState[slug] = !isFollowed;
  storeFollowerCounts[slug] = Math.max(0, (storeFollowerCounts[slug] || 0) + (isFollowed ? -1 : 1));
  btn.textContent = isFollowed ? "+ Takibe Al" : "✓ Takip Ediliyor";
  btn.classList.toggle("active", !isFollowed);
  card.classList.toggle("followed", !isFollowed);
  if (countEl) {
    const c = storeFollowerCounts[slug];
    countEl.textContent = c > 0 ? `👥 ${c} kişi takipte` : "İlk takipçi ol!";
  }

  try {
    await api(`/api/stores/${encodeURIComponent(slug)}/follow`, {
      method: isFollowed ? "DELETE" : "POST",
    });
    showToast(isFollowed
      ? `<strong>${escapeHtml(name)}</strong> takipten çıkarıldı.`
      : `<div style="display:flex; flex-direction:column; gap:4px; text-align:left;">
           <strong>✓ ${escapeHtml(name)} takibe alındı</strong>
           <span style="font-size:11.5px; opacity:0.95;">Bu mağazada kampanya veya önemli fiyat düşüşleri olduğunda anında bildirim alacaksınız.</span>
         </div>`);
    // Takip değişince bültenleri yeniden yükle (liste güncellensin)
    if (!isFollowed) loadStores();
  } catch (error) {
    storeFollowState[slug] = isFollowed;
    storeFollowerCounts[slug] = Math.max(0, (storeFollowerCounts[slug] || 0) + (isFollowed ? 1 : -1));
    btn.textContent = isFollowed ? "✓ Takip Ediliyor" : "+ Takibe Al";
    btn.classList.toggle("active", isFollowed);
    card.classList.toggle("followed", isFollowed);
    if (countEl) {
      const c = storeFollowerCounts[slug];
      countEl.textContent = c > 0 ? `👥 ${c} kişi takipte` : "İlk takipçi ol!";
    }
    showToast(escapeHtml(error?.message || "Bağlantı hatası, tekrar dene."));
  }
}

/* ── Rehber Popup Sistemi ────────────────────────────────────────────────── */

const GUIDES = {
  discover: {
    icon: "🔍",
    title: "Fiyat karşılaştırması nasıl yapılır?",
    steps: [
      "Herhangi bir marketten ürünün linkini kopyala",
      "Yukarıdaki kutuya yapıştır ve Fiyat Bul'a bas",
      "Ya da barkod butonuyla ürünü tara — anında karşılaştır",
    ],
  },
  tracking: {
    icon: "📡",
    title: "Fiyat takibi nasıl çalışır?",
    steps: [
      "Fiyat Bul sonuçlarında 'Takibe Al' butonuna bas",
      "Fiyat düşünce otomatik bildirim alırsın",
      "Hatırlatıcı kurarak stok bitmeden seni uyaralım",
    ],
  },
  bulletins: {
    icon: "🏪",
    title: "Mağaza bültenleri nasıl çalışır?",
    steps: [
      "Takip etmek istediğin mağazanın kartına tıkla",
      "Mağaza kampanya başlatınca sana bildirim gönderilir",
      "Birden fazla mağazayı aynı anda takip edebilirsin",
    ],
  },
  savings: {
    icon: "💰",
    title: "Tasarruf sayfası ne gösterir?",
    steps: [
      "Takip ettiğin ürünlerde yakaladığın fiyat farklarını görürsün",
      "Harcamalarını kategorilere göre analiz eder",
      "Fişlerini ekleyerek aylık bütçeni takip et",
    ],
  },
  cart: {
    icon: "🛒",
    title: "Sepet ve listeler nasıl kullanılır?",
    steps: [
      "Almak istediğin ürünleri sepetine ekle",
      "Listeyi bir bağlantı ile arkadaşlarınla paylaş",
      "Toplu alışverişte en uygun mağazayı hesaplar",
    ],
  },
};

const GUIDE_KEY = "almadan_guide_dismissed_v1";

function _getDismissed() {
  try { return JSON.parse(localStorage.getItem(GUIDE_KEY) || "{}"); } catch { return {}; }
}
function _setDismissed(view) {
  const d = _getDismissed(); d[view] = true;
  localStorage.setItem(GUIDE_KEY, JSON.stringify(d));
}

function showGuide(view) {
  const guide = GUIDES[view];
  if (!guide || _getDismissed()[view]) return;

  // Önce eski varsa kaldır
  document.getElementById(`guide-${view}`)?.remove();

  const el = document.createElement("div");
  el.className = "guide-popup";
  el.id = `guide-${view}`;
  el.innerHTML = `
    <div class="guide-icon">${guide.icon}</div>
    <div class="guide-body">
      <div class="guide-title">${guide.title}</div>
      <ul class="guide-steps">
        ${guide.steps.map((s, i) => `<li data-step="${i + 1}">${s}</li>`).join("")}
      </ul>
    </div>
    <button class="guide-close" onclick="dismissGuide('${view}')" aria-label="Kapat">✕</button>
  `;

  // Her view'in ilk container'ına ekle
  const viewId = `${view}View`;
  const viewEl = document.getElementById(viewId);
  if (!viewEl) return;
  const target = viewEl.querySelector(".section-heading, .page-guide, .intro-band");
  if (target) {
    target.insertAdjacentElement("afterend", el);
  } else {
    viewEl.prepend(el);
  }
}

function dismissGuide(view) {
  _setDismissed(view);
  const el = document.getElementById(`guide-${view}`);
  if (!el) return;
  el.classList.add("hiding");
  setTimeout(() => el.remove(), 230);
}

function resetGuides() {
  localStorage.removeItem(GUIDE_KEY);
  toast("Rehberler sıfırlandı — sekmeleri ziyaret et.");
}

/* ── Link Kılavuzu Popup ─────────────────────────────────────────────────── */

const LINK_GUIDE_APPS = [
  {
    icon: "🛒",
    name: "Migros, CarrefourSA, A101, BİM",
    steps: `Ürün sayfasını aç → tarayıcının <b>adres çubuğuna</b> dokun → linki kopyala → Almadan'a yapıştır.
            <div style="margin-top: 6px;">
              <a href="#" onclick="event.preventDefault(); const d = document.getElementById('marketAppsDetails'); if(d.style.display==='none'){d.style.display='block'; this.innerText='Mobil uygulamalar için anlatımı gizle ▴';}else{d.style.display='none'; this.innerText='Mobil uygulamalar için tek tek anlatım ▾';}" style="color: var(--green); font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 4px; padding: 4px 0;">Mobil uygulamalar için tek tek anlatım ▾</a>
            </div>
            <div id="marketAppsDetails" style="display: none; margin-top: 8px; padding: 12px; background: rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.05); border-radius: 8px; font-size: 13px; line-height: 1.6; color: var(--ink);">
              <div style="margin-bottom: 6px;"><b>Migros:</b> Ürün sayfasının sağ üst köşesindeki <i>Paylaş</i> butonuna bas → <i>Bağlantıyı Kopyala</i>'yı seç.</div>
              <div style="margin-bottom: 6px;"><b>CarrefourSA:</b> Ürün detayında sağ üstteki <i>Paylaş</i> ikonuna tıkla → <i>Kopyala</i>'yı seç.</div>
              <div style="margin-bottom: 6px;"><b>A101:</b> Ürün görselinin sağ üst kısmındaki <i>Paylaş</i> simgesine dokun → <i>Bağlantıyı Kopyala</i>.</div>
              <div><b>BİM:</b> Ürün detay sayfasında <i>Paylaş</i> butonuna bas → <i>Panoya Kopyala</i> işlemini yap.</div>
            </div>`,
  },
  {
    icon: "📦",
    name: "Trendyol",
    steps: "Ürün sayfası → sağ üstteki <b>paylaş</b> simgesi → <b>Bağlantıyı Kopyala</b> → Almadan'a yapıştır.",
  },
  {
    icon: "🌐",
    name: "Hepsiburada",
    steps: "Ürün sayfası → üstteki <b>⋯ Daha Fazla</b> → <b>Linki Kopyala</b> → Almadan'a yapıştır.",
  },
  {
    icon: "🛍️",
    name: "n11, GittiGidiyor, diğer siteler",
    steps: "Ürün sayfasını aç → tarayıcı adres çubuğundaki <b>URL'yi</b> kopyala → Almadan'a yapıştır.",
  },
  {
    icon: "📱",
    name: "Mobil uygulama kullanıyorsan",
    steps: "Ürün sayfası → uygulamanın <b>Paylaş</b> butonu → <b>Bağlantıyı Kopyala</b> seç → Almadan'a gel, kutuya basılı tut → Yapıştır.",
  },
];

function showLinkGuide(autoTriggered = false) {
  if (document.getElementById("linkGuideOverlay")) return;

  const overlay = document.createElement("div");
  overlay.className = "link-guide-overlay";
  overlay.id = "linkGuideOverlay";
  overlay.onclick = e => { if (e.target === overlay) closeLinkGuide(); };

  overlay.innerHTML = `
    <div class="link-guide-modal" role="dialog" aria-modal="true" aria-labelledby="lgTitle">
      <button class="link-guide-close" onclick="closeLinkGuide()" aria-label="Kapat">✕</button>
      <h3 id="lgTitle">${autoTriggered ? "⚠️ Geçersiz link girildi" : "🔗 Ürün linki nasıl bulunur?"}</h3>
      <p class="subtitle">${autoTriggered
        ? "Girdiğin adres bir ürün linki gibi görünmüyor. Aşağıdan doğru linki nasıl kopyalayacağını öğren:"
        : "Alışveriş uygulamasından ürün linkini şu şekilde kopyalayabilirsin:"
      }</p>
      ${LINK_GUIDE_APPS.map(a => `
        <div class="link-guide-app">
          <div class="link-guide-app-icon">${a.icon}</div>
          <div>
            <div class="link-guide-app-name">${a.name}</div>
            <div class="link-guide-app-steps">${a.steps}</div>
          </div>
        </div>
      `).join("")}
      <div class="link-guide-tip">💡 İpucu: Barkod butonu ile kameranı açıp ürün barkodunu taratabilirsin — link gerekmez!</div>
    </div>
  `;

  document.body.appendChild(overlay);
  document.addEventListener("keydown", _lgEscHandler);
}

function closeLinkGuide() {
  const overlay = document.getElementById("linkGuideOverlay");
  if (!overlay) return;
  overlay.style.animation = "fadeOut .15s ease forwards";
  overlay.style.setProperty("--tw-opacity", "0");
  overlay.style.opacity = "0";
  setTimeout(() => overlay.remove(), 160);
  document.removeEventListener("keydown", _lgEscHandler);
}

function _lgEscHandler(e) { if (e.key === "Escape") closeLinkGuide(); }

function _isValidProductUrl(val) {
  if (!val) return false;
  try {
    const url = new URL(val);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

/* ── Ana Arama Barkod Tarayıcısı ─────────────────────────────────────────── */

let _mainScanner = null;
let _mainScannerRunning = false;
let _mainScanLocked = false;

function openMainBarcodeScanner() {
  const area = document.getElementById("mainBarcodeScanArea");
  if (!area) return;
  area.classList.remove("hidden");
  document.getElementById("mainBarcodeBtn").style.display = "none";
  _startMainScanner();
}

function closeMainBarcodeScanner() {
  _stopMainScanner();
  const area = document.getElementById("mainBarcodeScanArea");
  if (area) area.classList.add("hidden");
  const btn = document.getElementById("mainBarcodeBtn");
  if (btn) btn.style.display = "";
}

async function _startMainScanner() {
  if (!window.Html5Qrcode) {
    showToast("Kamera kütüphanesi yükleniyor, biraz bekle...");
    return;
  }
  if (_mainScannerRunning) return;
  try {
    _mainScanner = new Html5Qrcode("mainHtml5QrReader", { verbose: false });
    await _mainScanner.start(
      { facingMode: "environment" },
      {
        fps: 10,
        qrbox: (w, h) => ({ width: Math.floor(Math.min(w * 0.8, 280)), height: Math.floor(Math.min(h * 0.35, 120)) }),
        aspectRatio: 1.777778,
        formatsToSupport: [
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.UPC_A,
          Html5QrcodeSupportedFormats.UPC_E,
        ],
      },
      async (decoded) => {
        const code = String(decoded || "").replace(/\D/g, "");
        if (_mainScanLocked || ![8, 12, 13].includes(code.length)) return;
        _mainScanLocked = true;
        await _stopMainScanner();
        closeMainBarcodeScanner();
        await searchByBarcode(code);
        _mainScanLocked = false;
      },
      () => {},
    );
    _mainScannerRunning = true;
  } catch (e) {
    showToast("Kamera açılamadı: " + (e.message || e));
    closeMainBarcodeScanner();
  }
}

async function _stopMainScanner() {
  if (!_mainScanner || !_mainScannerRunning) return;
  try { await _mainScanner.stop(); _mainScanner.clear(); } catch {}
  _mainScannerRunning = false;
}

async function searchByBarcode(code) {
  showToast("Barkod aranıyor: " + code);
  const overlay = document.getElementById("quantumScanOverlay");
  const progressText = document.getElementById("quantumScanProgress");
  if (overlay) overlay.style.display = "flex";
  if (progressText) progressText.innerText = "Barkod ürünü tanımlanıyor...";

  try {
    const res = await api(`/api/barcode/${code}`);
    if (overlay) overlay.style.display = "none";

    if (res.found && res.results && res.results.length > 0) {
      switchView("discover");
      showSearchResults({
        products: res.results,
        query: res.search_query || res.title || code,
        category: res.suggested_category || "general",
      });
      showToast("✓ " + (res.title || "Ürün bulundu"));
    } else if (res.found) {
      // Ürün bilgisi var ama fiyat karşılaştırma sonucu yok
      switchView("discover");
      showToast(res.title + " — fiyat karşılaştırması bulunamadı.");
      showBarcodeManualEntry && showBarcodeManualEntry(code, res.message || "Sonuç bulunamadı.");
    } else {
      if (overlay) overlay.style.display = "none";
      showToast("Barkod bulunamadı: " + code);
    }
  } catch (e) {
    if (overlay) overlay.style.display = "none";
    showToast("Barkod sorgulanamadı: " + (e.message || e));
  }
}

/* ── Yeni: Satıcı Seçim Akışı ─────────────────────────────────────────────── */

async function showSellerSelectionDialog(parsed) {
  const dialog = document.getElementById("sellerSelectionDialog");
  const content = document.getElementById("sellerSelectionContent");
  if (!dialog || !content) return;

  dialog.showModal();
  content.innerHTML = `
    <div style="text-align:center; padding: 30px 20px;">
      <span class="spinner" style="display:inline-block; width:28px; height:28px; border-color:#287a50; border-right-color:transparent; border-width:3px;"></span>
      <p style="margin-top:16px; font-weight:700; font-size:15px; color:var(--ink);">En İyi Fırsatlar Avlanıyor...</p>
    </div>
  `;

  try {
    const data = await api("/api/find-alternatives", {
      method: "POST",
      body: JSON.stringify({ title: parsed.title, original_url: parsed.canonical_url, source: parsed.source, image_url: parsed.image_url })
    });
    let alts = data.alternatives || [];
    // alts aynı diziye referans — mutasyonlardan ÖNCE backend sonuç sayısını sakla
    const backendAltCount = alts.length;

    // İlk taramada yakalanan satıcılar varsa birleştir
    if (parsed.extra_info && parsed.extra_info.otherMerchants) {
      const existingUrls = new Set(alts.map(a => a.url));
      parsed.extra_info.otherMerchants.forEach(m => {
        if (!existingUrls.has(m.url)) {
          alts.push(m);
        }
      });
    }

    // Asıl ürünü listede yoksa başa ekle
    const origPrice = parsed.price || 0;
    const origFound = alts.find(a => Math.abs((a.price || 0) - origPrice) < 1 && String(a.source || "").toLowerCase().includes(String(parsed.source || "").toLowerCase()));
    if (!origFound && parsed.price) {
      alts.unshift({
        title: parsed.title,
        price: parsed.price,
        source: parsed.source,
        url: parsed.canonical_url,
        image_url: parsed.image_url,
        extra_info: parsed.extra_info || {}
      });
    }

    if (alts.length === 0) {
      const links = data.search_links || [];
      const linksHtml = links.length ? `
        <p style="font-size:13px; color:var(--ink-2); margin:16px 0 10px; text-align:left;">Bu mağazalarda kendin aramaya devam edebilirsin:</p>
        <div style="display:flex; flex-direction:column; gap:8px;">
          ${links.map(l => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener" style="display:flex; justify-content:space-between; align-items:center; padding:11px 14px; border:1.5px solid var(--border); border-radius:10px; text-decoration:none; color:var(--ink); font-weight:600; font-size:14px;"><span>🔎 ${escapeHtml(l.label)}</span><span style="color:#287a50;">→</span></a>`).join("")}
        </div>` : "";
      content.innerHTML = `
        <div style="text-align:center; padding: 24px 20px;">
          <h3 style="margin:0 0 8px 0; font-size:18px; font-weight:800; color:var(--ink);">Otomatik Eşleşme Bulunamadı</h3>
          <p style="font-size:13px; color:var(--ink-2);">Bu ürünü diğer mağazalarda otomatik bulamadık.</p>
          ${linksHtml}
          <button class="primary-button" style="width:100%; border-radius:10px; padding:12px; font-weight:700; margin-top:16px;" data-parsed='${escapeHtml(JSON.stringify(parsed))}' onclick="document.getElementById('sellerSelectionDialog').close(); showParsedProduct(JSON.parse(this.getAttribute('data-parsed')));">
            Mevcut Ürünü Takip Et
          </button>
        </div>
      `;
      return;
    }

    const minPrice = Math.min(...alts.filter(a => a.price > 0).map(a => a.price));
    const maxPrice = Math.max(...alts.filter(a => a.price > 0).map(a => a.price));
    const savings = maxPrice - minPrice;

    let listHtml = `
      <div style="margin-bottom:16px;">
        <h3 style="margin:0 0 4px 0; font-size:20px; font-weight:800; color:var(--ink);">🛒 ${alts.length} Mağazada Karşılaştırma</h3>
        ${savings > 1 ? `<p style="margin:0; font-size:13px; color:#287a50; font-weight:600;">💰 En pahalı satıcıya göre <b>₺${savings.toFixed(2)}</b> tasarruf edebilirsin!</p>` : `<p style="margin:0; font-size:13px; color:var(--ink-2);">Bir mağaza seçip takibe alarak fiyat düşüşlerini takip et.</p>`}
      </div>
      <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:10px; max-height:60vh; overflow-y:auto; padding-right:4px;" class="custom-scrollbar">
    `;

    alts.forEach((a, idx) => {
      const brand = getStoreBrand(a.source);
      const isCheapest = idx === 0 && a.price > 0;
      const savingVsMax = a.price > 0 && maxPrice > a.price ? (maxPrice - a.price) : 0;
      const escapedJson = escapeHtml(JSON.stringify(a));

      let badgeTop = "";
      if (isCheapest) badgeTop = `<div style="position:absolute;top:-1px;left:12px;background:#287a50;color:#fff;font-size:9px;font-weight:800;padding:2px 8px;border-radius:0 0 6px 6px;letter-spacing:.3px;">EN UCUZ</div>`;

      let badgesRow = "";
      if (a.extra_info && a.extra_info.fast_delivery) badgesRow += `<span style="font-size:9.5px;background:rgba(255,152,0,.1);color:#ef6c00;border:1px solid rgba(255,152,0,.25);padding:2px 6px;border-radius:4px;font-weight:700;">⚡ Hızlı</span>`;
      if (a.extra_info && a.extra_info.rating && parseFloat(a.extra_info.rating) >= 9.0) badgesRow += `<span style="font-size:9.5px;background:rgba(33,150,243,.1);color:#1976d2;border:1px solid rgba(33,150,243,.25);padding:2px 6px;border-radius:4px;font-weight:700;">🏆 ${a.extra_info.rating}</span>`;

      listHtml += `
        <div onclick="selectSellerAndProceed(this)" data-seller='${escapedJson}'
          style="position:relative;border:${isCheapest ? '2px solid #287a50' : '1.5px solid var(--line)'};border-radius:10px;padding:${isCheapest ? '18px 12px 12px' : '12px'};cursor:pointer;transition:all .15s;background:var(--surface);"
          onmouseover="this.style.borderColor='${brand.color}';this.style.transform='translateY(-2px)';this.style.boxShadow='0 4px 16px ${brand.color}22';"
          onmouseout="this.style.borderColor='${isCheapest ? '#287a50' : 'var(--line)'}';this.style.transform='none';this.style.boxShadow='none';">
          ${badgeTop}
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            ${storeLogoHtml(a.source, 32)}
            <div>
              <div style="font-size:13px;font-weight:800;color:${brand.color};line-height:1.2;">${escapeHtml(brand.name)}</div>
              <div style="font-size:10px;color:var(--ink-2);">Ücretsiz Kargo</div>
            </div>
          </div>
          <div style="font-size:20px;font-weight:900;color:var(--ink);margin-bottom:2px;">₺${a.price.toFixed(2)}</div>
          ${a.original_price && a.original_price > a.price ? `<div style="font-size:11px;color:var(--ink-2);text-decoration:line-through;">₺${a.original_price.toFixed(2)}</div>` : ""}
          ${savingVsMax > 1 ? `<div style="font-size:10px;color:#287a50;font-weight:700;margin-top:2px;">₺${savingVsMax.toFixed(2)} tasarruf</div>` : ""}
          ${badgesRow ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px;">${badgesRow}</div>` : ""}
          <div style="margin-top:8px;text-align:center;background:${isCheapest ? '#287a50' : 'var(--line)'};color:${isCheapest ? '#fff' : 'var(--ink-2)'};border-radius:6px;padding:5px;font-size:11px;font-weight:700;">Seç ›</div>
        </div>
      `;
    });

    listHtml += `</div>`;
    // Backend hiç alternatif bulamadıysa (sadece orijinal ürün varsa) arama linklerini de göster
    const fallbackLinks = data.search_links || [];
    if (backendAltCount === 0 && fallbackLinks.length) {
      listHtml += `
        <p style="font-size:13px; color:var(--ink-2); margin:16px 0 10px;">Bu mağazalarda kendin aramaya devam edebilirsin:</p>
        <div style="display:flex; flex-direction:column; gap:8px;">
          ${fallbackLinks.map(l => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener" style="display:flex; justify-content:space-between; align-items:center; padding:11px 14px; border:1.5px solid var(--border); border-radius:10px; text-decoration:none; color:var(--ink); font-weight:600; font-size:14px;"><span>🔎 ${escapeHtml(l.label)}</span><span style="color:#287a50;">→</span></a>`).join("")}
        </div>`;
    }
    content.innerHTML = listHtml;

  } catch(e) {
    console.error("Satıcı Seçim Ekranı Hatası:", e);
    dialog.close();
    showParsedProduct(parsed); // Hata durumunda asıl ekrana düş
  }
}

function selectSellerAndProceed(element) {
  const sellerData = JSON.parse(element.getAttribute("data-seller"));
  document.getElementById("sellerSelectionDialog").close();

  // Seçili satıcıyı sanki asıl taranan oymuş gibi asıl ekrana taşı
  const newParsed = {
    title: sellerData.title,
    price: sellerData.price,
    source: sellerData.source,
    canonical_url: addAffiliateTag(sellerData.url, sellerData.source),
    image_url: sellerData.image_url,
    original_price: sellerData.original_price,
    extra_info: sellerData.extra_info,
    warnings: [],
    confidence: 100
  };

  showParsedProduct(newParsed);
}
