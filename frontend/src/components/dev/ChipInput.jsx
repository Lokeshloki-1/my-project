import { useState } from 'react'

// Edit a short list of words (sizes, colourways): type and press Enter or comma to add.
export default function ChipInput({ label, value, onChange, disabled, placeholder }) {
  const [text, setText] = useState('')
  const add = () => {
    const parts = text.split(',').map((t) => t.trim()).filter(Boolean)
    const next = [...value]
    parts.forEach((p) => { if (!next.includes(p)) next.push(p) })
    onChange(next)
    setText('')
  }
  return (
    <div className="field full">
      <span>{label}</span>
      <div className="chip-input">
        {value.map((v) => (
          <span key={v} className="chip on">
            {v}
            {!disabled && <button type="button" className="chip-x" onClick={() => onChange(value.filter((x) => x !== v))} aria-label={`Remove ${v}`}>×</button>}
          </span>
        ))}
        {!disabled && (
          <input value={text} placeholder={value.length ? '' : placeholder} aria-label={label}
            onChange={(e) => setText(e.target.value)} onBlur={() => text.trim() && add()}
            onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ',') && text.trim()) { e.preventDefault(); add() } }} />
        )}
      </div>
    </div>
  )
}
