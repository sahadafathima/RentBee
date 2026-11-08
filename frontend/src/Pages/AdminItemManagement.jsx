import { useEffect, useState, useRef } from 'react'
import AdminLayout from '../Components/AdminLayout'
import { getAdminItems, createAdminItem, updateAdminItem, softDeleteAdminItem, getAdminCategories } from '../services/api'
import { getCategoryIcon } from './AdminCategoryManagement'
import { Plus, Search, X, Eye, Pencil, Trash2, Upload, Star } from 'lucide-react'

export default function AdminItemManagement() {
  const [items, setItems] = useState([])
  // filterCategories: all non-deleted (active + inactive) — used in the listing filter dropdown
  const [filterCategories, setFilterCategories] = useState([])
  // formCategories: only active non-deleted — used in the Add/Edit item form
  const [formCategories, setFormCategories] = useState([])
  const [stats, setStats] = useState({ total: 0, published: 0, unpublished: 0, deleted: 0 })
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sort, setSort] = useState('-created_at')
  const [toast, setToast] = useState('')
  const [modal, setModal] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [modalError, setModalError] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  const notify = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3500) }

  const loadCategories = () => {
    // Filter out any DB category that might be named "All Categories" or uses the reserved ▦ icon
    const sanitize = (list) => list.filter(
      (c) => c.name.toLowerCase() !== 'all categories' && c.icon !== '▦'
    )
    // Fetch all non-deleted categories for the listing filter (admin can filter by inactive too)
    getAdminCategories().then((res) => setFilterCategories(sanitize(res.results || []))).catch(() => {})
    // Fetch only active categories for the Add/Edit form (backend also enforces this)
    getAdminCategories({ status: 'active' }).then((res) => setFormCategories(sanitize(res.results || []))).catch(() => {})
  }

  useEffect(() => {
    loadCategories()
  }, [])

  useEffect(() => {
    let isCurrent = true
    getAdminItems({ search, category: categoryFilter, status: statusFilter, sort, page, page_size: 8 })
      .then((data) => {
        if (!isCurrent) return
        setItems(data.results || [])
        setTotalPages(data.total_pages || 1)
        setTotalCount(data.count || 0)
        if (data.stats) setStats(data.stats)
      })
      .catch((err) => {
        if (!isCurrent) return
        notify(err.message || 'Failed to load items.')
      })
      .finally(() => {
        if (isCurrent) setLoading(false)
      })
    return () => {
      isCurrent = false
    }
  }, [search, categoryFilter, statusFilter, sort, page, reloadToken])

  const handleSave = async (formData, id) => {
    setSubmitting(true); setModalError('')
    try {
      if (modal.mode === 'add') { await createAdminItem(formData); notify('Item created successfully.') }
      else if (modal.mode === 'edit') { await updateAdminItem(id, formData); notify('Item updated successfully.') }
      else if (modal.mode === 'delete') { await softDeleteAdminItem(modal.item.id); notify(`Item "${modal.item.name}" soft-deleted.`) }
      setModal(null)
      setReloadToken((t) => t + 1)
      loadCategories()
      window.dispatchEvent(new CustomEvent('rentbee:items_changed'))
    } catch (err) {
      setModalError(err.message || 'Operation failed.'); notify(err.message || 'Error occurred.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AdminLayout pageTitle="Item Management" breadcrumbs={['Admin Panel', 'Catalog', 'Item Management']}>
      <div className="w-full text-[#302820]">
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Item Management</h1>
            <p className="mt-1 text-sm text-gray-500">Manage, inspect, publish, and track rental inventory and equipment.</p>
          </div>
          <button type="button" onClick={() => { setModalError(''); setModal({ mode: 'add' }) }} className="flex items-center gap-2 rounded-lg bg-[#9D4C29] px-5 py-2.5 font-medium text-white hover:bg-[#813d21] transition shadow-xs cursor-pointer shrink-0">
            <Plus size={18} /> Add Item
          </button>
        </div>

        {/* 4 Statistics Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Total Items', val: stats.total, sub: 'All non-deleted' },
            { label: 'Published', val: stats.published, sub: 'Live in catalog' },
            { label: 'Unpublished', val: stats.unpublished, sub: 'Hidden from users' },
            { label: 'Soft Deleted', val: stats.deleted, sub: 'Archived records' },
          ].map((m) => (
            <div key={m.label} className="rounded-lg border border-[#eee3da] bg-white px-5 py-3.5">
              <p className="text-sm text-gray-500">{m.label}</p>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold text-[#302820]">{m.val}</span>
                <span className="text-xs text-gray-400">{m.sub}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Search & Filters */}
        <div className="mb-5 flex flex-col lg:flex-row gap-3 items-stretch lg:items-center justify-between">
          <div className="flex flex-col sm:flex-row gap-3 flex-1">
            <div className="relative min-w-0 sm:w-72">
              <Search size={17} className="absolute left-3.5 top-3 text-gray-400 pointer-events-none" />
              <input type="text" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} placeholder="Search items by name..." className="w-full rounded-lg border border-[#e5d9cf] bg-white pl-10 pr-8 py-2 text-sm outline-none focus:border-[#9D4C29]" />
              {search && <button onClick={() => setSearch('')} className="absolute right-3 top-2.5 text-gray-400"><X size={15} /></button>}
            </div>
            <select value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }} className="rounded-lg border border-[#e5d9cf] bg-white px-3 py-2 text-sm text-[#302820] outline-none">
              <option value="">All Categories</option>
              {filterCategories.map((c) => <option key={c.id} value={c.id}>{getCategoryIcon(c.icon)} {c.name}{!c.is_active ? ' (inactive)' : ''}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }} className="rounded-lg border border-[#e5d9cf] bg-white px-3 py-2 text-sm text-[#302820] outline-none">
              <option value="all">Status: All Active</option><option value="published">Status: Published</option><option value="unpublished">Status: Unpublished</option><option value="deleted">Status: Deleted</option>
            </select>
          </div>
          <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-[#e5d9cf] bg-white px-3 py-2 text-sm text-[#302820] outline-none">
            <option value="-created_at">Sort: Latest</option><option value="created_at">Sort: Oldest</option><option value="name">Sort: Name (A-Z)</option><option value="-name">Sort: Name (Z-A)</option><option value="rental_price">Sort: Price (Low-High)</option><option value="-rental_price">Sort: Price (High-Low)</option>
          </select>
        </div>

        {/* Items Table */}
        <div className="overflow-x-auto rounded-xl border border-[#eee3da] bg-white">
          {loading ? (
            <p className="p-10 text-center text-gray-500">Loading items...</p>
          ) : items.length === 0 ? (
            <div className="p-10 text-center">
              <p className="text-base font-semibold text-[#302820]">No items found.</p>
              <p className="mt-1 text-sm text-gray-500">Try adjusting your filters or add a new rental item.</p>
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-sm">
              <thead className="bg-[#f7eee7] text-[#51463d]">
                <tr>
                  <th className="p-4 font-semibold">ITEM</th><th className="p-4 font-semibold">CATEGORY</th><th className="p-4 font-semibold">OWNER</th><th className="p-4 font-semibold">RENTAL PRICE</th><th className="p-4 font-semibold">STOCK</th><th className="p-4 font-semibold">DEPOSIT</th><th className="p-4 font-semibold">STATUS</th><th className="p-4 font-semibold">DATE LISTED</th><th className="p-4 font-semibold text-right">ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-[#f0e9e3] hover:bg-[#fdfaf7] transition-colors">
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        {item.primary_image_url ? (
                          <img src={item.primary_image_url} alt={item.name} className="w-11 h-11 rounded-lg object-cover border border-[#eee3da] shrink-0" />
                        ) : (
                          <div className="w-11 h-11 rounded-lg bg-[#FFF0E7] flex items-center justify-center text-base shrink-0">{getCategoryIcon(item.category_icon)}</div>
                        )}
                        <div><div className="font-medium text-[#302820]">{item.name}</div><div className="text-xs font-mono text-gray-500">slug: {item.slug}</div></div>
                      </div>
                    </td>
                    <td className="p-4">
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-[#faf5f0] border border-[#eee3da] text-xs font-medium text-[#51463d]">
                        <span>{getCategoryIcon(item.category_icon)}</span><span>{item.category_name}</span>
                      </span>
                    </td>
                    <td className="p-4 text-gray-600">{item.owner_name}</td>
                    <td className="p-4 font-semibold text-[#9D4C29] whitespace-nowrap">₹{item.rental_price} <span className="text-xs font-normal text-gray-500">/ day</span></td>
                    <td className="p-4 text-gray-600 whitespace-nowrap">{item.stock} available</td>
                    <td className="p-4 font-semibold text-[#302820] whitespace-nowrap">₹{item.deposit ?? 0}</td>
                    <td className="p-4 whitespace-nowrap">
                      <span className={item.is_deleted ? 'rounded-full bg-red-100 px-3 py-1 text-xs text-red-700' : item.is_published ? 'rounded-full bg-green-100 px-3 py-1 text-xs text-green-700' : 'rounded-full bg-orange-100 px-3 py-1 text-xs text-orange-700'}>
                        {item.is_deleted ? 'Deleted' : item.is_published ? 'Published' : 'Unpublished'}
                      </span>
                    </td>
                    <td className="p-4 text-gray-600 whitespace-nowrap">{item.created_at ? new Date(item.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}</td>
                    <td className="p-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <button type="button" onClick={() => setModal({ mode: 'view', item })} className="p-1.5 rounded-md border border-[#e5d9cf] bg-white text-[#51463d] hover:bg-gray-50" title="View"><Eye size={15} /></button>
                        {!item.is_deleted && (
                          <>
                            <button type="button" onClick={() => { setModalError(''); setModal({ mode: 'edit', item }) }} className="p-1.5 rounded-md border border-[#e5d9cf] bg-white text-[#302820] hover:bg-gray-50" title="Edit"><Pencil size={15} /></button>
                            <button type="button" onClick={() => { setModalError(''); setModal({ mode: 'delete', item }) }} className="p-1.5 rounded-md border border-red-200 bg-white text-red-600 hover:bg-red-50" title="Delete"><Trash2 size={15} /></button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* Pagination */}
          <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-[#f0e9e3] bg-[#faf5f0]/50 text-xs text-gray-600">
            <span>Showing {items.length} of {totalCount} items (Page {page} of {totalPages})</span>
            <div className="flex items-center gap-2">
              <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="px-3 py-1.5 rounded-md border border-[#e5d9cf] bg-white disabled:opacity-40 hover:bg-gray-50 font-medium">Previous</button>
              <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} className="px-3 py-1.5 rounded-md border border-[#e5d9cf] bg-white disabled:opacity-40 hover:bg-gray-50 font-medium">Next</button>
            </div>
          </div>
        </div>

        {modal && (
          <ItemModal
            key={`${modal.mode}-${modal.item?.id || 'new'}`}
            mode={modal.mode}
            item={modal.item}
            categories={formCategories}
            loading={submitting}
            error={modalError}
            onClose={() => setModal(null)}
            onSave={handleSave}
          />
        )}
        {toast && <div className="fixed bottom-6 right-6 z-50 rounded-lg bg-[#302820] text-white px-5 py-3 shadow-lg text-sm font-medium">{toast}</div>}
      </div>
    </AdminLayout>
  )
}

function ItemModal({ mode, item, categories, loading, error, onClose, onSave }) {
  const getInitialCategoryId = () => {
    if (item?.category_id) return item.category_id
    if (item?.category_name && categories.length > 0) {
      const found = categories.find((c) => c.name.toLowerCase() === item.category_name.toLowerCase())
      if (found) return found.id
    }
    return categories.length > 0 ? categories[0].id : ''
  }

  const [form, setForm] = useState({
    name: item?.name || '',
    categoryId: getInitialCategoryId(),
    rentalPrice: item?.rental_price || '',
    stock: item?.stock ?? 1,
    deposit: item?.deposit !== undefined && item?.deposit !== null ? String(item.deposit) : '',
    description: item?.description || '',
    isPublished: item ? Boolean(item.is_published) : true
  })
  const [rentalKit, setRentalKit] = useState(
    Array.isArray(item?.rental_kit) ? [...item.rental_kit] : []
  )
  const [newFiles, setNewFiles] = useState([])
  const [newPreviews, setNewPreviews] = useState([])
  const [existingImages, setExistingImages] = useState(item?.images || [])
  const [deleteImageIds, setDeleteImageIds] = useState([])
  const [primaryImageId, setPrimaryImageId] = useState(item?.images?.find((i) => i.is_primary)?.id || null)
  const [primaryNewIndex, setPrimaryNewIndex] = useState(0)
  const objectUrlsRef = useRef([])

  useEffect(() => {
    return () => {
      objectUrlsRef.current.forEach((url) => {
        try {
          URL.revokeObjectURL(url)
        } catch {
          // ignore
        }
      })
      objectUrlsRef.current = []
    }
  }, [])

  const handleFileSelect = (e) => {
    const selected = Array.from(e.target.files || [])
    if (!selected.length) return
    const urls = selected.map((f) => {
      const url = URL.createObjectURL(f)
      objectUrlsRef.current.push(url)
      return url
    })
    setNewFiles((prev) => [...prev, ...selected])
    setNewPreviews((prev) => [...prev, ...urls])
  }
  const removeNewFile = (idx) => {
    const targetUrl = newPreviews[idx]
    if (targetUrl) {
      try {
        URL.revokeObjectURL(targetUrl)
      } catch {
        // ignore
      }
      objectUrlsRef.current = objectUrlsRef.current.filter((u) => u !== targetUrl)
    }
    setNewFiles((prev) => prev.filter((_, i) => i !== idx))
    setNewPreviews((prev) => prev.filter((_, i) => i !== idx))
    if (primaryNewIndex >= idx && primaryNewIndex > 0) {
      setPrimaryNewIndex((prev) => Math.max(0, prev - 1))
    }
  }
  const removeExistingImage = (id) => {
    setExistingImages((prev) => prev.filter((img) => img.id !== id))
    setDeleteImageIds((prev) => [...prev, id])
    if (primaryImageId === id) setPrimaryImageId(null)
  }

  const handleAddRentalKitEntry = () => {
    setRentalKit((prev) => [...prev, ''])
  }
  const handleUpdateRentalKitEntry = (index, value) => {
    setRentalKit((prev) => prev.map((entry, idx) => (idx === index ? value : entry)))
  }
  const handleRemoveRentalKitEntry = (index) => {
    setRentalKit((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const fd = new FormData()
    const effectiveCategoryId = form.categoryId || (categories.length > 0 ? categories[0].id : '')
    fd.append('name', form.name.trim()); fd.append('category_id', effectiveCategoryId)
    fd.append('rental_price', form.rentalPrice); fd.append('stock', form.stock)
    const depositVal = String(form.deposit ?? '').trim() || '0.00'
    fd.append('deposit', depositVal)
    fd.append('description', form.description.trim()); fd.append('is_published', form.isPublished)
    fd.append('rental_kit', JSON.stringify(rentalKit.map((s) => s.trim()).filter(Boolean)))
    newFiles.forEach((f) => fd.append('images', f))
    if (mode === 'add') { fd.append('primary_image_index', primaryNewIndex) }
    else {
      if (primaryImageId) fd.append('primary_image_id', primaryImageId)
      if (deleteImageIds.length > 0) fd.append('delete_image_ids', JSON.stringify(deleteImageIds))
    }
    onSave(fd, item?.id)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="rounded-xl border border-[#eee3da] bg-white max-w-lg w-full p-6 shadow-xl flex flex-col gap-4 text-[#302820] max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-[#f0e9e3] pb-3">
          <h3 className="text-lg font-bold">{mode === 'view' ? 'Item Details' : mode === 'delete' ? 'Confirm Soft Delete' : mode === 'add' ? 'Add Rental Item' : 'Edit Item'}</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        {error && <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">{error}</div>}
        {mode === 'view' ? (
          <div className="flex flex-col gap-3">
            <div className="flex justify-between items-center">
              <div><h4 className="text-xl font-bold">{item.name}</h4><p className="text-xs font-mono text-gray-500">slug: {item.slug}</p></div>
              <span className={item.is_published ? 'rounded-full bg-green-100 px-3 py-1 text-xs text-green-700' : 'rounded-full bg-orange-100 px-3 py-1 text-xs text-orange-700'}>{item.is_published ? 'Published' : 'Unpublished'}</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm pt-2 border-t border-[#f0e9e3]">
              <div><span className="text-gray-500 text-xs block">Category</span><span className="font-medium">{getCategoryIcon(item.category_icon)} {item.category_name}</span></div>
              <div><span className="text-gray-500 text-xs block">Rental Price</span><span className="font-bold text-[#9D4C29]">₹{item.rental_price} / day</span></div>
              <div><span className="text-gray-500 text-xs block">Stock</span><span className="font-medium">{item.stock} units</span></div>
              <div><span className="text-gray-500 text-xs block">Deposit</span><span className="font-bold text-[#302820]">₹{item.deposit ?? 0}</span></div>
              <div><span className="text-gray-500 text-xs block">Owner</span><span className="font-medium">{item.owner_name}</span></div>
            </div>
            {item.description && <div className="pt-2 border-t border-[#f0e9e3] text-sm bg-[#faf5f0] p-2.5 rounded-lg leading-relaxed">{item.description}</div>}
            <div className="pt-2 border-t border-[#f0e9e3]">
              <span className="text-gray-500 text-xs block mb-1.5">What's Included in the Rental Kit ({item.rental_kit?.length || 0})</span>
              {Array.isArray(item.rental_kit) && item.rental_kit.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {item.rental_kit.map((acc, idx) => (
                    <span key={idx} className="inline-flex items-center gap-1 rounded-md bg-[#faf5f0] border border-[#eee3da] px-2.5 py-1 text-xs font-medium text-[#51463d]">
                      <span className="text-emerald-600 font-bold">✓</span> {acc}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-400 italic">No rental kit accessories specified for this item.</p>
              )}
            </div>
            <div className="pt-2 border-t border-[#f0e9e3]">
              <span className="text-gray-500 text-xs block mb-1.5">Images ({item.images?.length || 0})</span>
              <div className="grid grid-cols-4 gap-2">
                {item.images?.map((img) => (
                  <div key={img.id} className="relative rounded-lg overflow-hidden border border-[#eee3da] aspect-square">
                    <img src={img.image} alt="Gallery" className="w-full h-full object-cover" />
                    {img.is_primary && <span className="absolute top-1 left-1 bg-[#9D4C29] text-white text-[9px] px-1.5 py-0.5 rounded font-bold">Cover</span>}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-[#f0e9e3]"><button type="button" onClick={onClose} className="rounded-lg border border-[#e5d9cf] bg-white px-5 py-2 text-sm font-medium hover:bg-gray-50">Close</button></div>
          </div>
        ) : mode === 'delete' ? (
          <div>
            <p className="text-sm text-gray-600 mb-4">Soft delete "{item?.name}"? It will be unpublished and hidden from customer listings while preserving records.</p>
            <div className="flex justify-end gap-2.5 pt-2 border-t border-[#f0e9e3]">
              <button type="button" onClick={onClose} className="rounded-lg border border-[#e5d9cf] bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50">Cancel</button>
              <button type="button" disabled={loading} onClick={() => onSave(null, item.id)} className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50">{loading ? 'Deleting…' : 'Soft Delete'}</button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div>
              <label className="block text-xs font-semibold text-[#51463d] mb-1">Item Name *</label>
              <input required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Sony Alpha A7 III Camera" className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm outline-none focus:border-[#9D4C29]" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-semibold text-[#51463d] mb-1">Category *</label>
                <select required value={form.categoryId || (categories.length > 0 ? categories[0].id : '')} onChange={(e) => setForm({ ...form, categoryId: e.target.value })} className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3 py-2 text-sm outline-none">
                  {categories.length === 0 && <option value="" disabled>Loading categories…</option>}
                  {categories.map((c) => <option key={c.id} value={c.id}>{getCategoryIcon(c.icon)} {c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#51463d] mb-1">Price / Day (₹) *</label>
                <input required type="number" step="0.01" min="1" value={form.rentalPrice} onChange={(e) => setForm({ ...form, rentalPrice: e.target.value })} placeholder="e.g. 450" className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm outline-none" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#51463d] mb-1">Stock Available *</label>
                <input required type="number" min="0" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} placeholder="1" className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm outline-none" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#51463d] mb-1">Deposit (₹)</label>
                <input type="number" step="0.01" min="0" value={form.deposit ?? ''} onChange={(e) => setForm({ ...form, deposit: e.target.value })} placeholder="0.00" className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm outline-none focus:border-[#9D4C29]" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#51463d] mb-1">Description (optional)</label>
              <textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Details, condition, accessories included..." className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm resize-none outline-none" />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-[#51463d]">Item Images (Multiple Upload)</label>
                <span className="text-[11px] text-gray-400">Max 1200×900 auto-resized by Pillow</span>
              </div>
              <label className="flex flex-col items-center justify-center p-3 border-2 border-dashed border-[#e5d9cf] rounded-lg bg-[#faf5f0]/60 hover:bg-[#FFF0E7]/40 cursor-pointer">
                <Upload size={18} className="text-[#9D4C29] mb-1" />
                <span className="text-xs font-medium text-[#302820]">Click to select one or multiple images</span>
                <span className="text-[10px] text-gray-400 mt-0.5">JPG, PNG, WEBP (Max 5MB each)</span>
                <input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={handleFileSelect} className="hidden" />
              </label>
              {(existingImages.length > 0 || newPreviews.length > 0) && (
                <div className="mt-2 grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-32 overflow-y-auto p-1 bg-[#faf5f0]/40 rounded-lg">
                  {existingImages.map((img) => (
                    <div key={img.id} className={`relative rounded-lg overflow-hidden border-2 aspect-square ${primaryImageId === img.id ? 'border-[#9D4C29]' : 'border-[#eee3da]'}`}>
                      <img src={img.image} alt="Thumb" className="w-full h-full object-cover" />
                      <button type="button" onClick={() => removeExistingImage(img.id)} className="absolute top-1 right-1 w-4 h-4 bg-red-600 text-white rounded-full flex items-center justify-center text-[10px]">✕</button>
                      <button type="button" onClick={() => setPrimaryImageId(img.id)} className={`absolute bottom-1 left-1 p-0.5 rounded text-[9px] font-bold flex items-center ${primaryImageId === img.id ? 'bg-[#9D4C29] text-white' : 'bg-black/60 text-white'}`}><Star size={9} fill={primaryImageId === img.id ? 'currentColor' : 'none'} /> {primaryImageId === img.id ? 'Cover' : 'Set'}</button>
                    </div>
                  ))}
                  {newPreviews.map((src, idx) => (
                    <div key={idx} className={`relative rounded-lg overflow-hidden border-2 aspect-square ${primaryNewIndex === idx && !primaryImageId ? 'border-[#9D4C29]' : 'border-[#eee3da]'}`}>
                      <img src={src} alt="New" className="w-full h-full object-cover" />
                      <button type="button" onClick={() => removeNewFile(idx)} className="absolute top-1 right-1 w-4 h-4 bg-red-600 text-white rounded-full flex items-center justify-center text-[10px]">✕</button>
                      {mode === 'add' && (
                        <button type="button" onClick={() => setPrimaryNewIndex(idx)} className={`absolute bottom-1 left-1 p-0.5 rounded text-[9px] font-bold flex items-center ${primaryNewIndex === idx ? 'bg-[#9D4C29] text-white' : 'bg-black/60 text-white'}`}><Star size={9} fill={primaryNewIndex === idx ? 'currentColor' : 'none'} /> {primaryNewIndex === idx ? 'Cover' : 'Set'}</button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* What's Included in the Rental Kit? */}
            <div className="pt-1">
              <div className="flex items-center justify-between mb-1.5">
                <div>
                  <label className="text-xs font-semibold text-[#51463d] block">What's Included in the Rental Kit? (optional)</label>
                  <span className="text-[11px] text-gray-400">Add accessories included with this item (e.g. Lens, Battery, Charger)</span>
                </div>
                <button
                  type="button"
                  onClick={handleAddRentalKitEntry}
                  className="inline-flex items-center gap-1 text-xs font-medium text-[#9D4C29] hover:text-[#813d21] bg-[#FFF0E7]/60 hover:bg-[#FFF0E7] px-2.5 py-1 rounded-md transition cursor-pointer"
                >
                  <Plus size={13} /> Add Item
                </button>
              </div>
              {rentalKit.length === 0 ? (
                <div className="p-3 rounded-lg border border-dashed border-[#e5d9cf] bg-[#faf5f0]/40 text-center text-xs text-gray-400">
                  No accessories added yet. Click &quot;+ Add Item&quot; to specify rental kit contents.
                </div>
              ) : (
                <div className="flex flex-col gap-2 max-h-36 overflow-y-auto p-1">
                  {rentalKit.map((entry, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={entry}
                        onChange={(e) => handleUpdateRentalKitEntry(idx, e.target.value)}
                        placeholder="e.g. 50mm f/1.8 Lens, 2x Battery, Charger"
                        className="flex-1 rounded-lg border border-[#e5d9cf] bg-white px-3 py-1.5 text-xs outline-none focus:border-[#9D4C29]"
                      />
                      <button
                        type="button"
                        onClick={() => handleRemoveRentalKitEntry(idx)}
                        className="p-1.5 rounded-md border border-[#e5d9cf] text-gray-400 hover:text-red-600 hover:border-red-200 transition cursor-pointer"
                        title="Remove accessory"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <label className="flex items-center justify-between p-2 rounded-lg border border-[#eee3da] bg-[#faf5f0] cursor-pointer">
              <div>
                <span className="text-xs font-semibold text-[#51463d] block">Published in Catalog</span>
                <span className="text-[11px] text-gray-500">Customers can discover and rent this item</span>
              </div>
              <input type="checkbox" checked={form.isPublished} onChange={(e) => setForm({ ...form, isPublished: e.target.checked })} className="w-4 h-4 accent-[#9D4C29]" />
            </label>
            <div className="flex justify-end gap-2.5 pt-2 border-t border-[#f0e9e3]">
              <button type="button" onClick={onClose} className="rounded-lg border border-[#e5d9cf] bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50">Cancel</button>
              <button type="submit" disabled={loading} className="rounded-lg bg-[#9D4C29] px-5 py-2 text-sm font-medium text-white hover:bg-[#813d21] disabled:opacity-50 transition">
                {loading ? 'Saving…' : mode === 'add' ? 'Create Item' : 'Update Item'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
