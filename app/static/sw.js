self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', function(event) {
  let data = { title: "Almadan", message: "Yeni bir bildiriminiz var!" };
  if (event.data) {
    try {
      data = event.data.json();
    } catch(e) {
      data.message = event.data.text();
    }
  }

  const options = {
    body: data.message,
    icon: 'https://img.icons8.com/color/192/shopping-cart--v1.png',
    badge: 'https://img.icons8.com/color/96/shopping-cart--v1.png',
    data: data.url || '/'
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data)
  );
});
