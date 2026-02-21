import React, { useRef, useEffect, useState, useCallback } from 'react'

const INTERVAL_MS = 400
const STROKE_WIDTH = 3
const IOU_THRESHOLD = 0.25
const CONFIDENT_SCORE = 0.42

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
    const hasConfidentMatch =
      score >= CONFIDENT_SCORE &&
      d.name &&
      String(d.name).trim() !== '' &&
      String(d.name).trim() !== 'Unknown'
    if (hasConfidentMatch) return d
    let bestIou = 0
    let best = null
    for (const p of previous) {
      const o = iou(d.bbox, p.bbox)
      if (o > bestIou) { bestIou = o; best = p }
    }
    if (bestIou >= IOU_THRESHOLD && best && best.name && best.name.trim() && best.name.trim() !== 'Unknown') {
      return { ...d, name: best.name, role: best.role, authorized: best.authorized }
    }
    return d
  })
}

function friendlyError(msg) {
  if (!msg) return ''
  if (/device in use|in use/i.test(msg)) return 'Camera in use — close other apps or click Retry.'
  if (/could not start|not found|notreadable/i.test(msg)) return 'Could not start camera — check permissions.'
  return `Error: ${msg}`
}

// ---------------------------------------------------------------------------
// Zone drawing helpers
// ---------------------------------------------------------------------------

function drawZonesOnCanvas(ctx, zones, canvasW, canvasH, fontSize) {
  for (const zone of zones) {
    const pts = (zone.points || []).map(([x, y]) => [x * canvasW, y * canvasH])
    if (pts.length === 0) continue
    const color = zone.color || '#ef4444'
    ctx.font = `${fontSize}px system-ui, sans-serif`

    if (zone.zone_type === 'polygon' && pts.length >= 3) {
      ctx.save()
      ctx.strokeStyle = color
      ctx.fillStyle = color + '2a'  // 17% opacity fill
      ctx.lineWidth = 2
      ctx.setLineDash([])
      ctx.beginPath()
      pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)))
      ctx.closePath()
      ctx.fill()
      ctx.stroke()
      // Zone label at centroid
      const cx = pts.reduce((s, [x]) => s + x, 0) / pts.length
      const cy = pts.reduce((s, [, y]) => s + y, 0) / pts.length
      ctx.fillStyle = color
      ctx.fillText(`⚠ ${zone.name}`, cx - ctx.measureText(`⚠ ${zone.name}`).width / 2, cy)
      ctx.restore()
    } else if (zone.zone_type === 'line' && pts.length >= 2) {
      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth = 3
      ctx.setLineDash([10, 5])
      ctx.beginPath()
      ctx.moveTo(pts[0][0], pts[0][1])
      ctx.lineTo(pts[1][0], pts[1][1])
      ctx.stroke()
      ctx.setLineDash([])
      // Label near midpoint
      const mx = (pts[0][0] + pts[1][0]) / 2
      const my = (pts[0][1] + pts[1][1]) / 2
      ctx.fillStyle = color
      const lbl = `🚧 ${zone.name}`
      ctx.fillText(lbl, mx - ctx.measureText(lbl).width / 2, my - 6)
      ctx.restore()
    }
  }
}

function drawZoneAlerts(ctx, zoneAlerts, scaleX, scaleY, fontSize) {
  for (const za of zoneAlerts) {
    if (za.authorized) continue
    const [x1, y1, x2, y2] = za.person_bbox
    const sx1 = Math.round(x1 * scaleX)
    const sy1 = Math.round(y1 * scaleY)
    const sw = Math.round((x2 - x1) * scaleX)
    const sh = Math.round((y2 - y1) * scaleY)
    const alertColor = za.alert_type === 'line_crossing' ? '#f97316' : '#f59e0b'
    ctx.save()
    ctx.strokeStyle = alertColor
    ctx.lineWidth = 3
    ctx.setLineDash([6, 3])
    ctx.strokeRect(sx1, sy1, sw, sh)
    ctx.setLineDash([])
    const msg =
      za.alert_type === 'line_crossing'
        ? `BREACH — ${za.person_name}`
        : `ZONE VIOLATION — ${za.person_name}`
    const msgW = Math.max(sw, ctx.measureText(msg).width + 12)
    ctx.fillStyle = alertColor
    ctx.fillRect(sx1, Math.max(0, sy1 - fontSize - 12), msgW, fontSize + 10)
    ctx.fillStyle = '#0f0f12'
    ctx.font = `bold ${fontSize}px system-ui, sans-serif`
    ctx.fillText(msg, sx1 + 6, Math.max(fontSize, sy1 - 4))
    ctx.restore()
  }
}

