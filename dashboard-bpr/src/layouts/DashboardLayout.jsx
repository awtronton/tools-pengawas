import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart3,
  Bell,
  Building2,
  ChevronDown,
  Database,
  FileText,
  Files,
  GitCompareArrows,
  HelpCircle,
  LayoutDashboard,
  Menu,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings2,
  Table2,
  Upload,
  UserRound,
} from 'lucide-react'

import '../styles/vibe-shell.css'
import '../styles/vibe-typography.css'

const navigationGroups = [
  {
    label: 'Workspace',
    items: [
      {
        id: 'dashboard',
        label: 'Dashboard Utama',
        path: '/dashboard',
        icon: LayoutDashboard,
      },
    ],
  },
  {
    label: 'Data Warehouse',
    items: [
      {
        id: 'upload',
        label: 'Upload Data',
        path: '/upload',
        icon: Upload,
      },
      {
        id: 'tables',
        label: 'Data Tables',
        path: '/tables',
        icon: Table2,
      },
      {
        id: 'explorer',
        label: 'Table Explorer',
        path: '/explorer',
        icon: Database,
      },
      {
        id: 'schema',
        label: 'Schema Manager',
        path: '/schema',
        icon: Network,
      },
    ],
  },
  {
    label: 'Analysis',
    items: [
      {
        id: 'visualization',
        label: 'Visualisasi',
        path: '/visualization',
        icon: BarChart3,
      },
      {
        id: 'comparison',
        label: 'Perbandingan',
        path: '/comparison',
        icon: GitCompareArrows,
      },
      {
        id: 'detail-bank',
        label: 'Detail Bank',
        path: '/bank',
        icon: Building2,
      },
    ],
  },
  {
    label: 'Output',
    items: [
      {
        id: 'reports',
        label: 'Laporan Pengawasan',
        path: '/reports',
        icon: FileText,
      },
      {
        id: 'documents',
        label: 'Dokumen',
        path: '/documents',
        icon: Files,
      },
    ],
  },
]

const routeMeta = {
  '/dashboard': {
    activeItem: 'dashboard',
    section: 'Workspace',
    page: 'Dashboard Utama',
  },
  '/upload': {
    activeItem: 'upload',
    section: 'Data Warehouse',
    page: 'Upload Data',
  },
  '/tables': {
    activeItem: 'tables',
    section: 'Data Warehouse',
    page: 'Data Tables',
  },
  '/explorer': {
    activeItem: 'explorer',
    section: 'Data Warehouse',
    page: 'Table Explorer',
  },
  '/schema': {
    activeItem: 'schema',
    section: 'Data Warehouse',
    page: 'Schema Manager',
  },
  '/visualization': {
    activeItem: 'visualization',
    section: 'Analysis',
    page: 'Visualisasi',
  },
  '/comparison': {
    activeItem: 'comparison',
    section: 'Analysis',
    page: 'Perbandingan',
  },
  '/bank': {
    activeItem: 'detail-bank',
    section: 'Analysis',
    page: 'Detail Bank',
  },
  '/reports': {
    activeItem: 'reports',
    section: 'Output',
    page: 'Laporan Pengawasan',
  },
  '/documents': {
    activeItem: 'documents',
    section: 'Output',
    page: 'Dokumen',
  },
  '/input-data': {
    activeItem: null,
    section: 'Workspace',
    page: 'Input Data',
  },
}

function SidebarItem({
  item,
  activeItem,
  collapsed,
  onNavigate,
}) {
  const Icon = item.icon
  const isActive = activeItem === item.id

  return (
    <button
      type="button"
      className={`vibe-shell-nav-item ${
        isActive
          ? 'vibe-shell-nav-item--active'
          : ''
      }`}
      title={collapsed ? item.label : undefined}
      aria-current={isActive ? 'page' : undefined}
      onClick={() => onNavigate(item.path)}
    >
      <Icon
        size={18}
        strokeWidth={1.8}
        aria-hidden="true"
      />

      {!collapsed && (
        <span className="truncate">
          {item.label}
        </span>
      )}
    </button>
  )
}

