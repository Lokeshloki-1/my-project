import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err.response?.status === 401 ? 'Wrong username or password.' : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand big">Hazpo<span>ERP</span></div>
        <p className="muted">Sign in to continue</p>
        <label className="field"><span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </label>
        <label className="field"><span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
