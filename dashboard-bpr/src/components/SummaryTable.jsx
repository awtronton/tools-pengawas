function SummaryTable({ data }) {
  const latestByBpr = {}

  data.forEach((item) => {
    latestByBpr[item.bpr_name] = item
  })

  const rows = Object.values(latestByBpr)

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
      <div className="p-4 border-b border-slate-200">
        <h2 className="text-sm font-bold text-slate-800">
          Ringkasan Kinerja BPR
        </h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-4 py-3">BPR</th>
              <th className="text-right px-4 py-3">Aset</th>
              <th className="text-right px-4 py-3">Kredit</th>
              <th className="text-right px-4 py-3">NPL</th>
              <th className="text-right px-4 py-3">ROA</th>
              <th className="text-right px-4 py-3">CAR</th>
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => (
              <tr
                key={row.bpr_name}
                className="border-t border-slate-100"
              >
                <td className="px-4 py-3 font-semibold text-slate-800">
                  {row.bpr_name}
                </td>

                <td className="px-4 py-3 text-right">
                  {row.aset?.toLocaleString('id-ID')}
                </td>

                <td className="px-4 py-3 text-right">
                  {row.kredit?.toLocaleString('id-ID')}
                </td>

                <td className="px-4 py-3 text-right">
                  {row.npl_gross}%
                </td>

                <td className="px-4 py-3 text-right">
                  {row.roa}%
                </td>

                <td className="px-4 py-3 text-right">
                  {row.car}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default SummaryTable