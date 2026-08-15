// Ce fichier tourne en arrière-plan dans Chrome, indépendamment de la page.
// Il s'occupe uniquement de deux choses : afficher une notification quand
// le serveur en envoie une, et réagir si l'utilisateur clique dessus.

self.addEventListener('push', (event) => {
  let data = { titre: '🎂 Anniversaire', corps: 'Tu as un anniversaire aujourd\'hui !' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.corps = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.titre, {
      body: data.corps,
      icon: '/static/icone-notification.png',
      badge: '/static/icone-notification.png',
      data: { url: '/' },
    })
  );
});

// Quand on clique sur la notification : on ouvre (ou on ramène au premier plan) le calendrier
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const urlCible = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(urlCible) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlCible);
      }
    })
  );
});