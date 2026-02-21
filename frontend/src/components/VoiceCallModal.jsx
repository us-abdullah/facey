import React, { useEffect, useRef, useState } from 'react'

/**
 * Simulated phone call in the browser: ring tone, then "Answer" plays the
 * ElevenLabs TTS message from the backend.
 */
export default function VoiceCallModal({ alert, apiBase, onClose }) {
  const [phase, setPhase] = useState('ringing') // 'ringing' | 'connected' | 'ended'
  const ringIntervalRef = useRef(null)
  const audioRef = useRef(null)

  // Ring tone: simple "ring ring" with Web Audio API
  useEffect(() => {
    if (!alert || phase !== 'ringing') return
    let audioContext = null
    const scheduleRing = () => {
      if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const osc = audioContext.createOscillator()
      const gain = audioContext.createGain()
      osc.connect(gain)
      gain.connect(audioContext.destination)
      osc.frequency.value = 800
      osc.type = 'sine'
      gain.gain.setValueAtTime(0.15, audioContext.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.4)
      osc.start(audioContext.currentTime)
      osc.stop(audioContext.currentTime + 0.4)
    }
    const ring = () => {
      scheduleRing()
      setTimeout(scheduleRing, 400)
    }
    ring()
    const id = setInterval(ring, 2000)
    ringIntervalRef.current = id
    return () => {
      if (ringIntervalRef.current) clearInterval(ringIntervalRef.current)
    }
  }, [alert?.alert_id, phase])

  const handleAnswer = () => {
    if (ringIntervalRef.current) {
      clearInterval(ringIntervalRef.current)
      ringIntervalRef.current = null
    }
    setPhase('connected')
    const url = `${apiBase}/security/voice/playback/${alert.alert_id}`
    const audio = new Audio(url)
    audioRef.current = audio
    audio.play().catch((e) => {
      console.warn('Voice playback failed:', e)
      setPhase('ended')
    })
    audio.onended = () => setPhase('ended')
  }

  const handleDecline = () => {
    if (ringIntervalRef.current) clearInterval(ringIntervalRef.current)
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    onClose()
  }

  const handleEndCall = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    onClose()
  }

  if (!alert) return null

  const zoneName = alert.zone_name || 'Analyst Zone'

  return (
    <div className="voice-call-overlay" role="dialog" aria-label="Incoming security call">
      <div className="voice-call-modal">
        {phase === 'ringing' && (
          <>
            <div className="voice-call-icon">📞</div>
            <p className="voice-call-title">Incoming call</p>
            <p className="voice-call-subtitle">Security Alert — {zoneName}</p>
            <p className="voice-call-hint">Unknown person detected</p>
            <div className="voice-call-actions">
              <button type="button" className="voice-call-btn decline" onClick={handleDecline}>
                Decline
              </button>
              <button type="button" className="voice-call-btn answer" onClick={handleAnswer}>
                Answer
              </button>
            </div>
          </>
        )}
        {phase === 'connected' && (
          <>
            <div className="voice-call-icon">🔊</div>
            <p className="voice-call-title">Playing message…</p>
            <p className="voice-call-subtitle">Security violation — {zoneName}</p>
          </>
        )}
        {phase === 'ended' && (
          <>
            <div className="voice-call-icon">✓</div>
            <p className="voice-call-title">Call ended</p>
            <button type="button" className="voice-call-btn answer" onClick={handleEndCall}>
              Dismiss
            </button>
          </>
        )}
      </div>
    </div>
  )
}
