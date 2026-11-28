import ResourcePage from '../components/ResourcePage'
import { DEFECT_CATEGORIES, SEVERITIES } from '../components/qa/constants'
import { labelOf, opts } from '../components/buyers/constants'

export default function DefectTypes() {
  return (
    <ResourcePage
      title="Defect Library"
      subtitle="Defect types used in inline QC and final inspection, with their usual severity"
      endpoint="/defect-types/"
      managerOnly
      defaults={{ category: 'sewing', severity: 'major', is_active: true }}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Defect', render: (r) => <><b>{r.name}</b>{!r.is_active && <span className="badge badge-fi-failed">inactive</span>}</> },
        { key: 'category', label: 'Category', render: (r) => labelOf(DEFECT_CATEGORIES, r.category) },
        { key: 'severity', label: 'Default severity', render: (r) => <span className={`badge badge-sev-${r.severity}`}>{labelOf(SEVERITIES, r.severity)}</span> },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Defect', required: true },
        { name: 'category', label: 'Category', type: 'select', options: opts(DEFECT_CATEGORIES), required: true },
        { name: 'severity', label: 'Default severity', type: 'select', options: opts(SEVERITIES), required: true },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
    />
  )
}
