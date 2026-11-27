import { COST_STATUSES, ORDER_STATUSES, QUOTE_STATUSES } from './constants'

const LISTS = { cs: COST_STATUSES, qt: QUOTE_STATUSES, oc: ORDER_STATUSES }

export default function DocBadge({ kind, status }) {
  const label = LISTS[kind].find(([v]) => v === status)?.[1] ?? status
  return <span className={`badge badge-${kind}-${status}`}>{label}</span>
}
