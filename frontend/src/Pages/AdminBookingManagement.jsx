import { useEffect, useState } from 'react'
import AdminLayout from '../Components/AdminLayout'
import {
  getAdminBookings,
  getAdminBookingDetails,
  updateAdminBookingStatus,
  adminReturnAction,
} from '../services/api'
import {
  Search,
  Calendar,
  Clock,
  User,
  Package,
  AlertTriangle,
  CheckCircle2,
  Eye,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
  RotateCcw,
  X,
} from 'lucide-react'
import { formatKolkataDateTime } from '../utils/dateUtils'

export default function AdminBookingManagement() {
  const [bookings, setBookings] = useState([])
  const [counts, setCounts] = useState({})
  const [productSummaries, setProductSummaries] = useState([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  // Filters & Search
  const [activeTab, setActiveTab] = useState('all')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [paymentStatusFilter, setPaymentStatusFilter] = useState('')
  const [sort, setSort] = useState('-created_at')
  const [createdAfter, setCreatedAfter] = useState('')
  const [createdBefore, setCreatedBefore] = useState('')
  const [startDateFilter, setStartDateFilter] = useState('')
  const [endDateFilter, setEndDateFilter] = useState('')

  // Detail Modal & Action Modal State
  const [selectedBooking, setSelectedBooking] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  // Confirmation / Action Dialog State
  const [actionModal, setActionModal] = useState({
    isOpen: false,
    title: '',
    message: '',
    confirmText: 'Confirm',
    confirmColor: 'bg-[#9D4C29] hover:bg-[#813d21]',
    requiresReason: false,
    reasonLabel: 'Reason',
    actionType: '', // 'status_transition' | 'return_accept' | 'return_reject'
    targetStatus: '',
    bookingId: null,
  })
  const [actionReason, setActionReason] = useState('')
  const [actionError, setActionError] = useState('')
  const [submittingAction, setSubmittingAction] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  // Reset loading and error states during render when request parameters change
  const currentRequestKey = `${page}|${activeTab}|${appliedSearch}|${statusFilter}|${paymentStatusFilter}|${sort}|${createdAfter}|${createdBefore}|${startDateFilter}|${endDateFilter}|${refreshKey}`
  const [prevRequestKey, setPrevRequestKey] = useState(currentRequestKey)

  if (currentRequestKey !== prevRequestKey) {
    setPrevRequestKey(currentRequestKey)
    setLoading(true)
    setError('')
  }

  // Fetch Bookings with cancellation guard to prevent race conditions and cascading renders
  useEffect(() => {
    let isCurrent = true
    const params = {
      page,
      page_size: 10,
      sort,
    }
    if (activeTab !== 'all') params.tab = activeTab
    if (appliedSearch) params.search = appliedSearch
    if (statusFilter) params.status = statusFilter
    if (paymentStatusFilter) params.payment_status = paymentStatusFilter
    if (createdAfter) params.created_after = createdAfter
    if (createdBefore) params.created_before = createdBefore
    if (startDateFilter) params.start_date = startDateFilter
    if (endDateFilter) params.end_date = endDateFilter

    getAdminBookings(params)
      .then((res) => {
        if (!isCurrent) return
        setBookings(res.results || [])
        setCounts(res.counts || {})
        setProductSummaries(res.product_summaries || [])
        setTotalPages(res.total_pages || 1)
        setTotalCount(res.count || 0)
        setError('')
      })
      .catch((err) => {
        if (!isCurrent) return
        setError(err.message || 'Failed to load bookings.')
      })
      .finally(() => {
        if (isCurrent) {
          setLoading(false)
        }
      })

    return () => {
      isCurrent = false
    }
  }, [
    page,
    activeTab,
    appliedSearch,
    statusFilter,
    paymentStatusFilter,
    sort,
    createdAfter,
    createdBefore,
    startDateFilter,
    endDateFilter,
    refreshKey,
  ])

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    setPage(1)
    setAppliedSearch(search.trim())
  }

  const handleClearFilters = () => {
    setSearch('')
    setAppliedSearch('')
    setProductSummaries([])
    setStatusFilter('')
    setPaymentStatusFilter('')
    setSort('-created_at')
    setCreatedAfter('')
    setCreatedBefore('')
    setStartDateFilter('')
    setEndDateFilter('')
    setActiveTab('all')
    setPage(1)
  }

  // View Details
  const handleOpenDetails = (id) => {
    const existing = bookings.find((b) => b.id === id)
    if (existing) {
      setSelectedBooking(existing)
    }
    setDetailLoading(true)
    setDetailError('')
    getAdminBookingDetails(id)
      .then((data) => {
        setSelectedBooking(data)
      })
      .catch((err) => {
        const msg = err.message || 'Failed to load booking details.'
        setDetailError(msg)
        if (!existing) {
          setError(msg)
        }
      })
      .finally(() => {
        setDetailLoading(false)
      })
  }

  // Action Dialog Triggers
  const openActionDialog = ({ title, message, confirmText, confirmColor, requiresReason, actionType, targetStatus, bookingId, reasonLabel }) => {
    setActionError('')
    setActionReason('')
    setActionModal({
      isOpen: true,
      title,
      message,
      confirmText: confirmText || 'Confirm',
      confirmColor: confirmColor || 'bg-[#9D4C29] hover:bg-[#813d21]',
      requiresReason: Boolean(requiresReason),
      reasonLabel: reasonLabel || 'Reason',
      actionType,
      targetStatus,
      bookingId,
    })
  }

  const handleConfirmAction = async () => {
    if (actionModal.requiresReason && !actionReason.trim()) {
      setActionError(`${actionModal.reasonLabel || 'Reason'} is mandatory for this action.`)
      return
    }

    setSubmittingAction(true)
    setActionError('')

    try {
      if (actionModal.actionType === 'status_transition') {
        const payload = { target_status: actionModal.targetStatus }
        if (actionReason.trim()) payload.reason = actionReason.trim()
        await updateAdminBookingStatus(actionModal.bookingId, payload)
        setSuccessMsg(`Booking status transitioned to ${actionModal.targetStatus.replace(/_/g, ' ')} successfully.`)
      } else if (actionModal.actionType === 'return_accept') {
        await adminReturnAction(actionModal.bookingId, { action: 'accept' })
        setSuccessMsg('Return request accepted! Rental completed and stock restored.')
      } else if (actionModal.actionType === 'return_reject') {
        await adminReturnAction(actionModal.bookingId, { action: 'reject', reason: actionReason.trim() })
        setSuccessMsg('Return request rejected and logged. Rental remains active for inspection.')
      }

      setActionModal((prev) => ({ ...prev, isOpen: false }))
      setLoading(true)
      setRefreshKey((k) => k + 1)

      // Refresh opened detail if active
      if (selectedBooking && selectedBooking.id === actionModal.bookingId) {
        handleOpenDetails(actionModal.bookingId)
      }
    } catch (err) {
      setActionError(err.message || 'Action failed. Please verify status and try again.')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Status Badge Helper
  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending_approval':
        return { label: 'Pending Approval', bg: 'bg-amber-100 text-amber-800 border-amber-200' }
      case 'waiting_for_pickup':
        return { label: 'Waiting for Pickup', bg: 'bg-orange-100 text-[#9D4C29] border-orange-200' }
      case 'rental_in_progress':
        return { label: 'Rental in Progress', bg: 'bg-blue-100 text-blue-800 border-blue-200' }
      case 'completed':
        return { label: 'Completed', bg: 'bg-emerald-100 text-emerald-800 border-emerald-200' }
      case 'rejected':
        return { label: 'Declined by Owner', bg: 'bg-rose-100 text-rose-800 border-rose-200' }
      case 'cancelled':
        return { label: 'Cancelled', bg: 'bg-gray-100 text-gray-800 border-gray-300' }
      case 'expired':
        return { label: 'Expired', bg: 'bg-slate-100 text-slate-800 border-slate-300' }
      default:
        return { label: status, bg: 'bg-gray-100 text-gray-700 border-gray-300' }
    }
  }

  // Payment Status Badge Helper
  const getPaymentBadge = (paymentStatus) => {
    switch (paymentStatus) {
      case 'paid':
        return { label: 'Payment Verified', bg: 'bg-emerald-100 text-emerald-800 border-emerald-200' }
      case 'pending':
        return { label: 'Pending Payment', bg: 'bg-amber-100 text-amber-800 border-amber-200' }
      case 'failed':
        return { label: 'Payment Failed', bg: 'bg-rose-100 text-rose-800 border-rose-200' }
      case 'refunded':
        return { label: 'Refunded', bg: 'bg-purple-100 text-purple-800 border-purple-200' }
      default:
        return { label: paymentStatus, bg: 'bg-gray-100 text-gray-700 border-gray-200' }
    }
  }

  return (
    <AdminLayout
      pageTitle="Booking Management"
      breadcrumbs={['Admin Panel', 'Rentals', 'Booking Management']}
    >
      <div className="w-full text-[#302820] space-y-6">

        {/* Header & Overview Stats */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[#302820]">
              Booking Management
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Review and manage customer reservations, status transitions, and item returns.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-xl border border-[#eee3da] bg-white px-4 py-2.5 shadow-xs">
              <span className="block text-xs text-gray-500 font-medium">Total Bookings</span>
              <span className="text-xl font-bold text-[#302820]">{counts.all ?? totalCount}</span>
            </div>
            <div className="rounded-xl border border-blue-100 bg-blue-50/50 px-4 py-2.5 shadow-xs">
              <span className="block text-xs text-blue-700 font-medium">Active Rentals</span>
              <span className="text-xl font-bold text-blue-900">{counts.active ?? 0}</span>
            </div>
            <div className="rounded-xl border border-amber-100 bg-amber-50/50 px-4 py-2.5 shadow-xs">
              <span className="block text-xs text-amber-700 font-medium">Pending Approval</span>
              <span className="text-xl font-bold text-amber-900">{counts.pending ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Global Success / Error Alerts */}
        {successMsg && (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-xs font-semibold text-emerald-900 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <span>{successMsg}</span>
            </div>
            <button type="button" onClick={() => setSuccessMsg('')} className="text-emerald-700 hover:text-emerald-900">
              <X size={14} />
            </button>
          </div>
        )}

        {error && (
          <div className="rounded-xl bg-rose-50 border border-rose-200 p-4 text-xs font-semibold text-rose-900 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-rose-600" />
              <span>{error}</span>
            </div>
            <button type="button" onClick={() => setError('')} className="text-rose-700 hover:text-rose-900">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Status Tab Navigation */}
        <div className="flex flex-wrap items-center gap-2 border-b border-[#eee3da] pb-3">
          {[
            { id: 'all', label: 'All Bookings', count: counts.all },
            { id: 'pending', label: 'Pending Approval', count: counts.pending },
            { id: 'pickup', label: 'Waiting for Pickup', count: counts.pickup },
            { id: 'active', label: 'Active Rentals / Returns', count: counts.active },
            { id: 'completed', label: 'Completed', count: counts.completed },
            { id: 'cancelled', label: 'Cancelled', count: counts.cancelled },
            { id: 'rejected', label: 'Declined', count: counts.rejected },
          ].map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id)
                  setPage(1)
                }}
                className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-[#9D4C29] text-white shadow-xs'
                    : 'bg-white text-gray-600 border border-[#eee3da] hover:bg-[#faf5f0] hover:text-[#302820]'
                }`}
              >
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                      isActive ? 'bg-white/20 text-white' : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Search & Advanced Filters Card */}
        <div className="rounded-2xl border border-[#eee3da] bg-white p-4 sm:p-5 shadow-xs space-y-4">
          <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  if (!e.target.value.trim() && appliedSearch) {
                    setAppliedSearch('')
                    setProductSummaries([])
                    setPage(1)
                  }
                }}
                placeholder="Search by Booking ID (BK-XXXXXX), customer name, email, item, or owner..."
                className="w-full rounded-xl border border-[#e5d9cf] bg-white pl-9 pr-4 py-2 text-xs outline-none focus:border-[#9D4C29]"
              />
            </div>
            <button
              type="submit"
              className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-[#9D4C29] px-5 py-2 text-xs font-bold text-white hover:bg-[#813d21] transition cursor-pointer"
            >
              <Search size={14} /> Search
            </button>
            <button
              type="button"
              onClick={handleClearFilters}
              className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-[#e5d9cf] bg-white px-4 py-2 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition cursor-pointer"
            >
              <RotateCcw size={13} /> Reset
            </button>
          </form>

          {/* Filter Dropdowns Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 pt-3 border-t border-[#f0e9e3] text-xs">
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">Booking Status</label>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value)
                  setPage(1)
                }}
                className="w-full rounded-lg border border-[#e5d9cf] bg-white p-2 text-xs outline-none focus:border-[#9D4C29]"
              >
                <option value="">All Statuses</option>
                <option value="pending_approval">Pending Approval</option>
                <option value="waiting_for_pickup">Waiting for Pickup</option>
                <option value="rental_in_progress">Rental in Progress</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
                <option value="rejected">Declined</option>
                <option value="expired">Expired</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">Payment Status</label>
              <select
                value={paymentStatusFilter}
                onChange={(e) => {
                  setPaymentStatusFilter(e.target.value)
                  setPage(1)
                }}
                className="w-full rounded-lg border border-[#e5d9cf] bg-white p-2 text-xs outline-none focus:border-[#9D4C29]"
              >
                <option value="">All Payment Statuses</option>
                <option value="paid">Payment Verified (Paid)</option>
                <option value="pending">Pending Payment</option>
                <option value="failed">Failed</option>
                <option value="refunded">Refunded</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">Sort Bookings</label>
              <select
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value)
                  setPage(1)
                }}
                className="w-full rounded-lg border border-[#e5d9cf] bg-white p-2 text-xs outline-none focus:border-[#9D4C29]"
              >
                <option value="-created_at">Newest Bookings First</option>
                <option value="created_at">Oldest Bookings First</option>
                <option value="-total_amount">Amount: High to Low</option>
                <option value="total_amount">Amount: Low to High</option>
                <option value="-start_date">Rental Date: Furthest First</option>
                <option value="start_date">Rental Date: Nearest First</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">Booking Date Range</label>
              <div className="flex items-center gap-1">
                <input
                  type="date"
                  value={createdAfter}
                  onChange={(e) => { setCreatedAfter(e.target.value); setPage(1); }}
                  className="w-1/2 rounded-lg border border-[#e5d9cf] bg-white p-1.5 text-xs outline-none"
                  title="Created on or after"
                />
                <span className="text-gray-400">→</span>
                <input
                  type="date"
                  value={createdBefore}
                  onChange={(e) => { setCreatedBefore(e.target.value); setPage(1); }}
                  className="w-1/2 rounded-lg border border-[#e5d9cf] bg-white p-1.5 text-xs outline-none"
                  title="Created on or before"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Product Search Results: Total Bookings Count */}
        {appliedSearch && productSummaries.length > 0 && (
          <div className="rounded-2xl border border-[#eee3da] bg-white p-4 sm:p-5 shadow-xs">
            <div className="divide-y divide-[#f0e9e3]">
              {productSummaries.map((prod) => (
                <div
                  key={prod.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  {/* Left: Product Image & Name */}
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-orange-50 border border-orange-100 flex items-center justify-center">
                      {prod.primary_image_url ? (
                        <img
                          src={prod.primary_image_url}
                          alt={prod.name}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <Package size={20} className="text-orange-300" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <span className="font-bold text-[#302820] text-sm truncate block" title={prod.name}>
                        {prod.name}
                      </span>
                      {prod.category_name && (
                        <span className="text-[11px] text-[#D97745] font-medium block">
                          {prod.category_name}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right: Total Bookings: X */}
                  <div className="shrink-0 text-right">
                    <span className="text-xs sm:text-sm font-semibold text-gray-600">
                      Total Bookings:{' '}
                      <span className="font-bold text-[#9D4C29]">
                        {prod.total_bookings}
                      </span>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bookings Table */}
        <div className="overflow-x-auto rounded-2xl border border-[#eee3da] bg-white shadow-xs">
          {loading ? (
            <div className="py-16 text-center text-gray-500 space-y-2">
              <Clock size={28} className="mx-auto text-orange-400 animate-spin" />
              <p className="text-xs font-semibold">Loading platform bookings...</p>
            </div>
          ) : bookings.length === 0 ? (
            <div className="py-16 text-center text-gray-500 space-y-2">
              <Package size={32} className="mx-auto text-orange-300" />
              <h3 className="text-sm font-bold text-[#302820]">No bookings found</h3>
              <p className="text-xs text-gray-400">
                Try adjusting your search criteria, status filter, or clear filters.
              </p>
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-[#f7eee7] text-[#51463d] uppercase tracking-wider font-semibold text-[11px]">
                <tr>
                  <th className="p-3.5">Booking ID & Date</th>
                  <th className="p-3.5">Customer</th>
                  <th className="p-3.5">Rental Item</th>
                  <th className="p-3.5 text-center">Qty</th>
                  <th className="p-3.5">Rental Period</th>
                  <th className="p-3.5 text-right">Total Amount</th>
                  <th className="p-3.5 text-center">Payment Status</th>
                  <th className="p-3.5 text-center">Booking Status</th>
                  <th className="p-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f0e9e3]">
                {bookings.map((b) => {
                  const sBadge = getStatusBadge(b.status)
                  const pBadge = getPaymentBadge(b.payment_status)
                  return (
                    <tr key={b.id} className="hover:bg-[#FFFDFB] transition-colors">
                      {/* ID & Date */}
                      <td className="p-3.5 whitespace-nowrap">
                        <span className="font-mono font-bold text-[#9D4C29] block">
                          {b.booking_reference}
                        </span>
                        <span className="text-[11px] text-gray-400">
                          {formatKolkataDateTime(b.created_at)}
                        </span>
                      </td>

                      {/* Customer Details */}
                      <td className="p-3.5">
                        <span className="font-semibold text-[#302820] block">
                          {b.renter?.full_name || 'Customer'}
                        </span>
                        <span className="text-gray-500 text-[11px] block">{b.renter?.email}</span>
                        {b.renter?.phone_number && (
                          <span className="text-gray-400 text-[10px] block">{b.renter.phone_number}</span>
                        )}
                      </td>

                      {/* Rental Item Details */}
                      <td className="p-3.5">
                        <div className="flex items-center gap-2.5">
                          <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-orange-50 border border-orange-100 flex items-center justify-center">
                            {b.item?.primary_image_url ? (
                              <img
                                src={b.item.primary_image_url}
                                alt={b.item.name}
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <Package size={18} className="text-orange-300" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-baseline justify-between gap-2">
                              <span className="font-semibold text-[#302820] line-clamp-1 block">
                                {b.item?.name}
                              </span>
                              {appliedSearch && b.item?.total_bookings_count !== undefined && (
                                <span
                                  className="shrink-0 text-[10px] font-semibold text-gray-600 bg-[#faf5f0] border border-[#eedfd5] px-1.5 py-0.5 rounded whitespace-nowrap"
                                  title={`Total booking records for ${b.item.name}: ${b.item.total_bookings_count}`}
                                >
                                  Total Bookings:{' '}
                                  <span className="font-bold text-[#9D4C29]">
                                    {b.item.total_bookings_count}
                                  </span>
                                </span>
                              )}
                            </div>
                            <span className="text-[11px] text-[#D97745] font-medium block">
                              {b.item?.category_name}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Rental Quantity */}
                      <td className="p-3.5 text-center font-bold text-[#302820] whitespace-nowrap">
                        {b.requested_quantity || 1}
                      </td>

                      {/* Rental Start and End Dates */}
                      <td className="p-3.5 whitespace-nowrap">
                        <span className="font-medium text-[#302820] block">
                          {b.start_date} → {b.end_date}
                        </span>
                        <span className="text-[11px] text-gray-400">
                          {b.duration_days} {b.duration_days === 1 ? 'day' : 'days'} ({b.duration_days * 24}h)
                        </span>
                      </td>

                      {/* Total Rental Amount */}
                      <td className="p-3.5 text-right whitespace-nowrap">
                        <span className="font-black text-[#9D4C29] text-sm block">
                          ₹{b.total_amount}
                        </span>
                        <span className="text-[10px] text-gray-400">
                          Rental: ₹{b.rental_amount} + Dep: ₹{b.deposit_amount}
                        </span>
                      </td>

                      {/* Payment Status */}
                      <td className="p-3.5 text-center whitespace-nowrap">
                        <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${pBadge.bg}`}>
                          {pBadge.label}
                        </span>
                      </td>

                      {/* Booking Status */}
                      <td className="p-3.5 text-center whitespace-nowrap">
                        <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${sBadge.bg}`}>
                          {sBadge.label}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="p-3.5 text-right whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => handleOpenDetails(b.id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-[#e5d9cf] bg-white px-3 py-1.5 text-xs font-semibold text-[#302820] hover:bg-orange-50 hover:text-[#9D4C29] transition shadow-2xs cursor-pointer"
                        >
                          <Eye size={13} /> View Details
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}

          {/* Pagination Footer */}
          {!loading && bookings.length > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-4 border-t border-[#f0e9e3] text-xs text-gray-600">
              <div>
                Showing page <span className="font-bold text-[#302820]">{page}</span> of{' '}
                <span className="font-bold text-[#302820]">{totalPages}</span> ({totalCount} total bookings)
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="inline-flex items-center gap-1 rounded-lg border border-[#e5d9cf] bg-white px-3 py-1.5 font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition cursor-pointer"
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="inline-flex items-center gap-1 rounded-lg border border-[#e5d9cf] bg-white px-3 py-1.5 font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition cursor-pointer"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ================================================================== */}
        {/* Full Booking Details Modal / Drawer */}
        {/* ================================================================== */}
        {selectedBooking && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs overflow-y-auto">
            <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-3xl bg-white p-6 sm:p-8 shadow-2xl border border-orange-100 space-y-6 my-auto text-xs text-[#302820]">
              
              {/* Header */}
              <div className="flex items-start justify-between border-b border-[#f0e9e3] pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-base font-black text-[#9D4C29]">
                      {selectedBooking.booking_reference}
                    </span>
                    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getStatusBadge(selectedBooking.status).bg}`}>
                      {getStatusBadge(selectedBooking.status).label}
                    </span>
                    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getPaymentBadge(selectedBooking.payment_status).bg}`}>
                      {getPaymentBadge(selectedBooking.payment_status).label}
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-400 mt-1">
                    Created on: {formatKolkataDateTime(selectedBooking.created_at)}
                  </p>
                  {detailLoading && (
                    <span className="text-[10px] text-orange-600 font-medium">Updating details...</span>
                  )}
                  {detailError && (
                    <span className="text-[10px] text-rose-600 font-medium block mt-1">{detailError}</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedBooking(null)}
                  className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition"
                >
                  <X size={20} />
                </button>
              </div>

              {/* 3-Column Info Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Customer Details */}
                <div className="rounded-2xl border border-orange-100 bg-[#FFFDFB] p-4 space-y-2">
                  <div className="flex items-center gap-1.5 font-bold text-[#9D4C29] text-[11px] uppercase tracking-wider">
                    <User size={14} /> Customer Details
                  </div>
                  <p className="font-bold text-[#302820] text-sm">{selectedBooking.renter?.full_name}</p>
                  <p className="text-gray-600">{selectedBooking.renter?.email}</p>
                  <p className="text-gray-500">{selectedBooking.renter?.phone_number || 'No phone recorded'}</p>
                  {selectedBooking.renter_address && (
                    <div className="pt-2 border-t border-orange-100/70 text-[11px] text-gray-600">
                      <span className="font-semibold block text-gray-500">Delivery Address:</span>
                      <span>
                        {selectedBooking.renter_address.full_formatted_address || (
                          `${selectedBooking.renter_address.house_number ? `${selectedBooking.renter_address.house_number}, ` : ''}${selectedBooking.renter_address.address || ''}, ${selectedBooking.renter_address.city || ''} - ${selectedBooking.renter_address.pincode || ''}`
                        )}
                      </span>
                    </div>
                  )}
                </div>

                {/* Rental Item & Owner Details */}
                <div className="rounded-2xl border border-orange-100 bg-[#FFFDFB] p-4 space-y-2">
                  <div className="flex items-center gap-1.5 font-bold text-[#9D4C29] text-[11px] uppercase tracking-wider">
                    <Package size={14} /> Item & Owner
                  </div>
                  <p className="font-bold text-[#302820] text-sm">{selectedBooking.item?.name}</p>
                  <p className="text-[11px] text-[#D97745] font-semibold">{selectedBooking.item?.category_name}</p>
                  <div className="pt-2 border-t border-orange-100/70 text-[11px] text-gray-600 space-y-0.5">
                    <span className="font-semibold block text-gray-500">Item Owner / Lender:</span>
                    <p className="font-bold text-[#302820]">{selectedBooking.owner?.full_name}</p>
                    <p>{selectedBooking.owner?.email}</p>
                    <p>{selectedBooking.owner?.phone_number || 'No owner phone'}</p>
                  </div>
                </div>

                {/* Rental Dates & Pricing Breakdown */}
                <div className="rounded-2xl border border-orange-100 bg-[#FFFDFB] p-4 space-y-2">
                  <div className="flex items-center gap-1.5 font-bold text-[#9D4C29] text-[11px] uppercase tracking-wider">
                    <Calendar size={14} /> Rental & Pricing
                  </div>
                  <div className="text-[11px] text-gray-600 space-y-1">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Dates:</span>
                      <strong className="text-[#302820]">{selectedBooking.start_date} → {selectedBooking.end_date}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Duration:</span>
                      <span>{selectedBooking.duration_days} day(s)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Quantity:</span>
                      <span className="font-bold text-[#9D4C29]">{selectedBooking.requested_quantity} unit(s)</span>
                    </div>
                    <div className="flex justify-between pt-1 border-t border-orange-100/60">
                      <span className="text-gray-400">Rental Rate:</span>
                      <span>₹{selectedBooking.daily_price}/day</span>
                    </div>
                    {parseFloat(selectedBooking.discount_amount || 0) > 0 && (
                      <div className="flex justify-between text-emerald-700">
                        <span>Discount:</span>
                        <span>-₹{selectedBooking.discount_amount}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-gray-400">Deposit:</span>
                      <span>₹{selectedBooking.deposit_amount}</span>
                    </div>
                    <div className="flex justify-between text-sm font-black text-[#9D4C29] pt-1 border-t border-orange-200">
                      <span>Total Amount:</span>
                      <span>₹{selectedBooking.total_amount}</span>
                    </div>
                    <div className="text-[10px] text-gray-400 pt-0.5">
                      Method: {selectedBooking.payment_method_display || selectedBooking.payment_method}
                    </div>
                  </div>
                </div>
              </div>

              {/* Lifecycle Audit History */}
              <div className="rounded-2xl border border-gray-200 bg-gray-50/50 p-4 space-y-2">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
                  <Clock size={13} /> Complete Booking History & Audit Trail
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-[11px] text-gray-600 pt-1">
                  <div>
                    <span className="text-gray-400 block">Created:</span>
                    <strong className="text-[#302820]">{formatKolkataDateTime(selectedBooking.created_at)}</strong>
                  </div>
                  <div>
                    <span className="text-gray-400 block">Approved At:</span>
                    <span className="text-[#302820]">{selectedBooking.approved_at ? formatKolkataDateTime(selectedBooking.approved_at) : '—'}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block">Pickup Confirmed:</span>
                    <span className="text-[#302820]">{selectedBooking.picked_up_at_display || (selectedBooking.picked_up_at ? formatKolkataDateTime(selectedBooking.picked_up_at) : '—')}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block">Return Deadline:</span>
                    <span className="text-[#302820] font-semibold">{selectedBooking.return_deadline_display || (selectedBooking.return_deadline ? formatKolkataDateTime(selectedBooking.return_deadline) : '—')}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block">Returned & Completed:</span>
                    <span className="text-[#302820] font-semibold">{selectedBooking.returned_at_display || (selectedBooking.returned_at ? formatKolkataDateTime(selectedBooking.returned_at) : '—')}</span>
                  </div>
                  {selectedBooking.payment_verified_at && (
                    <div>
                      <span className="text-gray-400 block">Payment Verified:</span>
                      <span className="text-emerald-700 font-semibold">{formatKolkataDateTime(selectedBooking.payment_verified_at)}</span>
                    </div>
                  )}
                  {selectedBooking.rejection_reason && (
                    <div className="sm:col-span-2">
                      <span className="text-rose-600 font-semibold block">Decline Reason:</span>
                      <span className="text-rose-950">{selectedBooking.rejection_reason}</span>
                    </div>
                  )}
                  {selectedBooking.cancellation_reason && (
                    <div className="sm:col-span-2">
                      <span className="text-rose-600 font-semibold block">Cancellation Reason:</span>
                      <span className="text-rose-950">{selectedBooking.cancellation_reason}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Associated Issue Reports / Disputes if any */}
              {selectedBooking.issue_reports && selectedBooking.issue_reports.length > 0 && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50/60 p-4 space-y-2">
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-rose-800 flex items-center gap-1.5">
                    <ShieldAlert size={14} className="text-rose-600" /> Issue Reports & Return Inspection Notes
                  </h4>
                  <div className="space-y-2">
                    {selectedBooking.issue_reports.map((rep) => (
                      <div key={rep.id} className="rounded-xl bg-white border border-rose-100 p-3 text-xs space-y-1">
                        <div className="flex justify-between items-center text-[11px]">
                          <span className="font-bold text-[#302820]">Reported by {rep.renter_name || 'Renter'}</span>
                          <span className={`px-2 py-0.5 rounded-full font-bold ${rep.status === 'open' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`}>
                            {rep.status}
                          </span>
                        </div>
                        <p className="text-gray-700">{rep.description}</p>
                        <span className="text-[10px] text-gray-400 block">{formatKolkataDateTime(rep.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Permitted Admin Action Buttons */}
              <div className="pt-4 border-t border-[#f0e9e3] flex flex-wrap items-center justify-between gap-3">
                <div className="text-[11px] text-gray-400">
                  Admins can execute authorized lifecycle transitions matching platform business rules.
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* Status: pending_approval */}
                  {selectedBooking.status === 'pending_approval' && (
                    <>
                      <button
                        type="button"
                        onClick={() => openActionDialog({
                          title: 'Approve Booking Request',
                          message: `Are you sure you want to approve booking ${selectedBooking.booking_reference}? This will reserve ${selectedBooking.requested_quantity} unit(s) of "${selectedBooking.item?.name}" for the selected rental dates.`,
                          confirmText: 'Approve & Reserve Stock',
                          confirmColor: 'bg-emerald-600 hover:bg-emerald-700',
                          actionType: 'status_transition',
                          targetStatus: 'waiting_for_pickup',
                          bookingId: selectedBooking.id,
                        })}
                        className="rounded-xl bg-emerald-600 px-4 py-2 font-bold text-white hover:bg-emerald-700 transition cursor-pointer"
                      >
                        Approve Booking
                      </button>
                      <button
                        type="button"
                        onClick={() => openActionDialog({
                          title: 'Decline Booking Request',
                          message: `Please specify the reason why booking ${selectedBooking.booking_reference} is being declined.`,
                          confirmText: 'Decline Request',
                          confirmColor: 'bg-rose-600 hover:bg-rose-700',
                          requiresReason: true,
                          reasonLabel: 'Rejection Reason',
                          actionType: 'status_transition',
                          targetStatus: 'rejected',
                          bookingId: selectedBooking.id,
                        })}
                        className="rounded-xl border border-rose-300 bg-white px-4 py-2 font-semibold text-rose-700 hover:bg-rose-50 transition cursor-pointer"
                      >
                        Decline Request
                      </button>
                    </>
                  )}

                  {/* Status: waiting_for_pickup */}
                  {selectedBooking.status === 'waiting_for_pickup' && (
                    <>
                      {selectedBooking.payment_status === 'paid' ? (
                        <button
                          type="button"
                          onClick={() => openActionDialog({
                            title: 'Confirm Item Handover & Start Rental',
                            message: `Confirm that item handover has taken place for booking ${selectedBooking.booking_reference}. This will activate the rental in progress and stamp the return countdown.`,
                            confirmText: 'Confirm Pickup',
                            confirmColor: 'bg-[#D97745] hover:bg-[#B85D32]',
                            actionType: 'status_transition',
                            targetStatus: 'rental_in_progress',
                            bookingId: selectedBooking.id,
                          })}
                          className="rounded-xl bg-[#D97745] px-4 py-2 font-bold text-white hover:bg-[#B85D32] transition cursor-pointer"
                        >
                          Confirm Pickup (Start Rental)
                        </button>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-xl bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs font-semibold text-amber-800">
                          <AlertTriangle size={13} className="text-amber-600" /> Pickup blocked until payment verified
                        </span>
                      )}

                      <button
                        type="button"
                        onClick={() => openActionDialog({
                          title: 'Cancel Booking',
                          message: `Are you sure you want to cancel booking ${selectedBooking.booking_reference}? Reserved stock will be automatically released.`,
                          confirmText: 'Cancel Booking & Release Stock',
                          confirmColor: 'bg-rose-600 hover:bg-rose-700',
                          requiresReason: true,
                          reasonLabel: 'Cancellation Reason',
                          actionType: 'status_transition',
                          targetStatus: 'cancelled',
                          bookingId: selectedBooking.id,
                        })}
                        className="rounded-xl border border-rose-300 bg-white px-4 py-2 font-semibold text-rose-700 hover:bg-rose-50 transition cursor-pointer"
                      >
                        Cancel Booking
                      </button>
                    </>
                  )}

                  {/* Status: rental_in_progress (Return Management) */}
                  {selectedBooking.status === 'rental_in_progress' && (
                    <>
                      <button
                        type="button"
                        onClick={() => openActionDialog({
                          title: 'Accept Return & Complete Rental',
                          message: `Confirm that "${selectedBooking.item?.name}" has been physically returned in acceptable condition for booking ${selectedBooking.booking_reference}. This will mark the rental as Completed, release reserved stock, and conclude the countdown.`,
                          confirmText: 'Accept Return & Complete',
                          confirmColor: 'bg-emerald-700 hover:bg-emerald-800',
                          actionType: 'return_accept',
                          bookingId: selectedBooking.id,
                        })}
                        className="rounded-xl bg-emerald-700 px-4 py-2 font-bold text-white hover:bg-emerald-800 transition cursor-pointer"
                      >
                        Accept Return (Complete Rental)
                      </button>

                      <button
                        type="button"
                        onClick={() => openActionDialog({
                          title: 'Reject Return Request / Log Dispute',
                          message: `Specify why the return for booking ${selectedBooking.booking_reference} is being rejected (e.g. equipment damaged, missing accessories, or disputed). An issue report will be logged and the rental will remain in progress.`,
                          confirmText: 'Reject Return Request',
                          confirmColor: 'bg-rose-600 hover:bg-rose-700',
                          requiresReason: true,
                          reasonLabel: 'Return Rejection Reason',
                          actionType: 'return_reject',
                          bookingId: selectedBooking.id,
                        })}
                        className="rounded-xl border border-rose-300 bg-white px-4 py-2 font-semibold text-rose-700 hover:bg-rose-50 transition cursor-pointer"
                      >
                        Reject Return Request
                      </button>
                    </>
                  )}

                  <button
                    type="button"
                    onClick={() => setSelectedBooking(null)}
                    className="rounded-xl border border-[#e5d9cf] bg-white px-4 py-2 font-semibold text-gray-700 hover:bg-gray-50 transition cursor-pointer"
                  >
                    Close
                  </button>
                </div>
              </div>

            </div>
          </div>
        )}

        {/* ================================================================== */}
        {/* Action Confirmation & Reason Prompt Dialog */}
        {/* ================================================================== */}
        {actionModal.isOpen && (
          <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
            <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl border border-orange-100 space-y-4 text-xs text-[#302820]">
              <div className="flex items-start justify-between border-b border-[#f0e9e3] pb-3">
                <h3 className="font-bold text-sm text-[#302820] flex items-center gap-1.5">
                  <ShieldAlert size={16} className="text-[#9D4C29]" />
                  {actionModal.title}
                </h3>
                <button
                  type="button"
                  onClick={() => setActionModal((prev) => ({ ...prev, isOpen: false }))}
                  className="text-gray-400 hover:text-gray-700"
                >
                  <X size={18} />
                </button>
              </div>

              <p className="text-gray-600 leading-relaxed">
                {actionModal.message}
              </p>

              {actionModal.requiresReason && (
                <div className="space-y-1 pt-1">
                  <label className="block font-semibold text-[#51463d]">
                    {actionModal.reasonLabel} <span className="text-rose-600">*</span>
                  </label>
                  <textarea
                    rows={3}
                    value={actionReason}
                    onChange={(e) => setActionReason(e.target.value)}
                    placeholder="Enter detailed reason here..."
                    className="w-full rounded-xl border border-[#e5d9cf] bg-white p-3 text-xs outline-none focus:border-[#9D4C29]"
                  />
                </div>
              )}

              {actionError && (
                <div className="rounded-xl bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800 font-medium">
                  {actionError}
                </div>
              )}

              <div className="pt-3 border-t border-[#f0e9e3] flex justify-end gap-2">
                <button
                  type="button"
                  disabled={submittingAction}
                  onClick={() => setActionModal((prev) => ({ ...prev, isOpen: false }))}
                  className="rounded-xl border border-[#e5d9cf] bg-white px-4 py-2 font-semibold text-gray-700 hover:bg-gray-50 transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={submittingAction}
                  onClick={handleConfirmAction}
                  className={`rounded-xl px-5 py-2 font-bold text-white transition disabled:opacity-50 cursor-pointer ${actionModal.confirmColor}`}
                >
                  {submittingAction ? 'Processing...' : actionModal.confirmText}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </AdminLayout>
  )
}

