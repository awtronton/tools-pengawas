import { Database } from 'lucide-react'
import DashboardLayout from '../layouts/DashboardLayout'
import KpiGrid from '../components/KpiGrid'
import SummaryTable from '../components/SummaryTable'
import TrendCharts from '../components/TrendCharts'
import ReviewPriority from '../components/ReviewPriority'

const dummyData = [
  {
    bpr_name: 'BPR Alpha',
    tahun: 2025,
    bulan: 12,
    aset: 125000000000,
    kredit: 95000000000,
    dpk: 90000000000,
    npl_gross: 4.2,
    roa: 2.4,
    car: 18.5,
  },
  {
    bpr_name: 'BPR Alpha',
    tahun: 2026,
    bulan: 6,
    aset: 132000000000,
    kredit: 101000000000,
    dpk: 96000000000,
    npl_gross: 5.1,
    roa: 2.1,
    car: 17.8,
  },
  {
    bpr_name: 'BPR Beta',
    tahun: 2025,
    bulan: 12,
    aset: 98000000000,
    kredit: 71000000000,
    dpk: 73000000000,
    npl_gross: 7.5,
    roa: 1.2,
    car: 15.4,
  },
  {
    bpr_name: 'BPR Beta',
    tahun: 2026,
    bulan: 6,
    aset: 95000000000,
    kredit: 69000000000,
    dpk: 70000000000,
    npl_gross: 9.4,
    roa: 0.7,
    car: 14.8,
  },
]

function Dashboard() {
  const minYear = Math.min(...dummyData.map((item) => item.tahun))
  const maxYear = Math.max(...dummyData.map((item) => item.tahun))

  const bprNames = [...new Set(dummyData.map((item) => item.bpr_name))]

  const bprList = bprNames.map((name, index) => ({
    id: `bpr-${index}`,
    name,
    evaluationNote: '',
    deepDiveArea: '',
  }))

  const totalBprCount = bprList.length
  const totalRecordsCount = dummyData.length

  return (
    <DashboardLayout>
      <main className="space-y-4 md:space-y-6 max-w-7xl mx-auto w-full">
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-3 text-slate-800">
            <div className="p-2.5 bg-blue-50 text-blue-600 rounded-xl shrink-0">
              <Database size={20} />
            </div>

            <div>
              <h3 className="text-[10px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">
                Modul Pengawasan Makro BPR
              </h3>

              <div className="text-xs sm:text-sm font-extrabold text-slate-800 leading-snug">
                Dashboard Analisis Keuangan Terpadu ({minYear} — {maxYear})
              </div>
            </div>
          </div>

          <div className="text-[11px] font-bold bg-slate-50 border border-slate-200 text-slate-600 px-3 py-1.5 rounded-xl w-full sm:w-auto text-center shrink-0">
            Data Dummy Aktif
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
          <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-sm">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
              Jumlah BPR Terdaftar
            </div>

            <div className="text-base sm:text-xl font-extrabold text-slate-800 mt-1">
              {totalBprCount} Entitas
            </div>
          </div>

          <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-sm">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
              Total Data Periode Masuk
            </div>

            <div className="text-base sm:text-xl font-extrabold text-slate-800 mt-1">
              {totalRecordsCount} Rekaman Laporan
            </div>
          </div>

          <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-sm">
            <div className="text-[10px] font-bold text-emerald-600 uppercase tracking-wide">
              Status Koneksi Database
            </div>

            <div className="text-base sm:text-xl font-extrabold text-emerald-600 mt-1">
              Mode Dummy
            </div>
          </div>
        </div>

        <KpiGrid
          startYear={minYear}
          endYear={maxYear}
          data={dummyData}
        />

        <SummaryTable
          startYear={minYear}
          endYear={maxYear}
          data={dummyData}
        />

        <TrendCharts
          bprList={bprList}
          startYear={minYear}
          endYear={maxYear}
          data={dummyData}
        />

        <ReviewPriority />
      </main>
    </DashboardLayout>
  )
}

export default Dashboard