function DashboardLayout({
  children,
  activeItem,
}) {
  const location = useLocation()
  const navigate = useNavigate()

  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  const searchPopoverRef = useRef(null)
  const searchInputRef = useRef(null)

  const currentRoute =
    routeMeta[location.pathname] ||
    routeMeta['/dashboard']

  const resolvedActiveItem =
    activeItem ?? currentRoute.activeItem


  useEffect(() => {
    if (!searchOpen) {
      return undefined
    }

    window.requestAnimationFrame(() => {
      searchInputRef.current?.focus()
    })

    function handlePointerDown(event) {
      if (
        searchPopoverRef.current &&
        !searchPopoverRef.current.contains(
          event.target,
        )
      ) {
        setSearchOpen(false)
      }
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setSearchOpen(false)
      }
    }

    document.addEventListener(
      'pointerdown',
      handlePointerDown,
    )
    document.addEventListener(
      'keydown',
      handleKeyDown,
    )

    return () => {
      document.removeEventListener(
        'pointerdown',
        handlePointerDown,
      )
      document.removeEventListener(
        'keydown',
        handleKeyDown,
      )
    }
  }, [searchOpen])

  function handleNavigate(path) {
    setMobileOpen(false)

    if (location.pathname !== path) {
      navigate(path)
    }
  }

  function canUseSidebarHover() {
    return window.matchMedia(
      '(hover: hover) and (pointer: fine) and (min-width: 821px)',
    ).matches
  }

  function handleSidebarMouseEnter() {
    if (canUseSidebarHover()) {
      setCollapsed(false)
    }
  }

  function handleSidebarMouseLeave() {
    if (canUseSidebarHover()) {
      setCollapsed(true)
    }
  }

  return (
    <div className="vibe-shell">
      {mobileOpen && (
        <button
          type="button"
          className="vibe-shell-backdrop"
          aria-label="Tutup menu"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`vibe-shell-sidebar ${
          collapsed
            ? 'vibe-shell-sidebar--collapsed'
            : ''
        } ${
          mobileOpen
            ? 'vibe-shell-sidebar--mobile-open'
            : ''
        }`}
        onMouseEnter={handleSidebarMouseEnter}
        onMouseLeave={handleSidebarMouseLeave}
      >
        <div className="vibe-shell-brand">
          <div className="vibe-shell-brand-mark">
            TP
          </div>

          {!collapsed && (
            <div className="min-w-0">
              <div className="vibe-shell-brand-title">
                Tools Pengawas
              </div>

              <div className="vibe-shell-brand-subtitle">
                Supervisory Workspace
              </div>
            </div>
          )}

          <button
            type="button"
            className="vibe-shell-icon-button vibe-shell-collapse"
            aria-label={
              collapsed
                ? 'Perbesar sidebar'
                : 'Perkecil sidebar'
            }
            onClick={() =>
              setCollapsed((value) => !value)
            }
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
          </button>
        </div>

        <div className="vibe-shell-sidebar-scroll">
          <button
            type="button"
            className={`vibe-shell-workspace-switcher ${
              collapsed ? 'is-collapsed' : ''
            }`}
          >
            <div className="vibe-shell-workspace-mark">
              P
            </div>

            {!collapsed && (
              <>
                <div className="min-w-0 flex-1 text-left">
                  <div className="truncate text-[12px] font-semibold">
                    Workspace Pengawasan
                  </div>

                  <div className="mt-0.5 truncate text-[10px] text-slate-400">
                    Data & Analytics
                  </div>
                </div>

                <ChevronDown
                  size={15}
                  className="text-slate-400"
                />
              </>
            )}
          </button>

          <nav
            className="vibe-shell-navigation"
            aria-label="Navigasi utama"
          >
            {navigationGroups.map((group) => (
              <div
                key={group.label}
                className="vibe-shell-nav-group"
              >
                {!collapsed && (
                  <div className="vibe-shell-nav-label">
                    {group.label}
                  </div>
                )}

                <div className="space-y-1">
                  {group.items.map((item) => (
                    <SidebarItem
                      key={item.id}
                      item={item}
                      activeItem={resolvedActiveItem}
                      collapsed={collapsed}
                      onNavigate={handleNavigate}
                    />
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </div>

        <div className="vibe-shell-sidebar-footer">
          <button
            type="button"
            className="vibe-shell-nav-item"
            title={collapsed ? 'Pengaturan' : undefined}
          >
            <Settings2
              size={18}
              strokeWidth={1.8}
            />

            {!collapsed && (
              <span>Pengaturan</span>
            )}
          </button>

          <div
            className={`vibe-shell-user ${
              collapsed ? 'is-collapsed' : ''
            }`}
          >
            <div className="vibe-shell-user-avatar">
              <UserRound size={15} />
            </div>

            {!collapsed && (
              <div className="min-w-0">
                <div className="truncate text-[11px] font-semibold">
                  Pengawas
                </div>

                <div className="truncate text-[10px] text-slate-400">
                  Tools Pengawas
                </div>
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="vibe-shell-main">
        <header className="vibe-shell-topbar">
          <div className="vibe-shell-frozen-page">
            <button
              type="button"
              className="vibe-shell-icon-button vibe-shell-mobile-menu"
              aria-label="Buka menu"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={19} />
            </button>

            <div className="vibe-shell-frozen-page-copy">
              <div className="vibe-shell-frozen-page-title">
                {currentRoute.page}
              </div>

              <div
                id="vibe-shell-page-meta"
                className="vibe-shell-frozen-page-meta"
              />
            </div>
          </div>

          <div className="vibe-shell-topbar-actions">
            <div className="vibe-shell-breadcrumb">
              <span>{currentRoute.section}</span>
              <span className="vibe-shell-breadcrumb-separator">
                /
              </span>
              <strong>{currentRoute.page}</strong>
            </div>

            <div
              ref={searchPopoverRef}
              className={`vibe-shell-search-anchor ${
                searchOpen
                  ? 'is-open'
                  : ''
              }`}
            >
              <button
                type="button"
                className={`vibe-shell-icon-button vibe-shell-search-trigger ${
                  searchOpen
                    ? 'is-active'
                    : ''
                }`}
                aria-label={
                  searchOpen
                    ? 'Tutup pencarian'
                    : 'Buka pencarian'
                }
                aria-expanded={searchOpen}
                onClick={() =>
                  setSearchOpen(
                    (value) => !value,
                  )
                }
              >
                <Search size={18} />
              </button>

              <div
                className="vibe-shell-search-popover"
                aria-hidden={!searchOpen}
              >
                <Search
                  size={17}
                  aria-hidden="true"
                />

                <input
                  ref={searchInputRef}
                  type="search"
                  placeholder="Cari tabel, bank, atau laporan..."
                  aria-label="Pencarian global"
                />

                <span className="vibe-shell-search-shortcut">
                  ⌘ K
                </span>
              </div>
            </div>

            <button
              type="button"
              className="vibe-shell-icon-button"
              aria-label="Bantuan"
            >
              <HelpCircle size={18} />
            </button>

            <button
              type="button"
              className="vibe-shell-icon-button vibe-shell-notification"
              aria-label="Notifikasi"
            >
              <Bell size={18} />
              <span className="vibe-shell-notification-dot" />
            </button>

            <div
              className="vibe-shell-topbar-avatar"
              aria-label="Profil Pengawas"
            >
              P
            </div>
          </div>
        </header>

        <div className="vibe-shell-content">
          {children}
        </div>
      </div>
    </div>
  )
}

export default DashboardLayout
