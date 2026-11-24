import axios from 'axios'

// All API calls go through this client. It adds the JWT token and
// refreshes it automatically when it expires.
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' })

const ACCESS = 'hazpo_access'
const REFRESH = 'hazpo_refresh'

export const tokens = {
  get access() { return localStorage.getItem(ACCESS) },
  get refresh() { return localStorage.getItem(REFRESH) },
  set(access, refresh) {
    localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}

api.interceptors.request.use((config) => {
  if (tokens.access) config.headers.Authorization = `Bearer ${tokens.access}`
  return config
})

let refreshing = null
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    const isAuthCall = original?.url?.startsWith('/auth/')
    if (error.response?.status === 401 && tokens.refresh && !original._retry && !isAuthCall) {
      original._retry = true
      try {
        refreshing ??= api.post('/auth/refresh/', { refresh: tokens.refresh })
        const { data } = await refreshing
        tokens.set(data.access)
        return api(original)
      } catch {
        tokens.clear()
        window.location.href = '/login'
      } finally {
        refreshing = null
      }
    }
    return Promise.reject(error)
  },
)

// Turn a DRF error response into a readable message.
export function errorMessage(error) {
  const data = error?.response?.data
  if (!data) return error?.message || 'Something went wrong'
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.join(' ')
  return Object.entries(data)
    .map(([field, msgs]) => `${field === 'detail' || field === 'non_field_errors' ? '' : field + ': '}${[].concat(msgs).join(' ')}`)
    .join('\n')
}

// Download a file from the API (with the login token) and save it in the browser.
export async function downloadFile(url, filename) {
  const res = await api.get(url, { responseType: 'blob' })
  const href = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}

export default api
