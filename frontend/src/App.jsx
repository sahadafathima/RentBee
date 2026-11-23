import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { initAuthSession } from './services/authentication'

import Home from './Pages/Home'
import MyListings from './Pages/MyListings'
import Notifications from './Pages/Notifications'
import { NotificationProvider } from './Context/NotificationContext'
import Browse from './Pages/Browse'
import ItemDetails from './Pages/ItemDetails'
import RequestBooking from './Pages/RequestBooking'
import Signup from './Pages/Signup'
import Login from './Pages/Login'
import ForgetPassword from './Pages/ForgetPassword'
import ResetPassword from './Pages/ResetPassword'
import AdminLogin from './Pages/AdminLogin'
import Profile from './Pages/Profile'
import EditProfile from './Pages/EditProfile'
import MyAddress from './Pages/MyAddress'
import MyBookings from './Pages/MyBookings'
import BookingDetails from './Pages/BookingDetails'
import BookingSuccess from './Pages/BookingSuccess'
import ReportProblem from './Pages/ReportProblem'
import HostHub from './Pages/HostHub'
import ListItem from './Pages/ListItem'
import UserManagement from './Pages/UserManagement'
import AdminCategoryManagement from './Pages/AdminCategoryManagement'
import AdminItemManagement from './Pages/AdminItemManagement'
import AdminBookingManagement from './Pages/AdminBookingManagement'
import AdminInventoryManagement from './Pages/AdminInventoryManagement'
import Wishlist from './Pages/Wishlist'

import ProtectedAdminRoute from './Components/ProtectedAdminRoute'
import ProtectedUserRoute from './Components/ProtectedUserRoute'
import { WishlistProvider } from './Context/WishlistContext'

function App() {
  useEffect(() => {
    initAuthSession().catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <WishlistProvider><NotificationProvider>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<Home />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/items/:id" element={<ItemDetails />} />
          <Route path="/request-booking/:id" element={<RequestBooking />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/login" element={<Login />} />
          <Route path="/forget-password" element={<ForgetPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/admin/login" element={<AdminLogin />} />

          {/* Protected User Account Routes */}
          <Route element={<ProtectedUserRoute />}>
            <Route path="/my-listings" element={<MyListings />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/edit-profile" element={<EditProfile />} />
            <Route path="/my-address" element={<MyAddress />} />
            <Route path="/wishlist" element={<Wishlist />} />
            <Route path="/bookings" element={<MyBookings />} />
            <Route path="/bookings/:id" element={<BookingDetails />} />
            <Route path="/booking-success" element={<BookingSuccess />} />
            <Route path="/report-problem/:id" element={<ReportProblem />} />
            <Route path="/host-hub" element={<HostHub />} />
            <Route path="/list-item" element={<ListItem />} />
          </Route>

          {/* Protected Admin Routes */}
          <Route element={<ProtectedAdminRoute />}>
            <Route path="/admin/users" element={<UserManagement />} />
            <Route path="/admin/categories" element={<AdminCategoryManagement />} />
            <Route path="/admin/items" element={<AdminItemManagement />} />
            <Route path="/admin/bookings" element={<AdminBookingManagement />} />
            <Route path="/admin/inventory" element={<AdminInventoryManagement />} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </NotificationProvider></WishlistProvider>
    </BrowserRouter>
  )
}

export default App
