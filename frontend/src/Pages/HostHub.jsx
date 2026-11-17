import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import CancelBookingModal from '../Components/CancelBookingModal'
import PickupOtpModal from '../Components/PickupOtpModal'
import ReturnCountdownTimer from '../Components/ReturnCountdownTimer'
import useCurrentUserId from '../hooks/useCurrentUserId'
import {
  getHostBookings,
  getMyBookings,
  getHostReports,
  ownerApproveBooking,
  ownerRejectBooking,
  confirmPickup,
  confirmReturn,
  cancelBooking,
  confirmOfflineBookingPayment,
} from '../services/api'
import {
  Inbox,
  CheckCircle2,
  Clock,
  Calendar,
  Package,
  User,
  ShieldCheck,
  Check,
  X,
  Phone,
  MapPin,
  MessageSquare,
  Layers,
  ArrowDownLeft,
  ArrowUpRight,
  Search,
  Banknote,
} from 'lucide-react'
import { formatKolkataDateTime, calculateReturnCountdown } from '../utils/dateUtils'

async function fetchAllOutgoingBookings(params = {}) {
  const firstPage = await getMyBookings({ ...params, page: 1, page_size: 100 })
  let allResults = Array.isArray(firstPage?.results) ? [...firstPage.results] : []
  const totalPages = Number(firstPage?.total_pages) || 1

  if (totalPages > 1) {
    const pagePromises = []
    for (let p = 2; p <= totalPages; p++) {
      pagePromises.push(getMyBookings({ ...params, page: p, page_size: 100 }))
    }
    const remainingPages = await Promise.all(pagePromises)
    for (const pageData of remainingPages) {
      if (Array.isArray(pageData?.results)) {
        allResults = allResults.concat(pageData.results)
      }
    }
  }

  const seenIds = new Set()
  const deduplicated = []
  for (const item of allResults) {
    if (item && !seenIds.has(item.id)) {
      seenIds.add(item.id)
      deduplicated.push(item)
    }
  }

  return {
    counts: firstPage?.counts || {},
    results: deduplicated,
  }
}

