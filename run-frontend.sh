#!/usr/bin/env bash
# Install deps if needed, then start frontend. Run from facey/ or project root.
cd "$(dirname "$0")/frontend"
[[ ! -d node_modules ]] && npm install
npm run dev
