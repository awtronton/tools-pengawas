import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  UploadCloud,
  Table2,
  Search,
  Settings2,
  BarChart3,
  Scale,
  Building2,
  FileText,
  FolderOpen,
  ShieldCheck,
  ChevronRight,
  X,
} from 'lucide-react'

function Sidebar({ isOpen = false, onClose = () => {} }) {
  const groups = [
    {
      title: 'Modul Pengawasan',
      items: [
        {
          name: 'Dashboard Utama',
          href: '/',
          icon: LayoutDashboard,
        },
      ],
    },
    {
      title: 'Data Warehouse',
      items: [
        {
          name: 'Upload Data',
          href: '/upload-data',
          icon: UploadCloud,
        },
        {
          name: 'Data Tables',
          href: '/data-tables',
          icon: Table2,
        },
        {
          name: 'Table Explorer',
          href: '/table-explorer',
          icon: Search,
        },
        {
          name: 'Schema Manager',
          href: '/schema-manager',
          icon: Settings2,
        },
      ],
    },
    {
      title: 'Analisis',
      items: [
        {
          name: 'Visualisasi',
          href: '/visualisasi',
          icon: BarChart3,
        },
        {
          name: 'Perbandingan',
          href: '/perbandingan',
          icon: Scale,
        },
        {
          name: 'Detail BPR',
          href: '/detail-bpr',
          icon: Building2,
        },
      ],
    },
    {
      title: 'Output',
      items: [
        {
          name: 'Laporan Pengawasan',
          href: '/laporan',
          icon: FileText,
        },
        {
          name: 'Dokumen',
          href: '/dokumen',
          icon: FolderOpen,
        },
      ],
    },
  ]

  return (
    <>
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-screen w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-900 text-slate-300 shadow-2xl transition-transform duration-300 md:relative ${
          isOpen
            ? 'translate-x-0'
            : '-translate-x-full md:translate-x-0'
        }`}
      >
        <div className="flex-1 overflow-y-auto">
          <div className="relative flex items-center justify-between border-b border-slate-800 px-5 py-5">
            <div className="absolute inset-y-0 left-0 w-1 bg-red-600" />

            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-red-500/30 bg-red-500/10 text-red-500">
                <ShieldCheck size={23} />
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <span className="font-extrabold tracking-wider text-white">
                    OJK
                  </span>

                  <span className="rounded bg-red-600 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
                    Core
                  </span>
                </div>

                <p className="mt-0.5 text-[11px] text-slate-400">
                  Data & Supervisory Analytics
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white md:hidden"
            >
              <X size={19} />
            </button>
          </div>

          <div className="space-y-6 px-3 py-5">
            {groups.map((group) => (
              <div key={group.title}>
                <div className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  {group.title}
                </div>

                <div className="space-y-1.5">
                  {group.items.map((item) => {
                    const Icon = item.icon

                    return (
                      <NavLink
                        key={item.href}
                        to={item.href}
                        onClick={onClose}
                        className={({ isActive }) =>
                          `group flex items-center justify-between rounded-xl px-3.5 py-3 text-xs font-semibold transition ${
                            isActive
                              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                              : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-100'
                          }`
                        }
                      >
                        {({ isActive }) => (
                          <>
                            <div className="flex items-center gap-3">
                              <div
                                className={`rounded-lg p-1.5 ${
                                  isActive
                                    ? 'bg-blue-500/30 text-white'
                                    : 'bg-slate-800 text-slate-400'
                                }`}
                              >
                                <Icon size={16} />
                              </div>

                              <span>{item.name}</span>
                            </div>

                            <ChevronRight
                              size={14}
                              className={`transition ${
                                isActive
                                  ? 'opacity-100'
                                  : 'opacity-0 group-hover:opacity-50'
                              }`}
                            />
                          </>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-slate-800 bg-slate-950 p-4">
          <div className="flex items-center justify-between text-[11px]">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="font-medium text-slate-300">
                Data Warehouse Ready
              </span>
            </div>

            <span className="font-mono text-[10px] text-slate-500">
              v1.0
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}

export default Sidebar