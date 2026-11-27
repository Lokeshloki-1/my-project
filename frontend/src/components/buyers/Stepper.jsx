import { STEP_TAB } from './constants'

// Seven onboarding steps from the API's `onboarding` list. Clicking a step opens its tab.

export default function Stepper({ steps, onSelect }) {
  const current = steps.find((s) => !s.done && !s.optional)
  return (
    <div className="card stepper-card">
      <ol className="stepper">
        {steps.map((s, i) => {
          const state = s.done ? 'done' : s === current ? 'current' : s.optional ? 'skipped' : 'todo'
          return (
            <li key={s.key} className={`step ${state}`}>
              <button type="button" className="step-btn" onClick={() => onSelect(STEP_TAB[s.key])} aria-current={state === 'current' ? 'step' : undefined}>
                <span className="dot">{s.done ? '✓' : i + 1}</span>
                <span className="step-label">{s.label}{s.optional && !s.done && <small> (optional)</small>}</span>
              </button>
            </li>
          )
        })}
      </ol>
      {current && current.missing.length > 0 && (
        <div className="step-missing">
          <b>To do for “{current.label}”:</b> {current.missing.join(' · ')}
        </div>
      )}
    </div>
  )
}
