import { useState } from 'react'
import api, { errorMessage } from '../../api/client'
import FormField from '../FormField'
import { BUYER_TYPES, INCOTERMS, opts } from './constants'

const SECTIONS = [
  ['Registration', [
    { name: 'legal_name', label: 'Legal name', required: true },
    { name: 'trade_name', label: 'Trade / brand name' },
    { name: 'buyer_type', label: 'Buyer type', type: 'select', options: opts(BUYER_TYPES), required: true },
    { name: 'country', label: 'Country', required: true },
  ]],
  ['Company profile', [
    { name: 'city', label: 'City', required: true },
    { name: 'tax_id', label: 'Tax / VAT ID' },
    { name: 'website', label: 'Website', type: 'url' },
    { name: 'year_established', label: 'Year established', type: 'number' },
    { name: 'annual_turnover', label: 'Annual turnover', type: 'number' },
    { name: 'bank_name', label: 'Bank' },
    { name: 'address', label: 'Registered address', type: 'textarea', full: true, required: true },
  ]],
  ['Trade terms', [
    { name: 'preferred_currency', label: 'Preferred currency', required: true },
    { name: 'default_incoterm', label: 'Default incoterm', type: 'select', options: opts(INCOTERMS), required: true },
    { name: 'notes', label: 'Notes', type: 'textarea', full: true },
  ]],
]
const FIELD_NAMES = SECTIONS.flatMap(([, fields]) => fields.map((f) => f.name))

export default function ProfileTab({ buyer, editable, onSaved }) {
  const [form, setForm] = useState(() => Object.fromEntries(FIELD_NAMES.map((n) => [n, buyer[n]])))
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setError(''); setSaved(false)
    // Empty optional numbers must go as null, not "".
    const body = { ...form, year_established: form.year_established || null, annual_turnover: form.annual_turnover || null }
    try {
      const { data } = await api.patch(`/buyers/${buyer.id}/`, body)
      onSaved(data)
      setSaved(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save}>
      <fieldset className="plain" disabled={!editable}>
        {SECTIONS.map(([title, fields]) => (
          <div key={title} className="form-section">
            <h3>{title}</h3>
            <div className="form-grid">
              {fields.map((f) => (
                <FormField key={f.name} field={f} value={form[f.name]}
                  onChange={(name, v) => { setSaved(false); setForm((prev) => ({ ...prev, [name]: v })) }} />
              ))}
            </div>
          </div>
        ))}
      </fieldset>
      {error && <div className="error">{error}</div>}
      {editable ? (
        <div className="form-actions">
          {saved && <span className="pos small">✓ Saved</span>}
          <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</button>
        </div>
      ) : (
        <p className="muted small">The profile is locked in this status.</p>
      )}
    </form>
  )
}
