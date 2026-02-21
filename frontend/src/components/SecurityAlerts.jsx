import React, { useState, useEffect, useCallback } from 'react'

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
  // ts = "2024-01-01T12:00:00"
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch {
    return ts
  }
}

export default function SecurityAlerts({ apiBase, viewerRole = 'C-Level' }) {
  const [alerts, setAlerts] = useState([])
  const [open, setOpen] = useState(false)
  const [unackCount, setUnackCount] = useState(0)

  const fetchAlerts = useCallback(() => {
    fetch(`${apiBase}/security/alerts`)
      .then((r) => (r.ok ? r.json() : { alerts: [] }))
      .then((data) => {
        const list = Array.isArray(data?.alerts) ? data.alerts : []
        setAlerts(list)
        setUnackCount(list.filter((a) => !a.acknowledged).length)
      })
      .catch(() => {})
  }, [apiBase])

  // Poll every 5 seconds
  useEffect(() => {
    fetchAlerts()
    const id = setInterval(fetchAlerts, 5000)
    return () => clearInterval(id)
  }, [fetchAlerts])

  const acknowledge = (alertId) => {
    fetch(`${apiBase}/security/alerts/${alertId}/acknowledge`, { method: 'POST' })
      .then(() => fetchAlerts())
      .catch(() => {})
  }

  const clearAll = () => {
    if (!window.confirm('Clear all security alerts? This cannot be undone.')) return
    fetch(`${apiBase}/security/alerts`, { method: 'DELETE' })
      .then(() => { setAlerts([]); setUnackCount(0) })
      .catch(() => {})
  }

  const feature1 = alerts.filter((a) => a.alert_type === 'unauthorized_door_access')
  const feature2 = alerts.filter((a) => a.alert_type !== 'unauthorized_door_access')

  return (
    <section className="security-alerts-section">
      <button
        type="button"
        className="manage-link manage-btn security-toggle-btn"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? '▼' : '▶'} Security Alerts
        {unackCount > 0 && (
          <span className="alert-badge">{unackCount}</span>
        )}
      </button>

      {open && (
        <div className="alerts-panel">
          {/* Header row */}
          <div className="alerts-panel-header">
            <span className="alerts-count">{alerts.length} alert{alerts.length !== 1 ? 's' : ''}</span>
            {alerts.length > 0 && (
              <button type="button" className="btn-clear-alerts" onClick={clearAll}>
                Clear all
              </button>
            )}
          </div>

          {alerts.length === 0 ? (
            <p className="no-alerts-msg">No security alerts logged.</p>
          ) : (
            <div className="alerts-scroll">
              {/* Feature 1 section */}
              {feature1.length > 0 && (
                <div className="alert-group">
                  <div className="alert-group-title">Unauthorized Door Access ({feature1.length})</div>
                  {feature1.map((a) => <AlertRow key={a.alert_id} alert={a} onAck={acknowledge} />)}
                </div>
              )}
              {/* Feature 2 section */}
              {feature2.length > 0 && (
                <div className="alert-group">
                  <div className="alert-group-title">Restricted Zone Violations ({feature2.length})</div>
                  {feature2.map((a) => <AlertRow key={a.alert_id} alert={a} onAck={acknowledge} />)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function AlertRow({ alert, onAck }) {
  const [showRec, setShowRec] = useState(false)
  const meta = ALERT_META[alert.alert_type] || { icon: '⚠️', label: alert.alert_type, color: '#ef4444' }
  return (
    <div
      className={`alert-row-item ${alert.acknowledged ? 'acked' : 'unacked'}`}
      style={{ borderLeftColor: meta.color }}
    >
      <span className="alert-type-icon">{meta.icon}</span>
      <div className="alert-body">
        <div className="alert-top">
          <strong style={{ color: meta.color }}>{meta.label}</strong>
          <span className="alert-feed-badge">Feed {(alert.feed_id ?? 0) + 1}</span>
          {alert.acknowledged && <span className="acked-badge">✓ ack</span>}
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
              <img
                src={alert.recording_url}
                alt="Violation recording"
                className="recording-gif"
              />
            )}
          </div>
        )}
      </div>
      {!alert.acknowledged && (
        <button
          type="button"
          className="ack-btn"
          onClick={() => onAck(alert.alert_id)}
          title="Acknowledge"
        >
          ✓
        </button>
      )}
    </div>
  )
}
