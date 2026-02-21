import React, { useRef, useEffect, useState, useCallback } from 'react'

const INTERVAL_MS = 400
const STROKE_WIDTH = 3
const IOU_THRESHOLD = 0.25
const CONFIDENT_SCORE = 0.42  // above this we trust server name; below we may use sticky to avoid flicker

function iou(bboxA, bboxB) {
  const [ax1, ay1, ax2, ay2] = bboxA
  const [bx1, by1, bx2, by2] = bboxB
  const ix1 = Math.max(ax1, bx1)
  const iy1 = Math.max(ay1, by1)
  const ix2 = Math.min(ax2, bx2)
  const iy2 = Math.min(ay2, by2)
  if (ix2 <= ix1 || iy2 <= iy1) return 0
  const inter = (ix2 - ix1) * (iy2 - iy1)
  const areaA = (ax2 - ax1) * (ay2 - ay1)
  const areaB = (bx2 - bx1) * (by2 - by1)
  return inter / (areaA + areaB - inter)
}

function applyStickyLabels(newDetections, previous) {
  if (!previous || previous.length === 0) return newDetections
  return newDetections.map((d) => {
    const score = typeof d.score === 'number' ? d.score : 0
    const hasConfidentMatch = score >= CONFIDENT_SCORE && d.name && String(d.name).trim() !== '' && String(d.name).trim() !== 'Unknown'
    if (hasConfidentMatch) return d
    let bestIou = 0
    let best = null
    for (const p of previous) {
      const o = iou(d.bbox, p.bbox)
      if (o > bestIou) {
        bestIou = o
        best = p
      }
    }
    if (bestIou >= IOU_THRESHOLD && best && best.name && best.name.trim() && best.name.trim() !== 'Unknown') {
      return { ...d, name: best.name, role: best.role, authorized: best.authorized }
    }
    return d
  })
}

function friendlyError(msg) {
  if (!msg) return ''
  if (/device in use|in use/i.test(msg)) return 'Camera in use — close other apps (Camo, Zoom, etc.) or click Retry.'
  if (/could not start|not found|notreadable/i.test(msg)) return 'Could not start camera — check browser permissions or click Retry.'
  return `Error: ${msg}`
}

