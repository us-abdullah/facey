import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Shield, Lock, Unlock, AlertTriangle, 
  Activity, Database, Terminal, 
  RefreshCw, ArrowLeft, Mail, CheckCircle, XCircle
} from 'lucide-react'
import GenieConsole from '../components/GenieConsole'

const API_BASE = '/api'

export default function SecurityIntel({ onBack }) {
  const [intelligence, setIntelligence] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [connected, setConnected] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [userEmail, setUserEmail] = useState('guest@restricted.local') // Default: Guest mode
  const [isAdmin, setIsAdmin] = useState(false)

  const ADMIN_EMAIL = 'mr6761@nyu.edu'

  const fetchIntelligence = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Always send email - default to guest if empty
      const emailToSend = userEmail.trim() || 'guest@restricted.local'
      const url = `${API_BASE}/security-intel?limit=20&email=${encodeURIComponent(emailToSend)}`
      
      const response = await fetch(url)
      
      // Check if response is ok
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`)
      }
      
      // Check if response has content
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text()
        throw new Error(`Expected JSON but got: ${contentType}. Response: ${text.substring(0, 100)}`)
      }
      
      // Get response text first to check if it's empty
      const responseText = await response.text()
      if (!responseText || responseText.trim() === '') {
        console.warn('Empty response from server')
        setIntelligence([])
        setConnected(true)
        setLastRefresh(new Date())
        return
      }
      
      // Parse JSON
      let data
      try {
        data = JSON.parse(responseText)
      } catch (parseError) {
        console.error('JSON parse error:', parseError)
        console.error('Response text:', responseText)
        throw new Error(`Invalid JSON response: ${parseError.message}`)
      }
      
      if (data.error) {
        setError(data.error)
        setConnected(false)
      } else {
        setIntelligence(data.intelligence || [])
        setConnected(true)
        setLastRefresh(new Date())
      }
    } catch (err) {
      console.error('Fetch error:', err)
      setError(err.message || 'Failed to fetch intelligence data')
      setConnected(false)
      setIntelligence([]) // Set empty array on error
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setIsAdmin(userEmail.toLowerCase().trim() === ADMIN_EMAIL.toLowerCase())
  }, [userEmail])

  useEffect(() => {
    fetchIntelligence()
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchIntelligence, 30000)
    return () => clearInterval(interval)
  }, [userEmail]) // Re-fetch when email changes

  const getThreatColor = (score) => {
    if (score >= 80) return 'from-red-600 to-red-800'
    if (score >= 50) return 'from-yellow-500 to-orange-600'
    return 'from-green-500 to-green-700'
  }

  const getThreatBorderColor = (score) => {
    if (score >= 70) return 'border-red-500/50'
    if (score >= 40) return 'border-yellow-500/50'
    return 'border-green-500/50'
  }

  const getThreatGlow = (score) => {
    if (score >= 80) return 'shadow-red-500/50'
    if (score >= 50) return 'shadow-yellow-500/30'
    return 'shadow-green-500/20'
  }

  const isMasked = (value) => {
    if (!value || typeof value !== 'string') return false
    return (
      value.includes('🔒') || 
      value.includes('Restricted User') || 
      value === 'Restricted' ||
      value.toLowerCase().includes('restricted')
    )
  }

  const handleRequestDecryption = () => {
    // Show toast notification
    alert('Permission Denied: Admin Clearance Required')
  }

  return (
    <div className="min-h-screen bg-[#0f0f12] text-[#e4e4e7] p-6">
      <div className="max-w-6xl mx-auto">
        {/* Back Button */}
        {onBack && (
          <button
            onClick={onBack}
            className="mb-4 flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </button>
        )}

        {/* Header with Connection Status */}
        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2 bg-gradient-to-r from-red-500 to-orange-500 bg-clip-text text-transparent">
              Security Intelligence Center
            </h1>
            <p className="text-sm text-gray-400">
              Real-time threat analysis from Databricks Intelligence Layer
            </p>
          </div>
          
          {/* Security Clearance Input */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-gray-400" />
              <input
                type="email"
                placeholder="Enter Security Clearance (Email) - Default: Guest"
                value={userEmail === 'guest@restricted.local' ? '' : userEmail}
                onChange={(e) => setUserEmail(e.target.value || 'guest@restricted.local')}
                onBlur={(e) => {
                  if (!e.target.value.trim()) {
                    setUserEmail('guest@restricted.local')
                  }
                }}
                className="px-3 py-2 bg-[#09090b] border border-[#27272a] rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#3f3f46] focus:ring-1 focus:ring-[#3f3f46] min-w-[250px]"
              />
            </div>

            {/* Clearance Level Badge */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${
                isAdmin
                  ? 'bg-green-900/30 border-green-500/50 text-green-400'
                  : 'bg-red-900/30 border-red-500/50 text-red-400'
              }`}
              style={{
                boxShadow: isAdmin ? '0 0 20px rgba(34, 197, 94, 0.4)' : 'none'
              }}
            >
              {isAdmin ? (
                <>
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-sm font-semibold">ADMIN VIEW</span>
                </>
              ) : (
                <>
                  <Lock className="w-4 h-4" />
                  <span className="text-sm font-semibold">LOW CLEARANCE</span>
                </>
              )}
            </motion.div>

            {/* Connection Status Indicator */}
            <div className="flex items-center gap-2 px-4 py-2 bg-[#18181b] border border-[#27272a] rounded-lg">
              <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} 
                   style={{ boxShadow: connected ? '0 0 10px rgba(34, 197, 94, 0.8)' : 'none' }} />
              <span className="text-sm text-gray-300">
                {connected ? 'Connected to Databricks' : 'Disconnected'}
              </span>
            </div>
            
            <button
              onClick={fetchIntelligence}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-[#27272a] border border-[#3f3f46] rounded-lg hover:bg-[#3f3f46] transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span className="text-sm">Refresh</span>
            </button>
          </div>
        </div>

        {lastRefresh && (
          <p className="text-xs text-gray-500 mb-4">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </p>
        )}

        {/* Error State */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-500/50 rounded-lg">
            <p className="text-red-400 text-sm">Error: {error}</p>
          </div>
        )}

        {/* Loading State */}
        {loading && intelligence.length === 0 && (
          <div className="flex items-center justify-center py-20">
            <div className="flex items-center gap-3">
              <Database className="w-6 h-6 animate-pulse text-gray-400" />
              <span className="text-gray-400">Loading intelligence data...</span>
            </div>
          </div>
        )}

        {/* Intelligence Feed */}
        {!loading && intelligence.length === 0 && !error && (
          <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6">
            <div className="text-center py-10 text-gray-500">
              <Database className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="mb-2">No intelligence data available</p>
              <p className="text-sm text-gray-600">Data will appear here when available</p>
            </div>
            {/* Empty table structure for visual consistency */}
            <div className="mt-6 border-t border-[#27272a] pt-4">
              <div className="text-xs text-gray-500 mb-2">Table Structure:</div>
              <div className="grid grid-cols-6 gap-2 text-xs text-gray-600">
                <div>Person Name</div>
                <div>Role</div>
                <div>Threat Score</div>
                <div>Alert Type</div>
                <div>Infraction</div>
                <div>Timestamp</div>
              </div>
            </div>
          </div>
        )}

        {/* Compact Log-Style Card List */}
        <div className="space-y-2">
          <AnimatePresence>
            {intelligence.map((record, index) => {
              const threatScore = record.threat_score || 0
              const isRepeat = record.is_repeat_offender === true || record.is_repeat_offender === 'true' || record.is_repeat_offender === 'True'
              const personName = record.person_name || 'Unknown'
              const personRole = record.person_role || 'Unknown'
              const aiAnalysis = record.ai_analysis || record.infraction_sentence || 'No analysis available'
              const timestamp = record.timestamp || new Date().toISOString()
              const alertType = record.alert_type || 'unknown'
              const infractionSentence = record.infraction_sentence || ''
              const escalationLevel = record.escalation_level || 'ROUTINE'
              const isPersonMasked = isMasked(personName)
              const isRoleMasked = isMasked(personRole)

              return (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ duration: 0.2, delay: index * 0.02 }}
                  className={`bg-[#18181b] border-l-4 ${
                    threatScore >= 70 ? 'border-red-500/50' :
                    threatScore >= 40 ? 'border-yellow-500/50' :
                    'border-green-500/50'
                  } rounded-r-lg p-3 hover:bg-[#1f1f23] transition-all cursor-pointer`}
                >
                  <div className="grid grid-cols-12 gap-3 items-center text-sm">
                    {/* Timestamp - Compact */}
                    <div className="col-span-2 text-xs text-gray-500 font-mono">
                      {new Date(timestamp).toLocaleTimeString()}
                    </div>

                    {/* Threat Score - Compact Badge */}
                    <div className="col-span-1">
                      <div className={`inline-flex items-center justify-center w-10 h-10 rounded-full font-bold text-xs ${
                        threatScore >= 80 ? 'bg-red-500/20 text-red-400 border border-red-500/50' :
                        threatScore >= 50 ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/50' :
                        'bg-green-500/20 text-green-400 border border-green-500/50'
                      }`}>
                        {threatScore}
                      </div>
                    </div>

                    {/* Person Name - VERY OBVIOUS if masked */}
                    <div className="col-span-2">
                      {isPersonMasked ? (
                        <div className="flex items-center gap-1.5 group">
                          <Lock className="w-4 h-4 text-red-500 flex-shrink-0" />
                          <span className="text-red-400 font-mono text-xs relative">
                            <span className="line-through decoration-red-500 decoration-2">{personName}</span>
                            <span className="absolute inset-0 bg-red-500/10 blur-sm"></span>
                          </span>
                          <span className="text-[8px] text-red-500/70 font-bold uppercase tracking-wider ml-1">MASKED</span>
                        </div>
                      ) : (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="flex items-center gap-1.5"
                        >
                          <Unlock className="w-3 h-3 text-green-400" />
                          <span className="text-white font-semibold text-xs">{personName}</span>
                        </motion.div>
                      )}
                    </div>

                    {/* Role - VERY OBVIOUS if masked */}
                    <div className="col-span-2">
                      {isRoleMasked ? (
                        <div className="flex items-center gap-1.5">
                          <Lock className="w-4 h-4 text-red-500 flex-shrink-0" />
                          <span className="text-red-400 font-mono text-xs relative">
                            <span className="line-through decoration-red-500 decoration-2">{personRole}</span>
                            <span className="absolute inset-0 bg-red-500/10 blur-sm"></span>
                          </span>
                          <span className="text-[8px] text-red-500/70 font-bold uppercase tracking-wider ml-1">MASKED</span>
                        </div>
                      ) : (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="flex items-center gap-1.5"
                        >
                          <Unlock className="w-3 h-3 text-green-400" />
                          <span className="text-white font-semibold text-xs">{personRole}</span>
                        </motion.div>
                      )}
                    </div>

                    {/* Alert Type */}
                    <div className="col-span-2 text-xs text-gray-400">
                      <span className="text-yellow-400">{alertType}</span>
                    </div>

                    {/* Escalation Level */}
                    <div className="col-span-1">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                        escalationLevel === 'CRITICAL' ? 'bg-red-500/20 text-red-400' :
                        escalationLevel === 'URGENT' ? 'bg-orange-500/20 text-orange-400' :
                        'bg-yellow-500/20 text-yellow-400'
                      }`}>
                        {escalationLevel.charAt(0)}
                      </span>
                    </div>

                    {/* Repeat Offender Badge */}
                    <div className="col-span-1">
                      {isRepeat && (
                        <div className="flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3 text-red-400 animate-pulse" />
                          <span className="text-[10px] text-red-400 font-bold">REPEAT</span>
                        </div>
                      )}
                    </div>

                    {/* Expandable Details */}
                    <div className="col-span-1 text-right">
                      <button className="text-gray-500 hover:text-white text-xs">
                        Details →
                      </button>
                    </div>
                  </div>

                  {/* Infraction Sentence - Always visible */}
                  {infractionSentence && (
                    <div className="mt-2 pt-2 border-t border-[#27272a]">
                      <p className="text-xs text-gray-400">{infractionSentence}</p>
                    </div>
                  )}

                  {/* AI Analysis - Collapsible */}
                  <details className="mt-2">
                    <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400 flex items-center gap-1">
                      <Terminal className="w-3 h-3" />
                      <span>AI Analysis</span>
                    </summary>
                    <div className="mt-2 p-2 bg-[#09090b] border border-[#27272a] rounded font-mono text-xs text-green-400">
                      <TypewriterText text={aiAnalysis} />
                    </div>
                  </details>
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>

        {/* Genie Console - Integrated below Security Incidents table */}
        <GenieConsole viewerEmail={userEmail} isAdmin={isAdmin} />
      </div>
    </div>
  )
}

// Typewriter effect component for AI analysis
function TypewriterText({ text }) {
  const [displayedText, setDisplayedText] = useState('')
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setDisplayedText(text.slice(0, currentIndex + 1))
        setCurrentIndex(currentIndex + 1)
      }, 20) // Adjust speed here
      return () => clearTimeout(timeout)
    }
  }, [currentIndex, text])

  useEffect(() => {
    setDisplayedText('')
    setCurrentIndex(0)
  }, [text])

  return (
    <div className="whitespace-pre-wrap">
      {displayedText}
      <span className="animate-pulse">▊</span>
    </div>
  )
}
