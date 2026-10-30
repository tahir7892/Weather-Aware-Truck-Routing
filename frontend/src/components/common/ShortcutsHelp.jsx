import './common.css'

const SHORTCUTS = [
  ['Space', 'Play / pause the forecast'],
  ['← →', 'Previous / next hour'],
  ['1  2  3', 'Select the route ranked #1, #2, #3'],
  ['Esc', 'Close popups and this panel'],
  ['?', 'Show / hide this panel'],
]

/** The "?" button in the top bar and the keyboard shortcuts panel it opens. */
export default function ShortcutsHelp({ open, onToggle }) {
  return (
    <div className="shortcuts">
      <button
        type="button"
        className="shortcuts-button"
        onClick={onToggle}
        aria-expanded={open}
        aria-label="Keyboard shortcuts"
        title="Keyboard shortcuts (?)"
      >
        ?
      </button>
      {open && (
        <div className="shortcuts-panel" role="dialog" aria-label="Keyboard shortcuts">
          <b>Keyboard shortcuts</b>
          <dl>
            {SHORTCUTS.map(([keys, action]) => (
              <div key={keys}>
                <dt>
                  {keys.split('  ').map((k) => (
                    <kbd key={k}>{k}</kbd>
                  ))}
                </dt>
                <dd>{action}</dd>
              </div>
            ))}
          </dl>
          <small>Shortcuts work when you are not typing in a field.</small>
        </div>
      )}
    </div>
  )
}
