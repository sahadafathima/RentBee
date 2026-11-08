import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import { getPublicItem } from '../services/api'
import { ChevronRight, ArrowLeft, Package, Clock, ShieldCheck } from 'lucide-react'

export default function RequestBooking() {
  const { id } = useParams()
  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isCurrent = true
    getPublicItem(id)
      .then((data) => {
        if (isCurrent) {
          setItem(data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (isCurrent) setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [id])

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
          {/* Breadcrumb */}
          <nav aria-label="Breadcrumb" className="mb-6">
            <ol className="flex flex-wrap items-center gap-1.5 text-xs text-gray-500 font-medium">
              <li>
                <Link to="/" className="hover:text-[#D97745] transition">
                  Home
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              <li>
                <Link to="/browse" className="hover:text-[#D97745] transition">
                  Browse Items
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              {item && (
                <>
                  <li>
                    <Link to={`/items/${item.id}`} className="hover:text-[#D97745] transition">
                      {item.name}
                    </Link>
                  </li>
                  <li>
                    <ChevronRight size={13} className="text-gray-400" />
                  </li>
                </>
              )}
              <li className="font-semibold text-[#352720]">Request Booking</li>
            </ol>
          </nav>

          {/* Placeholder Destination Container */}
          <div className="rounded-3xl border border-orange-100 bg-white p-8 shadow-xs">
            {loading ? (
              <div className="space-y-4 animate-pulse">
                <div className="h-6 w-1/3 bg-orange-100/60 rounded" />
                <div className="h-4 w-2/3 bg-orange-100/40 rounded" />
                <div className="h-32 bg-orange-50 rounded-2xl" />
              </div>
            ) : item ? (
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#D97745]">
                  <Package size={15} />
                  <span>Rental Booking</span>
                </div>

                <h1 className="mt-1 text-2xl font-black text-[#352720] sm:text-3xl">
                  Request Booking for {item.name}
                </h1>

                <div className="mt-4 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <span className="text-2xl font-black text-[#9D4C29]">
                        ₹{item.rental_price}
                      </span>
                      <span className="text-xs text-gray-500 font-medium"> / day</span>
                    </div>

                    <div className="text-right text-xs text-gray-500">
                      <span>Deposit: </span>
                      <strong className="text-[#352720]">
                        ₹{item.deposit !== undefined && item.deposit !== null ? item.deposit : 0}
                      </strong>
                    </div>
                  </div>
                </div>

                {/* Placeholder Notice */}
                <div className="mt-6 rounded-2xl bg-[#FFFDFB] border border-orange-200/80 p-5 text-xs text-[#49362D] leading-relaxed">
                  <div className="flex items-start gap-3">
                    <Clock size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                    <div>
                      <h2 className="font-bold text-[#352720] text-sm">
                        Booking Flow Placeholder
                      </h2>
                      <p className="mt-1 text-gray-600">
                        The full booking request flow (dates picker, rental duration calculations,
                        and lender communication) will be implemented here according to your
                        requirements.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-6 flex flex-wrap gap-3">
                  <Link
                    to={`/items/${item.id}`}
                    className="inline-flex items-center gap-2 rounded-xl bg-[#9D4C29] px-5 py-2.5 text-xs font-semibold text-white hover:bg-[#813B20] transition"
                  >
                    <ArrowLeft size={14} /> Back to Item Details
                  </Link>

                  <Link
                    to="/browse"
                    className="inline-flex items-center gap-2 rounded-xl border border-orange-200 bg-white px-5 py-2.5 text-xs font-semibold text-[#352720] hover:bg-orange-50 transition"
                  >
                    Browse More Items
                  </Link>
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm font-semibold text-[#352720]">Item not found</p>
                <Link
                  to="/browse"
                  className="mt-4 inline-block rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white"
                >
                  Return to Browse
                </Link>
              </div>
            )}
          </div>

          {/* Trust assurances */}
          <div className="mt-6 grid grid-cols-2 gap-4 text-xs text-gray-500">
            <div className="flex items-center gap-2">
              <ShieldCheck size={16} className="text-[#D97745]" />
              <span>Verified Community Equipment</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-[#D97745]" />
              <span>Flexible Handover Scheduling</span>
            </div>
          </div>
        </main>
      </div>

      <Footer />
    </div>
  )
}

