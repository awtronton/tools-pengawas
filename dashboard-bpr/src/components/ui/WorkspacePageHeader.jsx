import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

function WorkspacePageHeader({
  title,
  description,
  badge,
}) {
  const [portalTarget, setPortalTarget] =
    useState(null)

  useEffect(() => {
    setPortalTarget(
      document.getElementById(
        'vibe-shell-page-meta',
      ),
    )
  }, [])

  if (!portalTarget) {
    return null
  }

  return createPortal(
    <div
      className="tp-frozen-page-meta-content"
      aria-label={`${title} - informasi halaman`}
    >
      {badge && (
        <span className="tp-frozen-page-badge">
          {badge}
        </span>
      )}

      {description && (
        <span className="tp-frozen-page-description">
          {description}
        </span>
      )}
    </div>,
    portalTarget,
  )
}

export default WorkspacePageHeader
