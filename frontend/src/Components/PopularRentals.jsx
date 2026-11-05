
const rentals = [
  {
    id: 1,
    name: 'Canon DSLR Camera',
    category: 'Cameras',
    location: 'Kochi, Kerala',
    price: 450,
    rating: '4.9',
    image:
      'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600',
  },
  {
    id: 2,
    name: 'Gaming Laptop',
    category: 'Electronics',
    location: 'Thrissur, Kerala',
    price: 800,
    rating: '4.8',
    image:
      'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600',
  },
  {
    id: 3,
    name: 'Portable Projector',
    category: 'Electronics',
    location: 'Kochi, Kerala',
    price: 350,
    rating: '4.7',
    image:
      'https://images.unsplash.com/photo-1535016120720-40c646be5580?w=600',
  },
  {
    id: 4,
    name: 'Camping Tent',
    category: 'Camping',
    location: 'Calicut, Kerala',
    price: 300,
    rating: '4.8',
    image:
      'https://images.unsplash.com/photo-1478131143081-80f7f84ca84d?w=600',
  },
]

function PopularRentals() {
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

          <button
            type="button"
            className="shrink-0 text-sm font-semibold text-[#9D4C29] hover:underline"
          >
            View all →
          </button>
        </div>

        {/* Product cards */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {rentals.map((item) => (
            <article
              key={item.id}
              className="overflow-hidden rounded-2xl border border-orange-100 bg-white transition hover:-translate-y-1 hover:shadow-lg"
            >
              {/* Product image */}
              <div className="relative">
                <img
                  src={item.image}
                  alt={item.name}
                  className="h-48 w-full object-cover"
                />

                <button
                  type="button"
                  aria-label={`Add ${item.name} to wishlist`}
                  className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-white text-xl text-[#9D4C29] shadow-sm hover:bg-orange-50"
                >
                  ♡
                </button>
              </div>

              {/* Product details */}
              <div className="p-4">
                <p className="text-xs font-medium text-[#D97745]">
                  {item.category}
                </p>

                <h3 className="mt-1 text-base font-bold text-[#352720]">
                  {item.name}
                </h3>

                <p className="mt-2 text-xs text-gray-500">
                  📍 {item.location}
                </p>

                <div className="mt-4 flex items-center justify-between gap-2 border-t border-orange-50 pt-3">
                  <div>
                    <span className="text-lg font-bold text-[#9D4C29]">
                      ₹{item.price}
                    </span>
                    <span className="text-xs text-gray-500"> / day</span>
                  </div>

                  <span className="text-sm font-medium text-gray-600">
                    ★ {item.rating}
                  </span>
                </div>

                <button
                  type="button"
                  className="mt-4 w-full rounded-xl bg-[#9D4C29] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#813B20]"
                >
                  View Details
                </button>
              </div>
            </article>
          ))}
        </div>

      </div>
    </section>
  )
}

export default PopularRentals
