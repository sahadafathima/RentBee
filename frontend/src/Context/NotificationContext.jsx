import { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react'
import useCurrentUserId from '../hooks/useCurrentUserId'
import { getUserNotifications, markNotificationRead, markAllNotificationsRead } from '../services/api'
import {
  isPushSupported,
  getPushPermissionState,
  subscribeToPushNotifications,
  unsubscribeFromPushNotifications,
} from '../services/pushNotifications'

const NotificationContext = createContext(null)

export function NotificationProvider({ children }) {
  const userId = useCurrentUserId()
  const [snapshot, setSnapshot] = useState({ userId: null, results: [], unread_count: 0 })
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [pushPermission, setPushPermission] = useState(getPushPermissionState())

  const refresh = useCallback(() => setRevision((value) => value + 1), [])

  const enablePushNotifications = useCallback(async () => {
    try {
      const res = await subscribeToPushNotifications()
      setPushPermission(getPushPermissionState())
      return res
    } catch (err) {
      console.warn('Failed to enable push notifications:', err)
      setPushPermission(getPushPermissionState())
      throw err
    }
  }, [])

  const disablePushNotifications = useCallback(async () => {
    try {
      const res = await unsubscribeFromPushNotifications()
      setPushPermission(getPushPermissionState())
      return res
    } catch (err) {
      console.warn('Failed to disable push notifications:', err)
      setPushPermission(getPushPermissionState())
      throw err
    }
  }, [])

  // Auto-sync push subscription if already granted and user is logged in
  useEffect(() => {
    if (userId && isPushSupported() && Notification.permission === 'granted') {
      subscribeToPushNotifications().catch((err) => {
        console.debug('Background push subscription sync:', err.message)
      })
    }
  }, [userId])

  useEffect(() => {
    if (!userId) return
    let active = true
    let pending = false
    const fetchNotifications = async () => {
      if (pending || document.visibilityState === 'hidden') return
      pending = true
      try {
        const data = await getUserNotifications()
        if (active) {
          setSnapshot({ ...data, userId })
          setError('')
        }
      } catch (err) {
        if (active) setError(err.message || 'Notifications could not be loaded.')
      } finally { pending = false }
    }
    void fetchNotifications()
    const timer = setInterval(fetchNotifications, 15000)
    window.addEventListener('focus', fetchNotifications)
    document.addEventListener('visibilitychange', fetchNotifications)
    window.addEventListener('rentbee:bookings-changed', fetchNotifications)
    return () => {
      active = false
      clearInterval(timer)
      window.removeEventListener('focus', fetchNotifications)
      document.removeEventListener('visibilitychange', fetchNotifications)
      window.removeEventListener('rentbee:bookings-changed', fetchNotifications)
    }
  }, [userId, revision])
  const markRead = useCallback(async (id) => {
    try { await markNotificationRead(id); refresh() }
    catch (err) { setError(err.message); throw err }
  }, [refresh])
  const markAllRead = useCallback(async () => {
    try { await markAllNotificationsRead(); refresh() }
    catch (err) { setError(err.message); throw err }
  }, [refresh])
  const value = useMemo(() => ({
    notifications: userId && snapshot.userId === userId ? snapshot.results || [] : [],
    unreadCount: userId && snapshot.userId === userId ? snapshot.unread_count || 0 : 0,
    error: userId ? error : '',
    refresh,
    markRead,
    markAllRead,
    pushSupported: isPushSupported(),
    pushPermission,
    enablePushNotifications,
    disablePushNotifications,
  }), [userId, snapshot, error, refresh, markRead, markAllRead, pushPermission, enablePushNotifications, disablePushNotifications])
  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useNotifications() {
  return useContext(NotificationContext)
}
