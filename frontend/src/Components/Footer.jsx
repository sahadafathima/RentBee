
import { Link } from 'react-router-dom'
import rentBeeLogo from '../assets/rentbee_logo.png'

function Footer() {
  return (
    <footer className="bg-white px-4 pb-6 pt-10 sm:px-8">
      <div className="mx-auto max-w-7xl">

        {/* Footer main content */}
        <div className="grid grid-cols-1 gap-8 border-b border-orange-100 pb-8 sm:grid-cols-2 lg:grid-cols-4">

          {/* Brand */}
          <div>
            <Link to="/" className="flex shrink-0 items-center">
              <img
                src={rentBeeLogo}
                alt="RentBee Logo"
                className="h-12 w-auto object-contain"
              />
            </Link>

            <p className="mt-4 max-w-xs text-sm leading-6 text-gray-500">
              Rent what you need from people nearby. Save money, share more,
              and make everyday life easier.
            </p>
          </div>

          {/* Explore */}
          <div>
            <h3 className="font-bold text-[#352720]">Explore</h3>

            <ul className="mt-4 space-y-3 text-sm text-gray-500">
              <li>
                <Link to="/" className="hover:text-[#D97745]">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/browse" className="hover:text-[#D97745]">
                  Browse Items
                </Link>
              </li>
              <li>
                <Link to="/wishlist" className="hover:text-[#D97745]">
                  Wishlist
                </Link>
              </li>
              <li>
                <Link to="/bookings" className="hover:text-[#D97745]">
                  My Bookings
                </Link>
              </li>
            </ul>
          </div>

          {/* For owners */}
          <div>
            <h3 className="font-bold text-[#352720]">For Item Owners</h3>

            <ul className="mt-4 space-y-3 text-sm text-gray-500">
              <li>
                <Link to="/list-item" className="hover:text-[#D97745]">
                  List Your Item
                </Link>
              </li>
              <li>
                <Link to="/login" className="hover:text-[#D97745]">
                  Create an Account
                </Link>
              </li>
              <li>
                <Link to="/login" className="hover:text-[#D97745]">
                  Sign In
                </Link>
              </li>
            </ul>
          </div>

          {/* Help */}
          <div>
            <h3 className="font-bold text-[#352720]">Help & Safety</h3>

            <ul className="mt-4 space-y-3 text-sm text-gray-500">
              <li>How RentBee Works</li>
              <li>Trust & Safety</li>
              <li>Contact Us</li>
              <li>Privacy Policy</li>
            </ul>
          </div>
        </div>

        {/* Copyright */}
        <div className="flex flex-col items-center justify-between gap-3 pt-5 text-center text-xs text-gray-500 sm:flex-row">
          <p>© {new Date().getFullYear()} RentBee. All rights reserved.</p>

          <p>Rent smart. Live better.</p>
        </div>

      </div>
    </footer>
  )
}

export default Footer