export function CameraFeed({ slotIndex, devices, apiBase, doorAreas = [], doors = [] }) {
  const videoRef = useRef(null)
  const overlayRef = useRef(null)
  const streamRef = useRef(null)
  const [selectedId, setSelectedId] = useState('none')
  const [status, setStatus] = useState('')
  const [detections, setDetections] = useState([])
  const [doorResult, setDoorResult] = useState(null) // { doors, movement_detected, area_name, last_person, allowed, alert }
  const [retryKey, setRetryKey] = useState(0)
  const sendingRef = useRef(false)
  const rafRef = useRef(null)
  const stickyLabelsRef = useRef([])

  // Floor plan door point = one feed does both face + door; use combined analyze
  const useCombinedAnalyze = doors.some((d) => d.feed_id === slotIndex)
  const isDoorFeed = useCombinedAnalyze || doorAreas.some((a) => a.door_feed_id === slotIndex)
  const feedId = slotIndex

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const startStream = useCallback((deviceId, useExact = true) => {
    const constraints = useExact
      ? { video: { deviceId: { exact: deviceId } } }
      : { video: { deviceId: { ideal: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } } }
    return navigator.mediaDevices.getUserMedia(constraints)
  }, [])

  useEffect(() => {
    if (!selectedId || selectedId === 'none') {
      stopStream()
      setStatus('')
      setDetections([])
      setDoorResult(null)
      stickyLabelsRef.current = []
      return
    }
    let cancelled = false
    setStatus('Starting…')
    startStream(selectedId, true)
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach(t => t.stop())
          return
        }
        stopStream()
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setStatus('Live')
      })
      .catch(() => {
        if (cancelled) return
        return startStream(selectedId, false)
      })
      .then((stream) => {
        if (!stream || cancelled) return
        stopStream()
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setStatus('Live')
      })
      .catch((e) => {
        if (!cancelled) setStatus(friendlyError(e.message || e.name))
      })
    return () => {
      cancelled = true
      stopStream()
    }
  }, [selectedId, retryKey, stopStream, startStream])

  useEffect(() => {
    if (!selectedId || selectedId === 'none' || !videoRef.current || !overlayRef.current) return

    const video = videoRef.current
    const overlay = overlayRef.current

    function captureAndAnalyze() {
      if (sendingRef.current || video.readyState < 2) {
        rafRef.current = requestAnimationFrame(captureAndAnalyze)
        return
      }
      const w = video.videoWidth
      const h = video.videoHeight
      if (!w || !h) {
        rafRef.current = requestAnimationFrame(captureAndAnalyze)
        return
      }
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      ctx.drawImage(video, 0, 0)
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            rafRef.current = requestAnimationFrame(captureAndAnalyze)
            return
          }
          sendingRef.current = true
          const form = new FormData()
          form.append('file', blob, 'frame.jpg')

          if (useCombinedAnalyze) {
            form.append('feed_id', String(feedId))
            fetch(`${apiBase}/feed/analyze`, { method: 'POST', body: form })
              .then((r) => {
                if (r.ok) return r.json()
                return r.json().catch(() => ({})).then((body) => Promise.reject(new Error(body.detail || r.statusText)))
              })
              .then((data) => {
                const raw = data.detections || []
                const withSticky = applyStickyLabels(raw, stickyLabelsRef.current)
                stickyLabelsRef.current = withSticky.map((d) => ({ bbox: d.bbox.slice(), name: d.name, role: d.role, authorized: d.authorized }))
                setDetections(withSticky)
                setDoorResult({
                  doors: data.doors || [],
                  movement_detected: data.movement_detected || false,
                  area_name: data.area_name ?? null,
                  last_person: data.last_person ?? null,
                  allowed: data.allowed !== false,
                  alert: data.alert || false,
                  hint: data.hint,
                })
                setStatus('Live')
                const rect = overlay.getBoundingClientRect()
                const scaleX = rect.width / w
                const scaleY = rect.height / h
                const ovCtx = overlay.getContext('2d')
                overlay.width = rect.width
                overlay.height = rect.height
                ovCtx.clearRect(0, 0, overlay.width, overlay.height)
                const fontSize = Math.max(12, Math.round(14 * Math.min(scaleX, scaleY)))
                ovCtx.font = `${fontSize}px system-ui, sans-serif`
                const doorColor = '#3b82f6'
                for (const d of data.doors || []) {
                  const [x1, y1, x2, y2] = d.bbox
                  const sx1 = Math.round(x1 * scaleX)
                  const sy1 = Math.round(y1 * scaleY)
                  const sw = Math.round((x2 - x1) * scaleX)
                  const sh = Math.round((y2 - y1) * scaleY)
                  ovCtx.strokeStyle = doorColor
                  ovCtx.lineWidth = STROKE_WIDTH
                  ovCtx.setLineDash([4, 4])
                  ovCtx.strokeRect(sx1, sy1, sw, sh)
                  ovCtx.setLineDash([])
                }
                for (const d of withSticky) {
                  const [x1, y1, x2, y2] = d.bbox
                  const color = d.authorized ? '#22c55e' : '#ef4444'
                  const sx1 = Math.round(x1 * scaleX)
                  const sy1 = Math.round(y1 * scaleY)
                  const sw = Math.round((x2 - x1) * scaleX)
                  const sh = Math.round((y2 - y1) * scaleY)
                  ovCtx.strokeStyle = color
                  ovCtx.lineWidth = STROKE_WIDTH
                  ovCtx.strokeRect(sx1, sy1, sw, sh)
                  const namePart = (d.name && d.name.trim()) ? d.name.trim() : 'Unknown'
                  const rolePart = (d.role && d.role.trim()) ? d.role.trim() : ''
                  const label = rolePart && namePart !== 'Unknown' ? `${namePart} (${rolePart})` : namePart
                  const labelW = Math.max(sw, ovCtx.measureText(label).width + 10)
                  const labelH = fontSize + 8
                  const labelY = sy1 - labelH - 2
                  ovCtx.fillStyle = color
                  ovCtx.fillRect(sx1, labelY, labelW, labelH)
                  ovCtx.fillStyle = '#0f0f12'
                  ovCtx.fillText(label, sx1 + 5, labelY + fontSize)
                }
                if (data.movement_detected && (data.area_name || data.last_person)) {
                  const msg = data.alert
                    ? `Entering — ${data.last_person?.name || 'Unknown'} — RESTRICTED`
                    : data.last_person ? `Entering — ${data.last_person.name} (${data.last_person.role}) — OK` : `Door movement — ${data.area_name || 'Door'}`
                  ovCtx.fillStyle = data.alert ? '#ef4444' : '#22c55e'
                  ovCtx.fillRect(8, 8, Math.max(200, ovCtx.measureText(msg).width + 16), fontSize + 16)
                  ovCtx.fillStyle = '#0f0f12'
                  ovCtx.fillText(msg, 12, 8 + fontSize + 4)
                }
                if ((!data.doors || data.doors.length === 0) && data.hint) {
                  ovCtx.fillStyle = 'rgba(0,0,0,0.7)'
                  ovCtx.fillRect(8, overlay.height - 28, overlay.width - 16, 22)
                  ovCtx.fillStyle = '#fbbf24'
                  ovCtx.font = `${Math.max(11, fontSize - 2)}px system-ui, sans-serif`
                  ovCtx.fillText(data.hint, 12, overlay.height - 11)
                }
              })
              .catch((err) => {
                setDetections([])
                setDoorResult({ doors: [], movement_detected: false, area_name: null, last_person: null, allowed: true, alert: false })
                setStatus(err.message && err.message.length < 80 ? err.message : 'Analysis unavailable')
              })
              .finally(() => { sendingRef.current = false })
          } else if (isDoorFeed) {
            form.append('feed_id', String(feedId))
            fetch(`${apiBase}/door/detect`, { method: 'POST', body: form })
              .then((r) => {
                if (r.ok) return r.json()
                return r.json().catch(() => ({})).then((body) => Promise.reject(new Error(body.detail || r.statusText)))
              })
              .then((data) => {
                setDoorResult(data || { doors: [], movement_detected: false, area_name: null, last_person: null, allowed: true, alert: false })
                setDetections([])
                setStatus('Live')
                const rect = overlay.getBoundingClientRect()
                const scaleX = rect.width / w
                const scaleY = rect.height / h
                const ovCtx = overlay.getContext('2d')
                overlay.width = rect.width
                overlay.height = rect.height
                ovCtx.clearRect(0, 0, overlay.width, overlay.height)
                const doorColor = '#3b82f6'
                for (const d of data.doors || []) {
                  const [x1, y1, x2, y2] = d.bbox
                  const sx1 = Math.round(x1 * scaleX)
                  const sy1 = Math.round(y1 * scaleY)
                  const sw = Math.round((x2 - x1) * scaleX)
                  const sh = Math.round((y2 - y1) * scaleY)
                  ovCtx.strokeStyle = doorColor
                  ovCtx.lineWidth = STROKE_WIDTH
                  ovCtx.strokeRect(sx1, sy1, sw, sh)
                  ovCtx.setLineDash([4, 4])
                  ovCtx.strokeRect(sx1, sy1, sw, sh)
                  ovCtx.setLineDash([])
                }
                const fontSize = Math.max(12, Math.round(14 * Math.min(scaleX, scaleY)))
                ovCtx.font = `${fontSize}px system-ui, sans-serif`
                if (data.movement_detected && data.area_name) {
                  const msg = data.alert
                    ? `Door movement — ${data.last_person?.name || 'Unknown'} — RESTRICTED`
                    : data.last_person ? `Door movement — ${data.last_person.name} (${data.last_person.role}) — OK` : `Door movement — ${data.area_name}`
                  ovCtx.fillStyle = data.alert ? '#ef4444' : '#22c55e'
                  ovCtx.fillRect(8, 8, Math.max(200, ovCtx.measureText(msg).width + 16), fontSize + 16)
                  ovCtx.fillStyle = '#0f0f12'
                  ovCtx.fillText(msg, 12, 8 + fontSize + 4)
                }
                if ((!data.doors || data.doors.length === 0) && data.hint) {
                  ovCtx.fillStyle = 'rgba(0,0,0,0.7)'
                  ovCtx.fillRect(8, overlay.height - 28, overlay.width - 16, 22)
                  ovCtx.fillStyle = '#fbbf24'
                  ovCtx.font = `${Math.max(11, fontSize - 2)}px system-ui, sans-serif`
                  ovCtx.fillText(data.hint, 12, overlay.height - 11)
                }
              })
              .catch((err) => {
                setDoorResult({ doors: [], movement_detected: false, area_name: null, last_person: null, allowed: true, alert: false })
                setStatus(err.message && err.message.length < 50 ? err.message : 'Door detection unavailable')
              })
              .finally(() => { sendingRef.current = false })
          } else {
            form.append('feed_id', String(feedId))
            fetch(`${apiBase}/recognize`, { method: 'POST', body: form })
              .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
              .then((data) => {
                const raw = data.detections || []
                const withSticky = applyStickyLabels(raw, stickyLabelsRef.current)
                stickyLabelsRef.current = withSticky.map((d) => ({ bbox: d.bbox.slice(), name: d.name, role: d.role, authorized: d.authorized }))
                setDetections(withSticky)
                setDoorResult(null)
                setStatus('Live')
                const rect = overlay.getBoundingClientRect()
                const scaleX = rect.width / w
                const scaleY = rect.height / h
                const ovCtx = overlay.getContext('2d')
                overlay.width = rect.width
                overlay.height = rect.height
                ovCtx.clearRect(0, 0, overlay.width, overlay.height)
                const fontSize = Math.max(12, Math.round(14 * Math.min(scaleX, scaleY)))
                ovCtx.font = `${fontSize}px system-ui, sans-serif`
                for (const d of withSticky) {
                  const [x1, y1, x2, y2] = d.bbox
                  const color = d.authorized ? '#22c55e' : '#ef4444'
                  const sx1 = Math.round(x1 * scaleX)
                  const sy1 = Math.round(y1 * scaleY)
                  const sw = Math.round((x2 - x1) * scaleX)
                  const sh = Math.round((y2 - y1) * scaleY)
                  ovCtx.strokeStyle = color
                  ovCtx.lineWidth = STROKE_WIDTH
                  ovCtx.strokeRect(sx1, sy1, sw, sh)
                  const namePart = (d.name && d.name.trim()) ? d.name.trim() : 'Unknown'
                  const rolePart = (d.role && d.role.trim()) ? d.role.trim() : ''
                  const label = rolePart && namePart !== 'Unknown' ? `${namePart} (${rolePart})` : namePart
                  const labelW = Math.max(sw, ovCtx.measureText(label).width + 10)
                  const labelH = fontSize + 8
                  const labelY = sy1 - labelH - 2
                  ovCtx.fillStyle = color
                  ovCtx.fillRect(sx1, labelY, labelW, labelH)
                  ovCtx.fillStyle = '#0f0f12'
                  ovCtx.fillText(label, sx1 + 5, labelY + fontSize)
                }
              })
              .catch(() => setStatus('Recognition error'))
              .finally(() => { sendingRef.current = false })
          }
        },
        'image/jpeg',
        0.85
      )
      rafRef.current = setTimeout(captureAndAnalyze, INTERVAL_MS)
    }

    const t = setTimeout(captureAndAnalyze, 500)
    return () => {
      clearTimeout(t)
      if (rafRef.current) clearTimeout(rafRef.current)
    }
  }, [selectedId, apiBase, useCombinedAnalyze, isDoorFeed, feedId])

  const options = [
    { deviceId: 'none', label: 'No camera' },
    ...devices.map((d) => ({ deviceId: d.deviceId, label: d.label || `Camera ${slotIndex + 1}` })),
  ]

  const doorPoint = doors.find((d) => d.feed_id === slotIndex)
  const doorArea = doorAreas.find((a) => a.door_feed_id === slotIndex)
  const faceArea = doorAreas.find((a) => a.face_feed_id === slotIndex)
  const roleLabel = doorPoint ? `Door: ${doorPoint.name}` : doorArea ? `Door (${doorArea.name})` : faceArea ? `Face (${faceArea.name})` : null

  return (
    <div className="feed-slot">
      <div className="header">
        <label>Feed {slotIndex + 1}{roleLabel ? ` — ${roleLabel}` : ''}</label>
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          aria-label={`Select camera for feed ${slotIndex + 1}`}
        >
          {options.map((opt) => (
            <option key={opt.deviceId} value={opt.deviceId}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="video-wrap">
        {!selectedId || selectedId === 'none' ? (
          <div className="placeholder">Select a camera</div>
        ) : (
          <>
            <video ref={videoRef} autoPlay playsInline muted />
            <canvas ref={overlayRef} className="overlay-canvas" />
          </>
        )}
      </div>
      <div className="feed-footer">
        {status && (
          <div className={`status ${status !== 'Live' && status !== 'Starting…' && status !== 'Recognition error' ? 'error' : 'analyzing'}`}>
            {status}
          </div>
        )}
        {status && status !== 'Live' && status !== 'Starting…' && selectedId && selectedId !== 'none' && (
          <button
            type="button"
            className="retry-btn"
            onClick={() => { setStatus(''); setRetryKey((k) => k + 1) }}
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
