import { Link } from 'react-router-dom'
import { Heart, Trash2, ArrowRight, Package, ChevronRight, Sparkles } from 'lucide-react'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import { useWishlist } from '../Context/WishlistContext'

export default function Wishlist() {
  const { wishlistItems, wishlistCount, loading, removeFromWishlist, isPending } = useWishlist()

  return (
    <div className="flex min-h-screen flex-col bg-[#FFFCF9]">
      <Navbar />

      <main className="flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          {/* Breadcrumb */}
          <nav aria-label="Breadcrumb" className="mb-6">
            <ol className="flex flex-wrap items-center gap-1.5 text-xs font-medium text-gray-500">
              <li>
                <Link to="/" className="transition hover:text-[#D97745]">
                  Home
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              <li className="font-semibold text-[#352720]">My Wishlist</li>
            </ol>
          </nav>

          {/* Page Header */}
          <div className="mb-8 flex flex-col justify-between gap-4 border-b border-orange-100 pb-6 sm:flex-row sm:items-end">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-black text-[#352720] sm:text-3xl">
                  My Wishlist
                </h1>
                {wishlistCount > 0 && (
                  <span className="inline-flex items-center rounded-full bg-[#FFF0E7] px-3 py-1 text-xs font-bold text-[#D97745] border border-orange-200">
                    {wishlistCount} {wishlistCount === 1 ? 'item' : 'items'}
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-[#7A675D]">
                Keep track of items you love and rent them whenever you are ready.
              </p>
            </div>

            <Link
              to="/browse"
              className="inline-flex items-center gap-1.5 self-start text-xs font-bold text-[#9D4C29] transition hover:text-[#813B20] sm:self-auto"
            >
              <span>Explore More Items</span>
              <ArrowRight size={14} />
            </Link>
          </div>

          {/* Content Area */}
          {loading ? (
            /* Loading Skeleton Grid */
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className="flex h-96 flex-col justify-between rounded-2xl border border-orange-100 bg-white p-4 shadow-xs animate-pulse"
                >
                  <div className="h-48 w-full rounded-xl bg-orange-100/60" />
                  <div className="mt-4 space-y-2">
                    <div className="h-4 w-3/4 rounded bg-orange-100/60" />
                    <div className="h-3 w-1/2 rounded bg-orange-100/40" />
                  </div>
                  <div className="mt-4 border-t border-orange-50 pt-3 space-y-2">
                    <div className="h-4 w-1/3 rounded bg-orange-100/60" />
                    <div className="h-9 w-full rounded-xl bg-orange-100/60" />
                  </div>
                </div>
              ))}
            </div>
          ) : wishlistItems.length === 0 ? (
            /* Empty State */
            <div className="mx-auto max-w-xl rounded-3xl border border-dashed border-orange-200 bg-white p-10 sm:p-14 text-center shadow-xs">
              <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-[#FFF0E7] text-[#D97745] shadow-inner">
                <Heart size={40} className="fill-[#D97745]/20 stroke-[1.8]" />
              </div>

              <h2 className="text-xl sm:text-2xl font-black text-[#352720]">
                Your Wishlist is empty
              </h2>

              <p className="mt-2 text-sm text-[#7A675D] leading-relaxed">
                Explore our collection of cameras, tools, camping equipment, and more. Tap the heart icon on any item to save it here for later.
              </p>

              <div className="mt-8 flex justify-center">
                <Link
                  to="/browse"
                  className="inline-flex items-center gap-2 rounded-2xl bg-[#D97745] px-6 py-3.5 text-sm font-bold text-white shadow-md transition hover:bg-[#B85D32] active:scale-[0.99]"
                >
                  <Package size={17} />
                  <span>Browse Items Now</span>
                  <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          ) : (
            /* Populated Items Grid */
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {wishlistItems.map((entry) => {
                const item = entry.item
                if (!item) return null
                const isAvailable = item.is_available !== undefined ? item.is_available : (item.stock > 0)
                const pending = isPending(item.id)

                return (
                  <article
                    key={entry.id || item.id}
                    className="group flex flex-col justify-between overflow-hidden rounded-2xl border border-orange-100 bg-white shadow-xs transition duration-200 hover:-translate-y-1 hover:shadow-md"
                  >
                    {/* Item Image & Quick Actions */}
                    <div className="relative">
                      <Link to={`/items/${item.id}`} className="block overflow-hidden">
                        <img
                          src={
                            item.primary_image_url ||
                            'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600'
                          }
                          alt={item.name}
                          loading="lazy"
                          className="h-48 w-full object-cover bg-orange-50 transition duration-300 group-hover:scale-[1.03]"
                        />
                      </Link>

                      {/* Availability Badge */}
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

                      {/* Remove Button in Top-Right Corner */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          if (pending) return
                          removeFromWishlist(item.id)
                        }}
                        disabled={pending}
                        aria-busy={pending}
                        aria-label={`Remove ${item.name} from wishlist`}
                        title="Remove from wishlist"
                        className={`absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-white/90 shadow-xs backdrop-blur-xs transition hover:bg-white hover:scale-110 active:scale-95 text-[#D97745] ${
                          pending ? 'cursor-wait opacity-80' : 'cursor-pointer'
                        }`}
                      >
                        <Heart size={16} className="fill-[#D97745] text-[#D97745]" />
                      </button>
                    </div>

                    {/* Card Body */}
                    <div className="flex flex-1 flex-col justify-between p-4">
                      <div>
                        {/* Category Tag */}
                        {item.category_name && (
                          <span className="inline-block rounded-md bg-[#FFF0E7] px-2 py-0.5 text-[10px] font-semibold text-[#D97745] mb-1.5">
                            {item.category_icon || '📦'} {item.category_name}
                          </span>
                        )}

                        <h2 className="text-base font-bold text-[#352720] line-clamp-1 group-hover:text-[#D97745] transition">
                          <Link to={`/items/${item.id}`}>{item.name}</Link>
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

                      {/* Pricing & Dual Action Buttons */}
                      <div className="mt-4 border-t border-orange-50 pt-3">
                        <div className="flex items-baseline justify-between mb-3">
                          <div>
                            <span className="text-xl font-black text-[#9D4C29]">
                              ₹{item.rental_price}
                            </span>
                            <span className="text-xs font-medium text-gray-500"> / day</span>
                          </div>
                        </div>

                        <div className="flex flex-col gap-2">
                          <Link
                            to={`/items/${item.id}`}
                            className="flex items-center justify-center gap-1.5 w-full rounded-xl bg-[#9D4C29] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#813B20]"
                          >
                            <Sparkles size={13} />
                            <span>View Details</span>
                          </Link>

                          <button
                            type="button"
                            onClick={() => removeFromWishlist(item.id)}
                            disabled={pending}
                            aria-busy={pending}
                            className={`flex items-center justify-center gap-1.5 w-full rounded-xl border border-orange-200 bg-white px-4 py-1.5 text-xs font-semibold text-[#8B776D] transition hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200 ${
                              pending ? 'cursor-wait opacity-60' : 'cursor-pointer'
                            }`}
                          >
                            <Trash2 size={13} />
                            <span>{pending ? 'Removing...' : 'Remove'}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}

