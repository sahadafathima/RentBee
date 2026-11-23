// Service Worker for RentBee Web Push Notifications

self.addEventListener('push', (event) => {
  let payload
  try {
    payload = event.data ? event.data.json() : {}
  } catch {
    payload = {
      title: 'RentBee',
      body: event.data ? event.data.text() : 'You have a new update.',
    }
  }

  const title = payload.title || 'RentBee'
  const options = {
    body: payload.body || '',
    icon: payload.icon || '/favicon.svg',
    badge: payload.badge || '/favicon.svg',
    data: payload.data || {},
    tag: payload.data && payload.data.booking_id ? `booking-${payload.data.booking_id}` : undefined,
    renotify: true,
    // Informational only: Do not add Accept or Reject action buttons to the browser notification
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const rawUrl = (event.notification.data && event.notification.data.url) || '/host-hub'
  const targetUrl = new URL(rawUrl, self.location.origin).href

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // If a RentBee window/tab is already open, focus it and navigate
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          if ('navigate' in client) {
            client.navigate(targetUrl)
          }
          return client.focus()
        }
      }
      // Otherwise open a new window
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl)
      }
    })
  )
})
