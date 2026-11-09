
import { apiRequest } from './authentication'

// PROFILE API

export function getUserProfile() {
  return apiRequest('/profile/')
}

// Change Password API
export function changePassword(passwordData) {
  return apiRequest('/profile/change-password/', {
    method: 'POST',
    body: JSON.stringify(passwordData),
  })
}

export function updateUserProfile(formData) {
  return apiRequest('/profile/', {
    method: 'PATCH',
    body: formData,
  })
}

// Email Change OTP API
export function sendEmailChangeOTP(email) {
  return apiRequest('/profile/email-change/send-otp/', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function verifyEmailChangeOTP(otp) {
  return apiRequest('/profile/email-change/verify-otp/', {
    method: 'POST',
    body: JSON.stringify({ otp }),
  })
}


// ADDRESS API

export function createAddress(addressData) {
  return apiRequest('/addresses/', {
    method: 'POST',
    body: JSON.stringify(addressData),
  })
}

export function getAddresses() {
  return apiRequest('/addresses/')
}

export function updateAddress(id, addressData) {
  return apiRequest(`/addresses/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(addressData),
  })
}

export function deleteAddress(id) {
  return apiRequest(`/addresses/${id}/`, {
    method: 'DELETE',
  })
}

// Get all users with search and pagination
export function getAdminUsers(params = {}) {
  const query = new URLSearchParams(params).toString()

  return apiRequest(
    `/admin/users/${query ? `?${query}` : ''}`
  )
}

// Get individual user details
export function getAdminUserDetails(userId) {
  return apiRequest(`/admin/users/${userId}/`)
}

// Block or unblock a user
export function updateAdminUserStatus(userId, action) {
  return apiRequest(`/admin/users/${userId}/status/`, {
    method: 'PATCH',
    body: JSON.stringify({ action }),
  })
}

// CATEGORY MANAGEMENT API (Admin)
export function getAdminCategories(params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
  return apiRequest(`/admin/categories/${q ? `?${q}` : ''}`)
}

export function createCategory(payload) {
  return apiRequest('/admin/categories/', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateCategory(id, payload) {
  return apiRequest(`/admin/categories/${id}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function softDeleteCategory(id) {
  return apiRequest(`/admin/categories/${id}/delete/`, { method: 'POST' })
}

// ITEM MANAGEMENT API (Admin)
export function getAdminItems(params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== '')).toString()
  return apiRequest(`/admin/items/${q ? `?${q}` : ''}`)
}

export function getAdminItem(id) {
  return apiRequest(`/admin/items/${id}/`)
}

export function createAdminItem(formData) {
  return apiRequest('/admin/items/', {
    method: 'POST',
    body: formData,
  })
}

export function updateAdminItem(id, formData) {
  return apiRequest(`/admin/items/${id}/`, {
    method: 'PATCH',
    body: formData,
  })
}

export function softDeleteAdminItem(id) {
  return apiRequest(`/admin/items/${id}/delete/`, {
    method: 'POST',
  })
}

// PUBLIC ITEMS & CATEGORIES API (Customer Frontend)
export function getPublicCategories() {
  return apiRequest('/categories/')
}

export function getPublicItems(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return apiRequest(`/items/${q ? `?${q}` : ''}`)
}

export function getPublicItem(id) {
  return apiRequest(`/items/${id}/`)
}

// ==========================================
// BOOKINGS & RENTALS API
// ==========================================

export function getMyBookings(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return apiRequest(`/bookings/my-bookings/${q ? `?${q}` : ''}`)
}

export function getBookingDetails(id) {
  return apiRequest(`/bookings/${id}/`)
}

export function createBooking(payload) {
  return apiRequest('/bookings/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function cancelBooking(id, reason = '') {
  return apiRequest(`/bookings/${id}/cancel/`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function ownerApproveBooking(id) {
  return apiRequest(`/bookings/${id}/approve/`, {
    method: 'POST',
  })
}

export function ownerRejectBooking(id, reason = '') {
  return apiRequest(`/bookings/${id}/reject/`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function confirmPickup(id) {
  return apiRequest(`/bookings/${id}/confirm-pickup/`, {
    method: 'POST',
  })
}

export function confirmReturn(id) {
  return apiRequest(`/bookings/${id}/confirm-return/`, {
    method: 'POST',
  })
}

export function reportBookingProblem(id, description) {
  return apiRequest(`/bookings/${id}/report-problem/`, {
    method: 'POST',
    body: JSON.stringify({ description }),
  })
}

export function getHostBookings(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return apiRequest(`/bookings/host/requests/${q ? `?${q}` : ''}`)
}

export function getHostReports() {
  return apiRequest('/bookings/host/reports/')
}

export function checkItemAvailability(itemId, startDate, endDate) {
  return apiRequest(`/bookings/check-availability/?item_id=${itemId}&start_date=${startDate}&end_date=${endDate}`)
}

export function requestAvailabilityNotification(itemId, startDate, endDate) {
  return apiRequest('/bookings/notify-availability/', {
    method: 'POST',
    body: JSON.stringify({
      item_id: itemId,
      start_date: startDate,
      end_date: endDate,
    }),
  })
}

export function getUserNotifications() {
  return apiRequest('/bookings/notifications/')
}

export function markNotificationRead(id) {
  return apiRequest(`/bookings/notifications/${id}/mark-read/`, {
    method: 'POST',
  })
}

export function markAllNotificationsRead() {
  return apiRequest('/bookings/notifications/mark-all-read/', {
    method: 'POST',
  })
}

// ==========================================
// WISHLIST API
// ==========================================

export function getWishlist() {
  return apiRequest('/wishlist/')
}

export function toggleWishlistApi(itemId) {
  return apiRequest('/wishlist/toggle/', {
    method: 'POST',
    body: JSON.stringify({ item_id: itemId }),
  })
}

export function addToWishlistApi(itemId) {
  return apiRequest('/wishlist/', {
    method: 'POST',
    body: JSON.stringify({ item_id: itemId }),
  })
}

export function removeFromWishlistApi(itemId) {
  return apiRequest(`/wishlist/${itemId}/`, {
    method: 'DELETE',
  })
}


