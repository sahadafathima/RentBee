
function HeroSection() {
  return (
    <section className="bg-[#FFFCF9] px-3 pb-5 pt-7 text-center sm:px-5 sm:pt-8">
      <div className="mx-auto max-w-3xl">

        <h1 className="text-3xl font-extrabold leading-[1.05] tracking-tight text-[#171412] sm:text-5xl">
          Rent what you need.
          <span className="text-[#D97745]">
            {' '}From people
          </span>
          <span className="block text-[#D97745]">
            near you.
          </span>
        </h1>

        <p className="mt-2 text-xs text-gray-500 sm:text-sm">
          Find trusted rentals from people in your area.
        </p>

        <form
          onSubmit={(event) => {
            event.preventDefault()
          }}
          className="mx-auto mt-4 flex max-w-2xl items-center gap-0 overflow-hidden rounded-full border border-orange-200 bg-white p-1 shadow-sm"
        >
          {/* Location selector */}
          <div className="flex w-[130px] shrink-0 items-center gap-1.5 px-2 sm:w-[165px] sm:px-3">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-4 w-4 shrink-0 text-[#D97745]"
              aria-hidden="true"
            >
              <path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" />
              <circle cx="12" cy="10" r="2.5" />
            </svg>

            <select
              aria-label="Select location"
              defaultValue=""
              className="min-w-0 flex-1 appearance-none bg-transparent py-2 text-[10px] text-[#49362D] outline-none sm:text-xs"
            >
              <option value="" disabled>
                Select Location
              </option>
              <option value="Kochi">Kochi</option>
              <option value="Thrissur">Thrissur</option>
              <option value="Calicut">Calicut</option>
              <option value="Trivandrum">Trivandrum</option>
            </select>

            <span className="text-[9px] text-gray-400">⌄</span>
          </div>

          <div className="h-6 shrink-0 border-l border-orange-100" />

          {/* Search input */}
          <input
            type="search"
            placeholder="Search cameras, bikes, tools..."
            aria-label="Search rental items"
            className="min-w-0 flex-1 bg-transparent px-2 py-2 text-[10px] outline-none placeholder:text-gray-400 sm:px-3 sm:text-xs"
          />

          <button
            type="submit"
            className="flex shrink-0 items-center gap-1 rounded-full bg-[#D97745] px-3 py-2 text-[10px] font-semibold text-white transition hover:bg-[#B85D32] sm:px-4 sm:text-xs"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-3 w-3"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m16 16 4 4" />
            </svg>
            Search
          </button>
        </form>
      </div>
    </section>
  )
}

export default HeroSection
