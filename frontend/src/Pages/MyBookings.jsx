import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import BookingStatusTabs from '../Components/BookingStatusTabs'
import BookingSearch from '../Components/BookingSearch'
import BookingCard from '../Components/BookingCard'
import CancelBookingModal from '../Components/CancelBookingModal'
import { getMyBookings, getMyListings, cancelBooking } from '../services/api'
import { Compass, Inbox, ChevronLeft, ChevronRight, CheckCircle2 } from 'lucide-react'

export default function MyBookings() {
  const [bookings, setBookings] = useState([])
  const [totalBookings, setTotalBookings] = useState(null)
  const [totalListings, setTotalListings] = useState(null)
  const [bookingCountError, setBookingCountError] = useState('')
  const [listingCountError, setListingCountError] = useState('')
  const [listingRevision, setListingRevision] = useState(0)

  useEffect(() => {
    let active = true
    let pending = false
    const fetchListingCount = async () => {
      if (pending || document.visibilityState === 'hidden') return
      pending = true
      try {
        const data = await getMyListings()
        if (!Array.isArray(data.results)) throw new Error('Could not read your listing count.')
        if (active) { setTotalListings(data.results.length); setListingCountError('') }
      } catch (err) {
        if (active) { setTotalListings(null); setListingCountError(err.message) }
      } finally { pending = false }
    }
    void fetchListingCount()
    const timer = setInterval(fetchListingCount, 15000)
    window.addEventListener('focus', fetchListingCount)
    document.addEventListener('visibilitychange', fetchListingCount)
    return () => {
      active = false
      clearInterval(timer)
      window.removeEventListener('focus', fetchListingCount)
      document.removeEventListener('visibilitychange', fetchListingCount)
    }
  }, [listingRevision])
  const [counts, setCounts] = useState({ all: 0, active: 0, completed: 0, cancelled: 0 })
  const [activeTab, setActiveTab] = useState('all')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [toastMessage, setToastMessage] = useState('')

  // Cancel modal state
  const [selectedBookingForCancel, setSelectedBookingForCancel] = useState(null)
  const [cancelModalOpen, setCancelModalOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
      setLoading(true)
    }, 350)
    return () => clearTimeout(timer)
  }, [search])

  const refetchBookings = () => {
    setLoading(true)
    getMyBookings({
      tab: activeTab,
      search: debouncedSearch,
      page,
      page_size: 6,
    })
      .then((data) => {
        setBookings(data.results || [])
        setTotalBookings(Number.isInteger(data.counts?.all) ? data.counts.all : null)
        setBookingCountError(Number.isInteger(data.counts?.all) ? '' : 'Could not read your booking count.')
        setCounts(data.counts || { all: 0, active: 0, completed: 0, cancelled: 0 })
        setTotalPages(data.total_pages || 1)
        setLoading(false)
      })
      .catch((err) => {
        setTotalBookings(null)
        setBookingCountError(err.message || 'Could not load your booking count.')
        console.error('Failed to fetch bookings:', err)
        setLoading(false)
      })
  }

  useEffect(() => {
    let isCurrent = true
    const fetchBookings = () => getMyBookings({
      tab: activeTab,
      search: debouncedSearch,
      page,
      page_size: 6,
    })
      .then((data) => {
        if (isCurrent) {
          setBookings(data.results || [])
          setTotalBookings(Number.isInteger(data.counts?.all) ? data.counts.all : null)
          setBookingCountError(Number.isInteger(data.counts?.all) ? '' : 'Could not read your booking count.')
          setCounts(data.counts || { all: 0, active: 0, completed: 0, cancelled: 0 })
          setTotalPages(data.total_pages || 1)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isCurrent) {
          setTotalBookings(null)
          setBookingCountError(err.message || 'Could not load your booking count.')
          console.error('Failed to fetch bookings:', err)
          setLoading(false)
        }
      })

    void fetchBookings()
    const refresh = () => { if (document.visibilityState !== 'hidden') void fetchBookings() }
    const interval = setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    window.addEventListener('rentbee:bookings-changed', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('rentbee:bookings-changed', refresh)
      document.removeEventListener('visibilitychange', refresh)
      isCurrent = false
    }
  }, [activeTab, debouncedSearch, page])

  const handleTabChange = (newTab) => {
    setActiveTab(newTab)
    setPage(1)
    setLoading(true)
  }

  const handleClearSearch = () => {
    setSearch('')
    setDebouncedSearch('')
    setPage(1)
    setLoading(true)
  }

  const handleOpenCancelModal = (booking) => {
    setSelectedBookingForCancel(booking)
    setCancelModalOpen(true)
  }

  const handleConfirmCancel = async (bookingId, reason) => {
    setCancelling(true)
    try {
      await cancelBooking(bookingId, reason)
      setCancelModalOpen(false)
      setSelectedBookingForCancel(null)
      setToastMessage('Booking cancelled successfully.')
      setTimeout(() => setToastMessage(''), 4000)
      refetchBookings()
    } catch (err) {
      alert(err.message || 'Failed to cancel booking.')
    } finally {
      setCancelling(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          
          {/* Toast Notification */}
          {toastMessage && (
            <div className="mb-6 flex items-center gap-2 rounded-2xl bg-emerald-50 border border-emerald-200 p-4 text-xs font-semibold text-emerald-800 animate-in fade-in duration-200">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <span>{toastMessage}</span>
            </div>
          )}

          {/* Page Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
            <div>
              <h1 className="text-2xl font-black text-[#352720] sm:text-3xl">
                My Bookings
              </h1>
              <p className="mt-1 text-xs text-gray-500 sm:text-sm max-w-2xl">
                Manage your rentals, track pickup status, view booking details, and manage your rental requests.
              </p>
            </div>

            <Link
              to="/browse"
              className="inline-flex items-center gap-2 rounded-full bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition shadow-xs self-start sm:self-center shrink-0"
            >
              <Compass size={15} />
              <span>Explore Items</span>
            </Link>
          </div>

          <section aria-label="Your booking and listing totals" className="mb-8">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-2xl border border-orange-100 bg-white p-5 shadow-xs">
                <h2 className="text-sm font-semibold text-gray-600">Total Bookings</h2>
                <p role="status" className="mt-2 text-3xl font-black text-[#352720]">
                  {bookingCountError ? 'Unavailable' : totalBookings ?? 'Loading...'}
                </p>
                <p className="mt-2 text-xs text-gray-500">All bookings you made, across every status.</p>
              </div>
              <div className="rounded-2xl border border-orange-100 bg-white p-5 shadow-xs">
                <h2 className="text-sm font-semibold text-gray-600">Total Listings</h2>
                <p role="status" className="mt-2 text-3xl font-black text-[#352720]">
                  {listingCountError ? 'Unavailable' : totalListings ?? 'Loading...'}
                </p>
                <p className="mt-2 text-xs text-gray-500">Your published and unpublished listings, excluding deactivated items.</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <Link to="/my-listings" className="inline-flex w-full justify-center rounded-full bg-[#9D4C29] px-5 py-2.5 text-sm font-bold text-white hover:bg-[#813B20] sm:w-auto">My Listings</Link>
              {(bookingCountError || listingCountError) && <p role="alert" className="text-xs text-rose-700">
                A summary count could not be loaded.
                <button type="button" className="ml-2 font-bold underline" onClick={() => {
                  refetchBookings()
                  setListingRevision((value) => value + 1)
                }}>Retry counts</button>
              </p>}
            </div>
          </section>

          {/* Booking Status Tabs (Top 4 Cards) */}
          <section aria-label="Booking Status Overview" className="mb-8">
            <BookingStatusTabs
              activeTab={activeTab}
              onTabChange={handleTabChange}
              counts={counts}
            />
          </section>

          {/* Search Bar & Filter Bar */}
          <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <BookingSearch
              value={search}
              onChange={setSearch}
              onClear={handleClearSearch}
            />

            <div className="text-xs text-gray-400 font-medium">
              Showing {bookings.length} {bookings.length === 1 ? 'rental' : 'rentals'}
              {activeTab !== 'all' && ` in ${activeTab}`}
            </div>
          </div>

          {/* Booking Cards List */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((n) => (
                <div
                  key={n}
                  className="h-44 rounded-3xl bg-white border border-orange-100 p-6 animate-pulse"
                >
                  <div className="flex gap-4">
                    <div className="h-28 w-28 bg-orange-100/60 rounded-2xl" />
                    <div className="flex-1 space-y-3">
                      <div className="h-4 bg-orange-100/50 rounded w-1/3" />
                      <div className="h-5 bg-orange-100/70 rounded w-1/2" />
                      <div className="h-4 bg-orange-100/30 rounded w-1/4" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : bookings.length > 0 ? (
            <div className="space-y-4">
              {bookings.map((booking) => (
                <BookingCard
                  key={booking.id}
                  booking={booking}
                  onCancelClick={handleOpenCancelModal}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-50 text-[#D97745]">
                <Inbox size={28} />
              </div>
              <h3 className="mt-4 text-base font-bold text-[#352720]">
                No bookings found
              </h3>
              <p className="mt-1 text-xs text-gray-500 max-w-sm mx-auto">
                {search
                  ? `No rentals match "${search}". Try clearing your search.`
                  : activeTab === 'all'
                  ? 'You have not booked any rental items yet.'
                  : `You have no ${activeTab} rentals at this time.`}
              </p>
              <div className="mt-6 flex justify-center gap-3">
                {search && (
                  <button
                    type="button"
                    onClick={handleClearSearch}
                    className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
                  >
                    Clear Search
                  </button>
                )}
                <Link
                  to="/browse"
                  className="rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition"
                >
                  Browse Rental Items
                </Link>
              </div>
            </div>
          )}

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-orange-200 bg-white text-[#49362D] hover:bg-orange-50 transition disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                aria-label="Previous Page"
              >
                <ChevronLeft size={16} />
              </button>

              <span className="px-3 text-xs font-semibold text-gray-600">
                Page {page} of {totalPages}
              </span>

              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-orange-200 bg-white text-[#49362D] hover:bg-orange-50 transition disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                aria-label="Next Page"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}

        </main>
      </div>

      <Footer />

      {/* Cancellation Modal */}
      <CancelBookingModal
        booking={selectedBookingForCancel}
        isOpen={cancelModalOpen}
        onClose={() => {
          setCancelModalOpen(false)
          setSelectedBookingForCancel(null)
        }}
        onConfirm={handleConfirmCancel}
        loading={cancelling}
      />
    </div>
  )
}
