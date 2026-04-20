#!/bin/bash
# Build the MDM management agent .pkg for a specific device.
# Usage: ./build_agent_pkg.sh <DEVICE_ID> <SERVER_URL> <AGENT_TOKEN>
# Output: prints the path to the built .pkg file
#
# Requirements: macOS with Xcode Command Line Tools (pkgbuild)
# Install on target Mac: sudo installer -pkg mdm-agent-<id>.pkg -target /

set -euo pipefail

DEVICE_ID="${1:?Usage: $0 DEVICE_ID SERVER_URL AGENT_TOKEN}"
SERVER_URL="${2:?SERVER_URL required}"
AGENT_TOKEN="${3:?AGENT_TOKEN required}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$(mktemp -d)"
PKG_ROOT="${BUILD_DIR}/pkg_root"
SCRIPTS_DIR="${BUILD_DIR}/scripts"
OUTPUT_PKG="$(pwd)/mdm-agent-${DEVICE_ID:0:8}.pkg"

mkdir -p "${PKG_ROOT}/Library/MDMAgent"
mkdir -p "${PKG_ROOT}/Library/LaunchDaemons"
mkdir -p "${SCRIPTS_DIR}"

# Copy agent scripts (bash is the active agent; py kept as fallback)
cp "${SCRIPT_DIR}/mdm_agent.sh" "${PKG_ROOT}/Library/MDMAgent/agent.sh"
cp "${SCRIPT_DIR}/mdm_agent.py" "${PKG_ROOT}/Library/MDMAgent/agent.py"

# Write device-specific config
cat > "${PKG_ROOT}/Library/MDMAgent/config.json" <<CONFIG
{
  "server_url": "${SERVER_URL}",
  "agent_token": "${AGENT_TOKEN}"
}
CONFIG

# Copy LaunchDaemon plist
cp "${SCRIPT_DIR}/com.mdmsaas.agent.plist" \
   "${PKG_ROOT}/Library/LaunchDaemons/com.mdmsaas.agent.plist"

# Write postinstall script
cat > "${SCRIPTS_DIR}/postinstall" <<'POSTINSTALL'
#!/bin/bash
set -e

# Set permissions
chown -R root:wheel /Library/MDMAgent
chmod 755 /Library/MDMAgent
chmod 644 /Library/MDMAgent/agent.py
chmod 600 /Library/MDMAgent/config.json  # token — root only

chown root:wheel /Library/LaunchDaemons/com.mdmsaas.agent.plist
chmod 644 /Library/LaunchDaemons/com.mdmsaas.agent.plist

# Unload if already running (reinstall case)
launchctl unload /Library/LaunchDaemons/com.mdmsaas.agent.plist 2>/dev/null || true

# Load the daemon
launchctl load /Library/LaunchDaemons/com.mdmsaas.agent.plist

echo "MDM agent installed and started."
POSTINSTALL

chmod +x "${SCRIPTS_DIR}/postinstall"

# Build the pkg (no signing required for dev — use sudo installer -pkg ... -target /)
pkgbuild \
    --root "${PKG_ROOT}" \
    --scripts "${SCRIPTS_DIR}" \
    --identifier "com.mdmsaas.agent" \
    --version "1.0.0" \
    --install-location "/" \
    "${OUTPUT_PKG}" \
    > /dev/null 2>&1

# Cleanup temp build artifacts (keep the pkg)
rm -rf "${PKG_ROOT}" "${SCRIPTS_DIR}"

echo "${OUTPUT_PKG}"
