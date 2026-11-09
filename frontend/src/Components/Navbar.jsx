
import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Heart, Bell, ExternalLink } from 'lucide-react'
import rentBeeLogo from '../assets/rentbee_logo.png'
import { getAccessToken } from '../services/authentication'
import { useWishlist } from '../Context/WishlistContext'
import {
  getUserNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from '../services/api'

function Navbar() {
  const location = useLocation()
  const isLoggedIn = Boolean(getAccessToken())
  const { wishlistCount } = useWishlist()

  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isNotifOpen, setIsNotifOpen] = useState(false)
  const notifRef = useRef(null)

  // Close dropdown on route change without cascading effect renders
  const [prevPath, setPrevPath] = useState(location.pathname)
  if (location.pathname !== prevPath) {
    setPrevPath(location.pathname)
    setIsNotifOpen(false)
  }

  // Fetch notifications for logged-in user
  useEffect(() => {
    if (!isLoggedIn) return

    let isCurrent = true
    const fetchNotifs = () => {
      getUserNotifications()
        .then((data) => {
          if (!isCurrent) return
          setNotifications(data?.results || [])
          setUnreadCount(data?.unread_count || 0)
        })
        .catch(() => {
          // silently ignore network errors for notification poll
        })
    }

    fetchNotifs()
    const interval = setInterval(fetchNotifs, 30000)

    return () => {
      isCurrent = false
      clearInterval(interval)
    }
  }, [isLoggedIn])

  // Close notifications dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setIsNotifOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const handleMarkAsRead = async (id, e) => {
    if (e?.stopPropagation) e.stopPropagation()
    try {
      await markNotificationRead(id)
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      )
      setUnreadCount((c) => Math.max(0, c - 1))
    } catch (err) {
      console.error('Failed to mark notification read:', err)
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead()
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch (err) {
      console.error('Failed to mark all notifications read:', err)
    }
  }

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
            title="My Wishlist"
            className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-orange-200 bg-white text-[#D97745] hover:bg-orange-50 transition"
          >
            <Heart
              size={15}
              className={wishlistCount > 0 ? 'fill-[#D97745] text-[#D97745]' : 'text-[#D97745]'}
            />
            {wishlistCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#D97745] px-1 text-[10px] font-bold text-white shadow-xs">
                {wishlistCount > 99 ? '99+' : wishlistCount}
              </span>
            )}
          </Link>

          {/* In-App Notifications Bell for Logged-In Users */}
          {isLoggedIn && (
            <div className="relative" ref={notifRef}>
              <button
                type="button"
                onClick={() => setIsNotifOpen((prev) => !prev)}
                aria-label="Notifications"
                title="Notifications"
                className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-orange-200 bg-white text-[#D97745] hover:bg-orange-50 transition cursor-pointer"
              >
                <Bell size={15} />
                {unreadCount > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#D97745] px-1 text-[10px] font-bold text-white shadow-xs">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Popover Dropdown */}
              {isNotifOpen && (
                <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-2xl border border-orange-100 bg-white shadow-xl z-50 overflow-hidden">
                  <div className="flex items-center justify-between border-b border-orange-100 px-4 py-3 bg-[#FFFCF9]">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-[#352720]">Notifications</span>
                      {unreadCount > 0 && (
                        <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-bold text-[#D97745]">
                          {unreadCount} new
                        </span>
                      )}
                    </div>
                    {unreadCount > 0 && (
                      <button
                        type="button"
                        onClick={handleMarkAllRead}
                        className="text-[11px] font-semibold text-[#D97745] hover:text-[#9D4C29] transition cursor-pointer"
                      >
                        Mark all as read
                      </button>
                    )}
                  </div>

                  <div className="max-h-80 overflow-y-auto divide-y divide-orange-50">
                    {notifications.length === 0 ? (
                      <div className="py-8 text-center text-xs text-gray-500">
                        No notifications yet.
                      </div>
                    ) : (
                      notifications.map((n) => (
                        <div
                          key={n.id}
                          className={`p-3.5 transition flex gap-3 ${n.is_read ? 'bg-white opacity-85' : 'bg-orange-50/50'
                            }`}
                        >
                          <div className="mt-1 shrink-0">
                            <div
                              className={`h-2 w-2 rounded-full ${n.is_read ? 'bg-transparent' : 'bg-[#D97745]'
                                }`}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-bold text-[#352720] leading-snug">
                              {n.title}
                            </p>
                            <p className="mt-1 text-[11px] text-gray-600 leading-relaxed">
                              {n.message}
                            </p>
                            <div className="mt-2 flex items-center justify-between gap-2">
                              {n.item && (
                                <Link
                                  to={`/items/${n.item}`}
                                  onClick={() => {
                                    if (!n.is_read) handleMarkAsRead(n.id)
                                    setIsNotifOpen(false)
                                  }}
                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#D97745] hover:underline"
                                >
                                  <span>View {n.item_name || 'Item'}</span>
                                  <ExternalLink size={11} />
                                </Link>
                              )}
                              {!n.is_read && (
                                <button
                                  type="button"
                                  onClick={(e) => handleMarkAsRead(n.id, e)}
                                  className="text-[10px] text-gray-400 hover:text-gray-700 ml-auto cursor-pointer"
                                >
                                  Mark read
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

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
