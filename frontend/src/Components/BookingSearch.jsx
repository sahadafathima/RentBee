import { Search, X } from 'lucide-react'

export default function BookingSearch({ value, onChange, onClear, onSubmit }) {
  const handleSubmit = (e) => {
    e.preventDefault()
    if (onSubmit) onSubmit()
  }

  return (
    <form onSubmit={handleSubmit} className="relative w-full max-w-md">
      <div className="relative flex items-center">
        <span className="pointer-events-none absolute left-3.5 text-gray-400">
          <Search size={16} />
        </span>

        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search by item or owner name..."
          className="w-full rounded-2xl border border-orange-200 bg-white py-2.5 pl-10 pr-9 text-xs sm:text-sm text-[#352720] placeholder-gray-400 focus:border-[#D97745] focus:bg-[#FFFDFB] focus:outline-none focus:ring-2 focus:ring-orange-200/50 shadow-2xs transition"
        />

        {value && (
          <button
            type="button"
            onClick={onClear}
            className="absolute right-3 rounded-full p-1 text-gray-400 hover:bg-orange-50 hover:text-[#D97745] transition"
            title="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </form>
  )
}

