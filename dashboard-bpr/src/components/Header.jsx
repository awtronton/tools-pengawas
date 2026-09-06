import { Menu, Bell, User } from 'lucide-react'

function Header({ onMenuClick }) {
  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4 md:px-6 sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="md:hidden p-2 rounded-lg text-slate-500 hover:bg-slate-100"
        >
          <Menu size={20} />
        </button>

        <div>
          <h2 className="text-sm md:text-base font-extrabold text-slate-800">
            Dashboard Pengawasan BPR
          </h2>

          <p className="hidden sm:block text-[10px] text-slate-400 font-medium mt-0.5">
            Sistem Monitoring dan Analisis Kinerja
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100">
          <Bell size={18} />
        </button>

        <div className="h-8 w-px bg-slate-200 hidden sm:block" />

        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center">
            <User size={17} className="text-slate-500" />
          </div>

          <div className="hidden sm:block leading-tight">
            <p className="text-xs font-bold text-slate-700">
              Administrator
            </p>

            <p className="text-[10px] text-slate-400">
              Pengawas
            </p>
          </div>
        </div>
      </div>
    </header>
  )
}

export default Header