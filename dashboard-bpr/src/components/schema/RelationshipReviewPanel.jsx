import { useEffect, useRef, useState } from 'react'
import {
  decideRelationshipCandidate, getRelationshipAnalysisJob, getRelationshipCandidates,
  getRelationshipReview, getRelationshipReviewHistory, queueRelationshipAnalysis,
} from '../../services/dataWarehouseService'
import '../../styles/relationship-review.css'

const cardinalities = {
  one_to_one: '1:1', one_to_many: '1:N', many_to_one: 'N:1', many_to_many: 'N:N',
}
const percent = value => value == null ? 'Belum tersedia' : `${(value * 100).toFixed(1)}%`
const pairLabel = c => `${c.source_table}.${c.source_column} ↔ ${c.target_table}.${c.target_column}`
const tablePair = c => [c.source_table, c.target_table].sort().join('|')
const describe = value => value.replaceAll('_', ' ')

export default function RelationshipReviewPanel({ onPromoted }) {
  const [candidates, setCandidates] = useState([])
  const [status, setStatus] = useState('pending')
  const [ids, setIds] = useState([])
  const [reviewData, setReviewData] = useState(null)
  const [history, setHistory] = useState([])
  const [nextHistory, setNextHistory] = useState(null)
  const [reviewer, setReviewer] = useState('')
  const [note, setNote] = useState('')
  const [name, setName] = useState('')
  const [cardinality, setCardinality] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loadedListKey, setLoadedListKey] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [refresh, setRefresh] = useState(0)
  const reviewKey = JSON.stringify([ids, refresh])
  const listKey = JSON.stringify([status, refresh])
  const detail = reviewData?.key === reviewKey ? reviewData.detail : null
  const loading = ids.length > 0 && reviewData?.key !== reviewKey
  const listLoading = loadedListKey !== listKey
  const request = useRef(null)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  useEffect(() => {
    let cancelled = false
    getRelationshipCandidates(status).then(result => {
      if (!cancelled) setCandidates(result.candidates)
    }).catch(err => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoadedListKey(listKey) })
    return () => { cancelled = true }
  }, [status, refresh, listKey])

  useEffect(() => {
    let cancelled = false
    if (!ids.length) return () => { cancelled = true }
    Promise.all([getRelationshipReview(ids[0], ids), getRelationshipReviewHistory(ids[0])])
      .then(([result, past]) => {
        if (cancelled) return
        setReviewData({ key: reviewKey, detail: result })
        setConfirmed(false)
        setHistory(past.reviews)
        setNextHistory(past.next_before_id)
        const anchor = result.candidates.find(s => s.candidate.id === ids[0])
        setCardinality(anchor.cardinality_estimate?.estimated_cardinality || '')
      }).catch(err => { if (!cancelled) { setError(err.message); setReviewData({ key: reviewKey, detail: null }) } })
    return () => { cancelled = true }
  }, [ids, refresh, reviewKey])

  function selectCandidate(candidate) {
    setError('')
    setMessage('')
    setNote('')
    setName('')
    setConfirmed(false)
    request.current = null
    setIds(current => current.includes(candidate.id)
      ? current.filter(id => id !== candidate.id) : [...current, candidate.id])
  }

  const anchor = detail?.candidates.find(s => s.candidate.id === ids[0])
  const composite = ids.length > 1
  const override = cardinality !== anchor?.cardinality_estimate?.estimated_cardinality
  const selectable = candidates.find(c => ids.includes(c.id))
  const decided = detail?.candidates.some(s => ['promoted', 'rejected'].includes(s.candidate.status))
  const ready = !!detail && !busy && !loading && !!reviewer.trim() && !decided
  const approveReady = ready && detail.can_approve && cardinality
    && (!composite || confirmed) && (!(composite || override) || note.trim())

  async function decide(decision) {
    const body = {
      candidate_ids: ids, expected_revision: detail.review_revision, reviewed_by: reviewer.trim(),
      review_note: note.trim(), relationship_name: name.trim() || null, cardinality,
      composite_cardinality_confirmed: confirmed,
    }
    const signature = JSON.stringify({ decision, body })
    if (request.current?.signature !== signature) request.current = { signature, key: crypto.randomUUID() }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await decideRelationshipCandidate(ids[0], decision, { ...body, request_key: request.current.key })
      if (!mounted.current) return
      setMessage(decision === 'approve'
        ? `Disetujui. Relationship #${result.review.promoted_relationship_id} tersedia di Designer dan SQL Builder.`
        : 'Ditolak. Keputusan tersimpan dalam riwayat; rekomendasi ditekan sampai evidence berubah secara material dan dianalisis ulang.')
      setRefresh(value => value + 1)
      if (decision === 'approve') await onPromoted()
    } catch (err) {
      if (mounted.current) {
        setError(err.message)
        if (err.status === 409) setRefresh(value => value + 1)
      }
    } finally { if (mounted.current) setBusy(false) }
  }

  async function reanalyse() {
    setBusy(true)
    setError('')
    try {
      const scope = { source_tables: [anchor.candidate.source_table, anchor.candidate.target_table],
        target_tables: [anchor.candidate.source_table, anchor.candidate.target_table],
        candidate_status: status, min_discovery_score: 0, max_candidates: 10000 }
      for (const kind of ['scoring', 'cardinality']) {
        setMessage(`Menjalankan ${kind} untuk candidate pada kedua tabel…`)
        let { job } = await queueRelationshipAnalysis(kind, { ...scope, min_quality_score: 0 })
        while (['queued', 'running'].includes(job.status)) {
          await new Promise(resolve => setTimeout(resolve, 1500))
          if (!mounted.current) return
          ;({ job } = await getRelationshipAnalysisJob(kind, job.id))
        }
        if (job.status === 'failed') throw new Error(job.error_message || 'Analisis gagal')
      }
      if (mounted.current) {
        setRefresh(value => value + 1)
        setMessage('Analisis selesai. Periksa freshness dan evidence sebelum mengambil keputusan.')
      }
    } catch (err) { if (mounted.current) setError(err.message) }
    finally { if (mounted.current) setBusy(false) }
  }

  async function moreHistory() {
    setBusy(true)
    try {
      const result = await getRelationshipReviewHistory(ids[0], nextHistory)
      setHistory(current => [...current, ...result.reviews])
      setNextHistory(result.next_before_id)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return <section className="tp-human-review" aria-label="Human Approval">
    <div className="tp-human-review-toolbar">
      <div><h2>Human Approval</h2><p>Tinjau evidence sebelum mempromosikan candidate menjadi relationship aktif.</p></div>
      <label>Status <select value={status} disabled={busy} onChange={event => {
        setStatus(event.target.value); setIds([]); setError(''); setMessage('')
      }}>
        <option value="pending">Menunggu review</option><option value="rejected">Ditolak</option>
        <option value="promoted">Dipromosikan</option><option value="stale">Stale</option>
      </select></label>
      <button type="button" disabled={busy || loading || listLoading} onClick={() => setRefresh(v => v + 1)}>Muat ulang</button>
    </div>
    {error && <p role="alert" className="tp-human-review-error">{error}</p>}
    {message && <p role="status" className="tp-human-review-message">{message}</p>}
    <div className="tp-human-review-table-wrap"><table>
      <thead><tr><th>Pilih</th><th>Candidate relationship</th><th>Discovery</th><th>Confidence</th><th>Cardinality</th><th>Status</th></tr></thead>
      <tbody>{candidates.map(c => <tr key={c.id}>
        <td><input type="checkbox" aria-label={`Review ${pairLabel(c)}`} checked={ids.includes(c.id)}
          disabled={busy || listLoading || (!ids.includes(c.id) && (ids.length >= 12 || (selectable && tablePair(selectable) !== tablePair(c))))}
          onChange={() => selectCandidate(c)} /></td>
        <td>{pairLabel(c)}</td><td>{percent(c.discovery_score)}</td><td>{percent(c.quality_score?.confidence_score)}</td>
        <td>{cardinalities[c.cardinality_estimate?.estimated_cardinality] || 'Belum tersedia'}</td>
        <td>{c.status}{c.is_stale ? ' · stale' : ''}</td>
      </tr>)}</tbody>
    </table></div>
    {listLoading && <p role="status">Memuat candidate…</p>}
    {!listLoading && !candidates.length && <p>Belum ada candidate untuk status ini. Jalankan profiling dan candidate discovery bila belum tersedia.</p>}
    {candidates.length === 2000 && <p>Menampilkan maksimal 2.000 candidate dengan discovery score tertinggi.</p>}
    <p>Pilih satu candidate, atau beberapa pasangan pada dua tabel yang sama untuk composite relationship (maksimal 12).</p>
    {loading && <p role="status">Memeriksa freshness dan versi evidence…</p>}
    {detail && <>
      <div className="tp-human-review-evidence">
        {detail.candidates.map(snapshot => {
          const { candidate: c, quality_score: score, cardinality_estimate: estimate } = snapshot
          const flags = [...new Set([...(score?.quality_flags || []), ...(estimate?.quality_flags || [])])]
          return <article key={c.id}>
            <h3>{pairLabel(c)}</h3>
            <p>Discovery {percent(c.discovery_score)} · Confidence {percent(score?.confidence_score)} ({score?.confidence_level || 'belum dinilai'})</p>
            <p>Estimasi {cardinalities[estimate?.estimated_cardinality] || 'belum tersedia'} · Keyakinan {percent(estimate?.cardinality_confidence)}</p>
            <p className={snapshot.freshness.is_fresh ? '' : 'tp-human-review-error'}>
              Freshness: {snapshot.freshness.is_fresh ? 'Fresh — versi selaras' : snapshot.freshness.reasons.map(describe).join('; ')}
            </p>
            {snapshot.approval_blockers.length > 0 && <p>Approval diblokir: {snapshot.approval_blockers.map(describe).join('; ')}</p>}
            {(snapshot.columns.source.masked || snapshot.columns.target.masked) && <p>Melibatkan masked column. Masking tetap berlaku.</p>}
            {flags.length > 0 && <ul>{flags.map(flag => <li key={flag}>{describe(flag)}</li>)}</ul>}
            <details><summary>Evidence dan versi</summary>
              {['source', 'target'].map(side => <p key={side}>
                {side}: profile v{c[`${side}_profile_version`]} / data v{c[`${side}_data_version`]} ·
                {' '}{snapshot.profiles[side]?.profile_mode || 'profil belum tersedia'} · non-null {snapshot.profiles[side]?.sample_non_null_count ?? '—'} ·
                {' '}distinct {snapshot.profiles[side]?.sample_distinct_count ?? '—'}
              </p>)}
              <p>Detector {c.detector_version}; scoring {score?.scoring_version || '—'}; estimator {estimate?.estimation_version || '—'}.</p>
              <p>Name similarity {percent(c.name_similarity)}; fingerprint overlap {percent(c.fingerprint_overlap)}.</p>
            </details>
          </article>
        })}
      </div>
      {!decided && <div className="tp-human-review-form">
        <p>Estimasi adalah bahan pertimbangan. Semua promosi memerlukan keputusan reviewer.</p>
        <button type="button" disabled={busy || loading || detail.candidates.some(s => s.freshness.reasons.some(r =>
          r.startsWith('source_') || r.startsWith('target_') || r === 'candidate_stale'))} onClick={reanalyse}>Hitung ulang skor dan cardinality</button>
        <p>Jika profile atau candidate stale, jalankan kembali profiling dan candidate discovery terlebih dahulu.</p>
        <label>Nama reviewer (identitas yang dinyatakan sendiri)<input value={reviewer} maxLength={180} disabled={busy} onChange={e => setReviewer(e.target.value)} /></label>
        <label>Nama relationship (opsional)<input value={name} maxLength={180} disabled={busy} onChange={e => setName(e.target.value)} /></label>
        <label>Cardinality yang disetujui<select value={cardinality} disabled={busy} onChange={e => { setCardinality(e.target.value); setConfirmed(false) }}>
          <option value="">Pilih cardinality</option>{Object.entries(cardinalities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        {composite && <label className="tp-human-review-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />
          Saya mengonfirmasi cardinality untuk seluruh composite key. Estimasi per kolom tidak membuktikan keunikan composite.
        </label>}
        <label>Catatan review (wajib untuk reject, composite, atau override)<textarea value={note} rows={3} maxLength={4000} disabled={busy} onChange={e => setNote(e.target.value)} /></label>
        <div className="tp-human-review-actions">
          <button type="button" className="tp-human-review-approve" disabled={!approveReady} onClick={() => decide('approve')}>Approve dan promosikan</button>
          <button type="button" disabled={!ready || !note.trim()} onClick={() => decide('reject')}>Reject</button>
        </div>
      </div>}
      <div className="tp-human-review-history"><h3>Riwayat keputusan candidate #{ids[0]}</h3>
        {!history.length && <p>Belum ada keputusan.</p>}
        {history.map(review => <article key={review.id}>
          <strong>{review.decision} · {review.reviewed_by}</strong>
          <p>{review.reviewed_at} · {review.reviewer_source === 'self_declared' ? 'Identitas dinyatakan sendiri' : review.reviewer_source}</p>
          <p>{review.review_note || 'Tanpa catatan'}</p>
          {review.promoted_relationship_id && <p>Relationship #{review.promoted_relationship_id}</p>}
          <details><summary>Evidence saat keputusan</summary>
            <p>Cardinality {cardinalities[review.confirmation.cardinality] || '—'}; composite {review.confirmation.composite ? 'ya' : 'tidak'}; override {review.confirmation.cardinality_overridden ? 'ya' : 'tidak'}.</p>
            {review.snapshot.candidates.map(s => <p key={s.candidate.id}>{pairLabel(s.candidate)} · discovery {percent(s.candidate.discovery_score)} · confidence {percent(s.quality_score?.confidence_score)} · estimasi {cardinalities[s.cardinality_estimate?.estimated_cardinality] || '—'} · profile v{s.candidate.source_profile_version}/v{s.candidate.target_profile_version} · data v{s.candidate.source_data_version}/v{s.candidate.target_data_version}</p>)}
          </details>
        </article>)}
        {nextHistory && <button type="button" disabled={busy} onClick={moreHistory}>Riwayat sebelumnya</button>}
      </div>
    </>}
  </section>
}
