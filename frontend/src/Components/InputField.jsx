import { useState } from 'react'

function InputField({
  label,
  name,
  type = 'text',
  placeholder,
  value,
  onChange,
  required = true,
  autoComplete,
  showPasswordToggle = true,
}) {
  const [showPassword, setShowPassword] = useState(false)

  const isPassword = type === 'password'
  const showEyeIcon = isPassword && showPasswordToggle

  return (
    <div className="w-full">
      <label
        htmlFor={name}
        className="mb-2 block text-sm font-medium text-[#493329]"
      >
        {label}
      </label>

      <div className="relative">
        <input
          id={name}
          name={name}
          type={showEyeIcon && showPassword ? 'text' : type}
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          required={required}
          autoComplete={autoComplete}
          className={`w-full rounded-xl border border-[#E8DCD5] bg-[#FFFCFA] px-4 py-3 text-sm text-[#493329] outline-none transition placeholder:text-[#B3A29A] focus:border-[#9D4C29] focus:ring-2 focus:ring-[#9D4C29]/15 ${
            showEyeIcon ? 'pr-12' : ''
          }`}
        />

        {showEyeIcon && (
          <button
            type="button"
            onClick={() => setShowPassword((previous) => !previous)}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            aria-pressed={showPassword}
            className="absolute inset-y-0 right-3 flex items-center text-[#8B776D] hover:text-[#9D4C29] focus:outline-none"
          >
            {showPassword ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="21"
                height="21"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 3l18 18" />
                <path d="M10.6 10.6a2 2 0 002.8 2.8" />
                <path d="M9.9 5.2A11 11 0 0112 5c5 0 9 5 9 7a10 10 0 01-3 4.2" />
                <path d="M6.2 6.2C3.8 7.7 2 10 2 12c0 2 5 7 10 7a10 10 0 003.1-.5" />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="21"
                height="21"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            )}
          </button>
        )}
      </div>
    </div>
  )
}

export default InputField