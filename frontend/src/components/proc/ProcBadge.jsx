import { labelOf } from '../buyers/constants'
import { MR_STATUSES, PO_STATUSES, RFQ_STATUSES } from './constants'

const LISTS = { mr: MR_STATUSES, rfq: RFQ_STATUSES, po: PO_STATUSES }

export default function ProcBadge({ kind, status }) {
  return <span className={`badge badge-${kind}-${status}`}>{labelOf(LISTS[kind], status)}</span>
}
