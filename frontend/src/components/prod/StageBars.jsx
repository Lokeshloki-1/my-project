import { pcs } from './constants'

// Cut / sewn / finished against the planned quantity.
export default function StageBars({ quantity, progress, compact }) {
  const rows = [['Cut', progress.cut], ['Sewn', progress.sewn], ['Finished', progress.finished]]
  return (
    <div className={`stage-bars ${compact ? 'compact' : ''}`}>
      {rows.map(([label, v]) => {
        const pct = quantity ? Math.min(100, (v / quantity) * 100) : 0
        return (
          <div key={label} className="stage-bar" title={`${label}: ${pcs(v)} of ${pcs(quantity)}`}>
            <span className="sb-label">{label}</span>
            <span className="sb-track"><span className={`sb-fill sb-${label.toLowerCase()}`} style={{ width: `${pct}%` }} /></span>
            <span className="sb-val">{compact ? `${Math.round(pct)}%` : `${pcs(v)} / ${pcs(quantity)}`}</span>
          </div>
        )
      })}
    </div>
  )
}
