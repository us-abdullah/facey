import React, { useState, useEffect } from 'react'

const API_BASE = '/api'

export default function ManagePeople({ onBack }) {
  const [faces, setFaces] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editName, setEditName] = useState('')
  const [editRole, setEditRole] = useState('Visitor')
  const [editAuthorized, setEditAuthorized] = useState(true)
  const [newRoleName, setNewRoleName] = useState('')

  const loadRoles = () => {
    fetch(`${API_BASE}/roles`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => setRoles(data.roles || []))
      .catch(() => setRoles(['Visitor', 'Worker', 'Admin']))
  }

  const load = () => {
    setLoading(true)
    setError('')
    fetch(`${API_BASE}/faces`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => setFaces(data.faces || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    loadRoles()
  }, [])

  const startEdit = (f) => {
    setEditingId(f.identity_id)
    setEditName(f.name || '')
    setEditRole(roles.includes(f.role) ? f.role : (roles[0] || 'Visitor'))
    setEditAuthorized(f.authorized !== false)
  }

  const cancelEdit = () => {
    setEditingId(null)
  }

  const saveEdit = () => {
    if (!editingId) return
    fetch(`${API_BASE}/faces/${editingId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: editName.trim() || null, role: editRole, authorized: editAuthorized }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => {
        setEditingId(null)
        load()
      })
      .catch((e) => setError(e.message))
  }

  const addRole = () => {
    const name = newRoleName.trim()
    if (!name) return
    setError('')
    fetch(`${API_BASE}/roles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then((r) => (r.ok ? r.json() : r.json().then((j) => Promise.reject(new Error(j.detail || r.statusText)))))
      .then(() => {
        setNewRoleName('')
        loadRoles()
      })
      .catch((e) => setError(e.message))
  }

  const deleteRole = (roleName) => {
    if (!confirm(`Delete role "${roleName}"? This will fail if anyone has this role.`)) return
    setError('')
    fetch(`${API_BASE}/roles/${encodeURIComponent(roleName)}`, { method: 'DELETE' })
      .then((r) => {
        if (!r.ok) return r.json().then((j) => Promise.reject(new Error(j.detail || r.statusText)))
        return r.json()
      })
      .then(() => loadRoles())
      .catch((e) => setError(e.message))
  }

  const deleteFace = (identity_id) => {
    if (!confirm('Remove this person from the database? They will show as Unknown until re-registered.')) return
    fetch(`${API_BASE}/faces/${identity_id}`, { method: 'DELETE' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => load())
      .catch((e) => setError(e.message))
  }

  return (
    <div className="app manage-page">
      <div className="page-header">
        <h1>Manage registered people</h1>
        <button type="button" onClick={onBack} className="back-link back-btn">← Dashboard</button>
      </div>
      {error && <p className="status error">{error}</p>}

      <section className="roles-section">
        <h2 className="section-title">Roles</h2>
        <div className="roles-add">
          <input
            type="text"
            value={newRoleName}
            onChange={(e) => setNewRoleName(e.target.value)}
            placeholder="New role name"
            className="edit-input"
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addRole())}
          />
          <button type="button" onClick={addRole} className="btn btn-primary">Add role</button>
        </div>
        <ul className="roles-list">
          {roles.map((r) => (
            <li key={r} className="role-item">
              <span>{r}</span>
              <button type="button" onClick={() => deleteRole(r)} className="btn btn-small btn-danger">Delete</button>
            </li>
          ))}
        </ul>
      </section>

      <h2 className="section-title">Registered people</h2>
      {loading ? (
        <p className="status">Loading…</p>
      ) : faces.length === 0 ? (
        <p className="status">No one registered yet. Add people from the Dashboard.</p>
      ) : (
        <ul className="faces-list">
          {faces.map((f) => (
            <li key={f.identity_id} className="face-item">
              {editingId === f.identity_id ? (
                <div className="face-edit">
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="Name"
                    className="edit-input"
                  />
                  <select
                    value={editRole}
                    onChange={(e) => setEditRole(e.target.value)}
                    className="edit-input edit-select"
                  >
                    {roles.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                  <label className="edit-checkbox">
                    <input
                      type="checkbox"
                      checked={editAuthorized}
                      onChange={(e) => setEditAuthorized(e.target.checked)}
                    />
                    Authorized
                  </label>
                  <div className="edit-actions">
                    <button type="button" onClick={saveEdit} className="btn btn-primary">Save</button>
                    <button type="button" onClick={cancelEdit} className="btn btn-secondary">Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <span className="face-name">{f.name || '(no name)'}</span>
                  <span className="face-role">{f.role || 'Visitor'}</span>
                  <span className={`face-badge ${f.authorized ? 'authorized' : 'unauthorized'}`}>
                    {f.authorized ? 'Authorized' : 'Not authorized'}
                  </span>
                  <div className="face-actions">
                    <button type="button" onClick={() => startEdit(f)} className="btn btn-small">Edit</button>
                    <button type="button" onClick={() => deleteFace(f.identity_id)} className="btn btn-small btn-danger">Delete</button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
