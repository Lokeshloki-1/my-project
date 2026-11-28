import { labelOf } from '../buyers/constants'
import { ALLOC_STATUSES, GRN_STATUSES, RESULTS } from './constants'

const LISTS = { grn: GRN_STATUSES, res: RESULTS, alloc: ALLOC_STATUSES }

export default function StoresBadge({ kind, status }) {
  return <span className={`badge badge-${kind}-${status}`}>{labelOf(LISTS[kind], status)}</span>
}
