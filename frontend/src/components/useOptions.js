import { useEffect, useState } from 'react'
import api from '../api/client'

// Load a list of records for a <select>, e.g. useOptions('/companies/').
// Pass params = null to load nothing (e.g. until a company is chosen).
export default function useOptions(url, params) {
  const [options, setOptions] = useState([])
  const key = params === null ? null : JSON.stringify(params || {})
  useEffect(() => {
    if (!url || key === null) { setOptions([]); return }
    api.get(url, { params: { page_size: 500, ...JSON.parse(key) } })
      .then((res) => setOptions(res.data.results ?? res.data))
      .catch(() => setOptions([]))
  }, [url, key])
  return options
}
