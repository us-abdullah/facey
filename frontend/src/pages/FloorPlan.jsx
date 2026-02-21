import React, { useState, useEffect, useRef, useCallback } from 'react'

const API_BASE = '/api'
const RESTRICTION_LEVELS = [
  { value: 'restricted', label: 'Restricted (only selected roles)' },
  { value: 'authorized_only', label: 'Authorized only (any registered)' },
  { value: 'public', label: 'Public (anyone)' },
]
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function FloorPlan({ onBack }) {
  const [hasFloorplan, setHasFloorplan] = useState(false)
  const [doors, setDoors] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showDoorForm, setShowDoorForm] = useState(false)
  const [pendingPoint, setPendingPoint] = useState(null) // [x, y] normalized
  const [editingDoorId, setEditingDoorId] = useState(null)
  const [formName, setFormName] = useState('')
  const [formFeedId, setFormFeedId] = useState(0)
  const [formAllowedRoles, setFormAllowedRoles] = useState([])
  const [formRestriction, setFormRestriction] = useState('restricted')
  const [formTimeStart, setFormTimeStart] = useState('')
  const [formTimeEnd, setFormTimeEnd] = useState('')
  const [formDays, setFormDays] = useState([1, 2, 3, 4, 5])
  const containerRef = useRef(null)
  const imageRef = useRef(null)
  const canvasRef = useRef(null)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    Promise.all([
      fetch(`${API_BASE}/floorplan`).then((r) => r.json()),
      fetch(`${API_BASE}/floorplan/doors`).then((r) => (r.ok ? r.json() : { doors: [] })),
      fetch(`${API_BASE}/roles`).then((r) => (r.ok ? r.json() : { roles: [] })),
    ])
      .then(([fp, d, r]) => {
        setHasFloorplan(fp.has_floorplan || false)
        setDoors(d.doors || [])
        setRoles(r.roles || [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => load(), [load])

  const imageUrl = hasFloorplan ? `${API_BASE}/floorplan/image?t=${Date.now()}` : null

  const handleUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    const form = new FormData()
    form.append('file', file)
    fetch(`${API_BASE}/floorplan`, { method: 'POST', body: form })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => setHasFloorplan(true))
      .catch((e) => setError(e.message))
  }

  const getNorm = (e) => {
    const cont = containerRef.current
    const img = imageRef.current
    if (!cont || !img || !img.complete) return null
    const rect = cont.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    return [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))]
  }

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!ctx || !containerRef.current) return
    const { width, height } = containerRef.current.getBoundingClientRect()
    canvas.width = width
    canvas.height = height
    ctx.clearRect(0, 0, width, height)
    const scale = (p) => [p[0] * width, p[1] * height]
    doors.forEach((d) => {
      const [px, py] = scale(d.point || [0.5, 0.5])
      const isEditing = editingDoorId === d.id
      ctx.fillStyle = isEditing ? '#a3e635' : '#3b82f6'
      ctx.strokeStyle = isEditing ? '#22c55e' : '#1d4ed8'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(px, py, 10, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    })
    if (pendingPoint) {
      const [px, py] = scale(pendingPoint)
      ctx.fillStyle = 'rgba(245, 158, 11, 0.8)'
      ctx.strokeStyle = '#f59e0b'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(px, py, 10, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    }
  }, [doors, pendingPoint, editingDoorId])

  useEffect(() => {
    drawCanvas()
  }, [drawCanvas])

  const onCanvasClick = (e) => {
    const n = getNorm(e)
    if (!n) return
    if (editingDoorId) {
      const door = doors.find((d) => d.id === editingDoorId)
      if (door) {
        updateDoorPoint(editingDoorId, n)
        setEditingDoorId(null)
      }
      return
    }
    setPendingPoint(n)
    setShowDoorForm(true)
    setFormName('')
    setFormFeedId(0)
    setFormAllowedRoles([])
    setFormRestriction('restricted')
    setFormTimeStart('')
    setFormTimeEnd('')
    setFormDays([1, 2, 3, 4, 5])
  }

  const saveNewDoor = () => {
    if (!pendingPoint) return
    const name = formName.trim() || 'Door'
    const body = {
      name,
      point: pendingPoint,
      feed_id: formFeedId,
      allowed_roles: formAllowedRoles,
      restriction_level: formRestriction,
      rules:
        formTimeStart || formTimeEnd || formDays.length < 7
          ? {
              time_start: formTimeStart || null,
              time_end: formTimeEnd || null,
              days: formDays,
            }
          : null,
    }
    fetch(`${API_BASE}/floorplan/doors`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => {
        load()
        setPendingPoint(null)
        setShowDoorForm(false)
      })
      .catch((e) => setError(e.message))
  }

  const updateDoorPoint = (doorId, point) => {
    fetch(`${API_BASE}/floorplan/doors/${doorId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ point }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => load())
      .catch((e) => setError(e.message))
  }

  const cancelDoorForm = () => {
    setPendingPoint(null)
    setShowDoorForm(false)
    setEditingDoorId(null)
  }

  const startEditDoor = (d) => {
    setEditingDoorId(d.id)
    setFormName(d.name || '')
    setFormFeedId(d.feed_id ?? 0)
    setFormAllowedRoles(d.allowed_roles || [])
    setFormRestriction(d.restriction_level || 'restricted')
    const r = d.rules || {}
    setFormTimeStart(r.time_start || '')
    setFormTimeEnd(r.time_end || '')
    setFormDays(Array.isArray(r.days) ? r.days : [1, 2, 3, 4, 5])
  }

  const saveEditDoor = () => {
    if (!editingDoorId) return
    const body = {
      name: formName.trim() || undefined,
      feed_id: formFeedId,
      allowed_roles: formAllowedRoles,
      restriction_level: formRestriction,
      rules: {
        time_start: formTimeStart || null,
        time_end: formTimeEnd || null,
        days: formDays,
      },
    }
    fetch(`${API_BASE}/floorplan/doors/${editingDoorId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => {
        load()
        setEditingDoorId(null)
      })
      .catch((e) => setError(e.message))
  }

  const deleteDoor = (id) => {
    if (!confirm('Delete this door?')) return
    fetch(`${API_BASE}/floorplan/doors/${id}`, { method: 'DELETE' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => load())
      .catch((e) => setError(e.message))
  }

  const toggleRole = (role) => {
    setFormAllowedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    )
  }

  const toggleDay = (d) => {
    setFormDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort()))
  }

  return (
    <div className="app floorplan-page">
      <div className="page-header">
        <h1>Floor plan & doors</h1>
        <button type="button" onClick={onBack} className="back-link back-btn">
          ← Dashboard
        </button>
      </div>
      {error && <p className="status error">{error}</p>}

      {!hasFloorplan && (
        <section className="floorplan-upload">
          <p className="section-title">Upload floor plan</p>
          <label className="upload-zone">
            <input type="file" accept="image/*" onChange={handleUpload} style={{ display: 'none' }} />
            Drop an image or click to upload
          </label>
        </section>
      )}

      {hasFloorplan && (
        <>
          <section className="floorplan-tools">
            <span className="section-title">Click on the map to add a door point.</span>
            <span className="section-hint">Each point = one door; set Feed (camera index) and allowed roles.</span>
          </section>

          <div
            className="floorplan-canvas-wrap"
            ref={containerRef}
            style={{ position: 'relative' }}
          >
            <img
              ref={imageRef}
              src={imageUrl}
              alt="Floor plan"
              onLoad={drawCanvas}
              style={{ maxWidth: '100%', maxHeight: '70vh', display: 'block', verticalAlign: 'top' }}
            />
            <canvas
              ref={canvasRef}
              className="floorplan-overlay"
              onClick={onCanvasClick}
              style={{ position: 'absolute', inset: 0, cursor: 'crosshair' }}
            />
          </div>

          {(showDoorForm && pendingPoint) && (
            <div className="zone-form-modal">
              <div className="zone-form">
                <h3>New door</h3>
                <label>
                  Name
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Office entrance"
                    className="edit-input"
                  />
                </label>
                <label>
                  Feed (camera index)
                  <input
                    type="number"
                    min={0}
                    value={formFeedId}
                    onChange={(e) => setFormFeedId(parseInt(e.target.value, 10) || 0)}
                    className="edit-input"
                  />
                </label>
                <label>
                  Restriction level
                  <select
                    value={formRestriction}
                    onChange={(e) => setFormRestriction(e.target.value)}
                    className="edit-input"
                  >
                    {RESTRICTION_LEVELS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
                {formRestriction === 'restricted' && (
                  <div className="form-roles">
                    <span>Allowed roles:</span>
                    <div className="roles-chips">
                      {roles.map((r) => (
                        <button
                          key={r}
                          type="button"
                          className={`chip ${formAllowedRoles.includes(r) ? 'active' : ''}`}
                          onClick={() => toggleRole(r)}
                        >
                          {r}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div className="form-timing">
                  <span>Time rules (optional)</span>
                  <div className="timing-row">
                    <input
                      type="time"
                      value={formTimeStart}
                      onChange={(e) => setFormTimeStart(e.target.value)}
                    />
                    <span>to</span>
                    <input
                      type="time"
                      value={formTimeEnd}
                      onChange={(e) => setFormTimeEnd(e.target.value)}
                    />
                  </div>
                  <div className="days-row">
                    {DAYS.map((_, i) => (
                      <label key={i} className="day-check">
                        <input
                          type="checkbox"
                          checked={formDays.includes(i)}
                          onChange={() => toggleDay(i)}
                        />
                        {DAYS[i]}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="zone-form-actions">
                  <button type="button" className="btn btn-primary" onClick={saveNewDoor}>
                    Save door
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={cancelDoorForm}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      <section className="zones-list-section">
        <h2 className="section-title">Doors</h2>
        {loading && !doors.length ? (
          <p className="status">Loading…</p>
        ) : doors.length === 0 ? (
          <p className="status">No doors yet. Upload a floor plan and click on the map to add a door point.</p>
        ) : (
          <ul className="zones-list">
            {doors.map((d) => (
              <li key={d.id} className="zone-card">
                {editingDoorId === d.id ? (
                  <div className="zone-edit-inline">
                    <p className="section-hint">Click on the map to move this door point.</p>
                    <input
                      type="text"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="Door name"
                      className="edit-input"
                    />
                    <label>
                      Feed
                      <input
                        type="number"
                        min={0}
                        value={formFeedId}
                        onChange={(e) => setFormFeedId(parseInt(e.target.value, 10) || 0)}
                        className="edit-input"
                      />
                    </label>
                    <select
                      value={formRestriction}
                      onChange={(e) => setFormRestriction(e.target.value)}
                      className="edit-input"
                    >
                      {RESTRICTION_LEVELS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    {formRestriction === 'restricted' && (
                      <div className="roles-chips">
                        {roles.map((r) => (
                          <button
                            key={r}
                            type="button"
                            className={`chip ${formAllowedRoles.includes(r) ? 'active' : ''}`}
                            onClick={() => toggleRole(r)}
                          >
                            {r}
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="zone-form-actions">
                      <button type="button" className="btn btn-primary btn-small" onClick={saveEditDoor}>
                        Save
                      </button>
                      <button type="button" className="btn btn-secondary btn-small" onClick={() => setEditingDoorId(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <span className="zone-name">{d.name || 'Unnamed'}</span>
                    <span className="zone-meta">Feed {d.feed_id}</span>
                    <span className="zone-meta">{d.restriction_level}</span>
                    {d.allowed_roles?.length ? (
                      <span className="zone-roles">{d.allowed_roles.join(', ')}</span>
                    ) : null}
                    {d.rules?.time_start && (
                      <span className="zone-time">
                        {d.rules.time_start}–{d.rules.time_end}
                      </span>
                    )}
                    <div className="zone-actions">
                      <button type="button" className="btn btn-small" onClick={() => startEditDoor(d)}>
                        Edit
                      </button>
                      <button type="button" className="btn btn-small btn-danger" onClick={() => deleteDoor(d.id)}>
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
