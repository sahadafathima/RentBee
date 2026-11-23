
import { apiRequest, getAccessToken } from './authentication'

const API_BASE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
  'http://127.0.0.1:8000/api'


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

// BOOKING MANAGEMENT API (Admin)
export function getAdminBookings(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return apiRequest(`/admin/bookings/${q ? `?${q}` : ''}`)
}

export function getAdminBookingDetails(id) {
  return apiRequest(`/admin/bookings/${id}/`)
}

export function updateAdminBookingStatus(id, payload) {
  return apiRequest(`/admin/bookings/${id}/status/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function adminReturnAction(id, payload) {
  return apiRequest(`/admin/bookings/${id}/return-action/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// INVENTORY MANAGEMENT API (Admin)
export function getAdminInventory(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return apiRequest(`/admin/inventory/${q ? `?${q}` : ''}`)
}

export function updateAdminStock(id, stock) {
  return apiRequest(`/admin/inventory/${id}/stock/`, {
    method: 'PATCH',
    body: JSON.stringify({ stock }),
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

export function createItem(formData) {
  return apiRequest('/items/', {
    method: 'POST',
    body: formData,
  })
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

export function retryBookingRefund(id) {
  return apiRequest(`/bookings/${id}/retry-refund/`, {
    method: 'POST',
  })
}

export function confirmOfflineRefund(id) {
  return apiRequest(`/bookings/${id}/confirm-offline-refund/`, {
    method: 'POST',
  })
}

export function createPaymentOrder(bookingId) {
  return apiRequest(`/bookings/${bookingId}/create-payment-order/`, {
    method: 'POST',
  })
}

export function verifyPayment(bookingId, paymentData) {
  return apiRequest(`/bookings/${bookingId}/verify-payment/`, {
    method: 'POST',
    body: JSON.stringify(paymentData),
  })
}

export function confirmOfflineBookingPayment(id) {
  return apiRequest(`/bookings/${id}/confirm-offline-payment/`, {
    method: 'POST',
  })
}

export async function downloadBookingInvoice(id, bookingReference = '') {
  const token = getAccessToken()
  const response = await fetch(`${API_BASE_URL}/bookings/${id}/invoice/`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (!response.ok) {
    let errorMsg = 'Failed to download invoice / receipt.'
    try {
      const errJson = await response.json()
      if (errJson?.error) {
        errorMsg = errJson.error
      }
    } catch {
      // Fallback if response body is not valid JSON
    }
    throw new Error(errorMsg)
  }

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `RentBee_Invoice_${bookingReference || id}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
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

export function sendPickupOtp(id) {
  return apiRequest(`/bookings/${id}/send-pickup-otp/`, {
    method: 'POST',
  })
}

export function verifyPickupOtp(id, otp) {
  return apiRequest(`/bookings/${id}/verify-pickup-otp/`, {
    method: 'POST',
    body: JSON.stringify({ otp }),
  })
}

export function confirmPickup(id, otp) {
  return apiRequest(`/bookings/${id}/confirm-pickup/`, {
    method: 'POST',
    body: JSON.stringify({ otp }),
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

export function checkDiscountEligibility() {
  return apiRequest('/bookings/discount-eligibility/')
}

export function checkItemAvailability(itemId, startDate, endDate, requestedQuantity) {
  const quantity = requestedQuantity === undefined ? '' : `&requested_quantity=${requestedQuantity}`
  return apiRequest(`/bookings/check-availability/?item_id=${itemId}&start_date=${startDate}&end_date=${endDate}${quantity}`)
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
// WEB PUSH NOTIFICATIONS API
// ==========================================

export function getPushVapidKey() {
  return apiRequest('/bookings/push/vapid-key/')
}

export function savePushSubscription(subscriptionData) {
  return apiRequest('/bookings/push/subscribe/', {
    method: 'POST',
    body: JSON.stringify(subscriptionData),
  })
}

export function removePushSubscription(endpoint) {
  return apiRequest('/bookings/push/unsubscribe/', {
    method: 'POST',
    body: JSON.stringify({ endpoint }),
  })
}

export function sendTestPushNotification() {
  return apiRequest('/bookings/push/test/', {
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




export function getMyListings() {
  return apiRequest('/items/mine/')
}
export function getMyListing(id) {
  return apiRequest(`/items/mine/${id}/`)
}
export function updateMyListing(id, formData) {
  return apiRequest(`/items/mine/${id}/`, { method: 'PATCH', body: formData })
}
export function deactivateMyListing(id) {
  return apiRequest(`/items/mine/${id}/deactivate/`, { method: 'POST' })
}
