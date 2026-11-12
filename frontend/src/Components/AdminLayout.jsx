import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Users, LayoutGrid, Package, ChevronRight, LogOut, ExternalLink } from 'lucide-react'
import rentBeeLogo from '../assets/rentbee_logo.png'
import { userLogout } from '../services/authentication'

const NAV = [
  { path: '/admin/users', label: 'User Management', icon: Users },
  { path: '/admin/categories', label: 'Category Management', icon: LayoutGrid },
  { path: '/admin/items', label: 'Item Management', icon: Package },
]

export default function AdminLayout({ pageTitle = 'Overview', breadcrumbs = [], children }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()

  const handleAdminLogout = async () => {
    await userLogout()
    navigate('/admin/login')
  }

  return (
    <div className="min-h-screen bg-[#FAF5F0] text-[#302820] font-sans">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 bg-[#FAF5F0] z-50 flex flex-col py-6 px-4 border-r border-[#eee3da]">
        <Link to="/admin/users" className="flex items-center gap-3 px-2 mb-8">
          <img
            src={rentBeeLogo}
            alt="RentBee Logo"
            className="h-10 w-auto object-contain"
          />
        </Link>

        <nav className="flex-1 flex flex-col gap-1.5">
          {NAV.map(({ path, label, icon: Icon }) => {
            const isActive = pathname === path
            return (
              <Link
                key={path}
                to={path}
                className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm transition-all ${
                  isActive
                    ? 'bg-[#FFF0E7] text-[#9D4C29] font-semibold border border-orange-200/60 shadow-xs'
                    : 'text-[#51463d] hover:bg-white hover:text-[#302820]'
                }`}
              >
                <Icon size={18} className={isActive ? 'text-[#9D4C29]' : 'text-gray-400'} />
                <span>{label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="pt-4 border-t border-[#eee3da] flex flex-col gap-2">
          <Link
            to="/"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2.5 px-3.5 py-2 text-xs font-medium text-[#766B63] hover:text-[#302820] transition rounded-lg hover:bg-white"
          >
            <ExternalLink size={15} />
            <span>View Marketplace</span>
          </Link>
          <button
            type="button"
            onClick={handleAdminLogout}
            className="flex items-center gap-2.5 px-3.5 py-2 text-xs font-semibold text-red-600 hover:text-red-700 transition rounded-lg hover:bg-red-50 text-left w-full cursor-pointer"
          >
            <LogOut size={15} />
            <span>Sign Out Admin</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="pl-64">
        <header className="fixed top-0 left-64 right-0 h-16 bg-white/90 backdrop-blur-md shadow-xs z-40 flex items-center justify-between px-8 border-b border-[#eee3da]">
          <span className="text-xl font-bold text-[#302820]">{pageTitle}</span>
          <button
            type="button"
            onClick={handleAdminLogout}
            className="flex items-center gap-2 text-xs font-semibold text-gray-500 hover:text-red-600 transition"
          >
            <LogOut size={16} /> Logout
          </button>
        </header>

        <main className="pt-20 p-8 min-h-screen bg-[#FAF5F0]">
          {breadcrumbs.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-5">
              {breadcrumbs.map((b, i) => (
                <span key={b} className="flex items-center gap-1.5">
                  {i > 0 && <ChevronRight size={13} className="text-gray-400" />}
                  <span className={i === breadcrumbs.length - 1 ? 'text-[#9D4C29] font-medium' : ''}>{b}</span>
                </span>
              ))}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  )
}
