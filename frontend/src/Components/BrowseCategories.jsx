import { useEffect, useState } from 'react'
import { getPublicCategories } from '../services/api'

function BrowseCategories({ selectedCategory = '', onSelectCategory }) {
  const [categories, setCategories] = useState([])

  useEffect(() => {
    getPublicCategories()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.results || [])
        setCategories(list)
      })
      .catch((err) => console.error('Failed to load categories:', err))
  }, [])

  return (
    <section className="overflow-hidden bg-[#FFFCF9] px-3 pb-5 pt-1 sm:px-5">
      <div className="mx-auto max-w-7xl">
        <h2 className="mb-2 text-sm font-bold text-[#352720] sm:text-base">
          Browse Categories
        </h2>

        {/* Horizontal scrolling category cards */}
        <div className="flex gap-2 overflow-x-auto pb-2 [scrollbar-width:thin] [scrollbar-color:#E58A62_transparent]">
          <button
            type="button"
            onClick={() => onSelectCategory && onSelectCategory('')}
            className={`flex min-w-[108px] shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-left transition hover:border-[#E58A62] sm:min-w-[130px] ${!selectedCategory
                ? 'border-[#E58A62] bg-[#FFF4ED]'
                : 'border-orange-100 bg-white hover:bg-orange-50'
              }`}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#FFF0E7] text-base">
              ▦
            </span>
            <span className="min-w-0">
              <span className="block whitespace-nowrap text-[10px] font-semibold text-[#352720] sm:text-xs">
                All Items
              </span>
              <span className="mt-0.5 block whitespace-nowrap text-[9px] text-gray-500">
                All Categories
              </span>
            </span>
          </button>

          {categories.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => onSelectCategory && onSelectCategory(String(category.id))}
              className={`flex min-w-[108px] shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-left transition hover:border-[#E58A62] sm:min-w-[130px] ${selectedCategory === String(category.id)
                  ? 'border-[#E58A62] bg-[#FFF4ED]'
                  : 'border-orange-100 bg-white hover:bg-orange-50'
                }`}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#FFF0E7] text-base">
                {category.icon || '📦'}
              </span>

              <span className="min-w-0">
                <span className="block whitespace-nowrap text-[10px] font-semibold text-[#352720] sm:text-xs">
                  {category.name}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

export default BrowseCategories
