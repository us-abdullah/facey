import React, { useState, useRef, useEffect } from 'react'

export function RegisterFace({ apiBase }) {
  const [name, setName] = useState('')
  const [role, setRole] = useState('Visitor')
  const [roles, setRoles] = useState(['Visitor', 'Worker', 'Admin'])
  const [file, setFile] = useState(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    fetch(`${apiBase}/roles`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => {
        const list = data.roles || []
        if (list.length) setRoles(list)
      })
      .catch(() => {})
  }, [apiBase])

  const onSubmit = (e) => {
    e.preventDefault()
    if (!name.trim() || !file) {
      setMessage('Enter name and choose a photo.')
      return
    }
    setLoading(true)
    setMessage('')
    const form = new FormData()
    form.append('name', name.trim())
    form.append('role', role)
    form.append('file', file)
    fetch(`${apiBase}/register`, { method: 'POST', body: form })
      .then((r) => {
        if (!r.ok) return r.json().then((j) => {
          const msg = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map(d => d.msg || d).join(', ') : r.statusText
          return Promise.reject(new Error(msg))
        })
        return r.json()
      })
      .then((data) => {
        setMessage(`Registered: ${data.name}. ${data.message}`)
        setName('')
        setFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
      })
      .catch((err) => setMessage(`Error: ${err.message}`))
      .finally(() => setLoading(false))
  }

  return (
    <section className="register-section" style={{ marginBottom: '1rem' }}>
      <form onSubmit={onSubmit} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{
            padding: '0.4rem 0.6rem',
            borderRadius: 6,
            border: '1px solid #3f3f46',
            background: '#18181b',
            color: '#e4e4e7',
            minWidth: 120,
          }}
        />
        <select
          value={roles.includes(role) ? role : roles[0]}
          onChange={(e) => setRole(e.target.value)}
          style={{
            padding: '0.4rem 0.6rem',
            borderRadius: 6,
            border: '1px solid #3f3f46',
            background: '#18181b',
            color: '#e4e4e7',
          }}
        >
          {roles.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          style={{ fontSize: '0.85rem' }}
        />
        <span style={{ fontSize: '0.75rem', color: '#71717a' }}>Clear, front-facing face photo</span>
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: '0.4rem 0.8rem',
            borderRadius: 6,
            border: '1px solid #3f3f46',
            background: '#27272a',
            color: '#e4e4e7',
            cursor: loading ? 'wait' : 'pointer',
          }}
        >
          {loading ? 'Registering…' : 'Register face'}
        </button>
      </form>
      {message && <p className="status" style={{ margin: '0.25rem 0 0 0' }}>{message}</p>}
    </section>
  )
}

export default RegisterFace
