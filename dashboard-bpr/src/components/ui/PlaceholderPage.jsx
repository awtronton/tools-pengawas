import {
  Construction,
} from 'lucide-react'

import DashboardLayout from '../../layouts/DashboardLayout'

function PlaceholderPage({
  title,
  description,
  module,
}) {
  return (
    <DashboardLayout>
      <main className="mx-auto w-full max-w-6xl">
        <section className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
              <Construction size={21} />
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                {module}
              </p>

              <h1 className="mt-1 text-xl font-bold text-slate-800">
                {title}
              </h1>

              <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-500">
                {description}
              </p>

              <span className="mt-4 inline-flex rounded-full bg-slate-100 px-3 py-1.5 text-[10px] font-bold text-slate-500">
                Coming Next
              </span>
            </div>
          </div>
        </section>
      </main>
    </DashboardLayout>
  )
}

export default PlaceholderPage
