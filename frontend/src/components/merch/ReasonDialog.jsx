import { useState } from 'react'
import Modal from '../Modal'

// Confirm an action, optionally asking for a reason/note.
export default function ReasonDialog({ title, text, label, required, button, tone, busy, onClose, onConfirm }) {
  const [reason, setReason] = useState('')
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onConfirm(reason.trim()) }}>
        {text && <p className="muted">{text}</p>}
        {label && (
          <label className="field" style={{ marginTop: 12 }}>
            <span>{label}{required ? ' *' : ''}</span>
            <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} required={required} autoFocus />
          </label>
        )}
        <div className="modal-foot">
          <span />
          <div>
            <button type="button" className="secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className={tone || ''} disabled={busy || (required && !reason.trim())}>{busy ? 'Working…' : button}</button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
