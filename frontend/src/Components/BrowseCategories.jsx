
const categories = [
  { name: 'All Categories', icon: '▦', count: '120+ items' },
  { name: 'Electronics', icon: '🎧', count: 'Gadgets' },
  { name: 'Cameras', icon: '📷', count: 'Photo & video' },
  { name: 'Bikes', icon: '🚲', count: 'Ride around' },
  { name: 'Tools', icon: '🔧', count: 'DIY & repairs' },
  { name: 'Furniture', icon: '🪑', count: 'Home essentials' },
  { name: 'Camping', icon: '⛺', count: 'Outdoor gear' },
  { name: 'Sports', icon: '🏸', count: 'Sports gear' },
  { name: 'Events', icon: '🎉', count: 'Event items' },
  
]

function BrowseCategories() {
  return (
    <section className="overflow-hidden bg-[#FFFCF9] px-3 pb-5 pt-1 sm:px-5">
      <div className="mx-auto max-w-7xl">

        <h2 className="mb-2 text-sm font-bold text-[#352720] sm:text-base">
          Browse Categories
        </h2>

        {/* Horizontal scrolling category cards */}
        <div className="flex gap-2 overflow-x-auto pb-2 [scrollbar-width:thin] [scrollbar-color:#E58A62_transparent]">
          {categories.map((category, index) => (
            <button
              key={category.name}
              type="button"
              className={`flex min-w-[108px] shrink-0 items-center gap-2 rounded-xl border px-2 py-2 text-left transition hover:border-[#E58A62] hover:bg-orange-50 sm:min-w-[130px] ${
                index === 0
                  ? 'border-[#E58A62] bg-[#FFF4ED]'
                  : 'border-orange-100 bg-white'
              }`}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#FFF0E7] text-base">
                {category.icon}
              </span>

              <span className="min-w-0">
                <span className="block whitespace-nowrap text-[10px] font-semibold text-[#352720] sm:text-xs">
                  {category.name}
                </span>
                <span className="mt-0.5 block whitespace-nowrap text-[9px] text-gray-500">
                  {category.count}
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
