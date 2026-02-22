import React from 'react'
import { motion } from 'framer-motion'
import { Sparkles, ExternalLink } from 'lucide-react'

const GENIE_ROOM_URL = "https://dbc-ddd96b9a-9fc6.cloud.databricks.com/genie/rooms/01f10fea98a51457bcb5737bd9a4501b?o=7474650151160124"

export default function GenieConsole({ viewerEmail, isAdmin }) {
  const handleOpenGenie = () => {
    window.open(GENIE_ROOM_URL, '_blank', 'noopener,noreferrer')
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-8 bg-[#121212] border border-[#27272a] rounded-lg overflow-hidden relative"
    >
      {/* Genie Glow Effect */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 blur-3xl pointer-events-none" />
      <div className="absolute top-0 right-0 text-blue-400/20 text-6xl font-bold p-4 pointer-events-none select-none">
        GENIE
      </div>

      {/* Content */}
      <div className="p-6 relative z-10">
        <div className="flex items-center gap-3 mb-4">
          <Sparkles className={`w-6 h-6 ${isAdmin ? 'text-blue-400' : 'text-amber-400'}`} />
          <h3 className="font-semibold text-white text-lg" style={{ fontFamily: 'Inter, sans-serif' }}>
            Databricks Genie
          </h3>
          {isAdmin && (
            <span className="px-2 py-1 text-xs bg-blue-500/20 text-blue-400 rounded border border-blue-500/30">
              ADMIN MODE
            </span>
          )}
        </div>
        
        <p className="text-sm text-gray-400 mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
          Access the Databricks Genie AI assistant for advanced security intelligence analysis.
        </p>

        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleOpenGenie}
          className={`w-full flex items-center justify-center gap-3 px-6 py-4 rounded-lg font-semibold transition-all ${
            isAdmin
              ? 'bg-blue-500/20 border-2 border-blue-500/50 text-blue-400 hover:bg-blue-500/30 hover:border-blue-500/70 hover:shadow-lg hover:shadow-blue-500/20'
              : 'bg-amber-500/20 border-2 border-amber-500/50 text-amber-400 hover:bg-amber-500/30 hover:border-amber-500/70 hover:shadow-lg hover:shadow-amber-500/20'
          }`}
          style={{ fontFamily: 'Inter, sans-serif' }}
        >
          <Sparkles className="w-5 h-5" />
          <span>Open Databricks Genie</span>
          <ExternalLink className="w-4 h-4" />
        </motion.button>
      </div>
    </motion.div>
  )
}
