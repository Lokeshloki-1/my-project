import useOptions from './useOptions'

// One input described by a config object:
// { name, label, type: 'text'|'number'|'date'|'email'|'textarea'|'checkbox'|'select', options, optionsUrl, optionLabel }
export default function FormField({ field, value, onChange, filters }) {
  const remote = useOptions(field.optionsUrl, field.optionsFilter?.(filters))
  const set = (v) => onChange(field.name, v)
  let input

  if (field.type === 'textarea') {
    input = <textarea value={value ?? ''} onChange={(e) => set(e.target.value)} rows={3} />
  } else if (field.type === 'checkbox') {
    input = <input type="checkbox" checked={!!value} onChange={(e) => set(e.target.checked)} />
  } else if (field.type === 'select') {
    const opts = field.options || remote.map((o) => ({ value: o.id, label: field.optionLabel ? field.optionLabel(o) : o.name }))
    input = (
      <select value={value ?? ''} onChange={(e) => set(e.target.value === '' ? null : e.target.value)} required={field.required}>
        <option value="">— select —</option>
        {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    )
  } else {
    input = (
      <input
        type={field.type || 'text'}
        step={field.type === 'number' ? '0.01' : undefined}
        value={value ?? ''}
        required={field.required}
        onChange={(e) => set(e.target.value)}
      />
    )
  }

  return (
    <label className={`field ${field.full ? 'full' : ''} ${field.type === 'checkbox' ? 'check' : ''}`}>
      <span>{field.label}{field.required ? ' *' : ''}</span>
      {input}
    </label>
  )
}
