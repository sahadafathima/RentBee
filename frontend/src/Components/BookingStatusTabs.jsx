import { Layers, PlayCircle, CheckCircle2, XCircle } from 'lucide-react'

export default function BookingStatusTabs({ activeTab, onTabChange, counts = {} }) {
  const tabs = [
    {
      id: 'all',
      label: 'All Bookings',
      count: counts.all ?? 0,
      icon: Layers,
      activeColor: 'border-[#9D4C29] bg-[#FFF5EE] text-[#9D4C29]',
      badgeColor: 'bg-[#9D4C29] text-white',
    },
    {
      id: 'active',
      label: 'Active',
      count: counts.active ?? 0,
      icon: PlayCircle,
      activeColor: 'border-[#D97745] bg-[#FFF9F5] text-[#D97745]',
      badgeColor: 'bg-[#D97745] text-white',
    },
    {
      id: 'completed',
      label: 'Completed',
      count: counts.completed ?? 0,
      icon: CheckCircle2,
      activeColor: 'border-emerald-600 bg-emerald-50 text-emerald-800',
      badgeColor: 'bg-emerald-600 text-white',
    },
    {
      id: 'cancelled',
      label: 'Cancelled',
      count: counts.cancelled ?? 0,
      icon: XCircle,
      activeColor: 'border-rose-500 bg-rose-50 text-rose-800',
      badgeColor: 'bg-rose-500 text-white',
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
      {tabs.map((tab) => {
        const Icon = tab.icon
        const isActive = activeTab === tab.id

        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onTabChange(tab.id)}
            className={`flex flex-col justify-between rounded-2xl border p-4 text-left transition-all duration-200 cursor-pointer shadow-xs ${
              isActive
                ? `${tab.activeColor} ring-2 ring-orange-200/50 shadow-sm scale-[1.01]`
                : 'border-orange-100 bg-white text-[#49362D] hover:border-orange-200 hover:bg-[#FFFDFB]'
            }`}
          >
            <div className="flex items-center justify-between">
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-xl ${
                  isActive ? 'bg-white/80' : 'bg-orange-50 text-[#D97745]'
                }`}
              >
                <Icon size={17} />
              </span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                  isActive ? tab.badgeColor : 'bg-orange-100/70 text-[#9D4C29]'
                }`}
              >
                {tab.count}
              </span>
            </div>

            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500">Status</p>
              <h3 className="text-sm font-bold sm:text-base">{tab.label}</h3>
            </div>
          </button>
        )
      })}
    </div>
  )
}

