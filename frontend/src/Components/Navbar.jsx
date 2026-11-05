
import { Link, useLocation } from 'react-router-dom'
import rentBeeLogo from '../assets/rentbee_logo.png'
import { getAccessToken } from '../services/authentication'

function Navbar() {
  const location = useLocation()
  const isLoggedIn = Boolean(getAccessToken())

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-orange-100 bg-[#FFFCF9] px-3 py-2 sm:px-5">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-2">

        {/* RentBee Logo */}
        <Link to="/" className="flex shrink-0 items-center">
          <img
            src={rentBeeLogo}
            alt="RentBee Logo"
            className="h-10 w-auto object-contain"
          />
        </Link>

        {/* Navigation */}
        <div className="flex items-center gap-1.5 text-[10px] font-medium sm:gap-2 sm:text-xs">

          {/* Home - Hide on Home page */}
          {location.pathname !== '/' && (
            <Link
              to="/"
              className="whitespace-nowrap rounded-full border border-orange-200 bg-white px-2.5 py-1.5 text-[#49362D] hover:bg-orange-50 sm:px-3"
            >
              Home
            </Link>
          )}

          {/* Browse Items */}
          <Link
            to="/browse"
            className="whitespace-nowrap rounded-full border border-orange-200 bg-white px-2.5 py-1.5 text-[#49362D] hover:bg-orange-50 sm:px-3"
          >
            Browse Items
          </Link>

          {/* List an Item */}
          <Link
            to="/list-item"
            className="whitespace-nowrap rounded-full bg-[#D97745] px-2.5 py-1.5 text-white hover:bg-[#B85D32] sm:px-3"
          >
            + List an Item
          </Link>

          {/* Wishlist */}
          <Link
            to="/wishlist"
            aria-label="Wishlist"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-orange-200 bg-white text-sm text-[#D97745] hover:bg-orange-50"
          >
            ♡
          </Link>

          {/* My Bookings */}
          <Link
            to="/bookings"
            className="hidden whitespace-nowrap rounded-full border border-orange-200 bg-white px-3 py-1.5 text-[#49362D] hover:bg-orange-50 sm:block"
          >
            My Bookings
          </Link>

          {/* Profile Icon or Login / Signup */}
          {isLoggedIn ? (
            <Link
              to="/profile"
              aria-label="My Profile"
              title="My Profile"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-orange-200 bg-white text-[#9D4C29] hover:bg-orange-50"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="8" r="4" />
                <path d="M5 21v-2a7 7 0 0 1 14 0v2" />
              </svg>
            </Link>
          ) : (
            <Link
              to="/signup"
              className="whitespace-nowrap rounded-full bg-[#9D4C29] px-2.5 py-1.5 text-white hover:bg-[#813B20] sm:px-3"
            >
              Login / Sign Up
            </Link>
          )}

        </div>
      </div>
    </nav>
  )
}

export default Navbar
