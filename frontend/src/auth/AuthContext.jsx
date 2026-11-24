import { createContext, useContext, useEffect, useState } from 'react'
import api, { tokens } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!tokens.access)

  useEffect(() => {
    if (!tokens.access) return
    api.get('/auth/me/')
      .then((res) => setUser(res.data))
      .catch(() => tokens.clear())
      .finally(() => setLoading(false))
  }, [])

  const login = async (username, password) => {
    const { data } = await api.post('/auth/login/', { username, password })
    tokens.set(data.access, data.refresh)
    const me = await api.get('/auth/me/')
    setUser(me.data)
  }

  const logout = () => {
    tokens.clear()
    setUser(null)
  }

  const canManage = !!user && (user.is_superuser || ['admin', 'manager'].includes(user.role))

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, canManage }}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext)
