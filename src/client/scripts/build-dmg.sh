#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
npm run build
npx electron-builder --mac --publish never
