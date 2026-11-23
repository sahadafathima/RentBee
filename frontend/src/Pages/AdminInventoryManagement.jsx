import { useEffect, useState } from 'react'
import AdminLayout from '../Components/AdminLayout'
import { getAdminInventory, updateAdminStock } from '../services/api'
import { getItemImageUrl } from '../utils/imageUrl'
import {
  Package,
  CheckCircle2,
  AlertTriangle,
  Search,
  RefreshCw,
  Edit3,
  ChevronLeft,
  ChevronRight,
  X,
  ShieldAlert,
  Boxes,
  Lock,
} from 'lucide-react'

export default function AdminInventoryManagement() {
  const [items, setItems] = useState([])
  const [metrics, setMetrics] = useState({
    total_items: 0,
    total_stock: 0,
    reserved_units: 0,
    available_units: 0,
  })
  const [categories, setCategories] = useState([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [successToast, setSuccessToast] = useState('')

  // Filters & Search
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [stockStatusFilter, setStockStatusFilter] = useState('all')
  const [sort, setSort] = useState('-created_at')

  // Edit Stock Modal State
  const [editingItem, setEditingItem] = useState(null)
  const [newStockInput, setNewStockInput] = useState('')
  const [updating, setUpdating] = useState(false)
  const [modalError, setModalError] = useState('')

  const notify = (msg) => {
    setSuccessToast(msg)
    setTimeout(() => setSuccessToast(''), 4000)
  }

  const [refreshKey, setRefreshKey] = useState(0)

  // Reset loading and error states during render when request parameters change
  const currentRequestKey = `${page}|${appliedSearch}|${categoryFilter}|${stockStatusFilter}|${sort}|${refreshKey}`
  const [prevRequestKey, setPrevRequestKey] = useState(currentRequestKey)

  if (currentRequestKey !== prevRequestKey) {
    setPrevRequestKey(currentRequestKey)
    setLoading(true)
    setError('')
  }

  // Fetch Inventory with cancellation guard to prevent race conditions and cascading renders
  useEffect(() => {
    let isCurrent = true
    const params = {
      page,
      page_size: 10,
      search: appliedSearch,
      category: categoryFilter,
      stock_status: stockStatusFilter,
      sort: sort,
    }

    getAdminInventory(params)
      .then((data) => {
        if (!isCurrent) return
        setItems(data.results || [])
        setTotalPages(data.total_pages || 1)
        setTotalCount(data.count || 0)
        if (data.page && data.page !== page) {
          setPage(data.page)
        }
        if (data.metrics) {
          setMetrics(data.metrics)
        }
        if (data.categories) {
          setCategories(data.categories)
        }
        setError('')
      })
      .catch((err) => {
        if (!isCurrent) return
        setError(err.message || 'Failed to fetch inventory data.')
      })
      .finally(() => {
        if (isCurrent) {
          setLoading(false)
        }
      })

    return () => {
      isCurrent = false
    }
  }, [appliedSearch, categoryFilter, stockStatusFilter, sort, page, refreshKey])

  const handleRefresh = () => {
    setLoading(true)
    setRefreshKey((k) => k + 1)
  }

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    setPage(1)
    setAppliedSearch(search.trim())
  }

  const handleClearFilters = () => {
    setSearch('')
    setAppliedSearch('')
    setCategoryFilter('')
    setStockStatusFilter('all')
    setSort('-created_at')
    setPage(1)
  }

  // Open Edit Stock Modal
  const openEditModal = (item) => {
    setEditingItem(item)
    setNewStockInput(item.total_stock.toString())
    setModalError('')
  }

  const closeEditModal = () => {
    setEditingItem(null)
    setNewStockInput('')
    setModalError('')
    setUpdating(false)
  }

  // Submit Stock Update
  const handleStockUpdateSubmit = async (e) => {
    e.preventDefault()
    if (!editingItem) return

    const parsedVal = parseInt(newStockInput, 10)
    if (isNaN(parsedVal) || parsedVal < 0) {
      setModalError('Stock quantity must be a non-negative whole number (0 or higher).')
      return
    }

    // Quick client-side check for Safeguard 4 (backend also strictly enforces atomically)
    if (parsedVal < editingItem.reserved_stock) {
      setModalError(
        `Cannot reduce stock below active reservations (${editingItem.reserved_stock} units currently reserved). Minimum allowed stock is ${editingItem.reserved_stock}.`
      )
      return
    }

    setUpdating(true)
    setModalError('')
    try {
      const res = await updateAdminStock(editingItem.id, parsedVal)
      notify(res.message || `Stock for "${editingItem.name}" updated to ${parsedVal}.`)
      closeEditModal()
      handleRefresh()
    } catch (err) {
      setModalError(err.message || 'Failed to update stock.')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <AdminLayout
      pageTitle="Inventory & Stock Management"
      breadcrumbs={['Admin Panel', 'Catalog', 'Inventory Management']}
    >
      <div className="w-full text-[#302820]">
        {/* Toast Notification */}
        {successToast && (
          <div className="mb-4 flex items-center justify-between rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-800 shadow-sm animate-fade-in">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
              <span>{successToast}</span>
            </div>
            <button
              onClick={() => setSuccessToast('')}
              className="text-emerald-600 hover:text-emerald-800 cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="mb-4 flex items-center justify-between rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-800 shadow-sm">
            <div className="flex items-center gap-2">
              <AlertTriangle size={18} className="text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => setError('')}
              className="text-rose-600 hover:text-rose-800 cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Page Header */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Inventory & Stock Management</h1>
            <p className="mt-1 text-sm text-gray-500">
              Track stock levels, monitor active reservations, and safely adjust available quantities with Safeguard 4 active booking protection.
            </p>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition shadow-xs cursor-pointer shrink-0 disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh Fleet
          </button>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Items</p>
              <h3 className="text-2xl font-bold mt-1 text-[#302820]">{metrics.total_items}</h3>
              <p className="text-xs text-gray-500 mt-1">Catalog listings</p>
            </div>
            <div className="w-12 h-12 rounded-xl bg-[#FAF6F0] flex items-center justify-center text-[#9D4C29]">
              <Package size={24} />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Units (Fleet)</p>
              <h3 className="text-2xl font-bold mt-1 text-[#302820]">{metrics.total_stock}</h3>
              <p className="text-xs text-gray-500 mt-1">Physical stock quantity</p>
            </div>
            <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600">
              <Boxes size={24} />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Active Reservations</p>
              <h3 className="text-2xl font-bold mt-1 text-amber-700">{metrics.reserved_units}</h3>
              <p className="text-xs text-gray-500 mt-1">Committed to active rentals</p>
            </div>
            <div className="w-12 h-12 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600">
              <Lock size={24} />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Available For Rent</p>
              <h3 className="text-2xl font-bold mt-1 text-emerald-700">{metrics.available_units}</h3>
              <p className="text-xs text-gray-500 mt-1">Ready for instant request</p>
            </div>
            <div className="w-12 h-12 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600">
              <CheckCircle2 size={24} />
            </div>
          </div>
        </div>

        {/* Search & Filters Card */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-xs">
          <form onSubmit={handleSearchSubmit} className="flex flex-col md:flex-row gap-3">
            <div className="relative flex-1">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search by item name, owner name/email, category..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#9D4C29] focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              className="bg-[#9D4C29] hover:bg-[#813d21] text-white px-5 py-2 rounded-lg text-sm font-medium transition cursor-pointer shrink-0"
            >
              Search
            </button>
          </form>

          {/* Secondary Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4 pt-3 border-t border-gray-100">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Stock Status</label>
              <select
                value={stockStatusFilter}
                onChange={(e) => {
                  setStockStatusFilter(e.target.value)
                  setPage(1)
                }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-[#9D4C29]"
              >
                <option value="all">All Stock Statuses</option>
                <option value="in_stock">In Stock (&gt; 2)</option>
                <option value="low_stock">Low Stock (1 - 2)</option>
                <option value="out_of_stock">Out of Stock (0)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Category</label>
              <select
                value={categoryFilter}
                onChange={(e) => {
                  setCategoryFilter(e.target.value)
                  setPage(1)
                }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-[#9D4C29]"
              >
                <option value="">All Categories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Sort By</label>
              <select
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value)
                  setPage(1)
                }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-[#9D4C29]"
              >
                <option value="-created_at">Newest First</option>
                <option value="created_at">Oldest First</option>
                <option value="-stock">Highest Total Stock</option>
                <option value="stock">Lowest Total Stock</option>
                <option value="-rental_price">Rental Price: High to Low</option>
                <option value="rental_price">Rental Price: Low to High</option>
              </select>
            </div>
          </div>

          {(appliedSearch || categoryFilter || stockStatusFilter !== 'all' || sort !== '-created_at') && (
            <div className="mt-3 flex items-center justify-end">
              <button
                type="button"
                onClick={handleClearFilters}
                className="text-xs text-[#9D4C29] hover:underline font-medium cursor-pointer"
              >
                Clear all filters
              </button>
            </div>
          )}
        </div>

        {/* Inventory Table Card */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-xs">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-base font-bold text-[#302820]">
              Inventory Fleet ({totalCount} items)
            </h2>
            <div className="text-xs text-gray-500">
              Page {page} of {totalPages}
            </div>
          </div>

          {loading ? (
            <div className="p-12 text-center text-gray-400">
              <RefreshCw className="w-8 h-8 mx-auto animate-spin text-[#9D4C29] mb-3" />
              <p className="text-sm">Loading inventory fleet...</p>
            </div>
          ) : items.length === 0 ? (
            <div className="p-12 text-center text-gray-400">
              <Package className="w-12 h-12 mx-auto text-gray-300 mb-3" />
              <p className="text-base font-semibold text-gray-700">No inventory items found</p>
              <p className="text-xs text-gray-500 mt-1">
                Try adjusting your search terms or filter settings.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#FAF6F0] text-gray-700 text-xs font-semibold uppercase tracking-wider border-b border-gray-200">
                  <tr>
                    <th className="px-6 py-3.5">Item & Category</th>
                    <th className="px-6 py-3.5">Owner / Host</th>
                    <th className="px-6 py-3.5">Rates (₹)</th>
                    <th className="px-6 py-3.5 text-center">Total Fleet</th>
                    <th className="px-6 py-3.5 text-center">Active Reserved</th>
                    <th className="px-6 py-3.5 text-center">Available Units</th>
                    <th className="px-6 py-3.5 text-center">Status</th>
                    <th className="px-6 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {items.map((item) => {
                    const isOutOfStock = item.total_stock === 0 || item.available_stock <= 0
                    const isLowStock = !isOutOfStock && item.available_stock <= 2

                    return (
                      <tr key={item.id} className="hover:bg-gray-50 transition">
                        {/* Item & Category */}
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            {/* Item Image with Fallback Placeholder */}
                            <div className="w-12 h-12 rounded-lg bg-orange-50 overflow-hidden shrink-0 border border-orange-100 flex items-center justify-center">
                              {getItemImageUrl(item) ? (
                                <img
                                  src={getItemImageUrl(item)}
                                  alt={item.name}
                                  className="w-full h-full object-cover"
                                  onError={(e) => {
                                    e.currentTarget.style.display = 'none'
                                    if (e.currentTarget.nextElementSibling) {
                                      e.currentTarget.nextElementSibling.style.display = 'flex'
                                    }
                                  }}
                                />
                              ) : null}
                              <div
                                style={{ display: getItemImageUrl(item) ? 'none' : 'flex' }}
                                className="w-full h-full items-center justify-center text-orange-300"
                              >
                                <Package size={20} />
                              </div>
                            </div>
                            <div className="min-w-0">
                              <p className="font-semibold text-gray-900 truncate max-w-xs">{item.name}</p>
                              <div className="flex items-center gap-2 mt-1">
                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-[#9D4C29] border border-amber-200">
                                  {item.category_name || item.category || 'General'}
                                </span>
                                <span className="text-xs text-gray-400">ID #{item.id}</span>
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Owner */}
                        <td className="px-6 py-4">
                          <div>
                            {(() => {
                              const ownerObj = typeof item.owner === 'object' && item.owner !== null ? item.owner : null
                              const ownerName = ownerObj?.full_name || item.owner_name
                              const ownerEmail = ownerObj?.email || item.owner_email
                              const ownerPhone = ownerObj?.phone || ownerObj?.phone_number || item.owner_phone

                              if (!ownerName && !ownerEmail) {
                                return (
                                  <p className="text-xs italic text-gray-400">
                                    Owner information unavailable
                                  </p>
                                )
                              }

                              return (
                                <>
                                  <p className="font-medium text-gray-900">
                                    {ownerName || 'Owner information unavailable'}
                                  </p>
                                  {ownerEmail && (
                                    <p className="text-xs text-gray-500">{ownerEmail}</p>
                                  )}
                                  {ownerPhone && (
                                    <p className="text-xs text-gray-400">{ownerPhone}</p>
                                  )}
                                </>
                              )
                            })()}
                          </div>
                        </td>

                        {/* Rates */}
                        <td className="px-6 py-4">
                          <div className="text-xs">
                            {(() => {
                              const priceVal = item.rental_price ?? item.price_per_day
                              const depositVal = item.deposit ?? item.security_deposit
                              const hasPrice = priceVal !== null && priceVal !== undefined && priceVal !== ''
                              const hasDeposit = depositVal !== null && depositVal !== undefined && depositVal !== ''

                              return (
                                <>
                                  <div className="font-semibold text-gray-900">
                                    {hasPrice ? `₹${priceVal}/day` : <span className="text-gray-400 font-normal">Rate: Not set</span>}
                                  </div>
                                  <div className="text-gray-500 mt-0.5">
                                    {hasDeposit ? `Deposit: ₹${depositVal}` : <span className="text-gray-400 font-normal">Deposit: Not set</span>}
                                  </div>
                                </>
                              )
                            })()}
                          </div>
                        </td>

                        {/* Total Fleet */}
                        <td className="px-6 py-4 text-center">
                          <span className="inline-flex items-center justify-center font-bold text-gray-900 text-sm px-2.5 py-1 rounded bg-gray-100">
                            {item.total_stock}
                          </span>
                        </td>

                        {/* Active Reserved */}
                        <td className="px-6 py-4 text-center">
                          {item.reserved_stock > 0 ? (
                            <span className="inline-flex items-center gap-1 font-semibold text-amber-700 text-xs px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200">
                              <Lock size={12} />
                              {item.reserved_stock} reserved
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400">0 reserved</span>
                          )}
                        </td>

                        {/* Available Units */}
                        <td className="px-6 py-4 text-center">
                          <span
                            className={`inline-flex items-center justify-center font-bold text-sm px-3 py-1 rounded-full ${
                              isOutOfStock
                                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                : isLowStock
                                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            }`}
                          >
                            {item.available_stock}
                          </span>
                        </td>

                        {/* Availability Status Badge */}
                        <td className="px-6 py-4 text-center">
                          {isOutOfStock ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800">
                              Out of Stock
                            </span>
                          ) : isLowStock ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
                              Low Stock ({item.available_stock} left)
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                              In Stock
                            </span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="px-6 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => openEditModal(item)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#9D4C29] text-[#9D4C29] hover:bg-[#FAF6F0] font-medium text-xs transition cursor-pointer shadow-2xs"
                          >
                            <Edit3 size={14} />
                            Edit Stock
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {!loading && items.length > 0 && totalPages > 1 && (
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
              <span className="text-xs text-gray-500">
                Showing {items.length} of {totalCount} items
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(p - 1, 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center gap-1"
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <span className="text-xs text-gray-700 font-semibold px-2">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center gap-1"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Safeguard 4 Explanation Note */}
        <div className="mt-6 rounded-xl bg-amber-50 border border-amber-200 p-4 text-xs text-amber-900 flex items-start gap-3">
          <ShieldAlert size={20} className="text-amber-700 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">Safeguard 4 Active Reservation Protection:</span> Total fleet stock cannot be reduced below the quantity already committed to active bookings (approved, paid, or currently in progress). Stock reductions are validated atomically by the backend to prevent overbooking and double-allocation.
          </div>
        </div>

        {/* Edit Stock Modal */}
        {editingItem && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-fade-in">
            <div className="bg-white rounded-2xl max-w-md w-full shadow-xl border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-[#FAF6F0]">
                <div className="flex items-center gap-2">
                  <Edit3 size={18} className="text-[#9D4C29]" />
                  <h3 className="font-bold text-gray-900">Update Stock Quantity</h3>
                </div>
                <button
                  type="button"
                  onClick={closeEditModal}
                  className="text-gray-400 hover:text-gray-600 cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleStockUpdateSubmit} className="p-6">
                {/* Item Details */}
                <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl mb-4 border border-gray-200">
                  {/* Modal Item Image with Fallback Placeholder */}
                  <div className="w-12 h-12 rounded-lg bg-orange-50 overflow-hidden shrink-0 border border-orange-100 flex items-center justify-center">
                    {getItemImageUrl(editingItem) ? (
                      <img
                        src={getItemImageUrl(editingItem)}
                        alt={editingItem.name}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none'
                          if (e.currentTarget.nextElementSibling) {
                            e.currentTarget.nextElementSibling.style.display = 'flex'
                          }
                        }}
                      />
                    ) : null}
                    <div
                      style={{ display: getItemImageUrl(editingItem) ? 'none' : 'flex' }}
                      className="w-full h-full items-center justify-center text-orange-300"
                    >
                      <Package size={20} />
                    </div>
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-900 text-sm truncate">{editingItem.name}</p>
                    <p className="text-xs text-gray-500">ID #{editingItem.id} • {editingItem.category_name || editingItem.category}</p>
                  </div>
                </div>

                {/* Stock Stats Grid */}
                <div className="grid grid-cols-3 gap-2 mb-4 text-center">
                  <div className="p-2.5 rounded-lg bg-gray-100 border border-gray-200">
                    <span className="block text-[11px] font-medium text-gray-500 uppercase">Current Fleet</span>
                    <span className="block text-lg font-bold text-gray-800">{editingItem.total_stock}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200">
                    <span className="block text-[11px] font-medium text-amber-700 uppercase">Reserved</span>
                    <span className="block text-lg font-bold text-amber-800">{editingItem.reserved_stock}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200">
                    <span className="block text-[11px] font-medium text-emerald-700 uppercase">Available</span>
                    <span className="block text-lg font-bold text-emerald-800">{editingItem.available_stock}</span>
                  </div>
                </div>

                {/* Modal Error */}
                {modalError && (
                  <div className="mb-4 rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800 flex items-start gap-2">
                    <AlertTriangle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                    <span>{modalError}</span>
                  </div>
                )}

                {/* Stock Input */}
                <div className="mb-4">
                  <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1.5">
                    New Total Stock Quantity
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={newStockInput}
                    onChange={(e) => setNewStockInput(e.target.value)}
                    className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-base font-semibold focus:outline-none focus:ring-2 focus:ring-[#9D4C29] focus:border-transparent"
                    placeholder="e.g. 5"
                    required
                  />
                  <p className="mt-1.5 text-xs text-gray-500">
                    Minimum allowed total stock: <span className="font-bold text-gray-700">{editingItem.reserved_stock} units</span> (due to {editingItem.reserved_stock} active booking reservation{editingItem.reserved_stock === 1 ? '' : 's'}).
                  </p>
                </div>

                {/* Preview Calculation */}
                {newStockInput !== '' && !isNaN(parseInt(newStockInput, 10)) && (
                  <div className="mb-5 p-3 rounded-lg bg-[#FAF6F0] border border-amber-200 text-xs text-gray-700">
                    <div className="flex justify-between py-0.5">
                      <span>New Total Stock:</span>
                      <span className="font-bold text-gray-900">{parseInt(newStockInput, 10)}</span>
                    </div>
                    <div className="flex justify-between py-0.5">
                      <span>Active Reserved Units:</span>
                      <span className="font-bold text-amber-700">- {editingItem.reserved_stock}</span>
                    </div>
                    <div className="flex justify-between py-1 border-t border-amber-200 mt-1 font-semibold text-sm">
                      <span>Resulting Available Stock:</span>
                      <span className={parseInt(newStockInput, 10) - editingItem.reserved_stock < 0 ? 'text-rose-600' : 'text-emerald-700'}>
                        {parseInt(newStockInput, 10) - editingItem.reserved_stock} units
                      </span>
                    </div>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex items-center justify-end gap-3 pt-2 border-t border-gray-100">
                  <button
                    type="button"
                    onClick={closeEditModal}
                    disabled={updating}
                    className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition cursor-pointer disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={updating}
                    className="flex items-center gap-2 px-5 py-2 bg-[#9D4C29] hover:bg-[#813d21] text-white rounded-lg text-sm font-semibold transition cursor-pointer shadow-xs disabled:opacity-50"
                  >
                    {updating ? (
                      <>
                        <RefreshCw size={14} className="animate-spin" />
                        Saving...
                      </>
                    ) : (
                      'Save Changes'
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}

