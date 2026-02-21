import React, { useState, useEffect, useCallback, useRef } from 'react'

const ALERT_META = {
  unauthorized_door_access: {
    icon: '🚪',
    label: 'Unauthorized Door Access',
    color: '#ef4444',
  },
  zone_presence: {
    icon: '⚠️',
    label: 'Restricted Zone Violation',
    color: '#f59e0b',
  },
  line_crossing: {
    icon: '🚧',
    label: 'Boundary Line Crossed',
    color: '#f97316',
  },
}

function fmtTime(ts) {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

export default function SecurityAlerts({ apiBase, viewerRole = 'C-Level' }) {
  const [alerts, setAlerts] = useState([])
  const [open, setOpen] = useState(false)
  const [showResolved, setShowResolved] = useState(false)
  const [generatingReport, setGeneratingReport] = useState({}) // alertId → true|false
  const previousAlertIdsRef = useRef(new Set())

  const fetchAlerts = useCallback(() => {
    fetch(`${apiBase}/security/alerts`)
      .then((r) => (r.ok ? r.json() : { alerts: [] }))
      .then((data) => {
        const list = Array.isArray(data?.alerts) ? data.alerts : []
        previousAlertIdsRef.current = new Set(list.map((a) => a.alert_id))
        setAlerts(list)
      })
      .catch(() => {})
  }, [apiBase])

  useEffect(() => {
    fetchAlerts()
    const id = setInterval(fetchAlerts, 5000)
    return () => clearInterval(id)
  }, [fetchAlerts])

  // "Problem fixed" → mark resolved and remove from active view
  const markProblemFixed = (alertId) => {
    fetch(`${apiBase}/security/alerts/${alertId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution: 'problem_fixed' }),
    })
      .then(() => fetchAlerts())
      .catch(() => {})
  }

  const generateReport = async (alertId) => {
    setGeneratingReport((prev) => ({ ...prev, [alertId]: true }))
    try {
      const r = await fetch(`${apiBase}/security/alerts/${alertId}/generate-report`, {
        method: 'POST',
      })
      if (!r.ok) throw new Error(`Server error: ${r.status}`)
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `HOF-Security-Report-${alertId.slice(0, 8).toUpperCase()}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Report generation failed:', e)
      alert('Report generation failed. Check that the backend is running and dependencies are installed.')
    } finally {
      setGeneratingReport((prev) => ({ ...prev, [alertId]: false }))
    }
  }

  const clearAll = () => {
    if (!window.confirm('Clear all security alerts? This cannot be undone.')) return
    fetch(`${apiBase}/security/alerts`, { method: 'DELETE' })
      .then(() => setAlerts([]))
      .catch(() => {})
  }

  const activeAlerts   = alerts.filter((a) => a.resolution !== 'problem_fixed')
  const resolvedAlerts = alerts.filter((a) => a.resolution === 'problem_fixed')
  const unackCount     = activeAlerts.filter((a) => !a.acknowledged).length

  const feature1 = activeAlerts.filter((a) => a.alert_type === 'unauthorized_door_access')
  const feature2 = activeAlerts.filter((a) => a.alert_type !== 'unauthorized_door_access')

  return (
    <section className="security-alerts-section">
      <button
        type="button"
        className="manage-link manage-btn security-toggle-btn"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? '▼' : '▶'} Security Alerts
        {unackCount > 0 && <span className="alert-badge">{unackCount}</span>}
      </button>

      {open && (
        <div className="alerts-panel">
          <div className="alerts-panel-header">
            <span className="alerts-count">
              {activeAlerts.length} active
              {resolvedAlerts.length > 0 && ` · ${resolvedAlerts.length} resolved`}
            </span>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {resolvedAlerts.length > 0 && (
                <button
                  type="button"
                  className="btn-show-resolved"
                  onClick={() => setShowResolved((s) => !s)}
                >
                  {showResolved ? 'Hide resolved' : `Show resolved (${resolvedAlerts.length})`}
                </button>
              )}
              {alerts.length > 0 && (
                <button type="button" className="btn-clear-alerts" onClick={clearAll}>
                  Clear all
                </button>
              )}
            </div>
          </div>

          {activeAlerts.length === 0 && !showResolved ? (
            <p className="no-alerts-msg">No active security alerts.</p>
          ) : (
            <div className="alerts-scroll">
              {feature1.length > 0 && (
                <div className="alert-group">
                  <div className="alert-group-title">
                    Unauthorized Door Access ({feature1.length})
                  </div>
                  {feature1.map((a) => (
                    <AlertRow
                      key={a.alert_id}
                      alert={a}
                      onGenerateReport={generateReport}
                      onProblemFixed={markProblemFixed}
                      isGenerating={!!generatingReport[a.alert_id]}
                    />
                  ))}
                </div>
              )}
              {feature2.length > 0 && (
                <div className="alert-group">
                  <div className="alert-group-title">
                    Restricted Zone Violations ({feature2.length})
                  </div>
                  {feature2.map((a) => (
                    <AlertRow
                      key={a.alert_id}
                      alert={a}
                      onGenerateReport={generateReport}
                      onProblemFixed={markProblemFixed}
                      isGenerating={!!generatingReport[a.alert_id]}
                    />
                  ))}
                </div>
              )}
              {showResolved && resolvedAlerts.length > 0 && (
                <div className="alert-group">
                  <div className="alert-group-title alert-group-resolved">
                    Resolved ({resolvedAlerts.length})
                  </div>
                  {resolvedAlerts.map((a) => (
                    <AlertRow
                      key={a.alert_id}
                      alert={a}
                      onGenerateReport={generateReport}
                      isGenerating={!!generatingReport[a.alert_id]}
                      readOnly
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function AlertRow({ alert, onGenerateReport, onProblemFixed, isGenerating, readOnly = false }) {
  const [showRec, setShowRec] = useState(false)
  const meta     = ALERT_META[alert.alert_type] || { icon: '⚠️', label: alert.alert_type, color: '#ef4444' }
  const resolved = alert.resolution === 'problem_fixed'

  return (
    <div
      className={`alert-row-item ${resolved ? 'acked' : 'unacked'}`}
      style={{ borderLeftColor: meta.color }}
    >
      <span className="alert-type-icon">{meta.icon}</span>

      <div className="alert-body">
        <div className="alert-top">
          <strong style={{ color: meta.color }}>{meta.label}</strong>
          <span className="alert-feed-badge">Feed {(alert.feed_id ?? 0) + 1}</span>
          {resolved && <span className="resolved-badge">✓ Problem fixed</span>}
        </div>

        <div className="alert-person-line">
          <span className="alert-person-name">{alert.person_name || 'Unknown'}</span>
          {alert.person_role && <span className="alert-role">({alert.person_role})</span>}
          {alert.zone_name && <span className="alert-zone-name"> → {alert.zone_name}</span>}
        </div>

        {alert.details && <div className="alert-details-text">{alert.details}</div>}
        <div className="alert-timestamp">{fmtTime(alert.timestamp)}</div>

        {alert.recording_url && (
          <div className="alert-recording">
            <button
              type="button"
              className="recording-toggle-btn"
              onClick={() => setShowRec((s) => !s)}
            >
              {showRec ? '▼ Hide clip' : '▶ View 3s clip'}
            </button>
            {showRec && (
              <img src={alert.recording_url} alt="Violation recording" className="recording-gif" />
            )}
          </div>
        )}
      </div>

      {!readOnly && (
        <div className="alert-actions">
          <button
            type="button"
            className={`report-btn ${isGenerating ? 'report-btn-loading' : ''}`}
            onClick={() => onGenerateReport(alert.alert_id)}
            disabled={isGenerating}
            title="Generate PDF incident report with VLM analysis"
          >
            {isGenerating ? '⏳ Generating…' : '📄 Generate Report'}
          </button>
          {!resolved && onProblemFixed && (
            <button
              type="button"
              className="resolve-btn"
              onClick={() => onProblemFixed(alert.alert_id)}
              title="Mark as resolved and remove from active alerts"
            >
              ✓ Problem fixed
            </button>
          )}
        </div>
      )}

      {readOnly && onGenerateReport && (
        <button
          type="button"
          className={`report-btn ${isGenerating ? 'report-btn-loading' : ''}`}
          onClick={() => onGenerateReport(alert.alert_id)}
          disabled={isGenerating}
          title="Re-download report"
        >
          {isGenerating ? '⏳ Generating…' : '📄 Report'}
        </button>
      )}
    </div>
  )
}
