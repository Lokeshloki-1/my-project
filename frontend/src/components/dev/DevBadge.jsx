import { labelOf } from '../buyers/constants'
import { SAMPLE_STATUSES, TP_STATUSES } from './constants'

export default function DevBadge({ kind, status }) {
  const list = kind === 'tp' ? TP_STATUSES : SAMPLE_STATUSES
  return <span className={`badge badge-${kind}-${status}`}>{labelOf(list, status)}</span>
}
