import { useCallback, useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import FormField from './FormField'
import Modal from './Modal'

/**
 * Generic list + search + create/edit page for one API resource.
 *
 * Props:
 *   title, endpoint ('/companies/'), columns [{ key, label, render? }],
 *   fields (form config, see FormField), defaults (new record values),
 *   managerOnly (hide edit buttons for non-managers), filters (extra query params),
 *   renderFormExtra(form) — optional extra UI under the form.
 */
export default function ResourcePage({ title, endpoint, columns, fields, defaults = {}, managerOnly, renderFormExtra, subtitle }) {
  const { canManage } = useAuth()
  const canEdit = !managerOnly || canManage
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    api.get(endpoint, { params: { page, search: search || undefined } })
      .then((res) => { setRows(res.data.results); setCount(res.data.count) })
      .catch((e) => setError(errorMessage(e)))
  }, [endpoint, page, search])

  useEffect(() => { load() }, [load])

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      if (form.id) await api.put(`${endpoint}${form.id}/`, form)
      else await api.post(endpoint, form)
      setForm(null)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this record? This cannot be undone.')) return
    try {
      await api.delete(`${endpoint}${form.id}/`)
      setForm(null)
      load()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const pages = Math.max(1, Math.ceil(count / 25))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
        <div className="actions">
          <input className="search" placeholder="Search…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
          {canEdit && <button onClick={() => { setError(''); setForm({ ...defaults }) }}>+ New</button>}
        </div>
      </div>

      {error && !form && <div className="error">{error}</div>}

      <div className="card table-wrap">
        <table>
          <thead>
            <tr>{columns.map((c) => <th key={c.key} className={c.num ? 'num' : ''}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={columns.length} className="muted center">No records yet.</td></tr>
            )}
            {rows.map((row) => (
              <tr key={row.id} className={canEdit ? 'clickable' : ''} onClick={() => canEdit && (setError(''), setForm({ ...row }))}>
                {columns.map((c) => (
                  <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(row) : row[c.key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="pager">
          <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span className="muted">Page {page} of {pages} · {count} records</span>
          <button className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {form && (
        <Modal title={form.id ? `Edit ${title.replace(/s$/, '')}` : `New ${title.replace(/s$/, '')}`} onClose={() => setForm(null)} wide>
          <form onSubmit={save}>
            <div className="form-grid">
              {fields.map((f) => (
                <FormField key={f.name} field={f} value={form[f.name]} filters={form}
                  onChange={(name, v) => setForm((prev) => ({ ...prev, [name]: v }))} />
              ))}
            </div>
            {renderFormExtra?.(form)}
            {error && <div className="error">{error}</div>}
            <div className="modal-foot">
              {form.id ? <button type="button" className="danger" onClick={remove}>Delete</button> : <span />}
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
