import { useState } from 'react'
import api, { errorMessage } from '../../api/client'
import FormField from '../FormField'
import Modal from '../Modal'
import { DEPARTMENTS, labelOf, opts } from './constants'

const FIELDS = [
  { name: 'name', label: 'Name', required: true },
  { name: 'designation', label: 'Designation' },
  { name: 'department', label: 'Department', type: 'select', options: opts(DEPARTMENTS), required: true },
  { name: 'email', label: 'Email', type: 'email' },
  { name: 'phone', label: 'Phone' },
  { name: 'is_primary', label: 'Primary contact (receives quotations and invoices)', type: 'checkbox', full: true },
]

export default function ContactsTab({ buyer, editable, onChanged }) {
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setError('')
    try {
      if (form.id) await api.put(`/buyer-contacts/${form.id}/`, form)
      else await api.post('/buyer-contacts/', { ...form, buyer: buyer.id })
      setForm(null)
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!window.confirm(`Remove ${form.name}?`)) return
    try {
      await api.delete(`/buyer-contacts/${form.id}/`)
      setForm(null)
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      <div className="card-head">
        <div>
          <h2>Contact details</h2>
          <p className="muted small">Merchandising, sourcing, QA and accounts people at the buyer. One must be primary with an email.</p>
        </div>
        {editable && <button onClick={() => { setError(''); setForm({ department: 'merchandising', is_primary: buyer.contacts.length === 0 }) }}>+ Add contact</button>}
      </div>

      {buyer.contacts.length === 0 ? (
        <div className="empty-state">No contacts yet. Add the person you deal with day to day first — they become the primary contact.</div>
      ) : (
        <div className="contact-grid">
          {buyer.contacts.map((c) => (
            <button key={c.id} type="button" className={`contact-card ${c.is_primary ? 'primary' : ''}`}
              onClick={() => editable && (setError(''), setForm({ ...c }))} disabled={!editable}>
              <div className="contact-top">
                <span className="avatar">{c.name.split(' ').map((p) => p[0]).slice(0, 2).join('')}</span>
                <div>
                  <b>{c.name}</b>
                  <div className="muted small">{[c.designation, labelOf(DEPARTMENTS, c.department)].filter(Boolean).join(' · ')}</div>
                </div>
                {c.is_primary && <span className="badge badge-b-approved">Primary</span>}
              </div>
              <div className="small">{c.email || <span className="muted">No email</span>}</div>
              <div className="small">{c.phone || <span className="muted">No phone</span>}</div>
            </button>
          ))}
        </div>
      )}

      {form && (
        <Modal title={form.id ? 'Edit contact' : 'Add contact'} onClose={() => setForm(null)}>
          <form onSubmit={save}>
            <div className="form-grid">
              {FIELDS.map((f) => (
                <FormField key={f.name} field={f} value={form[f.name]} onChange={(name, v) => setForm((p) => ({ ...p, [name]: v }))} />
              ))}
            </div>
            <p className="muted small">Give at least an email or a phone number.</p>
            {error && <div className="error">{error}</div>}
            <div className="modal-foot">
              {form.id ? <button type="button" className="danger" onClick={remove}>Remove</button> : <span />}
              <div>
                <button type="button" className="secondary" onClick={() => setForm(null)}>Cancel</button>
                <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
