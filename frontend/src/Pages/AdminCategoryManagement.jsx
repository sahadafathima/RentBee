import { useEffect, useState } from 'react'
import AdminLayout from '../Components/AdminLayout'
import { getAdminCategories, createCategory, updateCategory, softDeleteCategory } from '../services/api'
import { Plus, Search, X } from 'lucide-react'

// Real category icons — does NOT include '▦' (All Categories) since that is a UI-only sentinel
const HOMEPAGE_ICONS = [
  { icon: '🎧', name: 'Electronics' },
  { icon: '📷', name: 'Cameras' },
  { icon: '🚲', name: 'Bikes' },
  { icon: '🔧', name: 'Tools' },
  { icon: '🪑', name: 'Furniture' },
  { icon: '⛺', name: 'Camping' },
  { icon: '🏸', name: 'Sports' },
  { icon: '🎉', name: 'Events' },
  { icon: '📦', name: 'General' },
]

// Legacy compatibility map so old database records display the homepage emoji icons
const LEGACY_ICON_MAP = {
  category: '▦',
  devices: '🎧',
  photo_camera: '📷',
  pedal_bike: '🚲',
  home_repair_service: '🔧',
  chair: '🪑',
  camping: '⛺',
  sports_soccer: '🏸',
}

// eslint-disable-next-line react-refresh/only-export-components
export function getCategoryIcon(icon) {
  return LEGACY_ICON_MAP[icon] || icon || '📦'
}