export default function HostHub() {
  const currentUserId = useCurrentUserId()
  const [searchParams, setSearchParams] = useSearchParams()
  const itemFilter = searchParams.get('item')
  const requestedTab = searchParams.get('tab')
  const highlightBookingId = searchParams.get('highlight') || searchParams.get('booking')
  const validTabs = ['incoming', 'accepted', 'active', 'rejected', 'completed', 'reports']
  const normalizeTab = (tab) => {
    if (!tab) return 'incoming'
    if (tab === 'active') return 'accepted'
    return validTabs.includes(tab) ? tab : 'incoming'
  }
  const [activeTab, setActiveTab] = useState(normalizeTab(requestedTab))
  const [highlightedId, setHighlightedId] = useState(highlightBookingId || null)

  // Booking collections
  const [incomingBookings, setIncomingBookings] = useState([])
  const [outgoingBookings, setOutgoingBookings] = useState([])
  const [reports, setReports] = useState([])

  // Counts for incoming (host) and outgoing (renter)
  const [incomingCounts, setIncomingCounts] = useState({
    all: 0,
    incoming: 0,
    accepted: 0,
    active: 0,
    rejected: 0,
    completed: 0,
  })
  const [outgoingCounts, setOutgoingCounts] = useState({
    all: 0,
    incoming: 0,
    accepted: 0,
    active: 0,
    rejected: 0,
    completed: 0,
    cancelled: 0,
  })

  // Activity filter when user has both incoming and outgoing requests: 'all' | 'incoming' | 'outgoing'
  const [activityFilter, setActivityFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')

  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [toastMessage, setToastMessage] = useState('')

  // Modals
  const [rejectingBooking, setRejectingBooking] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [cancelModalBooking, setCancelModalBooking] = useState(null)
  const [cancellingBooking, setCancellingBooking] = useState(false)
  const [otpModalBooking, setOtpModalBooking] = useState(null)

  // Sync tab with URL search params without cascading effect renders
  const [prevParams, setPrevParams] = useState({ requestedTab, highlightBookingId })
  if (
    requestedTab !== prevParams.requestedTab ||
    highlightBookingId !== prevParams.highlightBookingId
  ) {
    setPrevParams({ requestedTab, highlightBookingId })
    if (requestedTab && validTabs.includes(requestedTab)) {
      setActiveTab(normalizeTab(requestedTab))
    } else if (highlightBookingId) {
      setActiveTab('incoming')
    }
    setHighlightedId(highlightBookingId || null)
  }

  const handleTabChange = (newTab) => {
    const normalized = normalizeTab(newTab)
    setActiveTab(normalized)
    setHighlightedId(null)
    setPrevParams({ requestedTab: normalized, highlightBookingId: null })
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', normalized)
      next.delete('highlight')
      next.delete('booking')
      return next
    }, { replace: true })
  }

  // Scroll to and focus highlighted booking card
  useEffect(() => {
    const allBookings = [...incomingBookings, ...outgoingBookings]
    if (highlightedId && !loading && allBookings.length > 0) {
      const timer = setTimeout(() => {
        const el = document.getElementById(`booking-card-${highlightedId}`)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      }, 200)
      return () => clearTimeout(timer)
    }
  }, [highlightedId, loading, incomingBookings, outgoingBookings])

  const [reloadToken, setReloadToken] = useState(0)
  const [loadError, setLoadError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const reloadData = () => setReloadToken((value) => value + 1)

  useEffect(() => {
    let isCurrent = true
    let inFlight = false
    const fetchData = async () => {
      if (inFlight || document.visibilityState === 'hidden') return
      inFlight = true
      try {
        if (activeTab === 'reports') {
          const reportsData = await getHostReports()
          const [hostCountsData, myCountsData] = await Promise.all([
            getHostBookings({ tab: 'incoming' }),
            getMyBookings({ tab: 'incoming', page_size: 1 }),
          ])
          if (!isCurrent) return
          setReports(reportsData || [])
          if (hostCountsData?.counts) setIncomingCounts(hostCountsData.counts)
          if (myCountsData?.counts) setOutgoingCounts(myCountsData.counts)
        } else {
          const [hostData, myData] = await Promise.all([
            getHostBookings({ tab: activeTab }),
            fetchAllOutgoingBookings({ tab: activeTab }),
          ])
          if (!isCurrent) return
          const taggedIncoming = (hostData?.results || []).map((b) => ({ ...b, requestType: 'incoming' }))
          const taggedOutgoing = (myData?.results || []).map((b) => ({ ...b, requestType: 'outgoing' }))
          setIncomingBookings(taggedIncoming)
          setOutgoingBookings(taggedOutgoing)
          if (hostData?.counts) setIncomingCounts(hostData.counts)
          if (myData?.counts) setOutgoingCounts(myData.counts)
        }
        setLoadError('')
      } catch (err) {
        if (isCurrent) {
          setLoadError(err.message || 'Unable to load Request Details. Please retry.')
        }
      } finally {
        inFlight = false
        if (isCurrent) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    }
    const refresh = () => {
      if (isCurrent && document.visibilityState !== 'hidden') {
        setRefreshing(true)
        void fetchData()
      }
    }
    // Defer initial state changes so loading covers tab switches and manual retries.
    queueMicrotask(() => {
      if (!isCurrent) return
      setLoading(true)
      refresh()
    })
    const timer = setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    window.addEventListener('rentbee:bookings-changed', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      isCurrent = false
      clearInterval(timer)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('rentbee:bookings-changed', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [activeTab, reloadToken])

  const showToast = (msg) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(''), 4000)
  }

  // Host Action: Approve
  const handleApprove = async (id) => {
    setActionLoading(true)
    try {
      await ownerApproveBooking(id)
      showToast('Booking request approved! Moved to Accepted.')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      const stringId = String(id)
      setActiveTab('accepted')
      setHighlightedId(stringId)
      setPrevParams({ requestedTab: 'accepted', highlightBookingId: stringId })
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', 'accepted')
        next.set('highlight', stringId)
        return next
      }, { replace: true })
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to approve booking.')
    } finally {
      setActionLoading(false)
    }
  }

  // Host Action: Reject
  const handleRejectConfirm = async () => {
    if (!rejectingBooking) return
    const trimmedReason = rejectReason.trim()
    if (!trimmedReason) {
      alert('Please explain why you are rejecting this booking. A rejection reason is required.')
      return
    }
    const rejectedId = rejectingBooking.id
    setActionLoading(true)
    try {
      await ownerRejectBooking(rejectedId, trimmedReason)
      setRejectingBooking(null)
      setRejectReason('')
      showToast('Booking request rejected. Moved to Rejected.')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      const stringId = String(rejectedId)
      setActiveTab('rejected')
      setHighlightedId(stringId)
      setPrevParams({ requestedTab: 'rejected', highlightBookingId: stringId })
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', 'rejected')
        next.set('highlight', stringId)
        return next
      }, { replace: true })
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to reject booking.')
    } finally {
      setActionLoading(false)
    }
  }

  // Host Action: Confirm Pickup
  const handlePickup = async (id) => {
    setActionLoading(true)
    try {
      await confirmPickup(id)
      showToast('Item handover confirmed! Rental is now in progress.')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to confirm pickup.')
    } finally {
      setActionLoading(false)
    }
  }

  // Host Action: Confirm Offline Cash Payment
  const handleConfirmOfflinePayment = async (id, totalAmount) => {
    if (!window.confirm(`Confirm receipt of ₹${totalAmount} cash payment from the renter?`)) {
      return
    }
    setActionLoading(true)
    try {
      await confirmOfflineBookingPayment(id)
      showToast('Cash payment confirmed successfully! Handover is now unlocked.')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to confirm offline payment.')
    } finally {
      setActionLoading(false)
    }
  }

  // Host Action: Confirm Return
  const handleReturn = async (id) => {
    if (!window.confirm('Confirm that the rental item has been returned safely in good condition?')) {
      return
    }
    setActionLoading(true)
    try {
      await confirmReturn(id)
      showToast('Rental return confirmed and marked completed!')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to confirm return.')
    } finally {
      setActionLoading(false)
    }
  }

  // Renter Action: Cancel Booking
  const handleCancelConfirm = async (id, reason) => {
    setCancellingBooking(true)
    try {
      await cancelBooking(id, reason)
      setCancelModalBooking(null)
      showToast('Booking request cancelled.')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to cancel booking.')
    } finally {
      setCancellingBooking(false)
    }
  }

  // Activity calculations
  const totalIncoming = incomingCounts.all || 0
  const totalOutgoing = outgoingCounts.all || 0
  const hasIncoming = totalIncoming > 0
  const hasOutgoing = totalOutgoing > 0
  const hasBoth = hasIncoming && hasOutgoing
  const hasNoRequests = !hasIncoming && !hasOutgoing

  // Tab counts based on activity mode
  const getTabCount = (tabKey) => {
    if (!hasIncoming && hasOutgoing) {
      // Only outgoing activity
      if (tabKey === 'incoming') return outgoingCounts.incoming || 0
      if (tabKey === 'accepted') return outgoingCounts.accepted || outgoingCounts.active || 0
      if (tabKey === 'rejected') return outgoingCounts.rejected || 0
      if (tabKey === 'completed') return outgoingCounts.completed || 0
      return 0
    }
    if (hasIncoming && !hasOutgoing) {
      // Only incoming activity
      if (tabKey === 'incoming') return incomingCounts.incoming || 0
      if (tabKey === 'accepted') return incomingCounts.accepted || incomingCounts.active || 0
      if (tabKey === 'rejected') return incomingCounts.rejected || 0
      if (tabKey === 'completed') return incomingCounts.completed || 0
      return 0
    }
    // Both activities exist
    if (activityFilter === 'incoming') {
      if (tabKey === 'incoming') return incomingCounts.incoming || 0
      if (tabKey === 'accepted') return incomingCounts.accepted || incomingCounts.active || 0
      if (tabKey === 'rejected') return incomingCounts.rejected || 0
      if (tabKey === 'completed') return incomingCounts.completed || 0
      return 0
    }
    if (activityFilter === 'outgoing') {
      if (tabKey === 'incoming') return outgoingCounts.incoming || 0
      if (tabKey === 'accepted') return outgoingCounts.accepted || outgoingCounts.active || 0
      if (tabKey === 'rejected') return outgoingCounts.rejected || 0
      if (tabKey === 'completed') return outgoingCounts.completed || 0
      return 0
    }
    // 'all' activityFilter (combined counts)
    if (tabKey === 'incoming') return (incomingCounts.incoming || 0) + (outgoingCounts.incoming || 0)
    if (tabKey === 'accepted') return (incomingCounts.accepted || incomingCounts.active || 0) + (outgoingCounts.accepted || outgoingCounts.active || 0)
    if (tabKey === 'rejected') return (incomingCounts.rejected || 0) + (outgoingCounts.rejected || 0)
    if (tabKey === 'completed') return (incomingCounts.completed || 0) + (outgoingCounts.completed || 0)
    return 0
  }

  // Filter and sort bookings for active view
  const displayedBookings = (() => {
    let list
    if (!hasIncoming && hasOutgoing) {
      list = outgoingBookings
    } else if (hasIncoming && !hasOutgoing) {
      list = incomingBookings
    } else if (activityFilter === 'incoming') {
      list = incomingBookings
    } else if (activityFilter === 'outgoing') {
      list = outgoingBookings
    } else {
      list = [...incomingBookings, ...outgoingBookings]
    }

    if (itemFilter) {
      list = list.filter((b) => String(b.item?.id) === itemFilter)
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      list = list.filter((b) =>
        (b.item?.name || '').toLowerCase().includes(q) ||
        (b.booking_reference || '').toLowerCase().includes(q) ||
        (b.renter?.full_name || '').toLowerCase().includes(q) ||
        (b.owner?.full_name || '').toLowerCase().includes(q)
      )
    }

    return [...list].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  })()

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">

          {/* Toast Notification */}
          {toastMessage && (
            <div className="mb-6 flex items-center gap-2 rounded-2xl bg-emerald-50 border border-emerald-200 p-4 text-xs font-semibold text-emerald-800 animate-in fade-in">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <span>{toastMessage}</span>
            </div>
          )}

          {/* Header */}
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-black text-[#352720] sm:text-3xl">
                Request Details
              </h1>
              <p className="mt-1 text-xs text-gray-500 sm:text-sm max-w-2xl">
                {!hasIncoming && hasOutgoing
                  ? 'Track your outgoing borrow requests, pickup schedules, and rental statuses.'
                  : hasBoth
                    ? 'Manage both your incoming rental requests as a host and your outgoing borrow requests as a renter in one place.'
                    : 'Manage incoming rental requests, coordinate pickup handovers, confirm returns, and review renter issues.'}
              </p>
            </div>
            <Link
              to="/list-item"
              className="inline-flex items-center gap-1.5 self-start rounded-full bg-[#D97745] px-5 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#B85D32] transition sm:self-auto cursor-pointer"
            >
              <span>+ List Another Item</span>
            </Link>
          </div>

          {itemFilter && (
            <div className="mb-4 text-sm text-[#9D4C29]">
              <Link to="/host-hub">Show requests for all listings</Link>
            </div>
          )}

          {/* Activity Filter (When user has both incoming and outgoing requests) */}
          {hasBoth && (
            <div className="mb-6 flex flex-wrap items-center gap-2 bg-orange-50/70 p-2.5 rounded-2xl border border-orange-200/60 text-xs">
              <span className="font-bold text-[#49362D] px-2">Filter Activity:</span>
              <button
                type="button"
                onClick={() => setActivityFilter('all')}
                className={`px-3.5 py-1.5 rounded-xl font-bold transition cursor-pointer ${activityFilter === 'all'
                    ? 'bg-[#352720] text-white shadow-xs'
                    : 'bg-white text-[#49362D] border border-orange-200 hover:bg-orange-100'
                  }`}
              >
                All Requests ({totalIncoming + totalOutgoing})
              </button>
              <button
                type="button"
                onClick={() => setActivityFilter('incoming')}
                className={`px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer ${activityFilter === 'incoming'
                    ? 'bg-[#9D4C29] text-white shadow-xs'
                    : 'bg-white text-[#49362D] border border-orange-200 hover:bg-orange-100'
                  }`}
              >
                <ArrowDownLeft size={13} />
                <span>Incoming (As Host: {totalIncoming})</span>
              </button>
              <button
                type="button"
                onClick={() => setActivityFilter('outgoing')}
                className={`px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer ${activityFilter === 'outgoing'
                    ? 'bg-blue-700 text-white shadow-xs'
                    : 'bg-white text-[#49362D] border border-orange-200 hover:bg-orange-100'
                  }`}
              >
                <ArrowUpRight size={13} />
                <span>Outgoing (As Renter: {totalOutgoing})</span>
              </button>
            </div>
          )}

          {/* Navigation Tabs */}
          <div className="flex flex-wrap gap-2 border-b border-orange-100 pb-3 mb-6">
            <button
              type="button"
              onClick={() => handleTabChange('incoming')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${activeTab === 'incoming'
                  ? 'bg-[#9D4C29] text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
                }`}
            >
              <span>
                {!hasIncoming && hasOutgoing
                  ? 'Pending Requests'
                  : hasBoth
                    ? 'Incoming & Pending'
                    : 'Incoming Requests'}
              </span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {getTabCount('incoming')}
              </span>
            </button>

            <button
              type="button"
              onClick={() => handleTabChange('accepted')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${activeTab === 'accepted' || activeTab === 'active'
                  ? 'bg-[#D97745] text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
                }`}
            >
              <span>Accepted</span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {getTabCount('accepted')}
              </span>
            </button>

            <button
              type="button"
              onClick={() => handleTabChange('rejected')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${activeTab === 'rejected'
                  ? 'bg-rose-700 text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
                }`}
            >
              <span>Rejected</span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {getTabCount('rejected')}
              </span>
            </button>

            <button
              type="button"
              onClick={() => handleTabChange('completed')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${activeTab === 'completed'
                  ? 'bg-emerald-700 text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
                }`}
            >
              <span>Completed</span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {getTabCount('completed')}
              </span>
            </button>

            <button
              type="button"
              onClick={() => handleTabChange('reports')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${activeTab === 'reports'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
                }`}
            >
              <span>Reported Issues</span>
              {reports.length > 0 && (
                <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                  {reports.length}
                </span>
              )}
            </button>
          </div>

          {/* Search bar and refresh controls */}
          <div className="mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="relative flex-1 max-w-md">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search requests by item, reference, or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl border border-orange-200 bg-white py-2 pl-9 pr-3 text-xs text-[#352720] placeholder-gray-400 focus:border-[#D97745] focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-2 self-end sm:self-auto">
              <span className="text-gray-500 hidden sm:inline">
                Requests refresh automatically while this page is visible.
              </span>
              <button
                type="button"
                onClick={reloadData}
                disabled={refreshing || actionLoading}
                className="rounded-xl border border-orange-200 bg-white px-4 py-2 font-bold text-[#9D4C29] disabled:opacity-50 cursor-pointer hover:bg-orange-50 transition"
              >
                {refreshing ? 'Refreshing…' : 'Refresh requests'}
              </button>
            </div>
          </div>

          {loadError && (
            <div role="alert" className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
              {loadError} Your requests could not be refreshed.
              <button type="button" onClick={reloadData} className="ml-2 font-bold underline cursor-pointer">Retry</button>
            </div>
          )}

          {/* Content Area */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2].map((n) => (
                <div
                  key={n}
                  className="h-36 rounded-3xl bg-white border border-orange-100 p-6 animate-pulse"
                />
              ))}
            </div>
          ) : loadError ? null : activeTab === 'reports' ? (
            /* Reported Issues Tab */
            reports.length > 0 ? (
              <div className="space-y-4">
                {reports.map((report) => (
                  <div
                    key={report.id}
                    className="rounded-3xl border border-rose-100 bg-white p-5 sm:p-6 shadow-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-[10px] font-bold text-rose-800 uppercase">
                          {report.status}
                        </span>
                        <span className="text-xs text-gray-400">
                          Filed on {new Date(report.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <Link
                        to={`/bookings/${report.booking}`}
                        className="text-xs font-semibold text-[#D97745] hover:underline"
                      >
                        View Booking
                      </Link>
                    </div>

                    <div className="mt-3 text-xs">
                      <div className="flex flex-wrap items-center gap-4 text-gray-500">
                        <p>
                          Renter: <strong className="text-[#352720]">{report.renter_name}</strong>
                        </p>
                        {report.owner_name && (
                          <p>
                            Owner: <strong className="text-[#352720]">{report.owner_name}</strong>
                          </p>
                        )}
                      </div>
                      <div className="mt-2 rounded-2xl bg-rose-50/50 border border-rose-100 p-3.5 text-[#352720]">
                        <strong className="block text-xs font-bold text-rose-900 mb-1">
                          Issue Description:
                        </strong>
                        <p className="leading-relaxed">{report.description}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
                <ShieldCheck size={36} className="mx-auto text-emerald-600 mb-3" />
                <h3 className="text-base font-bold text-[#352720]">No Reported Issues</h3>
                <p className="mt-1 text-xs text-gray-500">
                  Great job! You have no unresolved problems or complaints for your rentals.
                </p>
              </div>
            )
          ) : hasNoRequests ? (
            /* User has no booking requests at all */
            <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
              <Inbox size={40} className="mx-auto text-orange-300 mb-3" />
              <h3 className="text-base font-bold text-[#352720]">No Rental Requests Yet</h3>
              <p className="mt-1 text-xs text-gray-500 max-w-md mx-auto">
                You haven't requested any items to borrow or received any requests for your listed items yet.
              </p>
              <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                <Link
                  to="/browse"
                  className="rounded-full bg-[#D97745] px-5 py-2.5 text-xs font-bold text-white hover:bg-[#B85D32] transition"
                >
                  Browse Items to Borrow
                </Link>
                <Link
                  to="/list-item"
                  className="rounded-full border border-orange-200 bg-white px-5 py-2.5 text-xs font-bold text-[#49362D] hover:bg-orange-50 transition"
                >
                  + List an Item to Rent
                </Link>
              </div>
            </div>
          ) : displayedBookings.length > 0 ? (
            /* Render list of bookings */
            <div className="space-y-4">
              {displayedBookings.map((b) => {
                const isIncoming = b.requestType === 'incoming' || (currentUserId && b.owner?.id === currentUserId)
                const isOutgoing = b.requestType === 'outgoing' || (currentUserId && b.renter?.id === currentUserId)
                const isHighlighted = String(b.id) === String(highlightedId)

                return (
                  <div
                    key={`${b.requestType || 'b'}-${b.id}`}
                    id={`booking-card-${b.id}`}
                    className={`rounded-3xl bg-white p-5 sm:p-6 shadow-xs transition-all duration-500 ${isHighlighted
                        ? 'border-2 border-[#D97745] ring-4 ring-[#D97745]/20 bg-[#FFFDFB]'
                        : isIncoming
                          ? 'border border-orange-100'
                          : 'border border-blue-100/80 bg-[#FAFCFF]'
                      }`}
                  >
                    {/* Highlighted indicator */}
                    {isHighlighted && (
                      <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-3 py-1 text-xs font-bold text-[#D97745]">
                        <Clock size={13} /> Relevant Booking Request
                      </div>
                    )}

                    {/* Card Header: Activity Badge, Reference, Created At timestamp, Status Badge */}
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-orange-100/70 pb-3 mb-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Clear Distinction Badge */}
                        {isIncoming ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100/80 border border-orange-200 px-3 py-1 text-[11px] font-bold text-[#9D4C29]">
                            <ArrowDownLeft size={13} className="text-[#D97745]" />
                            <span>Incoming Request • You are the Host</span>
                          </span>
                        ) : isOutgoing ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-100/80 border border-blue-200 px-3 py-1 text-[11px] font-bold text-blue-900">
                            <ArrowUpRight size={13} className="text-blue-600" />
                            <span>Outgoing Request • You are the Renter</span>
                          </span>
                        ) : null}

                        <span className="font-mono text-xs font-bold text-[#9D4C29] bg-orange-50 px-2.5 py-0.5 rounded-lg border border-orange-200">
                          {b.booking_reference}
                        </span>

                        {b.created_at && (
                          <span className="flex items-center gap-1 text-[11px] text-gray-500">
                            <Clock size={12} className="text-[#D97745]" />
                            Requested on <strong className="text-gray-700">{formatKolkataDateTime(b.created_at)}</strong>
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-orange-50 text-[#D97745] border border-orange-200 px-2.5 py-0.5 text-xs font-semibold inline-flex items-center gap-1">
                          {b.payment_method === 'offline' ? (
                            <>
                              <Banknote size={12} />
                              <span>{b.payment_method_display || 'Pay at Pickup'}</span>
                            </>
                          ) : (
                            <span>{b.payment_method_display || 'Online Payment'}</span>
                          )}
                        </span>
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${b.status === 'pending_approval'
                              ? 'bg-amber-100 text-amber-800'
                              : b.status === 'waiting_for_pickup'
                                ? 'bg-orange-100 text-[#9D4C29]'
                                : b.status === 'rental_in_progress'
                                  ? 'bg-blue-100 text-blue-800'
                                  : b.status === 'rejected'
                                    ? 'bg-rose-100 text-rose-800'
                                    : b.status === 'cancelled'
                                      ? 'bg-gray-100 text-gray-700'
                                      : 'bg-emerald-100 text-emerald-800'
                            }`}
                        >
                          {b.status_display}
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="flex flex-col sm:flex-row gap-4 flex-1">
                        <div className="h-28 w-28 shrink-0 overflow-hidden rounded-2xl bg-orange-50 border border-orange-100">
                          {b.item?.primary_image_url ? (
                            <img
                              src={b.item.primary_image_url}
                              alt={b.item.name}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-orange-300">
                              <Package size={34} />
                            </div>
                          )}
                        </div>

                        <div className="space-y-2 text-xs flex-1">
                          <div>
                            <h3 className="text-base font-bold text-[#352720]">
                              {b.item?.name}
                            </h3>
                            {b.item?.category_name && (
                              <span className="text-[11px] text-gray-400">
                                Category: {b.item.category_name}
                              </span>
                            )}
                          </div>

                          {/* Participant Information */}
                          {isIncoming ? (
                            <div className="flex flex-wrap items-center gap-3 text-gray-600">
                              <span className="flex items-center gap-1">
                                <User size={13} className="text-[#D97745]" />
                                Renter: <strong className="text-[#49362D]">{b.renter?.full_name || 'Renter'}</strong>
                              </span>
                              {b.renter?.phone_number ? (
                                <a
                                  href={`tel:${b.renter.phone_number}`}
                                  className="flex items-center gap-1 text-emerald-700 font-medium"
                                >
                                  <Phone size={12} /> {b.renter.phone_number}
                                </a>
                              ) : (
                                <span className="text-[11px] text-gray-400 italic">
                                  Contact details shared upon acceptance
                                </span>
                              )}
                              {b.renter?.address_info?.city && (
                                <span className="flex items-center gap-1 text-[11px] text-gray-500">
                                  <MapPin size={11} className="text-gray-400" />
                                  {b.renter.address_info.locality ? `${b.renter.address_info.locality}, ` : ''}{b.renter.address_info.city}
                                </span>
                              )}
                            </div>
                          ) : (
                            <div className="flex flex-wrap items-center gap-3 text-gray-600">
                              <span className="flex items-center gap-1">
                                <User size={13} className="text-blue-600" />
                                Item Owner / Host: <strong className="text-[#49362D]">{b.owner?.full_name || 'Item Owner'}</strong>
                              </span>
                              {b.owner?.phone_number ? (
                                <a
                                  href={`tel:${b.owner.phone_number}`}
                                  className="flex items-center gap-1 text-emerald-700 font-medium"
                                >
                                  <Phone size={12} /> {b.owner.phone_number}
                                </a>
                              ) : (
                                <span className="text-[11px] text-gray-400 italic">
                                  Host contact available after approval
                                </span>
                              )}
                            </div>
                          )}

                          {/* Schedule and Quantity */}
                          <div className="flex flex-wrap items-center gap-3 text-gray-600 pt-0.5">
                            <span className="flex items-center gap-1.5 font-medium">
                              <Calendar size={13} className="text-[#D97745]" />
                              {b.start_date} → {b.end_date}
                              <span className="text-gray-400 font-normal">
                                ({b.duration_days} {b.duration_days === 1 ? 'day' : 'days'})
                              </span>
                            </span>
                            <span className="flex items-center gap-1 font-semibold text-[#49362D]">
                              <Layers size={13} className="text-[#D97745]" />
                              Quantity: {b.requested_quantity || 1}
                            </span>
                          </div>

                          {/* Pricing Breakdown */}
                          <div className="rounded-2xl bg-[#FFFDFB] border border-orange-100/90 p-3 text-xs space-y-1.5">
                            <div className="flex items-center justify-between text-[11px] text-gray-500 border-b border-orange-50 pb-1.5">
                              <span className="font-semibold text-[#352720]">Price Breakdown</span>
                              <span className="font-bold text-[#9D4C29] text-xs">
                                Total Amount: ₹{b.total_amount}
                              </span>
                            </div>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                              <div>
                                <span className="text-gray-400 block text-[10px]">Daily Rate</span>
                                <span className="font-semibold text-[#49362D]">₹{b.daily_price}/day</span>
                              </div>
                              <div>
                                <span className="text-gray-400 block text-[10px]">Rental ({b.duration_days}d)</span>
                                <span className="font-semibold text-[#49362D]">₹{b.rental_amount}</span>
                              </div>
                              <div>
                                <span className="text-gray-400 block text-[10px]">Security Deposit</span>
                                <span className="font-semibold text-[#49362D]">₹{b.deposit_amount || '0.00'}</span>
                              </div>
                              <div>
                                <span className="text-gray-400 block text-[10px]">Total Price</span>
                                <span className="font-bold text-[#9D4C29]">₹{b.total_amount}</span>
                              </div>
                            </div>
                          </div>

                          {/* Handover Information */}
                          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-500 pt-0.5">
                            <MapPin size={12} className={isIncoming ? 'text-[#D97745] shrink-0' : 'text-blue-600 shrink-0'} />
                            <span>
                              Handover:{' '}
                              <strong>{isIncoming ? 'Self-pickup at your location' : 'Self-pickup at host location'}</strong>
                            </span>
                            {isIncoming && b.renter?.address_info?.city && (
                              <span className="text-gray-400">
                                (Renter: {b.renter.address_info.locality ? `${b.renter.address_info.locality}, ` : ''}{b.renter.address_info.city})
                              </span>
                            )}
                          </div>

                          {/* Renter Message (if available) */}
                          {(b.renter_message || b.message) && (
                            <div className="rounded-xl bg-orange-50/60 border border-orange-100 p-2.5 text-xs text-[#352720]">
                              <div className="flex items-center gap-1 text-[11px] font-semibold text-[#9D4C29] mb-0.5">
                                <MessageSquare size={12} />
                                <span>Message from renter:</span>
                              </div>
                              <p className="text-gray-700 italic">{b.renter_message || b.message}</p>
                            </div>
                          )}

                          {/* Rental in Progress: Shared Return Deadline & Countdown */}
                          <ReturnCountdownTimer booking={b} compact={true} />

                          {/* Completed: Return confirmation timestamp */}
                          {b.status === 'completed' && (b.returned_at || b.returned_at_display) && (
                            <div className="mt-1 text-[11px] text-gray-500">
                              Returned: {b.returned_at_display || formatKolkataDateTime(b.returned_at)}
                            </div>
                          )}

                          {/* Rejected: Reason if provided */}
                          {b.status === 'rejected' && b.rejection_reason && (
                            <div className="mt-1 text-[11px] text-rose-700">
                              Decline reason: <span className="font-semibold text-rose-900">{b.rejection_reason}</span>
                            </div>
                          )}

                          {/* Cancelled: Reason if provided */}
                          {b.status === 'cancelled' && b.cancellation_reason && (
                            <div className="mt-1 text-[11px] text-gray-600">
                              Cancellation reason: <span className="font-medium text-gray-800">{b.cancellation_reason}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Status and Action Buttons */}
                      <div className="flex flex-row lg:flex-col items-center lg:items-end justify-between lg:justify-start gap-2 border-t border-orange-50 pt-3 lg:border-0 lg:pt-0 shrink-0">
                        {/* Incoming Host Actions */}
                        {isIncoming && (
                          <>
                            {b.status === 'pending_approval' && (
                              <div className="flex flex-wrap lg:flex-col gap-2 w-full sm:w-auto">
                                <button
                                  type="button"
                                  onClick={() => handleApprove(b.id)}
                                  disabled={actionLoading}
                                  className="inline-flex items-center justify-center gap-1 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700 transition cursor-pointer shadow-xs"
                                >
                                  <Check size={13} /> Accept
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setRejectingBooking(b)}
                                  disabled={actionLoading}
                                  className="inline-flex items-center justify-center gap-1 rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                                >
                                  <X size={13} /> Reject
                                </button>
                              </div>
                            )}

                            {b.status === 'waiting_for_pickup' && (
                              <div className="flex flex-col items-end gap-1.5">
                                {b.payment_status === 'paid' ? (
                                  <button
                                    type="button"
                                    onClick={() => setOtpModalBooking(b)}
                                    disabled={actionLoading}
                                    className="inline-flex items-center gap-1.5 rounded-xl bg-[#D97745] px-4 py-1.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition cursor-pointer shadow-xs"
                                  >
                                    <ShieldCheck size={13} />
                                    {b.has_active_pickup_otp ? 'Verify Pickup OTP' : 'Send Pickup OTP'}
                                  </button>
                                ) : (
                                  <>
                                    {b.can_confirm_offline_payment && (
                                      <button
                                        type="button"
                                        onClick={() => handleConfirmOfflinePayment(b.id, b.total_amount)}
                                        disabled={actionLoading}
                                        className="inline-flex items-center gap-1 rounded-xl bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 transition cursor-pointer shadow-xs"
                                      >
                                        <Banknote size={13} /> Confirm Cash Payment
                                      </button>
                                    )}
                                    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-xl">
                                      <Clock size={12} />
                                      <span>
                                        {b.payment_method === 'offline' ? 'Awaiting Cash at Pickup' : 'Awaiting Payment Verification'}
                                      </span>
                                    </div>
                                  </>
                                )}
                              </div>
                            )}

                            {b.status === 'rental_in_progress' && (
                              <div className="flex flex-col items-end gap-1.5">
                                <div className="flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-xl">
                                  <CheckCircle2 size={12} className="text-emerald-600" />
                                  <span>Pickup Confirmed ({b.pickup_confirmed_at_display || b.picked_up_at_display})</span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleReturn(b.id)}
                                  disabled={actionLoading}
                                  className="rounded-xl bg-emerald-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 transition cursor-pointer"
                                >
                                  Confirm Return
                                </button>
                              </div>
                            )}
                          </>
                        )}

                        {/* Outgoing Renter Actions */}
                        {isOutgoing && (
                          <>
                            {b.can_cancel && (
                              <button
                                type="button"
                                onClick={() => setCancelModalBooking(b)}
                                disabled={actionLoading}
                                className="rounded-xl border border-rose-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                              >
                                Cancel Request
                              </button>
                            )}
                          </>
                        )}

                        <Link
                          to={`/bookings/${b.id}`}
                          className="rounded-xl border border-orange-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition text-center"
                        >
                          Details
                        </Link>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : activeTab === 'incoming' ? (
            <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
              <Inbox size={36} className="mx-auto text-orange-300 mb-3" />
              <h3 className="text-base font-bold text-[#352720]">
                {!hasIncoming && hasOutgoing ? 'No Pending Outgoing Requests' : 'No Incoming Requests'}
              </h3>
              <p className="mt-1 text-xs text-gray-500">
                {!hasIncoming && hasOutgoing
                  ? "You don't have any borrow requests pending owner approval right now."
                  : hasBoth
                    ? "You don't have any pending incoming or outgoing requests at this moment."
                    : "You don't have any incoming rental requests for your listed items right now."}
              </p>
            </div>
          ) : activeTab === 'accepted' || activeTab === 'active' ? (
            <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
              <Clock size={36} className="mx-auto text-orange-300 mb-3" />
              <h3 className="text-base font-bold text-[#352720]">No Accepted Rentals</h3>
              <p className="mt-1 text-xs text-gray-500">
                You don't have any accepted bookings awaiting pickup or rentals in progress at this moment.
              </p>
            </div>
          ) : activeTab === 'rejected' ? (
            <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
              <X size={36} className="mx-auto text-orange-300 mb-3" />
              <h3 className="text-base font-bold text-[#352720]">No Rejected Requests</h3>
              <p className="mt-1 text-xs text-gray-500">
                You don't have any rejected booking requests.
              </p>
            </div>
          ) : (
            <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
              <CheckCircle2 size={36} className="mx-auto text-orange-300 mb-3" />
              <h3 className="text-base font-bold text-[#352720]">No Completed Rentals</h3>
              <p className="mt-1 text-xs text-gray-500">
                Completed rental history will appear here.
              </p>
            </div>
          )}

        </main>
      </div>

      <Footer />

      {/* Rejection Reason Modal */}
      {rejectingBooking && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl border border-orange-100">
            <h3 className="text-base font-bold text-[#352720]">Reject Booking Request</h3>
            <p className="text-xs text-gray-500 mt-1">
              For {rejectingBooking.item?.name} requested by {rejectingBooking.renter?.full_name}.
            </p>

            <div className="mt-4">
              <label className="block text-xs font-semibold text-[#352720] mb-1">
                Rejection Reason <span className="text-rose-600">*</span>
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Please explain why you are rejecting this booking."
                rows={3}
                className="w-full rounded-xl border border-orange-200 p-2.5 text-xs text-[#352720] focus:border-[#D97745] focus:outline-none"
              />
              {!rejectReason.trim() && (
                <p className="mt-1 text-[11px] text-gray-400">
                  A valid reason is required to reject this booking.
                </p>
              )}
            </div>

            <div className="mt-6 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => {
                  setRejectingBooking(null)
                  setRejectReason('')
                }}
                className="rounded-xl border border-orange-200 px-4 py-2 text-xs font-semibold text-gray-600 hover:bg-orange-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRejectConfirm}
                disabled={actionLoading || !rejectReason.trim()}
                className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {actionLoading ? 'Rejecting...' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Booking Modal (for Renter Outgoing Requests) */}
      <CancelBookingModal
        booking={cancelModalBooking}
        isOpen={Boolean(cancelModalBooking)}
        onClose={() => setCancelModalBooking(null)}
        onConfirm={handleCancelConfirm}
        loading={cancellingBooking}
      />

      {/* Pickup OTP Verification Modal */}
      {otpModalBooking && (
        <PickupOtpModal
          booking={otpModalBooking}
          isOpen={Boolean(otpModalBooking)}
          onClose={() => setOtpModalBooking(null)}
          onSuccess={() => {
            showToast('Pickup confirmed! Rental is now in progress.')
            reloadData()
          }}
        />
      )}
    </div>
  )
}
