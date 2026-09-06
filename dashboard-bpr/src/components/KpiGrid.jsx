function KpiGrid({ data }) {
  const latest = data[data.length - 1] || {}

  const formatRp = (value = 0) =>
    new Intl.NumberFormat('id-ID', {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)

  const cards = [
    {
      title: 'Total Aset',
      value: `Rp${formatRp(latest.aset)}`,
    },
    {
      title: 'Total Kredit',
      value: `Rp${formatRp(latest.kredit)}`,
    },
    {
      title: 'Total DPK',
      value: `Rp${formatRp(latest.dpk)}`,
    },
    {
      title: 'NPL Gross',
      value: `${latest.npl_gross || 0}%`,
    },
    {
      title: 'ROA',
      value: `${latest.roa || 0}%`,
    },
    {
      title: 'CAR',
      value: `${latest.car || 0}%`,
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
      {cards.map((card) => (
        <div
          key={card.title}
          className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm"
        >
          <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
            {card.title}
          </div>

          <div className="mt-2 text-lg font-extrabold text-slate-800">
            {card.value}
          </div>
        </div>
      ))}
    </div>
  )
}

export default KpiGrid