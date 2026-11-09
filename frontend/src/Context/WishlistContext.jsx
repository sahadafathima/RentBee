import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { getWishlist, toggleWishlistApi, removeFromWishlistApi } from '../services/api'
import { getAccessToken } from '../services/authentication'

const WishlistContext = createContext(null)

export function WishlistProvider({ children }) {
  const navigate = useNavigate()
  const [wishlistItems, setWishlistItems] = useState([])
  const [wishlistItemIds, setWishlistItemIds] = useState(() => new Set())
  const [wishlistCount, setWishlistCount] = useState(0)
  const [loading, setLoading] = useState(() => Boolean(getAccessToken()))
  const [reloadToken, setReloadToken] = useState(0)

  // Track in-flight items to prevent double-click race conditions
  const pendingRef = useRef(new Set())
  const [pendingItemIds, setPendingItemIds] = useState(() => new Set())

  const refreshWishlist = useCallback(() => {
    setReloadToken((t) => t + 1)
  }, [])

  useEffect(() => {
    let isCurrent = true
    const token = getAccessToken()
    if (!token) {
      return
    }

    getWishlist()
      .then((data) => {
        if (!isCurrent) return
        const results = Array.isArray(data?.results) ? data.results : []
        const ids = new Set(
          Array.isArray(data?.item_ids) ? data.item_ids : results.map((r) => r.item?.id).filter(Boolean)
        )
        setWishlistItems(results)
        setWishlistItemIds(ids)
        setWishlistCount(typeof data?.count === 'number' ? data.count : results.length)
      })
      .catch((err) => {
        if (!isCurrent) return
        console.error('Failed to load wishlist:', err)
      })
      .finally(() => {
        if (isCurrent) setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [reloadToken])

  const isWishlisted = useCallback(
    (itemId) => {
      if (!itemId) return false
      return wishlistItemIds.has(Number(itemId))
    },
    [wishlistItemIds]
  )

  const isPending = useCallback(
    (itemId) => {
      if (!itemId) return false
      return pendingItemIds.has(Number(itemId))
    },
    [pendingItemIds]
  )

  const toggleWishlist = useCallback(
    async (item) => {
      if (!item || !item.id) return

      const token = getAccessToken()
      if (!token) {
        if (typeof window !== 'undefined' && window.location) {
          const currentPath = window.location.pathname + window.location.search
          if (!currentPath.includes('/login')) {
            sessionStorage.setItem('rentbee_redirect_after_login', currentPath)
          }
        }
        navigate('/login')
        return
      }

      const itemId = Number(item.id)

      // Guard against rapid duplicate clicks while request is in-flight
      if (pendingRef.current.has(itemId)) {
        return
      }

      pendingRef.current.add(itemId)
      setPendingItemIds(new Set(pendingRef.current))

      const currentlyWishlisted = wishlistItemIds.has(itemId)

      // Optimistic update
      setWishlistItemIds((prev) => {
        const next = new Set(prev)
        if (currentlyWishlisted) {
          next.delete(itemId)
        } else {
          next.add(itemId)
        }
        return next
      })

      setWishlistCount((prev) => Math.max(0, currentlyWishlisted ? prev - 1 : prev + 1))

      if (currentlyWishlisted) {
        setWishlistItems((prev) => prev.filter((entry) => entry.item?.id !== itemId))
      } else {
        const tempEntry = {
          id: `temp-${itemId}-${Date.now()}`,
          created_at: new Date().toISOString(),
          item: item,
        }
        setWishlistItems((prev) => [tempEntry, ...prev])
      }

      try {
        const res = await toggleWishlistApi(itemId)
        if (typeof res?.count === 'number') {
          setWishlistCount(res.count)
        }
      } catch (err) {
        console.error('Failed to toggle wishlist on backend:', err)
        // Rollback optimistic update on error
        setWishlistItemIds((prev) => {
          const next = new Set(prev)
          if (currentlyWishlisted) {
            next.add(itemId)
          } else {
            next.delete(itemId)
          }
          return next
        })
        setWishlistCount((prev) => (currentlyWishlisted ? prev + 1 : Math.max(0, prev - 1)))
        refreshWishlist()
      } finally {
        pendingRef.current.delete(itemId)
        setPendingItemIds(new Set(pendingRef.current))
      }
    },
    [navigate, wishlistItemIds, refreshWishlist]
  )

  const removeFromWishlist = useCallback(
    async (itemId) => {
      if (!itemId) return
      const id = Number(itemId)

      // Guard against rapid duplicate clicks while request is in-flight
      if (pendingRef.current.has(id)) {
        return
      }

      pendingRef.current.add(id)
      setPendingItemIds(new Set(pendingRef.current))

      // Optimistic remove
      setWishlistItemIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
      setWishlistCount((prev) => Math.max(0, prev - 1))
      setWishlistItems((prev) => prev.filter((entry) => entry.item?.id !== id))

      try {
        const res = await removeFromWishlistApi(id)
        if (typeof res?.count === 'number') {
          setWishlistCount(res.count)
        }
      } catch (err) {
        console.error('Failed to remove from wishlist:', err)
        refreshWishlist()
      } finally {
        pendingRef.current.delete(id)
        setPendingItemIds(new Set(pendingRef.current))
      }
    },
    [refreshWishlist]
  )

  const value = useMemo(
    () => ({
      wishlistItems,
      wishlistItemIds,
      wishlistCount,
      loading,
      isWishlisted,
      isPending,
      toggleWishlist,
      removeFromWishlist,
      refreshWishlist,
    }),
    [
      wishlistItems,
      wishlistItemIds,
      wishlistCount,
      loading,
      isWishlisted,
      isPending,
      toggleWishlist,
      removeFromWishlist,
      refreshWishlist,
    ]
  )

  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWishlist() {
  const context = useContext(WishlistContext)
  if (!context) {
    throw new Error('useWishlist must be used within a WishlistProvider')
  }
  return context
}
