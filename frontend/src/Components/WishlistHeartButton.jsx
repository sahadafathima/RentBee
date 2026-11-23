import { Heart } from 'lucide-react'
import { useWishlist } from '../Context/WishlistContext'

export default function WishlistHeartButton({ item, className = '', size = 16 }) {
  const { isWishlisted, toggleWishlist, isPending } = useWishlist()
  const active = isWishlisted(item?.id)
  const pending = isPending(item?.id)

  const handleClick = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (pending) return
    toggleWishlist(item)
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={pending}
      aria-label={active ? `Remove ${item?.name} from wishlist` : `Add ${item?.name} to wishlist`}
      aria-busy={pending}
      title={active ? 'Remove from wishlist' : 'Save to wishlist'}
      className={`group/heart flex h-8 w-8 items-center justify-center rounded-full bg-white/90 shadow-xs backdrop-blur-xs transition hover:bg-white hover:scale-110 active:scale-95 ${
        pending ? 'cursor-wait opacity-80' : 'cursor-pointer'
      } ${className}`}
    >
      <Heart
        size={size}
        className={`transition-colors duration-150 ${
          active
            ? 'fill-[#D97745] text-[#D97745]'
            : 'text-[#9D4C29] group-hover/heart:text-[#D97745]'
        }`}
      />
    </button>
  )
}

