const CACHE_VERSION = "almadan-v21";

// Uygulama kabuğu (shell) -- offline'da bile sayfanın açılabilmesi için
// önceden önbelleğe alınır. Sepet/liste tik atma gibi çekirdek işlevler
// zaten localStorage kullanıyor, tek eksik parça sayfanın kendisinin
// offline'da yeniden açılabilmesiydi.
const APP_SHELL = [
  "/",
  "/static/index.html",
  "/static/app.js",
  "/static/styles.css",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

// API/auth/cron gibi dinamik yollar ASLA önbelleklenmez -- her zaman
// gerçek ağa gitmeye çalışır, offline'da normal şekilde başarısız olur
// (app.js zaten bu hataları yakalayıp sessizce yutuyor).
const NEVER_CACHE_PREFIXES = ["/api/", "/auth/", "/cron/", "/products", "/notifications"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL)).catch(() => {}),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE_PREFIXES.some((p) => url.pathname.startsWith(p))) return;

  // Sayfa navigasyonu (offline'da site açılışı) -- önbellekteki shell'e düş
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("/static/index.html")),
    );
    return;
  }

  // Statik dosyalar (JS/CSS/ikon): önce ağ dene, olmazsa önbellekten ver,
  // başarılı olursa önbelleği güncel tut.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(req, clone));
        }
        return res;
      })
      .catch(() => caches.match(req)),
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "Almadan", message: "Yeni bir bildiriminiz var!", url: "/" };
  if (event.data) {
    try { data = { ...data, ...event.data.json() }; } catch { data.message = event.data.text(); }
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.message,
      tag: "almadan-alert",
      data: { url: data.url },
      renotify: true,
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const existing = wins.find((w) => w.url.startsWith(self.location.origin));
      if (existing) { existing.navigate(target); return existing.focus(); }
      return clients.openWindow(target);
    }),
  );
});