export default function AdminCategoryManagement() {
  const [categories, setCategories] = useState([])
  const [usedIcons, setUsedIcons] = useState([])
  const [archivedCount, setArchivedCount] = useState(0)
  const [totalItemsCount, setTotalItemsCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('-created_at')
  const [toast, setToast] = useState('')
  const [modal, setModal] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [modalError, setModalError] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  const notify = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3500)
  }

  const applyCategoryData = (data) => {
    const list = data.results || []
    setCategories(list)
    if (data.stats) {
      setArchivedCount(data.stats.archived || 0)
      if (data.stats.total_items !== undefined) {
        setTotalItemsCount(data.stats.total_items)
      }
    }
    if (data.used_icons) {
      setUsedIcons(data.used_icons)
    } else {
      setUsedIcons(list.filter((c) => c.is_active).map((c) => c.icon))
    }
  }

  useEffect(() => {
    let isCurrent = true
    getAdminCategories({ search, sort })
      .then((data) => {
        if (isCurrent) applyCategoryData(data)
      })
      .catch((err) => {
        if (isCurrent) notify(err.message || 'Failed to load categories.')
      })
      .finally(() => {
        if (isCurrent) setLoading(false)
      })

    const handleRefresh = () => {
      getAdminCategories({ search, sort })
        .then((data) => {
          if (isCurrent) applyCategoryData(data)
        })
        .catch(() => {})
    }

    window.addEventListener('rentbee:items_changed', handleRefresh)
    window.addEventListener('focus', handleRefresh)
    return () => {
      isCurrent = false
      window.removeEventListener('rentbee:items_changed', handleRefresh)
      window.removeEventListener('focus', handleRefresh)
    }
  }, [search, sort, reloadToken])

  const handleSave = async (payload) => {
    setSubmitting(true)
    setModalError('')
    try {
      if (modal.mode === 'add') {
        await createCategory(payload)
        notify('Category created successfully.')
      } else if (modal.mode === 'edit') {
        await updateCategory(modal.cat.id, payload)
        notify('Category updated successfully.')
      } else if (modal.mode === 'delete') {
        await softDeleteCategory(modal.cat.id)
        notify(`Category "${modal.cat.name}" soft-deleted.`)
      }
      setModal(null)
      setReloadToken((t) => t + 1)
      window.dispatchEvent(new CustomEvent('rentbee:items_changed'))
    } catch (err) {
      setModalError(err.message || 'Operation failed.')
      notify(err.message || 'Error occurred.')
    } finally {
      setSubmitting(false)
    }
  }

  const activeCount = categories.filter((c) => c.is_active).length
  const totalItems = totalItemsCount || categories.reduce((sum, c) => sum + (c.items_count || 0), 0)
  const popularCat = [...categories].sort((a, b) => (b.items_count || 0) - (a.items_count || 0))[0]
  const popularVal = popularCat && (popularCat.items_count || 0) > 0 ? popularCat.name : '—'
  const popularSub = popularCat && (popularCat.items_count || 0) > 0
    ? `${popularCat.items_count} ${popularCat.items_count === 1 ? 'item' : 'items'}`
    : 'Awaiting items'

  return (
    <AdminLayout pageTitle="Category Management" breadcrumbs={['Admin Panel', 'Item & Catalog', 'Category Management']}>
      <div className="w-full text-[#302820]">
        {/* Top Header */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Category Management</h1>
            <p className="mt-1 text-sm text-gray-500">View, organize and manage equipment rental categories.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setModalError('')
              setModal({ mode: 'add' })
            }}
            className="flex items-center gap-2 rounded-lg bg-[#9D4C29] px-5 py-2.5 font-medium text-white hover:bg-[#813d21] transition shadow-xs cursor-pointer shrink-0 self-start sm:self-auto"
          >
            <Plus size={18} /> Add Category
          </button>
        </div>

        {/* 4 Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Active Categories', val: activeCount, sub: 'Live in catalog' },
            { label: 'Total Items', val: totalItems, sub: 'Categorized' },
            { label: 'Most Popular', val: popularVal, sub: popularSub },
            { label: 'Archived', val: archivedCount, sub: 'Soft-deleted' },
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

        {/* Search & Sort Controls */}
        <div className="mb-5 flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative w-full sm:w-80">
            <Search size={17} className="absolute left-3.5 top-3 text-gray-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or slug..."
              className="w-full rounded-lg border border-[#e5d9cf] bg-white pl-10 pr-8 py-2.5 text-sm outline-none focus:border-[#9D4C29]"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-3 top-3 text-gray-400 hover:text-gray-600">
                <X size={15} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-lg border border-[#e5d9cf] bg-white px-3 py-2 text-sm text-[#302820] outline-none focus:border-[#9D4C29]"
            >
              <option value="-created_at">Sort: Latest First</option>
              <option value="created_at">Sort: Oldest First</option>
              <option value="name">Sort: Alphabetical (A-Z)</option>
              <option value="-name">Sort: Alphabetical (Z-A)</option>
            </select>
            <span className="text-xs text-gray-500 whitespace-nowrap">Showing {categories.length} categories</span>
          </div>
        </div>

        {/* Category Table */}
        <div className="overflow-x-auto rounded-xl border border-[#eee3da] bg-white">
          {loading ? (
            <p className="p-10 text-center text-gray-500">Loading categories...</p>
          ) : categories.length === 0 ? (
            <div className="p-10 text-center">
              <p className="text-base font-semibold text-[#302820]">No categories found.</p>
              <p className="mt-1 text-sm text-gray-500">Try adjusting your search query or add a new category.</p>
              {search && (
                <button onClick={() => setSearch('')} className="mt-3 text-sm font-medium text-[#9D4C29] hover:underline">
                  Clear search
                </button>
              )}
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-sm">
              <thead className="bg-[#f7eee7] text-[#51463d]">
                <tr>
                  <th className="p-4 font-semibold">Category &amp; Slug</th>
                  <th className="p-4 font-semibold">Linked Items</th>
                  <th className="p-4 font-semibold">Created Date</th>
                  <th className="p-4 font-semibold">Status</th>
                  <th className="p-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => {
                  const dateStr = cat.created_at
                    ? new Date(cat.created_at).toLocaleDateString('en-IN', {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric',
                      })
                    : '—'

                  return (
                    <tr key={cat.id} className="border-t border-[#f0e9e3] hover:bg-[#fdfaf7] transition-colors">
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#FFF0E7] text-base">
                            {getCategoryIcon(cat.icon)}
                          </span>
                          <div>
                            <div className="font-medium text-[#302820]">{cat.name}</div>
                            <div className="text-xs font-mono text-gray-500">slug: {cat.slug}</div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 text-gray-600">
                        {cat.items_count ?? 0} {cat.items_count === 1 ? 'item listed' : 'items listed'}
                      </td>
                      <td className="p-4 text-gray-600 whitespace-nowrap">{dateStr}</td>
                      <td className="p-4 whitespace-nowrap">
                        <span
                          className={
                            cat.is_active
                              ? 'rounded-full bg-green-100 px-3 py-1 text-xs text-green-700'
                              : 'rounded-full bg-red-100 px-3 py-1 text-xs text-red-700'
                          }
                        >
                          {cat.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="p-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setModalError('')
                              setModal({ mode: 'edit', cat })
                            }}
                            className="rounded-md border border-[#e5d9cf] bg-white px-3 py-1 text-xs font-medium text-[#302820] hover:bg-gray-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setModalError('')
                              setModal({ mode: 'delete', cat })
                            }}
                            className="rounded-md border border-red-200 bg-white px-3 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Modal Dialog */}
        {modal && (
          <CategoryModal
            mode={modal.mode}
            cat={modal.cat}
            usedIcons={usedIcons}
            loading={submitting}
            error={modalError}
            onClose={() => setModal(null)}
            onSave={handleSave}
          />
        )}

        {/* Toast Alert */}
        {toast && (
          <div className="fixed bottom-6 right-6 z-50 rounded-lg bg-[#302820] text-white px-5 py-3 shadow-lg text-sm font-medium animate-in fade-in">
            {toast}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}

function CategoryModal({ mode, cat, usedIcons = [], onClose, onSave, loading, error }) {
  // Determine initial icon (default to first available homepage icon if adding)
  const defaultAvailableIcon = HOMEPAGE_ICONS.find((item) => !usedIcons.includes(item.icon))?.icon || '📦'
  const [name, setName] = useState(cat?.name || '')
  const [desc, setDesc] = useState(cat?.description || '')
  const [icon, setIcon] = useState(cat ? getCategoryIcon(cat.icon) : defaultAvailableIcon)
  const [isActive, setIsActive] = useState(cat ? Boolean(cat.is_active) : true)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (mode === 'delete') {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
        onClick={(e) => e.target === e.currentTarget && onClose()}
      >
        <div className="rounded-xl border border-[#eee3da] bg-white max-w-md w-full p-6 shadow-xl flex flex-col gap-4 text-[#302820]">
          <h3 className="text-lg font-bold">Soft Delete "{cat?.name}"?</h3>
          <p className="text-sm text-gray-600 leading-relaxed">
            This category will be set to inactive and hidden from catalog navigation. Equipment records will remain preserved, and its assigned icon will become available for reuse.
          </p>
          <div className="flex justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[#e5d9cf] bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => onSave()}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? 'Deleting…' : 'Soft Delete'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="rounded-xl border border-[#eee3da] bg-white max-w-lg w-full p-6 shadow-xl flex flex-col gap-4 text-[#302820]">
        <div className="flex items-center justify-between border-b border-[#f0e9e3] pb-3">
          <h3 className="text-lg font-bold">{mode === 'add' ? 'Add New Category' : 'Edit Category'}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
            {error}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSave({ name: name.trim(), description: desc.trim(), icon, is_active: isActive })
          }}
          className="flex flex-col gap-3.5"
        >
          <div>
            <label className="block text-xs font-semibold text-[#51463d] mb-1">Category Name *</label>
            <input
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Tools, Camping"
              className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm outline-none focus:border-[#9D4C29]"
            />
          </div>

          {mode === 'edit' && (
            <div>
              <label className="block text-xs font-semibold text-[#51463d] mb-1">Slug (read-only)</label>
              <div className="rounded-lg border border-[#eee3da] bg-[#faf6f2] px-3.5 py-1.5 font-mono text-xs text-gray-600">
                rentbee.app/category/<span className="font-semibold text-[#302820]">{cat.slug}</span>
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-[#51463d] mb-1">Description (optional)</label>
            <textarea
              rows={2}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="Brief description of the category..."
              className="w-full rounded-lg border border-[#e5d9cf] bg-white px-3.5 py-2 text-sm resize-none outline-none focus:border-[#9D4C29]"
            />
          </div>

          {/* Unique Icon Selection Grid */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-[#51463d]">Category Icon *</label>
              <span className="text-[11px] text-gray-500">Each icon can be used only once</span>
            </div>

            <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
              {HOMEPAGE_ICONS.map((item) => {
                // An icon is disabled if it's already assigned to an active category
                // (except in edit mode when it is the category's own icon)
                const isAssigned = usedIcons.includes(item.icon)
                const isOwnIcon = mode === 'edit' && getCategoryIcon(cat?.icon) === item.icon
                const isDisabled = isAssigned && !isOwnIcon
                const isSelected = icon === item.icon

                return (
                  <button
                    key={item.icon}
                    type="button"
                    disabled={isDisabled}
                    onClick={() => setIcon(item.icon)}
                    title={isDisabled ? `"${item.name}" icon is already assigned to an active category` : item.name}
                    className={`flex flex-col items-center justify-center p-2 rounded-lg text-center transition-all border ${
                      isDisabled
                        ? 'opacity-35 cursor-not-allowed bg-gray-100 text-gray-400 border-gray-200'
                        : isSelected
                        ? 'border-[#9D4C29] bg-[#FFF0E7] text-[#9D4C29] ring-2 ring-[#9D4C29]/30 shadow-xs cursor-pointer'
                        : 'border-[#e5d9cf] bg-white hover:border-[#E58A62] hover:bg-orange-50 cursor-pointer'
                    }`}
                  >
                    <span className="text-xl mb-0.5">{item.icon}</span>
                    <span className="text-[10px] font-medium truncate max-w-full">
                      {item.name}
                    </span>
                    {isDisabled && (
                      <span className="text-[9px] text-red-500 font-semibold mt-0.5">Used</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {mode === 'edit' && (
            <label className="flex items-center justify-between p-2.5 rounded-lg border border-[#eee3da] bg-[#faf6f2] cursor-pointer">
              <span className="text-xs font-semibold text-[#51463d]">Active in catalog</span>
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 accent-[#9D4C29]"
              />
            </label>
          )}

          <div className="flex justify-end gap-2.5 pt-3 border-t border-[#f0e9e3]">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[#e5d9cf] bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-[#9D4C29] px-5 py-2 text-sm font-medium text-white hover:bg-[#813d21] disabled:opacity-50 transition"
            >
              {loading ? 'Saving…' : mode === 'add' ? 'Save Category' : 'Update Category'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
