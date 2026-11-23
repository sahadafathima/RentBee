import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPublicItems } from '../services/api'
import { Package } from 'lucide-react'
import WishlistHeartButton from './WishlistHeartButton'

function PopularRentals({ selectedCategory = '' }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [prevCategory, setPrevCategory] = useState(selectedCategory)

  if (selectedCategory !== prevCategory) {
    setPrevCategory(selectedCategory)
    setLoading(true)
  }

  useEffect(() => {
    let isCurrent = true

    getPublicItems({
      category: selectedCategory,
      page_size: 8,
      sort: '-created_at',
    })
      .then((data) => {
        if (isCurrent) {
          setItems(data.results || [])
        }
      })
      .catch((err) => {
        console.error('Failed to load popular rentals:', err)
      })
      .finally(() => {
        if (isCurrent) setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [selectedCategory])

  return (
    <section className="bg-[#FFFCF9] px-4 py-12 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Heading */}
        <div className="mb-7 flex items-end justify-between gap-3">
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-[#D97745]">
              Discover something useful
            </p>

            <h2 className="text-2xl font-bold text-[#352720] sm:text-3xl">
              Popular Rentals
            </h2>

            <p className="mt-2 text-sm text-gray-500">
              Great finds available to rent from people near you.
            </p>
          </div>

          <Link
            to={selectedCategory ? `/browse?category=${selectedCategory}` : '/browse'}
            className="shrink-0 text-sm font-semibold text-[#9D4C29] hover:underline"
          >
            View all →
          </Link>
        </div>

        {/* Product cards */}
        {loading ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((n) => (
              <div
                key={n}
                className="h-80 rounded-2xl border border-orange-100 bg-white/60 animate-pulse"
              />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-orange-200 bg-white p-12 text-center">
            <Package size={36} className="mx-auto text-orange-300 mb-2" />
            <p className="text-sm font-semibold text-[#352720]">No items available in this category yet</p>
            <p className="text-xs text-gray-500 mt-1">Check back soon or browse all categories.</p>
            <Link
              to="/browse"
              className="mt-4 inline-block rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition"
            >
              Browse All Items
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((item) => (
              <article
                key={item.id}
                className="overflow-hidden rounded-2xl border border-orange-100 bg-white transition hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between"
              >
                {/* Product image */}
                <div className="relative">
                  <img
                    src={
                      item.primary_image_url ||
                      'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600'
                    }
                    alt={item.name}
                    className="h-48 w-full object-cover bg-orange-50"
                  />

                  <div className="absolute right-3 top-3">
                    <WishlistHeartButton item={item} />
                  </div>
                </div>

                {/* Product details */}
                <div className="p-4 flex-1 flex flex-col justify-between">
                  <div>
                    <h3 className="text-base font-bold text-[#352720] line-clamp-1">
                      {item.name}
                    </h3>
                  </div>

                  <div className="mt-4 border-t border-orange-50 pt-3">
                    <div className="flex items-baseline justify-between">
                      <div>
                        <span className="text-lg font-bold text-[#9D4C29]">
                          ₹{item.rental_price}
                        </span>
                        <span className="text-xs text-gray-500"> / day</span>
                      </div>
                      <span className="text-[11px] font-medium text-gray-500">
                        Stock: {item.stock}
                      </span>
                    </div>

                    <div className="mt-1 text-xs text-gray-500">
                      Deposit: <span className="font-semibold text-[#352720]">₹{item.deposit ?? 0}</span>
                    </div>

                    <Link
                      to={`/items/${item.id}`}
                      className="mt-3 block w-full text-center rounded-xl bg-[#9D4C29] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#813B20]"
                    >
                      View Details
                    </Link>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export default PopularRentals
