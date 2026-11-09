import { useEffect, useState, useMemo } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import WishlistHeartButton from '../Components/WishlistHeartButton'
import {
  getPublicItem,
  getPublicItems,
  checkItemAvailability,
  requestAvailabilityNotification,
} from '../services/api'
import { calculateRentalDuration, getNextDayStr } from '../utils/dateUtils'
import { getAccessToken } from '../services/authentication'
import {
  ChevronRight,
  ShieldCheck,
  MapPin,
  Calendar,
  Clock,
  Bell,
  Sparkles,
  Maximize2,
  X,
  AlertCircle,
  RefreshCw,
  Info,
  CheckCircle2,
} from 'lucide-react'

// Normalizes image URLs whether absolute or relative to backend media host
function resolveImageUrl(url) {
  if (!url) return null
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  const apiBase =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
    'http://127.0.0.1:8000/api'
  const origin = apiBase.replace(/\/api\/?$/, '')
  return `${origin}${url.startsWith('/') ? '' : '/'}${url}`
}

export default function ItemDetails() {
  const { id } = useParams()

  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Image gallery states
  const [selectedImage, setSelectedImage] = useState(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const todayStr = useMemo(() => new Date().toISOString().split('T')[0], [])

  // Rental date selection - do NOT default to today if user has not selected dates
  const [startDate, setStartDate] = useState(() => searchParams.get('start_date') || '')
  const [endDate, setEndDate] = useState(() => searchParams.get('end_date') || '')

  // Real-time availability check state
  const [checkingAvailability, setCheckingAvailability] = useState(false)
  const [availabilityResult, setAvailabilityResult] = useState(null)

  // Notification request state
  const [notifying, setNotifying] = useState(false)
  const [notifySuccess, setNotifySuccess] = useState(false)
  const [notifyMessage, setNotifyMessage] = useState('')
  const [notifyError, setNotifyError] = useState('')

  // Recommendation sections data
  const [relatedItems, setRelatedItems] = useState([])
  const [ownerItems, setOwnerItems] = useState([])
  const [alsoLikeItems, setAlsoLikeItems] = useState([])

  // Retry trigger
  const [reloadToken, setReloadToken] = useState(0)

  // Load item details
  useEffect(() => {
    let isCurrent = true

    getPublicItem(id)
      .then((data) => {
        if (!isCurrent) return
        setItem(data)
        const primary =
          data.primary_image_url ||
          (data.images && data.images.length > 0 ? resolveImageUrl(data.images[0].image) : null)
        setSelectedImage(primary)
        setError(null)
        setLoading(false)
      })
      .catch((err) => {
        if (!isCurrent) return
        console.error('Failed to load item:', err)
        setError(err.message || 'Item not found or unavailable.')
        setLoading(false)
      })

    window.scrollTo({ top: 0, behavior: 'smooth' })

    return () => {
      isCurrent = false
    }
  }, [id, reloadToken])

  // Prepare images list (deduplicating and normalizing)
  const allImages = useMemo(() => {
    if (!item) return []
    const list = []
    if (item.images && item.images.length > 0) {
      item.images.forEach((imgObj) => {
        const url = resolveImageUrl(imgObj.image)
        if (url && !list.includes(url)) list.push(url)
      })
    }
    if (item.primary_image_url) {
      const primaryUrl = resolveImageUrl(item.primary_image_url)
      if (primaryUrl && !list.includes(primaryUrl)) {
        list.unshift(primaryUrl)
      }
    }
    return list
  }, [item])

  // Fetch recommendations once item is loaded
  useEffect(() => {
    if (!item?.id) return

    let isCurrent = true

    const promises = [
      item.category_id
        ? getPublicItems({
          category: item.category_id,
          exclude: item.id,
          page_size: 4,
        })
        : Promise.resolve({ results: [] }),
      item.owner
        ? getPublicItems({
          owner: item.owner,
          exclude: item.id,
          page_size: 4,
        })
        : Promise.resolve({ results: [] }),
      getPublicItems({
        exclude: item.id,
        page_size: 8,
        sort: '-created_at',
      }),
    ]

    Promise.all(promises)
      .then(([relatedRes, ownerRes, alsoRes]) => {
        if (!isCurrent) return
        const rel = relatedRes.results || []
        const rawOwn = ownerRes.results || []
        const all = alsoRes.results || []

        // Deduplicate owner items against related items
        const relatedIds = new Set(rel.map((i) => i.id))
        const own = rawOwn.filter((i) => !relatedIds.has(i.id))

        setRelatedItems(rel)
        setOwnerItems(own)

        // Deduplicate also-like against both related items and owner items
        const ownerIds = new Set(own.map((i) => i.id))
        const filtered = all.filter(
          (i) => i.id !== item.id && !relatedIds.has(i.id) && !ownerIds.has(i.id)
        )
        setAlsoLikeItems(filtered.slice(0, 4))
      })
      .catch((err) => {
        console.error('Failed to load recommendation sections:', err)
      })

    return () => {
      isCurrent = false
    }
  }, [item?.id, item?.category_id, item?.owner])

  const hasSelectedDates = Boolean(startDate && endDate)
  const isDateRangeInvalid = hasSelectedDates && endDate <= startDate

  // Real-time availability check when dates are provided
  useEffect(() => {
    if (!item?.id || !startDate || !endDate || endDate <= startDate) {
      return
    }

    let isCurrent = true
    queueMicrotask(() => {
      if (isCurrent) setCheckingAvailability(true)
    })

    checkItemAvailability(item.id, startDate, endDate)
      .then((data) => {
        if (!isCurrent) return
        setAvailabilityResult(data)
      })
      .catch((err) => {
        if (!isCurrent) return
        setAvailabilityResult({
          is_available: false,
          status_label: 'Unavailable',
          message: err.message || 'Could not verify availability for these dates.',
        })
      })
      .finally(() => {
        if (isCurrent) setCheckingAvailability(false)
      })

    return () => {
      isCurrent = false
    }
  }, [item?.id, startDate, endDate])

  const activeAvailabilityResult =
    hasSelectedDates && !isDateRangeInvalid ? availabilityResult : null

  // Effective availability & status label
  const isAvailable = useMemo(() => {
    if (isDateRangeInvalid) return false
    if (activeAvailabilityResult) return Boolean(activeAvailabilityResult.is_available)
    return Boolean(item?.stock > 0 && item?.is_available !== false)
  }, [isDateRangeInvalid, activeAvailabilityResult, item])

  const statusLabel = useMemo(() => {
    if (isDateRangeInvalid) return 'Invalid Dates'
    if (activeAvailabilityResult) {
      return activeAvailabilityResult.is_available ? 'Available' : 'Booked'
    }
    return item?.stock > 0 && item?.is_available !== false ? 'Available to Rent' : 'Booked'
  }, [isDateRangeInvalid, activeAvailabilityResult, item])

  // Calculation (difference in calendar days, return date not counted as extra rental day)
  const durationDays = useMemo(() => {
    return calculateRentalDuration(startDate, endDate)
  }, [startDate, endDate])

  const rentalPrice = item ? parseFloat(item.rental_price || 0) : 0

  // Handle Notify Me registration
  const handleNotifyMe = async () => {
    setNotifyError('')
    setNotifyMessage('')

    if (!startDate || !endDate) {
      setNotifyError('Please select start and end dates below to receive an availability alert.')
      return
    }
    if (endDate <= startDate) {
      setNotifyError('End date must be after start date.')
      return
    }

    const token = getAccessToken()
    if (!token) {
      const redirectUrl = `/items/${item?.id}?start_date=${startDate}&end_date=${endDate}`
      sessionStorage.setItem('rentbee_redirect_after_login', redirectUrl)
      navigate('/login')
      return
    }

    setNotifying(true)
    try {
      const res = await requestAvailabilityNotification(item.id, startDate, endDate)
      setNotifySuccess(true)
      setNotifyMessage(
        res?.message || 'You will be notified as soon as these dates become available.'
      )
    } catch (err) {
      setNotifyError(err.message || 'Failed to register notification request.')
    } finally {
      setNotifying(false)
    }
  }

  const ownerDetails = item?.owner_details || {}

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
        <Navbar />
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 w-full">
          {/* Breadcrumb Skeleton */}
          <div className="h-4 w-64 bg-orange-100/60 rounded animate-pulse mb-6" />

          {/* Two-Column Skeleton */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-7 space-y-4">
              <div className="h-96 w-full bg-orange-100/60 rounded-3xl animate-pulse" />
              <div className="flex gap-3">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="h-20 w-20 bg-orange-100/40 rounded-xl animate-pulse" />
                ))}
              </div>
            </div>
            <div className="lg:col-span-5 space-y-5">
              <div className="h-8 w-3/4 bg-orange-100/60 rounded animate-pulse" />
              <div className="h-4 w-1/3 bg-orange-100/40 rounded animate-pulse" />
              <div className="h-24 bg-white rounded-2xl border border-orange-100 p-4 animate-pulse" />
              <div className="h-32 bg-white rounded-2xl border border-orange-100 p-4 animate-pulse" />
            </div>
          </div>
        </main>
        <Footer />
      </div>
    )
  }

  if (error || !item) {
    return (
      <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
        <Navbar />
        <main className="mx-auto max-w-3xl px-4 py-16 text-center">
          <div className="rounded-3xl border border-orange-200 bg-white p-12 shadow-xs">
            <AlertCircle size={48} className="mx-auto text-orange-400 mb-3" />
            <h1 className="text-xl font-bold text-[#352720]">Item Not Found</h1>
            <p className="mt-2 text-sm text-gray-500">
              {error || 'This rental item does not exist or may have been unlisted by the owner.'}
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setLoading(true)
                  setReloadToken((t) => t + 1)
                }}
                className="inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition cursor-pointer"
              >
                <RefreshCw size={14} /> Retry
              </button>
              <Link
                to="/browse"
                className="inline-flex items-center gap-2 rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#352720] hover:bg-orange-50 transition"
              >
                Browse All Items
              </Link>
            </div>
          </div>
        </main>
        <Footer />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          {/* 1. Breadcrumb Navigation */}
          <nav aria-label="Breadcrumb" className="mb-6">
            <ol className="flex flex-wrap items-center gap-1.5 text-xs text-gray-500 font-medium">
              <li>
                <Link to="/" className="hover:text-[#D97745] transition">
                  Home
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              <li>
                <Link to="/browse" className="hover:text-[#D97745] transition">
                  Browse Items
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              {item.category_name && (
                <>
                  <li>
                    <Link
                      to={`/browse?category=${item.category_id}`}
                      className="hover:text-[#D97745] transition"
                    >
                      {item.category_name}
                    </Link>
                  </li>
                  <li>
                    <ChevronRight size={13} className="text-gray-400" />
                  </li>
                </>
              )}
              <li className="font-semibold text-[#352720] truncate max-w-xs sm:max-w-md">
                {item.name}
              </li>
            </ol>
          </nav>

          {/* 2. Main Two-Column Layout (Desktop) / Single-Column (Mobile) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 xl:gap-12">
            {/* Left Column: Image Gallery & Rental Kit */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              {/* Main Image Showcase */}
              <div className="relative group overflow-hidden rounded-3xl border border-orange-100 bg-white shadow-xs">
                <img
                  src={
                    selectedImage ||
                    'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=800'
                  }
                  alt={item.name}
                  className="w-full h-80 sm:h-[430px] object-cover bg-orange-50/50 transition duration-300 group-hover:scale-[1.01]"
                />

                {/* Lightbox Trigger Button */}
                <button
                  type="button"
                  onClick={() => setLightboxOpen(true)}
                  aria-label="View larger image"
                  className="absolute bottom-4 right-4 flex items-center gap-1.5 rounded-xl bg-white/90 backdrop-blur-xs px-3 py-1.5 text-xs font-semibold text-[#352720] shadow-sm hover:bg-white transition cursor-pointer"
                >
                  <Maximize2 size={13} />
                  <span>Enlarge</span>
                </button>

                {/* Availability Badge Overlay */}
                <div className="absolute top-4 left-4">
                  {isAvailable ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50/95 backdrop-blur-xs px-3 py-1 text-xs font-bold text-emerald-700 border border-emerald-200 shadow-xs">
                      ● Available
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100/95 backdrop-blur-xs px-3 py-1 text-xs font-bold text-[#D97745] border border-orange-200 shadow-xs">
                      ● Booked
                    </span>
                  )}
                </div>
              </div>

              {/* Thumbnails Row */}
              {allImages.length > 1 && (
                <div className="flex gap-3 overflow-x-auto pb-2 [scrollbar-width:thin] [scrollbar-color:#E58A62_transparent]">
                  {allImages.map((imgUrl, index) => {
                    const isSelected = selectedImage === imgUrl
                    return (
                      <button
                        key={index}
                        type="button"
                        onClick={() => setSelectedImage(imgUrl)}
                        aria-label={`View image thumbnail ${index + 1}`}
                        className={`h-20 w-20 shrink-0 overflow-hidden rounded-2xl border-2 transition cursor-pointer ${isSelected
                            ? 'border-[#D97745] shadow-xs scale-102 ring-2 ring-[#D97745]/20'
                            : 'border-orange-100 bg-white hover:border-orange-300 opacity-80 hover:opacity-100'
                          }`}
                      >
                        <img
                          src={imgUrl}
                          alt={`${item.name} thumbnail ${index + 1}`}
                          className="h-full w-full object-cover"
                        />
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Description Section */}
              <section className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                <h2 className="text-base font-bold text-[#352720] mb-3">About This Item</h2>
                <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
                  {item.description ? (
                    item.description
                  ) : (
                    <span className="italic text-gray-400">
                      No specific description provided by the lender. Contact them via booking for
                      additional specifications.
                    </span>
                  )}
                </div>
              </section>

              {/* Included in this Rental Kit Section */}
              {Array.isArray(item.rental_kit) && item.rental_kit.length > 0 && (
                <section className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                  <h2 className="text-base sm:text-lg font-bold text-[#352720] mb-4">
                    Included in this Rental Kit
                  </h2>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {item.rental_kit.map((accessory, idx) => {
                      const name = typeof accessory === 'string' ? accessory : accessory?.name || ''
                      return (
                        <div
                          key={idx}
                          className="rounded-2xl border border-orange-100/80 bg-[#FFFDFB] px-4 py-3 text-sm font-semibold text-[#352720] break-words"
                        >
                          {name}
                        </div>
                      )
                    })}
                  </div>
                </section>
              )}
            </div>

            {/* Right Column: Pricing, Specs, CTAs, Booking Dates, Owner */}
            <div className="lg:col-span-5 flex flex-col gap-6">
              {/* Main Info Card */}
              <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                {/* Category & Status */}
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-[#FFF0E7] px-3 py-1 text-xs font-semibold text-[#D97745]">
                    <span>{item.category_icon || '📦'}</span>
                    <span>{item.category_name}</span>
                  </span>

                  {isAvailable ? (
                    <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-bold text-emerald-700 border border-emerald-200">
                      ● {statusLabel}
                    </span>
                  ) : (
                    <span className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-bold text-[#D97745] border border-orange-200">
                      ● {statusLabel}
                    </span>
                  )}
                </div>

                {/* Item Name */}
                <h1 className="text-2xl sm:text-3xl font-black text-[#352720] leading-tight">
                  {item.name}
                </h1>

                {/* Pricing Box */}
                <div className="mt-5 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-4">
                  <div className="flex items-baseline justify-between">
                    <div>
                      <span className="text-3xl font-black text-[#9D4C29]">
                        ₹{item.rental_price}
                      </span>
                      <span className="text-xs text-gray-500 font-medium"> / day</span>
                    </div>

                    <div className="text-right">
                      <p className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">
                        Security Deposit
                      </p>
                      <p className="text-sm font-bold text-[#352720]">
                        ₹{item.deposit !== undefined && item.deposit !== null ? item.deposit : 0}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 pt-3 border-t border-orange-100/80 flex items-center justify-between text-xs text-gray-600">
                    <span>Stock available:</span>
                    <span className="font-bold text-[#352720]">{item.stock} item(s)</span>
                  </div>
                </div>

                {/* Rental Date Selection */}
                <div className="mt-4 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-[#352720]">
                      <Calendar size={14} className="text-[#D97745]" />
                      <span>Rental Dates</span>
                    </div>
                    {checkingAvailability && (
                      <span className="text-[11px] text-gray-500 animate-pulse">Checking availability...</span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-gray-600 mb-1">Start Date</label>
                      <input
                        type="date"
                        min={todayStr}
                        value={startDate}
                        onChange={(e) => {
                          setStartDate(e.target.value)
                          setAvailabilityResult(null)
                          setNotifySuccess(false)
                          setNotifyMessage('')
                          setNotifyError('')
                          if (endDate && e.target.value >= endDate) {
                            setEndDate(getNextDayStr(e.target.value))
                          }
                        }}
                        className="w-full rounded-xl border border-orange-200 bg-white px-3 py-1.5 text-xs text-[#352720] outline-none focus:border-[#D97745]"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-gray-600 mb-1">End Date</label>
                      <input
                        type="date"
                        min={getNextDayStr(startDate) || todayStr}
                        value={endDate}
                        onChange={(e) => {
                          setEndDate(e.target.value)
                          setAvailabilityResult(null)
                          setNotifySuccess(false)
                          setNotifyMessage('')
                          setNotifyError('')
                        }}
                        className="w-full rounded-xl border border-orange-200 bg-white px-3 py-1.5 text-xs text-[#352720] outline-none focus:border-[#D97745]"
                      />
                    </div>
                  </div>

                  {hasSelectedDates && !isDateRangeInvalid && (
                    <div className="mt-2.5 pt-2 border-t border-orange-100 flex items-center justify-between text-xs">
                      <span className="text-gray-500">
                        Duration: <strong className="text-[#352720]">{durationDays} day(s)</strong>
                      </span>
                      <span className="text-gray-500">
                        Estimated Total: <strong className="text-[#9D4C29]">₹{(rentalPrice * durationDays).toFixed(2)}</strong>
                      </span>
                    </div>
                  )}

                  {/* Availability Status Feedback */}
                  {activeAvailabilityResult && !activeAvailabilityResult.is_available && (
                    <div className="mt-2.5 rounded-xl bg-orange-100/70 border border-orange-200 p-2.5 text-xs text-[#7A4C32] flex items-start gap-2">
                      <AlertCircle size={15} className="text-[#D97745] shrink-0 mt-0.5" />
                      <div>
                        <p className="font-bold text-[#352720]">Booked for Selected Dates</p>
                        <p className="mt-0.5 text-gray-600">
                          {activeAvailabilityResult.message || 'This item is already booked or reserved for these dates. Click Notify Me below to get an alert when it opens up.'}
                        </p>
                      </div>
                    </div>
                  )}

                  {notifyError && (
                    <p className="mt-2 text-xs font-semibold text-rose-600 flex items-center gap-1.5">
                      <AlertCircle size={13} /> {notifyError}
                    </p>
                  )}

                  {notifySuccess && (
                    <div className="mt-2.5 rounded-xl bg-emerald-50 border border-emerald-200 p-2.5 text-xs text-emerald-800 flex items-start gap-2">
                      <CheckCircle2 size={15} className="text-emerald-600 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-bold text-emerald-900">Notification Request Registered!</p>
                        <p className="mt-0.5 text-emerald-700">
                          {notifyMessage || "We'll notify you as soon as these dates become available."}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* CTAs: Rent Now (if Available) OR Notify Me (if Booked) + Wishlist Button */}
                <div className="mt-6 flex items-center gap-3">
                  {isAvailable ? (
                    <Link
                      to={
                        hasSelectedDates
                          ? `/request-booking/${item.id}?start_date=${startDate}&end_date=${endDate}`
                          : `/request-booking/${item.id}`
                      }
                      className="flex items-center justify-center gap-2 flex-1 rounded-2xl bg-[#D97745] px-6 py-3.5 text-sm font-bold text-white shadow-md transition hover:bg-[#B85D32] active:scale-[0.99] cursor-pointer"
                    >
                      <Sparkles size={16} />
                      <span>Rent Now</span>
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={handleNotifyMe}
                      disabled={notifying || notifySuccess}
                      className="flex items-center justify-center gap-2 flex-1 rounded-2xl border border-orange-200 bg-[#FFF0E7] px-6 py-3.5 text-sm font-bold text-[#D97745] shadow-xs transition hover:bg-[#FFE3D1] active:scale-[0.99] cursor-pointer disabled:opacity-75 disabled:cursor-not-allowed"
                    >
                      <Bell size={16} />
                      <span>
                        {notifySuccess
                          ? 'Notification Request Registered'
                          : notifying
                            ? 'Registering...'
                            : 'Notify Me When Available'}
                      </span>
                    </button>
                  )}

                  <WishlistHeartButton
                    item={item}
                    size={18}
                    className="h-12 w-12 rounded-2xl border border-orange-200 bg-white"
                  />
                </div>

                {/* Trust Badges */}
                <div className="mt-5 pt-4 border-t border-orange-50 grid grid-cols-2 gap-3 text-[11px] text-gray-500">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={16} className="text-[#D97745] shrink-0" />
                    <span>Identity Verified Lender</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock size={16} className="text-[#D97745] shrink-0" />
                    <span>Flexible Rental Terms</span>
                  </div>
                </div>
              </div>

              {/* 4. Booking Information Section (Displayed when item is Booked / stock <= 0) */}
              {!isAvailable && (
                <section className="rounded-3xl border border-orange-200 bg-[#FFFDFB] p-6 shadow-xs">
                  <div className="flex items-center gap-2 text-[#D97745] mb-3">
                    <Calendar size={18} />
                    <h2 className="text-base font-bold text-[#352720]">Booking Schedule</h2>
                  </div>

                  {item.active_booking ? (
                    /* Actual booking data if supplied by backend */
                    <div className="space-y-3 rounded-2xl bg-white border border-orange-100 p-4 text-xs">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">Booking Start Date:</span>
                        <span className="font-semibold text-[#352720]">
                          {item.active_booking.start_date || 'In progress'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">Expected Return Date:</span>
                        <span className="font-semibold text-[#352720]">
                          {item.active_booking.expected_return_date || 'To be announced'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center pt-2 border-t border-orange-50">
                        <span className="text-gray-500">Total Duration:</span>
                        <span className="font-bold text-[#9D4C29]">
                          {item.active_booking.duration_days
                            ? `${item.active_booking.duration_days} days`
                            : 'Standard term'}
                        </span>
                      </div>
                    </div>
                  ) : (
                    /* Honest status explanation when no booking schedule timestamps are in the DB */
                    <div className="rounded-2xl bg-orange-50/70 border border-orange-200/80 p-4 text-xs text-[#49362D] leading-relaxed">
                      <div className="flex items-start gap-2">
                        <Info size={16} className="text-[#D97745] shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold text-[#352720]">
                            Item Currently Reserved
                          </p>
                          <p className="mt-1 text-gray-600">
                            This item is currently out on rental. Return confirmation and next
                            available reservation dates will be updated as soon as the lender verifies
                            return.
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  <p className="mt-3 text-[11px] text-gray-400 italic">
                    * Renter privacy is strictly protected. Personal identities and contact details are never disclosed.
                  </p>
                </section>
              )}

              {/* 5. Owner / Lender Information Card */}
              <section className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                <div className="flex items-center gap-2 text-[#D97745] mb-3">
                  <MapPin size={18} />
                  <h2 className="text-base font-bold text-[#352720]">Listed by Lender</h2>
                </div>

                <div className="rounded-2xl bg-[#FFFCF9] border border-orange-100 p-4 space-y-2.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">Owner Name:</span>
                    <span className="font-bold text-[#352720]">
                      {ownerDetails.name || item.owner_name || 'RentBee Member'}
                    </span>
                  </div>

                  {ownerDetails.locality && (
                    <div className="flex justify-between items-center">
                      <span className="text-gray-500">Locality:</span>
                      <span className="font-semibold text-[#352720]">
                        {ownerDetails.locality}
                      </span>
                    </div>
                  )}

                  {ownerDetails.nearest_location && (
                    <div className="flex justify-between items-center">
                      <span className="text-gray-500">Nearest Landmark:</span>
                      <span className="font-semibold text-[#352720]">
                        {ownerDetails.nearest_location}
                      </span>
                    </div>
                  )}

                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">General Area:</span>
                    <span className="font-semibold text-[#352720]">
                      {[ownerDetails.city, ownerDetails.state].filter(Boolean).join(', ') ||
                        'Verified Area'}
                    </span>
                  </div>
                </div>

                <p className="mt-3 text-[11px] text-gray-400 italic">
                  * Strict privacy policy: residential door numbers and direct contact details are kept private until booking is confirmed.
                </p>
              </section>
            </div>
          </div>

          {/* 3. RECOMMENDATION SECTIONS BELOW DETAILS */}
          <div className="mt-16 space-y-12 border-t border-orange-100 pt-12">
            {/* 3.1 Related Items (Same Category) */}
            {relatedItems.length > 0 && (
              <section aria-labelledby="related-heading">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 id="related-heading" className="text-xl font-bold text-[#352720]">
                      Related Items in {item.category_name}
                    </h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Other gear from this category that you might need.
                    </p>
                  </div>
                  <Link
                    to={`/browse?category=${item.category_id}`}
                    className="text-xs font-semibold text-[#9D4C29] hover:underline"
                  >
                    View Category →
                  </Link>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                  {relatedItems.map((rel) => (
                    <ItemRecommendationCard key={rel.id} item={rel} />
                  ))}
                </div>
              </section>
            )}

            {/* 3.2 More Items from This Owner */}
            {ownerItems.length > 0 && (
              <section aria-labelledby="owner-items-heading">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 id="owner-items-heading" className="text-xl font-bold text-[#352720]">
                      More Items from {ownerDetails.name || 'This Lender'}
                    </h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Explore other equipment available from the same lender.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                  {ownerItems.map((ownerItem) => (
                    <ItemRecommendationCard key={ownerItem.id} item={ownerItem} />
                  ))}
                </div>
              </section>
            )}

            {/* 3.3 You May Also Like (Deduplicated items) */}
            {alsoLikeItems.length > 0 && (
              <section aria-labelledby="also-like-heading">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 id="also-like-heading" className="text-xl font-bold text-[#352720]">
                      You May Also Like
                    </h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Popular gear borrowed by community members.
                    </p>
                  </div>
                  <Link
                    to="/browse"
                    className="text-xs font-semibold text-[#9D4C29] hover:underline"
                  >
                    Browse All →
                  </Link>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                  {alsoLikeItems.map((likedItem) => (
                    <ItemRecommendationCard key={likedItem.id} item={likedItem} />
                  ))}
                </div>
              </section>
            )}
          </div>
        </main>
      </div>

      {/* Lightbox Modal for Enlarge Image */}
      {lightboxOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4">
          <div className="relative max-w-4xl max-h-[90vh] w-full flex flex-col items-center">
            <button
              type="button"
              onClick={() => setLightboxOpen(false)}
              className="absolute -top-10 right-0 text-white hover:text-orange-300 transition p-1 cursor-pointer"
              aria-label="Close enlarged view"
            >
              <X size={26} />
            </button>
            <img
              src={selectedImage}
              alt={item.name}
              className="max-h-[82vh] w-auto max-w-full rounded-2xl object-contain shadow-2xl"
            />
            <p className="mt-3 text-xs text-white/80 font-medium">{item.name}</p>
          </div>
        </div>
      )}

      <Footer />
    </div>
  )
}

// Reusable recommendation card for Related Items, More from Owner, and You May Also Like
function ItemRecommendationCard({ item }) {
  const isAvailable = item?.is_available !== undefined ? item.is_available : (item?.stock ?? 0) > 0

  return (
    <article className="group flex flex-col justify-between overflow-hidden rounded-2xl border border-orange-100 bg-white shadow-xs transition duration-200 hover:-translate-y-1 hover:shadow-md">
      <div className="relative">
        <img
          src={
            item.primary_image_url ||
            'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600'
          }
          alt={item.name}
          loading="lazy"
          className="h-40 w-full object-cover bg-orange-50 transition duration-300 group-hover:scale-[1.02]"
        />

        <div className="absolute left-2.5 top-2.5">
          {isAvailable ? (
            <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200 shadow-xs">
              ● Available
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-bold text-[#D97745] border border-orange-200 shadow-xs">
              ● Booked
            </span>
          )}
        </div>

        <div className="absolute right-2.5 top-2.5">
          <WishlistHeartButton item={item} size={14} className="h-7 w-7" />
        </div>
      </div>

      <div className="p-3.5 flex flex-1 flex-col justify-between">
        <div>
          <h3 className="text-sm font-bold text-[#352720] line-clamp-1 group-hover:text-[#D97745] transition">
            {item.name}
          </h3>
          <p className="mt-1 text-[11px] text-gray-500">
            Deposit: ₹{item.deposit !== undefined && item.deposit !== null ? item.deposit : 0}
          </p>
        </div>

        <div className="mt-3 pt-2.5 border-t border-orange-50 flex items-center justify-between">
          <div>
            <span className="text-base font-black text-[#9D4C29]">₹{item.rental_price}</span>
            <span className="text-[10px] text-gray-500"> / day</span>
          </div>

          <Link
            to={`/items/${item.id}`}
            className="rounded-lg bg-[#9D4C29] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#813B20] transition"
          >
            View
          </Link>
        </div>
      </div>
    </article>
  )
}
