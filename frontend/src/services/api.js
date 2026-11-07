
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
  const q = new URLSearchParams(Object.entries(params).filter(([_, v]) => v)).toString()
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
  const q = new URLSearchParams(Object.entries(params).filter(([_, v]) => v !== undefined && v !== '')).toString()
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

// PUBLIC ITEMS API (Customer Frontend)
export function getPublicItems(params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([_, v]) => v !== undefined && v !== '')).toString()
  return apiRequest(`/items/${q ? `?${q}` : ''}`)
}