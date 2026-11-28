import { BUYER_STATUSES, labelOf } from './constants'

export default function BuyerStatusBadge({ status }) {
  return <span className={`badge badge-b-${status}`}>{labelOf(BUYER_STATUSES, status)}</span>
}
