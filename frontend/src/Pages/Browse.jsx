import { useEffect, useState, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import WishlistHeartButton from '../Components/WishlistHeartButton'
import { getPublicItems, getPublicCategories } from '../services/api'
import { Search, X, Package, SlidersHorizontal, RefreshCw, AlertCircle, Bell, ArrowRight } from 'lucide-react'

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams()

  // Query parameter bindings
  const categoryParam = searchParams.get('category') || ''
  const searchParam = searchParams.get('search') || ''
  const minPriceParam = searchParams.get('min_price') || ''
  const maxPriceParam = searchParams.get('max_price') || ''
  const sortParam = searchParams.get('sort') || '-created_at'

  // Component states
  const [categories, setCategories] = useState([])
  const [items, setItems] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)

  // Local filter inputs
  const [searchInput, setSearchInput] = useState(searchParam)
  const [minPriceInput, setMinPriceInput] = useState(minPriceParam)
  const [maxPriceInput, setMaxPriceInput] = useState(maxPriceParam)
  const [priceError, setPriceError] = useState('')
  const [notifyModalItem, setNotifyModalItem] = useState(null)

  // Synchronize inputs with URL params during render (official React pattern without useEffect cascading renders)
  const [prevSearchParam, setPrevSearchParam] = useState(searchParam)
  if (prevSearchParam !== searchParam) {
    setPrevSearchParam(searchParam)
    setSearchInput(searchParam)
  }

  const [prevMinParam, setPrevMinParam] = useState(minPriceParam)
  const [prevMaxParam, setPrevMaxParam] = useState(maxPriceParam)
  if (prevMinParam !== minPriceParam || prevMaxParam !== maxPriceParam) {
    setPrevMinParam(minPriceParam)
    setPrevMaxParam(maxPriceParam)
    setMinPriceInput(minPriceParam)
    setMaxPriceInput(maxPriceParam)
  }

  // Load Categories on mount
  useEffect(() => {
    getPublicCategories()
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.results || []
        // Sanitize out any reserved sentinel categories
        setCategories(list.filter((c) => c.name.toLowerCase() !== 'all categories' && c.icon !== '▦'))
      })
      .catch((err) => {
        console.error('Failed to load categories:', err)
      })
  }, [])

  // Debounced search synchronization to URL
  const debounceTimerRef = useRef(null)
  const handleSearchChange = (e) => {
    const val = e.target.value
    setSearchInput(val)

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    debounceTimerRef.current = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (val.trim()) {
          next.set('search', val.trim())
        } else {
          next.delete('search')
        }
        return next
      })
    }, 350)
  }

  const handleClearSearch = () => {
    setSearchInput('')
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('search')
      return next
    })
  }

  // Handle Category selection
  const handleCategorySelect = (catId) => {
    const nextId = categoryParam === String(catId) ? '' : String(catId)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (nextId) {
        next.set('category', nextId)
      } else {
        next.delete('category')
      }
      return next
    })
  }

  // Handle Price Filter apply
  const handleApplyPriceFilter = (e) => {
    e?.preventDefault()
    setPriceError('')

    const minVal = minPriceInput.trim() ? parseFloat(minPriceInput) : null
    const maxVal = maxPriceInput.trim() ? parseFloat(maxPriceInput) : null

    if (minVal !== null && (isNaN(minVal) || minVal < 0)) {
      setPriceError('Min price must be a positive number.')
      return
    }
    if (maxVal !== null && (isNaN(maxVal) || maxVal < 0)) {
      setPriceError('Max price must be a positive number.')
      return
    }
    if (minVal !== null && maxVal !== null && minVal > maxVal) {
      setPriceError('Min price cannot exceed Max price.')
      return
    }

    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (minVal !== null) next.set('min_price', String(minVal))
      else next.delete('min_price')

      if (maxVal !== null) next.set('max_price', String(maxVal))
      else next.delete('max_price')
      return next
    })
  }

  // Handle Price Filter clear
  const handleClearPriceFilter = () => {
    setMinPriceInput('')
    setMaxPriceInput('')
    setPriceError('')
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('min_price')
      next.delete('max_price')
      return next
    })
  }

  // Handle Sorting change
  const handleSortChange = (newSort) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (newSort === '-created_at') {
        next.delete('sort')
      } else {
        next.set('sort', newSort)
      }
      return next
    })
  }

  // Reset all filters
  const handleClearAllFilters = () => {
    setSearchInput('')
    setMinPriceInput('')
    setMaxPriceInput('')
    setPriceError('')
    setSearchParams({})
  }

  // Reload trigger for retry button
  const [reloadToken, setReloadToken] = useState(0)

  // Fetch initial items whenever URL query parameters change
  useEffect(() => {
    let isCurrent = true

    getPublicItems({
      category: categoryParam,
      search: searchParam,
      min_price: minPriceParam,
      max_price: maxPriceParam,
      sort: sortParam,
      page: 1,
      page_size: 12,
    })
      .then((data) => {
        if (!isCurrent) return
        setItems(data.results || [])
        setTotalCount(data.count || 0)
        setTotalPages(data.total_pages || 1)
        setPage(1)
        setError(null)
        setLoading(false)
      })
      .catch((err) => {
        if (!isCurrent) return
        console.error('Failed to load items:', err)
        setError(err.message || 'Unable to load items. Please try again.')
        setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [categoryParam, searchParam, minPriceParam, maxPriceParam, sortParam, reloadToken])

  // Load More Handler (appends next page without duplicates)
  const handleLoadMore = async () => {
    if (loadingMore || page >= totalPages) return

    setLoadingMore(true)
    const nextPage = page + 1

    try {
      const data = await getPublicItems({
        category: categoryParam,
        search: searchParam,
        min_price: minPriceParam,
        max_price: maxPriceParam,
        sort: sortParam,
        page: nextPage,
        page_size: 12,
      })

      const newResults = data.results || []
      setItems((prevItems) => {
        const existingIds = new Set(prevItems.map((item) => item.id))
        const uniqueFresh = newResults.filter((item) => !existingIds.has(item.id))
        return [...prevItems, ...uniqueFresh]
      })

      setPage(nextPage)
      setTotalPages(data.total_pages || 1)
      setTotalCount(data.count || 0)
    } catch (err) {
      console.error('Failed to load more items:', err)
    } finally {
      setLoadingMore(false)
    }
  }

  const hasActiveFilters = Boolean(categoryParam || searchParam || minPriceParam || maxPriceParam)
  const hasMoreItems = page < totalPages && items.length < totalCount

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          {/* Header Title & Subtitle */}
          <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[#D97745]">
                RentBee Marketplace
              </p>
              <h1 className="mt-1 text-2xl font-black tracking-tight text-[#352720] sm:text-3xl">
                Browse Rental Items
              </h1>
              <p className="mt-1 text-xs text-gray-500 sm:text-sm">
                Explore quality gear, tools, and accessories available to borrow in your community.
              </p>
            </div>

            <div className="text-xs font-semibold text-gray-500">
              {loading ? (
                <span className="inline-block h-4 w-20 bg-orange-100/60 rounded animate-pulse" />
              ) : (
                <span>
                  Showing <strong className="text-[#352720]">{items.length}</strong> of{' '}
                  <strong className="text-[#352720]">{totalCount}</strong> items
                </span>
              )}
            </div>
          </div>

          {/* Search Bar */}
          <div className="mb-6">
            <div className="relative w-full max-w-2xl">
              <Search
                size={18}
                className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
              />
              <input
                type="text"
                value={searchInput}
                onChange={handleSearchChange}
                placeholder="Search items by name..."
                aria-label="Search items"
                className="w-full rounded-2xl border border-orange-200 bg-white pl-10 pr-10 py-3 text-sm text-[#352720] placeholder-gray-400 shadow-xs outline-none transition focus:border-[#D97745] focus:ring-2 focus:ring-[#D97745]/20"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  aria-label="Clear search"
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 transition rounded-full hover:bg-gray-100"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          </div>

          {/* Category Filter Section */}
          <section className="mb-6" aria-label="Categories">
            <div className="flex gap-2 overflow-x-auto pb-2 [scrollbar-width:thin] [scrollbar-color:#E58A62_transparent]">
              {/* All Categories Option */}
              <button
                type="button"
                onClick={() => handleCategorySelect('')}
                className={`flex shrink-0 items-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-semibold transition ${
                  !categoryParam
                    ? 'border-[#D97745] bg-[#FFF0E7] text-[#D97745] shadow-xs'
                    : 'border-orange-100 bg-white text-[#49362D] hover:bg-orange-50'
                }`}
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-orange-100/60 text-sm">
                  ▦
                </span>
                <span>All Categories</span>
              </button>

              {/* Individual Category Pills */}
              {categories.map((cat) => {
                const isSelected = categoryParam === String(cat.id)
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => handleCategorySelect(cat.id)}
                    className={`flex shrink-0 items-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-semibold transition ${
                      isSelected
                        ? 'border-[#D97745] bg-[#FFF0E7] text-[#D97745] shadow-xs'
                        : 'border-orange-100 bg-white text-[#49362D] hover:bg-orange-50'
                    }`}
                  >
                    <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-orange-100/60 text-sm">
                      {cat.icon || '📦'}
                    </span>
                    <span>{cat.name}</span>
                    {cat.items_count !== undefined && (
                      <span className="rounded-full bg-white/90 px-1.5 py-0.5 text-[10px] text-gray-500 font-medium">
                        {cat.items_count}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </section>

          {/* Controls Bar: Price Filter & Sorting */}
          <div className="mb-8 rounded-2xl border border-orange-100 bg-white p-4 shadow-xs">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              {/* Price Filter Controls */}
              <form onSubmit={handleApplyPriceFilter} className="flex flex-wrap items-center gap-2.5">
                <span className="text-xs font-bold text-[#352720] uppercase tracking-wider shrink-0">
                  Rental Price (₹/day):
                </span>

                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={minPriceInput}
                    onChange={(e) => {
                      setMinPriceInput(e.target.value)
                      setPriceError('')
                    }}
                    placeholder="Min"
                    aria-label="Minimum rental price"
                    className="w-24 rounded-xl border border-orange-200 bg-[#FFFCF9] px-3 py-1.5 text-xs text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745]"
                  />
                  <span className="text-xs text-gray-400 font-medium">—</span>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={maxPriceInput}
                    onChange={(e) => {
                      setMaxPriceInput(e.target.value)
                      setPriceError('')
                    }}
                    placeholder="Max"
                    aria-label="Maximum rental price"
                    className="w-24 rounded-xl border border-orange-200 bg-[#FFFCF9] px-3 py-1.5 text-xs text-[#352720] placeholder-gray-400 outline-none focus:border-[#D97745]"
                  />
                </div>

                <button
                  type="submit"
                  className="rounded-xl bg-[#D97745] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition shadow-xs cursor-pointer"
                >
                  Apply Filter
                </button>

                {(minPriceParam || maxPriceParam || minPriceInput || maxPriceInput) && (
                  <button
                    type="button"
                    onClick={handleClearPriceFilter}
                    className="rounded-xl border border-orange-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-orange-50 transition cursor-pointer"
                  >
                    Clear Filter
                  </button>
                )}

                {priceError && (
                  <span className="w-full text-xs text-red-600 font-medium flex items-center gap-1 mt-1">
                    <AlertCircle size={13} /> {priceError}
                  </span>
                )}
              </form>

              {/* Sorting Options (Exactly: Price: Low to High, Price: High to Low, Newest First) */}
              <div className="flex items-center gap-2 shrink-0">
                <SlidersHorizontal size={14} className="text-[#D97745]" />
                <label htmlFor="browse-sort" className="text-xs font-bold text-[#352720] uppercase tracking-wider">
                  Sort:
                </label>
                <select
                  id="browse-sort"
                  value={sortParam}
                  onChange={(e) => handleSortChange(e.target.value)}
                  className="rounded-xl border border-orange-200 bg-[#FFFCF9] px-3 py-1.5 text-xs font-semibold text-[#352720] outline-none transition focus:border-[#D97745] cursor-pointer"
                >
                  <option value="-created_at">Newest First</option>
                  <option value="rental_price">Price: Low to High</option>
                  <option value="-rental_price">Price: High to Low</option>
                </select>
              </div>
            </div>
          </div>

          {/* Content States */}
          {loading ? (
            /* Loading Skeletons */
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                <div
                  key={n}
                  className="h-96 rounded-2xl border border-orange-100 bg-white p-4 shadow-xs animate-pulse flex flex-col justify-between"
                >
                  <div className="h-48 w-full rounded-xl bg-orange-100/60" />
                  <div className="mt-4 space-y-2">
                    <div className="h-4 w-3/4 bg-orange-100/60 rounded" />
                    <div className="h-3 w-1/2 bg-orange-100/40 rounded" />
                  </div>
                  <div className="mt-4 border-t border-orange-50 pt-3 space-y-2">
                    <div className="h-4 w-1/3 bg-orange-100/60 rounded" />
                    <div className="h-9 w-full bg-orange-100/60 rounded-xl" />
                  </div>
                </div>
              ))}
            </div>
          ) : error ? (
            /* Error State with Retry */
            <div className="rounded-3xl border border-red-200 bg-white p-12 text-center shadow-xs">
              <AlertCircle size={44} className="mx-auto text-red-400 mb-3" />
              <h2 className="text-lg font-bold text-[#352720]">Unable to Load Items</h2>
              <p className="mt-1 text-sm text-gray-500 max-w-sm mx-auto">{error}</p>
              <button
                type="button"
                onClick={() => {
                  setLoading(true)
                  setReloadToken((t) => t + 1)
                }}
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition cursor-pointer"
              >
                <RefreshCw size={14} /> Retry
              </button>
            </div>
          ) : items.length === 0 ? (
            /* Empty State */
            <div className="rounded-3xl border border-dashed border-orange-200 bg-white p-16 text-center">
              <Package size={48} className="mx-auto text-orange-300 mb-3" />
              <h2 className="text-lg font-bold text-[#352720]">No Rental Items Found</h2>
              <p className="mt-1 text-sm text-gray-500 max-w-md mx-auto">
                {hasActiveFilters
                  ? 'No items matched your current filters. Try changing your search query, price range, or category.'
                  : 'There are currently no items published in the catalog. Check back soon!'}
              </p>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={handleClearAllFilters}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-5 py-2.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition cursor-pointer"
                >
                  Clear All Filters
                </button>
              )}
            </div>
          ) : (
            /* Item Cards Grid */
            <div>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {items.map((item) => {
                  const isAvailable = item.stock > 0

                  return (
                    <article
                      key={item.id}
                      className="group flex flex-col justify-between overflow-hidden rounded-2xl border border-orange-100 bg-white shadow-xs transition duration-200 hover:-translate-y-1 hover:shadow-md"
                    >
                      {/* Image & Availability Badge */}
                      <div className="relative">
                        <img
                          src={
                            item.primary_image_url ||
                            'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600'
                          }
                          alt={item.name}
                          loading="lazy"
                          className="h-48 w-full object-cover bg-orange-50 transition duration-300 group-hover:scale-[1.02]"
                        />

                        {/* Status Badge (Green Available / Orange Booked) */}
                        <div className="absolute left-3 top-3">
                          {isAvailable ? (
                            <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 border border-emerald-200 shadow-xs backdrop-blur-xs">
                              ● Available
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full bg-orange-100 px-2.5 py-0.5 text-[11px] font-bold text-[#D97745] border border-orange-200 shadow-xs backdrop-blur-xs">
                              ● Booked
                            </span>
                          )}
                        </div>

                        {/* Wishlist Heart Button */}
                        <div className="absolute right-3 top-3">
                          <WishlistHeartButton item={item} />
                        </div>
                      </div>

                      {/* Card Content (Category name intentionally excluded from card body per requirement) */}
                      <div className="flex flex-1 flex-col justify-between p-4">
                        <div>
                          <h2 className="text-base font-bold text-[#352720] line-clamp-1 group-hover:text-[#D97745] transition">
                            {item.name}
                          </h2>
                          <div className="mt-1 flex items-center justify-between text-xs text-gray-500">
                            <span className="font-medium">
                              Stock: <span className="font-bold text-[#352720]">{item.stock}</span>
                            </span>
                            <span>
                              Deposit:{' '}
                              <span className="font-semibold text-[#352720]">
                                ₹{item.deposit !== undefined && item.deposit !== null ? item.deposit : 0}
                              </span>
                            </span>
                          </div>
                        </div>

                        {/* Price & Actions */}
                        <div className="mt-4 border-t border-orange-50 pt-3">
                          <div className="flex items-baseline justify-between mb-3">
                            <div>
                              <span className="text-xl font-black text-[#9D4C29]">
                                ₹{item.rental_price}
                              </span>
                              <span className="text-xs text-gray-500 font-medium"> / day</span>
                            </div>
                          </div>

                          <div className="flex flex-col gap-2">
                            {/* View Details Button */}
                            <Link
                              to={`/items/${item.id}`}
                              className="flex items-center justify-center gap-1.5 w-full rounded-xl bg-[#9D4C29] px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-[#813B20] text-center"
                            >
                              <span>View Details</span>
                              <ArrowRight size={13} />
                            </Link>

                            {/* Notify Me Button (when booked / out of stock) */}
                            {!isAvailable && (
                              <button
                                type="button"
                                onClick={() => setNotifyModalItem(item)}
                                className="flex items-center justify-center gap-1.5 w-full rounded-xl border border-orange-200 bg-[#FFF0E7] px-4 py-2 text-xs font-semibold text-[#D97745] transition hover:bg-[#FFE3D1] cursor-pointer"
                              >
                                <Bell size={13} />
                                <span>Notify Me</span>
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>

              {/* Load More Pagination */}
              {hasMoreItems && (
                <div className="mt-12 text-center">
                  <button
                    type="button"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="inline-flex items-center gap-2 rounded-2xl bg-[#D97745] px-8 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-[#B85D32] disabled:opacity-50 cursor-pointer"
                  >
                    {loadingMore ? (
                      <>
                        <RefreshCw size={16} className="animate-spin" />
                        <span>Loading more items...</span>
                      </>
                    ) : (
                      <>
                        <span>Load More Items</span>
                        <span className="text-xs font-normal opacity-90">
                          ({items.length} of {totalCount})
                        </span>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </main>
      </div>

      {/* Notify Me Dependency Modal (Honest transparent notice, no fake success) */}
      {notifyModalItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl border border-orange-100">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5 text-[#D97745]">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-orange-100">
                  <Bell size={18} />
                </div>
                <h2 className="text-base font-bold text-[#352720]">Notify When Available</h2>
              </div>
              <button
                type="button"
                onClick={() => setNotifyModalItem(null)}
                className="text-gray-400 hover:text-gray-600 p-1 cursor-pointer"
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-4">
              <p className="text-xs font-semibold text-[#D97745] uppercase tracking-wider">
                {notifyModalItem.name}
              </p>
              <div className="mt-3 rounded-xl bg-amber-50 border border-amber-200 p-3.5 text-xs text-amber-900 leading-relaxed">
                <strong>Pending Backend Feature:</strong>
                <p className="mt-1 text-amber-800">
                  The automated notification subscription service and lender return-confirmation
                  triggers are pending backend integration. You will be able to subscribe to email
                  and in-app alerts once the notification engine is connected!
                </p>
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setNotifyModalItem(null)}
                className="rounded-xl bg-[#352720] px-4 py-2 text-xs font-semibold text-white hover:bg-black transition cursor-pointer"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  )
}
