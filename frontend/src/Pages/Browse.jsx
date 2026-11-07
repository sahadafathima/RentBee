import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import { getPublicItems, getPublicCategories } from '../services/api'
import { Search, X, Package, SlidersHorizontal } from 'lucide-react'

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedCategory = searchParams.get('category') || ''
  const searchParam = searchParams.get('search') || ''

  const [items, setItems] = useState([])
  const [categories, setCategories] = useState([])
  const [search, setSearch] = useState(searchParam)
  const [sort, setSort] = useState('-created_at')
  const [loading, setLoading] = useState(true)
  const [totalCount, setTotalCount] = useState(0)

  useEffect(() => {
    getPublicCategories()
      .then((data) => setCategories(Array.isArray(data) ? data : (data?.results || [])))
      .catch(() => {})
  }, [])

  useEffect(() => {
    setSearch(searchParam)
  }, [searchParam])

  const loadItems = async () => {
    setLoading(true)
    try {
      const data = await getPublicItems({
        category: selectedCategory,
        search: searchParam,
        sort,
      })
      setItems(data.results || [])
      setTotalCount(data.count || 0)
    } catch (err) {
      console.error('Failed to load items:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [selectedCategory, searchParam, sort])

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    const nextParams = new URLSearchParams(searchParams)
    if (search.trim()) nextParams.set('search', search.trim())
    else nextParams.delete('search')
    setSearchParams(nextParams)
  }

  const handleCategorySelect = (catId) => {
    const nextId = selectedCategory === String(catId) ? '' : String(catId)
    const nextParams = new URLSearchParams(searchParams)
    if (nextId) nextParams.set('category', nextId)
    else nextParams.delete('category')
    setSearchParams(nextParams)
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9]">
      <Navbar />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {/* Header & Search */}
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-[#352720]">
              Browse Rental Items
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Discover {totalCount} items available to rent in your community.
            </p>
          </div>

          <form onSubmit={handleSearchSubmit} className="flex gap-2 w-full md:w-80">
            <div className="relative flex-1">
              <Search size={17} className="absolute left-3.5 top-3 text-gray-400 pointer-events-none" />
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search cameras, tools, bikes..."
                className="w-full rounded-xl border border-orange-200 bg-white pl-10 pr-8 py-2.5 text-sm outline-none focus:border-[#D97745]"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => {
                    setSearch('')
                    const p = new URLSearchParams(searchParams)
                    p.delete('search')
                    setSearchParams(p)
                  }}
                  className="absolute right-3 top-3 text-gray-400"
                >
                  <X size={15} />
                </button>
              )}
            </div>
            <button
              type="submit"
              className="rounded-xl bg-[#D97745] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#B85D32] transition"
            >
              Search
            </button>
          </form>
        </div>

        {/* Category Filter Pills */}
        <div className="mb-8 flex gap-2 overflow-x-auto pb-2 [scrollbar-width:thin] [scrollbar-color:#E58A62_transparent]">
          <button
            type="button"
            onClick={() => handleCategorySelect('')}
            className={`flex shrink-0 items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
              !selectedCategory
                ? 'border-[#D97745] bg-[#FFF0E7] text-[#D97745]'
                : 'border-orange-100 bg-white text-[#49362D] hover:bg-orange-50'
            }`}
          >
            <span>▦</span> All Categories
          </button>
          {categories.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => handleCategorySelect(cat.id)}
              className={`flex shrink-0 items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
                selectedCategory === String(cat.id)
                  ? 'border-[#D97745] bg-[#FFF0E7] text-[#D97745]'
                  : 'border-orange-100 bg-white text-[#49362D] hover:bg-orange-50'
              }`}
            >
              <span>{cat.icon || '📦'}</span>
              <span>{cat.name}</span>
              {cat.items_count !== undefined && (
                <span className="rounded-full bg-white/80 px-1.5 py-0.2 text-[10px] text-gray-500">
                  {cat.items_count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Sort Controls */}
        <div className="mb-6 flex items-center justify-between border-b border-orange-100 pb-3">
          <span className="text-xs font-medium text-gray-500">
            Showing {items.length} of {totalCount} results
          </span>

          <div className="flex items-center gap-2">
            <SlidersHorizontal size={14} className="text-gray-400" />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-lg border border-orange-100 bg-white px-2.5 py-1.5 text-xs text-[#352720] outline-none"
            >
              <option value="-created_at">Newest First</option>
              <option value="created_at">Oldest First</option>
              <option value="rental_price">Price: Low to High</option>
              <option value="-rental_price">Price: High to Low</option>
            </select>
          </div>
        </div>

        {/* Items Grid */}
        {loading ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <div
                key={n}
                className="h-72 rounded-2xl border border-orange-100 bg-white/60 animate-pulse"
              />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-orange-200 bg-white p-16 text-center">
            <Package size={44} className="mx-auto text-orange-300 mb-3" />
            <h3 className="text-lg font-bold text-[#352720]">No items found</h3>
            <p className="mt-1 text-sm text-gray-500 max-w-sm mx-auto">
              {search || selectedCategory
                ? 'Try adjusting your search keywords or clearing the category filter.'
                : 'Items listed by lenders in your community will appear here.'}
            </p>
            {(search || selectedCategory) && (
              <button
                type="button"
                onClick={() => {
                  setSearch('')
                  setSelectedCategory('')
                  setSearchParams({})
                }}
                className="mt-4 rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition"
              >
                Clear Filters
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((item) => (
              <article
                key={item.id}
                className="overflow-hidden rounded-2xl border border-orange-100 bg-white transition hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between"
              >
                <div className="relative">
                  <img
                    src={
                      item.primary_image_url ||
                      'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600'
                    }
                    alt={item.name}
                    className="h-48 w-full object-cover bg-orange-50"
                  />
                  <span className="absolute left-3 top-3 rounded-md bg-white/90 backdrop-blur-xs px-2 py-0.5 text-[11px] font-semibold text-[#D97745]">
                    {item.category_icon || '📦'} {item.category_name}
                  </span>
                  <button
                    type="button"
                    aria-label={`Save ${item.name}`}
                    className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-white text-[#9D4C29] shadow-xs hover:bg-orange-50 transition"
                  >
                    ♡
                  </button>
                </div>

                <div className="p-4 flex-1 flex flex-col justify-between">
                  <div>
                    <h3 className="text-base font-bold text-[#352720] line-clamp-1">
                      {item.name}
                    </h3>
                    <p className="mt-1 text-xs text-gray-500 line-clamp-2">
                      {item.description || 'Quality rental equipment in good condition.'}
                    </p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-orange-50 flex items-center justify-between">
                    <div>
                      <span className="text-lg font-bold text-[#9D4C29]">
                        ₹{item.rental_price}
                      </span>
                      <span className="text-xs text-gray-400"> / day</span>
                    </div>

                    <span className="text-[11px] font-medium text-gray-500">
                      Owner: {item.owner_name}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>

      <Footer />
    </div>
  )
}

