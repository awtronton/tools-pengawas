function WorkspacePageHeader({
  eyebrow,
  title,
  description,
  icon: Icon,
  badge,
}) {
  return (
    <section className="tp-workspace-page-header">
      <div className="tp-workspace-page-header-main">
        <div className="flex min-w-0 items-start gap-3">
          {Icon && (
            <div className="tp-workspace-page-header-icon">
              <Icon size={20} strokeWidth={1.9} />
            </div>
          )}

          <div className="min-w-0">
            <div className="tp-workspace-page-eyebrow">
              {eyebrow}
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-2">
              <h1 className="tp-workspace-page-title">
                {title}
              </h1>

              {badge && (
                <span className="tp-workspace-page-badge">
                  {badge}
                </span>
              )}
            </div>

            <p className="tp-workspace-page-description">
              {description}
            </p>
          </div>
        </div>
      </div>

      <div className="tp-workspace-page-tabs">
        <button
          type="button"
          className="tp-workspace-page-tab tp-workspace-page-tab--active"
        >
          Main
        </button>

        <button
          type="button"
          className="tp-workspace-page-tab"
          disabled
        >
          Activity
        </button>
      </div>
    </section>
  )
}

export default WorkspacePageHeader
