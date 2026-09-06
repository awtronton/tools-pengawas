import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from 'recharts'

function TrendCharts({ data }) {
  const chartData = data.map((item) => ({
    periode: `${item.bulan}/${item.tahun}`,
    aset: item.aset / 1_000_000_000,
    kredit: item.kredit / 1_000_000_000,
  }))

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4">
      <div className="mb-4">
        <h2 className="text-sm font-bold text-slate-800">
          Tren Aset dan Kredit
        </h2>

        <p className="text-xs text-slate-400 mt-1">
          Dalam Rp miliar
        </p>
      </div>

      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="periode" />
            <YAxis />
            <Tooltip />
            <Legend />

            <Line
              type="monotone"
              dataKey="aset"
              stroke="#2563eb"
              strokeWidth={2}
            />

            <Line
              type="monotone"
              dataKey="kredit"
              stroke="#16a34a"
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default TrendCharts