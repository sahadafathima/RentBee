
function Button({
  children,
  type = 'button',
  onClick,
  disabled = false,
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-xl bg-[#9D4C29] px-4 py-3.5 font-semibold text-white transition hover:bg-[#813B20] focus:outline-none focus:ring-2 focus:ring-[#9D4C29] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {children}
    </button>
  )
}

export default Button
