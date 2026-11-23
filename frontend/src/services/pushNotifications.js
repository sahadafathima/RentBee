import { getPushVapidKey, savePushSubscription, removePushSubscription } from './api'

/**
 * Converts a base64url string to a Uint8Array for PushManager subscription.
 */
function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

/**
 * Checks if Service Worker, PushManager and Notification APIs are available.
 */
export function isPushSupported() {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  )
}

/**
 * Returns current Notification permission: 'granted', 'denied', 'default', or 'unsupported'.
 */
export function getPushPermissionState() {
  if (!isPushSupported()) return 'unsupported'
  return Notification.permission
}

/**
 * Registers the Service Worker at /sw.js if not already registered.
 */
export async function registerServiceWorker() {
  if (!isPushSupported()) return null
  return navigator.serviceWorker.register('/sw.js', { scope: '/' })
}

/**
 * Gets the current active PushSubscription from the browser.
 */
export async function getExistingSubscription() {
  if (!isPushSupported()) return null
  try {
    const registration = await navigator.serviceWorker.ready
    return await registration.pushManager.getSubscription()
  } catch (err) {
    console.warn('Failed to retrieve push subscription:', err)
    return null
  }
}

/**
 * Prompts user for notification permission, creates push subscription, and registers with backend.
 */
export async function subscribeToPushNotifications() {
  if (!isPushSupported()) {
    throw new Error('Web Push Notifications are not supported in this browser.')
  }

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    return { success: false, permission, message: 'Notification permission was not granted.' }
  }

  await registerServiceWorker()
  const registration = await navigator.serviceWorker.ready

  let existing = await registration.pushManager.getSubscription()
  if (!existing) {
    const keyData = await getPushVapidKey()
    const vapidKey = keyData.public_key
    if (!vapidKey) {
      throw new Error('VAPID public key not configured on backend.')
    }
    const convertedKey = urlB64ToUint8Array(vapidKey)
    existing = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: convertedKey,
    })
  }

  const subJson = existing.toJSON()
  await savePushSubscription({
    endpoint: existing.endpoint,
    keys: {
      p256dh: subJson.keys?.p256dh || '',
      auth: subJson.keys?.auth || '',
    },
  })

  return { success: true, permission: 'granted', subscription: existing }
}

/**
 * Unsubscribes from browser PushManager and removes subscription on backend.
 */
export async function unsubscribeFromPushNotifications() {
  if (!isPushSupported()) return { success: true }
  try {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    if (subscription) {
      const endpoint = subscription.endpoint
      await subscription.unsubscribe()
      await removePushSubscription(endpoint).catch(() => {})
    }
    return { success: true }
  } catch (err) {
    console.warn('Error unsubscribing from push:', err)
    return { success: false, error: err.message }
  }
}

