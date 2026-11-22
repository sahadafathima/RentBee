/**
 * Resolves a media image path or URL against the API backend origin.
 * Handles full URLs (http/https/data:), relative paths (/media/...),
 * and strips trailing /api from VITE_API_BASE_URL.
 */
export function resolveImageUrl(url) {
  if (!url || typeof url !== 'string') return null
  const trimmed = url.trim()
  if (!trimmed) return null
  if (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('data:')
  ) {
    return trimmed
  }
  const apiBase =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
    'http://127.0.0.1:8000/api'
  const origin = apiBase.replace(/\/api\/?$/, '')
  return `${origin}${trimmed.startsWith('/') ? '' : '/'}${trimmed}`
}

/**
 * Extracts and resolves the primary display image from an item object.
 */
export function getItemImageUrl(item) {
  if (!item) return null
  const src =
    item.primary_image_url ||
    item.primary_image ||
    (item.images && item.images[0]?.image)
  return resolveImageUrl(src)
}
