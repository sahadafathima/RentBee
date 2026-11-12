import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useNotifications } from '../Context/NotificationContext'
import { ownerApproveBooking, ownerRejectBooking } from '../services/api'

export default function BookingNotifications({ history = false, showResponseActions = true }) {
  const { notifications, unreadCount, error, refresh, markRead, markAllRead } = useNotifications()
  useEffect(() => { refresh() }, [refresh])
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [dismissedIds, setDismissedIds] = useState(() => new Set())

  const rawEntries = history ? notifications : notifications.filter((n) => n.booking && !n.is_read)
  const entries = rawEntries.filter((n) => !dismissedIds.has(n.id))

  const handleDismiss = async (notificationId) => {
    setActionError('')
    try {
      await markRead(notificationId)
      setDismissedIds((prev) => new Set([...prev, notificationId]))
    } catch (err) {
      setActionError(err.message || 'Failed to dismiss notification. Please try again.')
    }
  }

  const respond = async (notification, accept) => {
    if (busy) return
    let reason = ''
    if (!accept) {
      reason = window.prompt('Please enter a reason for declining this request (required):')
      if (reason === null) return
      if (!reason.trim()) {
        alert('A rejection reason is required.')
        return
      }
    }
    setBusy(true); setActionError('')
    try {
      if (accept) await ownerApproveBooking(notification.booking)
      else await ownerRejectBooking(notification.booking, reason)
      setNotice(accept ? 'Request accepted.' : 'Request rejected.')
      refresh()
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
    } catch (err) { setActionError(err.message); refresh() }
    finally { setBusy(false) }
  }

  if (!history && !entries.length && !error && !notice) return null
  return <section className="mx-auto my-5 max-w-6xl rounded-2xl border border-orange-200 bg-orange-50 p-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-lg font-bold text-[#49362D]">Notifications ({unreadCount} unread)</h2>
      <div className="flex gap-4 text-sm"><button onClick={refresh}>Refresh</button><Link to="/notifications">History</Link>
        {unreadCount > 0 && <button onClick={() => markAllRead().catch(() => {})}>Mark all read</button>}</div>
    </div>
    {(error || actionError) && <p role="alert" className="mt-3 text-rose-800">{actionError || error}</p>}
    {notice && <p role="status" className="mt-3 text-emerald-800">{notice}</p>}
    {!entries.length && history && <p className="mt-4">No notifications yet.</p>}
    {entries.map((n) => <article key={n.id} className="mt-3 rounded-xl bg-white p-4">
      <h3 className="font-bold">{n.title}</h3><p className="text-sm text-gray-600">{n.message}</p>
      <p className="mt-1 text-xs text-gray-500">{new Date(n.created_at).toLocaleString()} | {n.is_read ? 'Read' : 'Unread'}</p>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-[#9D4C29]">
        <Link
          to={n.booking ? (n.event === 'requested' ? `/host-hub?tab=incoming&highlight=${n.booking}` : `/bookings/${n.booking}`) : `/items/${n.item}`}
          onClick={() => { if (!n.is_read) void markRead(n.id).catch(() => {}) }}
          className="font-semibold text-[#D97745] hover:underline"
        >
          {n.event === 'requested' ? 'Review Request' : 'View Details'}
        </Link>
        {showResponseActions && n.can_respond && <>
          <button disabled={busy} onClick={() => respond(n, true)} className="font-semibold text-emerald-700 hover:underline">Accept</button>
          <button disabled={busy} onClick={() => respond(n, false)} className="font-semibold text-rose-600 hover:underline">Reject</button>
        </>}
        <button
          type="button"
          onClick={() => handleDismiss(n.id)}
          className="text-xs text-gray-500 hover:text-gray-800 ml-auto cursor-pointer"
        >
          Dismiss
        </button>
        {!n.is_read && <button type="button" onClick={() => markRead(n.id).catch(() => {})}>Mark read</button>}
      </div>
    </article>)}
  </section>
}
