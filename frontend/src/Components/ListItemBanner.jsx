
function ListItemBanner() {
  return (
    <section className="bg-[#FFFCF9] px-4 py-10 sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 overflow-hidden rounded-3xl bg-[#352720] px-6 py-10 text-center sm:px-10 md:flex-row md:text-left">

        {/* Banner text */}
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#F4B18D]">
            Make more from what you own
          </p>

          <h2 className="mt-3 text-2xl font-bold leading-tight text-white sm:text-3xl">
            Turn your unused items into extra income.
          </h2>

          <p className="mt-3 text-sm leading-6 text-orange-100/80 sm:text-base">
            List your items on RentBee and help people nearby get what they need.
          </p>
        </div>

        {/* Call to action */}
        <a
          href="/list-item"
          className="shrink-0 rounded-full bg-[#D97745] px-7 py-3.5 text-sm font-semibold text-white transition hover:bg-[#B85D32]"
        >
          + List Your Item
        </a>

      </div>
    </section>
  )
}

export default ListItemBanner
