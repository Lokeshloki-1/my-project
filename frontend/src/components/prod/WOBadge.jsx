import { labelOf } from '../buyers/constants'
import { WO_STATUSES } from './constants'

export default function WOBadge({ status }) {
  return <span className={`badge badge-wo-${status}`}>{labelOf(WO_STATUSES, status)}</span>
}
