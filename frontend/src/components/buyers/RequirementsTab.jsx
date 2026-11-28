import { useState } from 'react'
import api, { errorMessage } from '../../api/client'
import FormField from '../FormField'
import { CATEGORIES, CERTIFICATIONS } from './constants'

const EMPTY = {
  product_categories: [], certifications: [], fabric_composition: '', gsm_min: '', gsm_max: '', size_range: '',
  annual_volume: '', target_price_min: '', target_price_max: '', price_currency: 'USD', packaging: '', labelling: '',
  testing_lab: '', delivery_port: '', payment_terms_requested: '', notes: '',
}
const NUMBERS = ['gsm_min', 'gsm_max', 'annual_volume', 'target_price_min', 'target_price_max']

function Chips({ label, choices, value, onChange, disabled }) {
  const toggle = (v) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  return (
    <div className="field full">
      <span>{label}</span>
      <div className="chips" role="group" aria-label={label}>
        {choices.map(([v, l]) => (
          <button key={v} type="button" className={`chip ${value.includes(v) ? 'on' : ''}`} aria-pressed={value.includes(v)}
            onClick={() => toggle(v)} disabled={disabled}>
            {value.includes(v) && '✓ '}{l}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function RequirementsTab({ buyer, editable, onChanged }) {
  const existing = buyer.requirement
  const [form, setForm] = useState(() => ({ ...EMPTY, price_currency: buyer.preferred_currency || 'USD', ...(existing || {}) }))
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const set = (name, v) => { setSaved(false); setForm((p) => ({ ...p, [name]: v })) }
  const field = (name, label, extra = {}) => (
    <FormField field={{ name, label, ...extra }} value={form[name]} onChange={set} />
  )

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setError(''); setSaved(false)
    const body = { ...form, buyer: buyer.id }
    NUMBERS.forEach((n) => { if (body[n] === '' || body[n] == null) body[n] = null })
    try {
      if (existing) await api.put(`/buyer-requirements/${existing.id}/`, body)
      else await api.post('/buyer-requirements/', body)
      setSaved(true)
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save}>
      <fieldset className="plain" disabled={!editable}>
        <div className="form-section">
          <h3>What they buy</h3>
          <Chips label="Product categories *" choices={CATEGORIES} value={form.product_categories} onChange={(v) => set('product_categories', v)} disabled={!editable} />
          <div className="form-grid">
            {field('fabric_composition', 'Fabric / composition')}
            {field('size_range', 'Size range')}
            {field('gsm_min', 'GSM from', { type: 'number' })}
            {field('gsm_max', 'GSM to', { type: 'number' })}
            {field('annual_volume', 'Annual volume (pcs)', { type: 'number' })}
          </div>
        </div>
        <div className="form-section">
          <h3>Price & compliance</h3>
          <div className="form-grid">
            {field('target_price_min', 'Target FOB price from', { type: 'number' })}
            {field('target_price_max', 'Target FOB price to', { type: 'number' })}
            {field('price_currency', 'Price currency')}
            {field('testing_lab', 'Nominated testing lab')}
          </div>
          <Chips label="Required certifications" choices={CERTIFICATIONS} value={form.certifications} onChange={(v) => set('certifications', v)} disabled={!editable} />
        </div>
        <div className="form-section">
          <h3>Packing & delivery</h3>
          <div className="form-grid">
            {field('delivery_port', 'Loading / delivery port')}
            {field('payment_terms_requested', 'Payment terms asked for')}
            {field('packaging', 'Packaging', { type: 'textarea', full: true })}
            {field('labelling', 'Labels & tags', { type: 'textarea', full: true })}
            {field('notes', 'Other notes', { type: 'textarea', full: true })}
          </div>
        </div>
      </fieldset>
      {error && <div className="error">{error}</div>}
      {editable ? (
        <div className="form-actions">
          {saved && <span className="pos small">✓ Saved</span>}
          <button type="submit" disabled={saving}>{saving ? 'Saving…' : existing ? 'Save requirements' : 'Add requirements'}</button>
        </div>
      ) : (
        <p className="muted small">Requirements are locked in this status.</p>
      )}
    </form>
  )
}
