import { useSyncExternalStore } from 'react'
import { getAccessToken, getRefreshToken, parseJwtPayload } from '../services/authentication'

function subscribe(callback) {
  const events = ['rentbee:auth-changed', 'rentbee:auth-expired', 'storage']
  events.forEach((event) => window.addEventListener(event, callback))
  return () => events.forEach((event) => window.removeEventListener(event, callback))
}

export default function useCurrentUserId() {
  return useSyncExternalStore(
    subscribe,
    () => {
      const accessPayload = parseJwtPayload(getAccessToken())
      if (accessPayload?.user_id) return accessPayload.user_id
      const refreshPayload = parseJwtPayload(getRefreshToken())
      return refreshPayload?.user_id ?? null
    },
    () => null
  )
}
