import React, { useState, useEffect, useCallback } from 'react'
import { CameraFeed } from './CameraFeed'
import RegisterFace from './RegisterFace'
import ManagePeople from './pages/ManagePeople'
import FloorPlan from './pages/FloorPlan'

// Use same-origin /api so Vite proxies to backend (no CORS). Ensure backend runs on port 8000.
const API_BASE = '/api'

const DEFAULT_AREAS = [
  { id: 'office1', name: 'Office 1', face_feed_id: 0, door_feed_id: 1, allowed_roles: ['Admin'] },
  { id: 'office2', name: 'Office 2', face_feed_id: 2, door_feed_id: 3, allowed_roles: ['Admin', 'Worker'] },
]

export default function App() {
  const [view, setView] = useState('dashboard') // 'dashboard' | 'manage' | 'floorplan'
  const [devices, setDevices] = useState([])
  const [devicesError, setDevicesError] = useState(null)
  const [doorAreas, setDoorAreas] = useState(DEFAULT_AREAS)
  const [doors, setDoors] = useState([]) // floor plan door points (feed_id → permissions)
  const [roles, setRoles] = useState([])

  const loadDoorAreas = useCallback(() => {
    fetch(`${API_BASE}/door/areas`)
      .then((r) => {
        if (r.ok) return r.json()
        return Promise.reject(new Error(r.statusText))
      })
      .then((data) => setDoorAreas(Array.isArray(data?.areas) ? data.areas : DEFAULT_AREAS))
      .catch(() => setDoorAreas(DEFAULT_AREAS))
  }, [])
  const loadDoors = useCallback(() => {
    fetch(`${API_BASE}/floorplan/doors`)
      .then((r) => (r.ok ? r.json() : { doors: [] }))
      .then((data) => setDoors(Array.isArray(data?.doors) ? data.doors : []))
      .catch(() => setDoors([]))
  }, [])
  const loadRoles = useCallback(() => {
    fetch(`${API_BASE}/roles`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => setRoles(data.roles || []))
      .catch(() => setRoles([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true })
        stream.getTracks().forEach(t => t.stop())
        const list = await navigator.mediaDevices.enumerateDevices()
        const videoInputs = list.filter(d => d.kind === 'videoinput')
        if (!cancelled) setDevices(videoInputs)
      } catch (e) {
        if (!cancelled) {
          setDevicesError(e.message || 'Could not list cameras')
          setDevices([])
        }
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    loadDoorAreas()
    loadDoors()
    loadRoles()
  }, [loadDoorAreas, loadDoors, loadRoles])

  if (view === 'manage') {
    return (
      <div className="app">
        <ManagePeople onBack={() => setView('dashboard')} />
      </div>
    )
  }
  if (view === 'floorplan') {
    return (
      <div className="app">
        <FloorPlan onBack={() => { loadDoors(); setView('dashboard') }} />
      </div>
    )
  }

  return (
    <div className="app">
      <div className="app-header">
        <h1>Hof Capital Inspection — Client Dashboard</h1>
        <div className="header-links">
          <button type="button" onClick={() => setView('floorplan')} className="manage-link manage-btn">Floor plan →</button>
          <button type="button" onClick={() => setView('manage')} className="manage-link manage-btn">Manage people →</button>
        </div>
      </div>
      {devicesError && (
        <p className="status error">
          Camera access: {devicesError}. Allow camera permission and refresh.
        </p>
      )}
      <RegisterFace apiBase={API_BASE} />
      <DoorAccessSetup
        apiBase={API_BASE}
        doorAreas={doorAreas}
        roles={roles}
        onSave={() => { loadDoorAreas(); loadRoles() }}
      />
      <div className="feeds">
        {[0, 1, 2, 3].map((slot) => (
          <CameraFeed
            key={slot}
            slotIndex={slot}
            devices={devices}
            apiBase={API_BASE}
            doorAreas={doorAreas}
            doors={doors}
          />
        ))}
      </div>
    </div>
  )
}

function DoorAccessSetup({ apiBase, doorAreas, roles, onSave }) {
  const [open, setOpen] = useState(false)
  const [areas, setAreas] = useState(doorAreas)

  useEffect(() => {
    setAreas(doorAreas)
  }, [doorAreas])

  const setArea = (index, field, value) => {
    setAreas((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  const toggleRole = (areaIndex, role) => {
    const a = areas[areaIndex]
    const allowed = a.allowed_roles || []
    const next = allowed.includes(role)
      ? allowed.filter((r) => r !== role)
      : [...allowed, role]
    setArea(areaIndex, 'allowed_roles', next)
  }

  const save = () => {
    fetch(`${apiBase}/door/areas`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ areas }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => {
        setAreas(data.areas)
        onSave()
        setOpen(false)
      })
      .catch((e) => alert(e.message || 'Failed to save'))
  }

  return (
    <section className="door-access-setup">
      <button
        type="button"
        className="manage-link manage-btn"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? '▼ Door access setup' : '▶ Door access setup (Office 1 & 2)'}
      </button>
      {open && (
        <div className="door-access-form">
          <p className="door-access-hint">
            Assign which feed is the <strong>face camera</strong> (person at door) and which is the <strong>door camera</strong> for each area. When the door moves, the last recognized person and their role are checked against allowed roles.
          </p>
          {areas.map((area, i) => (
            <div key={area.id || i} className="door-area-row">
              <label>
                Area name
                <input
                  type="text"
                  value={area.name || ''}
                  onChange={(e) => setArea(i, 'name', e.target.value)}
                  placeholder="e.g. Office 1"
                  className="edit-input"
                />
              </label>
              <label>
                Face feed (person)
                <select
                  value={area.face_feed_id ?? 0}
                  onChange={(e) => setArea(i, 'face_feed_id', parseInt(e.target.value, 10))}
                  className="edit-input"
                >
                  {[0, 1, 2, 3].map((n) => (
                    <option key={n} value={n}>Feed {n + 1}</option>
                  ))}
                </select>
              </label>
              <label>
                Door feed (door view)
                <select
                  value={area.door_feed_id ?? 1}
                  onChange={(e) => setArea(i, 'door_feed_id', parseInt(e.target.value, 10))}
                  className="edit-input"
                >
                  {[0, 1, 2, 3].map((n) => (
                    <option key={n} value={n}>Feed {n + 1}</option>
                  ))}
                </select>
              </label>
              <div className="allowed-roles">
                <span>Allowed roles</span>
                <div className="roles-chips">
                  {roles.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className={`chip ${(area.allowed_roles || []).includes(r) ? 'active' : ''}`}
                      onClick={() => toggleRole(i, r)}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ))}
          <button type="button" className="btn btn-primary" onClick={save}>
            Save door access
          </button>
        </div>
      )}
    </section>
  )
}
