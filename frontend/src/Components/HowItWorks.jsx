
const steps = [
  {
    number: '01',
    icon: '🔎',
    title: 'Find Your Item',
    description: 'Browse categories and discover items you need.',
  },
  {
    number: '02',
    icon: '📅',
    title: 'Book with Owner',
    description: 'Choose your dates and send a booking request.',
  },
  {
    number: '03',
    icon: '🤝',
    title: 'Pickup & Enjoy',
    description: 'Coordinate with the owner and enjoy your rental.',
  },
  {
    number: '04',
    icon: '↩️',
    title: 'Return the Item',
    description: 'Return the item as agreed with the owner.',
  },
]

function HowItWorks() {
  return (
    <section className="bg-white px-4 py-12 sm:px-8">
      <div className="mx-auto max-w-7xl">

        <div className="mx-auto mb-10 max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#D97745]">
            Simple and convenient
          </p>

          <h2 className="mt-2 text-2xl font-bold text-[#352720] sm:text-3xl">
            How RentBee Works
          </h2>

          <p className="mt-3 text-sm text-gray-500 sm:text-base">
            Get what you need in four simple steps.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step) => (
            <div
              key={step.number}
              className="rounded-2xl border border-orange-100 bg-[#FFFCF9] p-6 text-center transition hover:-translate-y-1 hover:shadow-md"
            >
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-[#F9E8DE] text-3xl">
                {step.icon}
              </div>

              <p className="mt-4 text-xs font-bold tracking-widest text-[#D97745]">
                STEP {step.number}
              </p>

              <h3 className="mt-2 font-bold text-[#352720]">
                {step.title}
              </h3>

              <p className="mt-2 text-sm leading-6 text-gray-500">
                {step.description}
              </p>
            </div>
          ))}
        </div>

      </div>
    </section>
  )
}

export default HowItWorks