function drawInProgressZone(ctx, points, zoneType, canvasW, canvasH) {
  if (points.length === 0) return
  const pts = points.map(([x, y]) => [x * canvasW, y * canvasH])
  ctx.save()
  ctx.strokeStyle = '#facc15'
  ctx.lineWidth = 2
  ctx.setLineDash([6, 3])
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)))
  if (zoneType === 'polygon' && pts.length >= 2) ctx.closePath()
  ctx.stroke()
  ctx.setLineDash([])
  for (const [px, py] of pts) {
    ctx.beginPath()
    ctx.arc(px, py, 5, 0, Math.PI * 2)
    ctx.fillStyle = '#facc15'
    ctx.fill()
    ctx.strokeStyle = '#0f0f12'
    ctx.lineWidth = 1
    ctx.stroke()
  }
  ctx.restore()
}

// ===========================================================================
// Main component
// ===========================================================================

export function CameraFeed({
  slotIndex,
  devices,
  apiBase,
  doorAreas = [],
  doors = [],
  zones = [],           // camera-view zones for this feed (from App)
  onZoneAdded,         // callback after a zone is saved
  onZoneDeleted,       // callback after a zone is deleted
}) {
  const videoRef = useRef(null)
  const overlayRef = useRef(null)
  const streamRef = useRef(null)

  const [selectedId, setSelectedId] = useState('none')
  const [status, setStatus] = useState('')
  const [detections, setDetections] = useState([])
  const [doorResult, setDoorResult] = useState(null)
  const [zoneAlerts, setZoneAlerts] = useState([])
  const [retryKey, setRetryKey] = useState(0)

  const sendingRef = useRef(false)
  const rafRef = useRef(null)
  const stickyLabelsRef = useRef([])

  // Zone drawing state (use refs for access inside the RAF loop)
  const [isDrawingZone, setIsDrawingZone] = useState(false)
  const [drawingPoints, setDrawingPoints] = useState([])
  const [newZoneName, setNewZoneName] = useState('')
  const [newZoneType, setNewZoneType] = useState('polygon')

  const isDrawingZoneRef = useRef(false)
  const drawingPointsRef = useRef([])
  const newZoneTypeRef = useRef('polygon')
  const zonesRef = useRef(zones)

  // Keep refs in sync
  useEffect(() => { zonesRef.current = zones }, [zones])

  const useCombinedAnalyze = doors.some((d) => d.feed_id === slotIndex)
  const isDoorFeed = useCombinedAnalyze || doorAreas.some((a) => a.door_feed_id === slotIndex)
  const feedId = slotIndex

  // ---------------------------------------------------------------------------
  // Camera stream management
  // ---------------------------------------------------------------------------
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
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
      setZoneAlerts([])
      stickyLabelsRef.current = []
      return
    }
    let cancelled = false
    setStatus('Starting…')
    startStream(selectedId, true)
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        stopStream()
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setStatus('Live')
      })
      .catch(() => { if (!cancelled) return startStream(selectedId, false) })
      .then((stream) => {
        if (!stream || cancelled) return
        stopStream()
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setStatus('Live')
      })
      .catch((e) => { if (!cancelled) setStatus(friendlyError(e.message || e.name)) })
    return () => { cancelled = true; stopStream() }
  }, [selectedId, retryKey, stopStream, startStream])

  // ---------------------------------------------------------------------------
  // Analysis loop
  // ---------------------------------------------------------------------------
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
      if (!w || !h) { rafRef.current = requestAnimationFrame(captureAndAnalyze); return }

      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      ctx.drawImage(video, 0, 0)

      canvas.toBlob(
        (blob) => {
          if (!blob) { rafRef.current = requestAnimationFrame(captureAndAnalyze); return }
          sendingRef.current = true
          const form = new FormData()
          form.append('file', blob, 'frame.jpg')

          const endpoint = useCombinedAnalyze
            ? `${apiBase}/feed/analyze`
            : isDoorFeed
            ? `${apiBase}/door/detect`
            : `${apiBase}/recognize`

          form.append('feed_id', String(feedId))

          fetch(endpoint, { method: 'POST', body: form })
            .then((r) => {
              if (r.ok) return r.json()
              return r.json().catch(() => ({})).then((b) => Promise.reject(new Error(b.detail || r.statusText)))
            })
            .then((data) => {
              // ---------------------------------------------------------------
              // Parse response
              // ---------------------------------------------------------------
              let faces = []
              let doorData = null
              let zoneAlertsData = data.zone_alerts || []

              if (useCombinedAnalyze || !isDoorFeed) {
                const raw = data.detections || []
                const withSticky = applyStickyLabels(raw, stickyLabelsRef.current)
                stickyLabelsRef.current = withSticky.map((d) => ({
                  bbox: d.bbox.slice(),
                  name: d.name,
                  role: d.role,
                  authorized: d.authorized,
                }))
                setDetections(withSticky)
                faces = withSticky
              }

              if (useCombinedAnalyze || isDoorFeed) {
                doorData = {
                  doors: data.doors || [],
                  movement_detected: data.movement_detected || false,
                  area_name: data.area_name ?? null,
                  last_person: data.last_person ?? null,
                  allowed: data.allowed !== false,
                  alert: data.alert || false,
                  hint: data.hint,
                }
                if (!useCombinedAnalyze) setDetections([])
                setDoorResult(doorData)
              } else {
                setDoorResult(null)
              }

              setZoneAlerts(zoneAlertsData)
              setStatus('Live')

              // ---------------------------------------------------------------
              // Draw overlay
              // ---------------------------------------------------------------
              const rect = overlay.getBoundingClientRect()
              const scaleX = rect.width / w
              const scaleY = rect.height / h
              const ovCtx = overlay.getContext('2d')
              overlay.width = rect.width
              overlay.height = rect.height
              ovCtx.clearRect(0, 0, overlay.width, overlay.height)

              const fontSize = Math.max(12, Math.round(14 * Math.min(scaleX, scaleY)))
              ovCtx.font = `${fontSize}px system-ui, sans-serif`

              // Draw existing zones
              drawZonesOnCanvas(ovCtx, zonesRef.current, overlay.width, overlay.height, fontSize)

              // Draw door bboxes
              if (doorData) {
                for (const d of doorData.doors || []) {
                  const [x1, y1, x2, y2] = d.bbox
                  ovCtx.strokeStyle = '#3b82f6'
                  ovCtx.lineWidth = STROKE_WIDTH
                  ovCtx.setLineDash([4, 4])
                  ovCtx.strokeRect(
                    Math.round(x1 * scaleX), Math.round(y1 * scaleY),
                    Math.round((x2 - x1) * scaleX), Math.round((y2 - y1) * scaleY)
                  )
                  ovCtx.setLineDash([])
                }
              }

              // Draw face bboxes
              ovCtx.font = `${fontSize}px system-ui, sans-serif`
              for (const d of faces) {
                const [x1, y1, x2, y2] = d.bbox
                const color = d.authorized ? '#22c55e' : '#ef4444'
                const sx1 = Math.round(x1 * scaleX)
                const sy1 = Math.round(y1 * scaleY)
                const sw = Math.round((x2 - x1) * scaleX)
                const sh = Math.round((y2 - y1) * scaleY)
                ovCtx.strokeStyle = color
                ovCtx.lineWidth = STROKE_WIDTH
                ovCtx.strokeRect(sx1, sy1, sw, sh)
                const namePart = d.name?.trim() || 'Unknown'
                const rolePart = d.role?.trim() || ''
                const label = rolePart && namePart !== 'Unknown' ? `${namePart} (${rolePart})` : namePart
                const labelW = Math.max(sw, ovCtx.measureText(label).width + 10)
                const labelH = fontSize + 8
                const labelY = sy1 - labelH - 2
                ovCtx.fillStyle = color
                ovCtx.fillRect(sx1, labelY, labelW, labelH)
                ovCtx.fillStyle = '#0f0f12'
                ovCtx.fillText(label, sx1 + 5, labelY + fontSize)
              }

              // Draw zone violation overlays
              drawZoneAlerts(ovCtx, zoneAlertsData, scaleX, scaleY, fontSize)

              // Draw door movement banner
              if (doorData?.movement_detected && (doorData.area_name || doorData.last_person)) {
                const msg = doorData.alert
                  ? `DOOR ALERT — ${doorData.last_person?.name || 'Unknown'} — RESTRICTED`
                  : doorData.last_person
                  ? `Entering — ${doorData.last_person.name} (${doorData.last_person.role}) — OK`
                  : `Door movement — ${doorData.area_name || 'Door'}`
                ovCtx.fillStyle = doorData.alert ? '#ef4444' : '#22c55e'
                ovCtx.fillRect(8, 8, Math.max(200, ovCtx.measureText(msg).width + 16), fontSize + 16)
                ovCtx.fillStyle = '#0f0f12'
                ovCtx.fillText(msg, 12, 8 + fontSize + 4)
              }

              // Draw hint when no door detected
              if (doorData && !doorData.doors?.length && doorData.hint) {
                ovCtx.fillStyle = 'rgba(0,0,0,0.7)'
                ovCtx.fillRect(8, overlay.height - 28, overlay.width - 16, 22)
                ovCtx.fillStyle = '#fbbf24'
                ovCtx.font = `${Math.max(11, fontSize - 2)}px system-ui, sans-serif`
                ovCtx.fillText(doorData.hint, 12, overlay.height - 11)
              }

              // Draw in-progress zone (if user is drawing)
              drawInProgressZone(
                ovCtx,
                drawingPointsRef.current,
                newZoneTypeRef.current,
                overlay.width,
                overlay.height
              )
            })
            .catch((err) => {
              setDetections([])
              setDoorResult({ doors: [], movement_detected: false, area_name: null, last_person: null, allowed: true, alert: false })
              setZoneAlerts([])
              setStatus(err.message && err.message.length < 80 ? err.message : 'Analysis unavailable')
            })
            .finally(() => { sendingRef.current = false })
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

  // ---------------------------------------------------------------------------
  // Zone drawing handlers
  // ---------------------------------------------------------------------------
  const handleCanvasClick = useCallback((e) => {
    if (!isDrawingZoneRef.current) return
    const canvas = overlayRef.current
    if (!canvas) return
    // For line type, max 2 points
    if (newZoneTypeRef.current === 'line' && drawingPointsRef.current.length >= 2) return
    const rect = canvas.getBoundingClientRect()
    const nx = (e.clientX - rect.left) / rect.width
    const ny = (e.clientY - rect.top) / rect.height
    const newPts = [...drawingPointsRef.current, [nx, ny]]
    drawingPointsRef.current = newPts
    setDrawingPoints(newPts)
  }, [])

  const startDrawing = () => {
    setIsDrawingZone(true)
    isDrawingZoneRef.current = true
    setDrawingPoints([])
    drawingPointsRef.current = []
    setNewZoneName('')
    setNewZoneType('polygon')
    newZoneTypeRef.current = 'polygon'
  }

  const cancelDrawing = () => {
    setIsDrawingZone(false)
    isDrawingZoneRef.current = false
    setDrawingPoints([])
    drawingPointsRef.current = []
  }

  const changeZoneType = (t) => {
    setNewZoneType(t)
    newZoneTypeRef.current = t
    // If switching to line, trim to max 2 points
    if (t === 'line') {
      const trimmed = drawingPointsRef.current.slice(0, 2)
      drawingPointsRef.current = trimmed
      setDrawingPoints(trimmed)
    }
  }

  const saveZone = () => {
    const minPts = newZoneType === 'line' ? 2 : 3
    if (drawingPoints.length < minPts) return
    const zone = {
      feed_id: slotIndex,
      name: newZoneName.trim() || 'Restricted Zone',
      zone_type: newZoneType,
      points: drawingPoints,
      authorized_roles: [],
      color: newZoneType === 'line' ? '#f97316' : '#ef4444',
      active: true,
    }
    fetch(`${apiBase}/camera-zones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(zone),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => {
        cancelDrawing()
        onZoneAdded?.()
      })
      .catch((e) => alert(e.message || 'Failed to save zone'))
  }

  const deleteZone = (zoneId) => {
    if (!window.confirm('Delete this zone?')) return
    fetch(`${apiBase}/camera-zones/${zoneId}`, { method: 'DELETE' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(() => onZoneDeleted?.())
      .catch((e) => alert(e.message || 'Failed to delete zone'))
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const options = [
    { deviceId: 'none', label: 'No camera' },
    ...devices.map((d) => ({ deviceId: d.deviceId, label: d.label || `Camera ${slotIndex + 1}` })),
  ]

  const doorPoint = doors.find((d) => d.feed_id === slotIndex)
  const doorArea = doorAreas.find((a) => a.door_feed_id === slotIndex)
  const faceArea = doorAreas.find((a) => a.face_feed_id === slotIndex)
  const roleLabel = doorPoint
    ? `Door: ${doorPoint.name}`
    : doorArea
    ? `Door (${doorArea.name})`
    : faceArea
    ? `Face (${faceArea.name})`
    : null

  const isActive = selectedId && selectedId !== 'none'
  const minPts = newZoneType === 'line' ? 2 : 3
  const canSave = drawingPoints.length >= minPts

  const unauthorizedZoneAlerts = zoneAlerts.filter((za) => !za.authorized)

  return (
    <div className="feed-slot">
      {/* Header */}
      <div className="header">
        <label>Feed {slotIndex + 1}{roleLabel ? ` — ${roleLabel}` : ''}</label>
        <div className="header-controls">
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            aria-label={`Select camera for feed ${slotIndex + 1}`}
          >
            {options.map((opt) => (
              <option key={opt.deviceId} value={opt.deviceId}>{opt.label}</option>
            ))}
          </select>
          {isActive && !isDrawingZone && (
            <button
              type="button"
              className="zone-draw-btn"
              onClick={startDrawing}
              title="Draw a restricted zone on this feed"
            >
              ✏️ Zone
            </button>
          )}
        </div>
      </div>

      {/* Video + overlay canvas */}
      <div className="video-wrap">
        {!isActive ? (
          <div className="placeholder">Select a camera</div>
        ) : (
          <>
            <video ref={videoRef} autoPlay playsInline muted />
            <canvas
              ref={overlayRef}
              className="overlay-canvas"
              onClick={handleCanvasClick}
              style={{
                cursor: isDrawingZone ? 'crosshair' : 'default',
                pointerEvents: isDrawingZone ? 'auto' : 'none',
              }}
            />
          </>
        )}
      </div>

      {/* Zone drawing form */}
      {isDrawingZone && (
        <div className="zone-draw-panel">
          <div className="zone-draw-header">Define Restricted Zone for Feed {slotIndex + 1}</div>
          <input
            type="text"
            className="edit-input zone-name-input"
            placeholder="Zone name (e.g. Server Room)"
            value={newZoneName}
            onChange={(e) => setNewZoneName(e.target.value)}
          />
          <div className="zone-type-row">
            <span>Type:</span>
            <button
              type="button"
              className={`chip ${newZoneType === 'polygon' ? 'active' : ''}`}
              onClick={() => changeZoneType('polygon')}
            >
              Polygon Zone
            </button>
            <button
              type="button"
              className={`chip ${newZoneType === 'line' ? 'active' : ''}`}
              onClick={() => changeZoneType('line')}
            >
              Boundary Line
            </button>
          </div>
          <p className="zone-draw-hint">
            {newZoneType === 'line'
              ? 'Click exactly 2 points on the video to define the boundary line. Anyone crossing it will trigger an alert.'
              : 'Click 3+ points on the video to define the restricted area polygon. Anyone inside will trigger an alert.'}
          </p>
          <p className="zone-draw-count">
            Points placed: <strong>{drawingPoints.length}</strong>
            {newZoneType === 'line' ? ' / 2' : ` (min ${minPts})`}
          </p>
          <div className="zone-draw-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={saveZone}
              disabled={!canSave}
            >
              Save Zone
            </button>
            <button type="button" className="btn" onClick={cancelDrawing}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Existing zones list for this feed */}
      {zones.length > 0 && !isDrawingZone && (
        <div className="feed-zones-list">
          {zones.map((z) => (
            <div key={z.id} className="feed-zone-chip">
              <span style={{ color: z.color || '#ef4444' }}>
                {z.zone_type === 'line' ? '🚧' : '⚠️'}
              </span>
              <span className="feed-zone-name">{z.name}</span>
              <span className="feed-zone-type">({z.zone_type})</span>
              <button
                type="button"
                className="zone-delete-btn"
                onClick={() => deleteZone(z.id)}
                title="Delete zone"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Footer: status + zone alert count */}
      <div className="feed-footer">
        {status && (
          <div
            className={`status ${
              status !== 'Live' && status !== 'Starting…' ? 'error' : 'analyzing'
            }`}
          >
            {status}
          </div>
        )}
        {unauthorizedZoneAlerts.length > 0 && (
          <div className="zone-alert-badge">
            {unauthorizedZoneAlerts[0].alert_type === 'line_crossing' ? '🚧' : '⚠️'}{' '}
            <strong>
              {unauthorizedZoneAlerts.length} zone alert{unauthorizedZoneAlerts.length > 1 ? 's' : ''}
            </strong>
          </div>
        )}
        {status &&
          status !== 'Live' &&
          status !== 'Starting…' &&
          selectedId &&
          selectedId !== 'none' && (
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
