#!/bin/bash
# MDM Management Agent — runs as root LaunchDaemon
# Pure bash + curl only. No Python, no Xcode, no dependencies.
# Config: /Library/MDMAgent/config.json
# Logs:   /var/log/mdm-agent.log

CONFIG="/Library/MDMAgent/config.json"
POLL_INTERVAL=30
LOG="/var/log/mdm-agent.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

if [ ! -f "$CONFIG" ]; then
  log "ERROR: Config not found at $CONFIG"
  exit 1
fi

# Parse JSON by finding the key and returning the value 2 fields later
SERVER_URL=$(awk -F'"' '{for(i=1;i<=NF;i++) if($i=="server_url") print $(i+2)}' "$CONFIG")
TOKEN=$(awk -F'"' '{for(i=1;i<=NF;i++) if($i=="agent_token") print $(i+2)}' "$CONFIG")
SERVER_URL="${SERVER_URL%/}"

if [ -z "$SERVER_URL" ] || [ -z "$TOKEN" ]; then
  log "ERROR: Could not parse server_url or agent_token from $CONFIG"
  exit 1
fi

log "MDM agent started. server=$SERVER_URL interval=${POLL_INTERVAL}s"

# Escape a string for JSON
json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/g' | tr -d '\n' | sed 's/\\n$//'
}

poll_and_run() {
  RESPONSE=$(curl -s --http1.1 --max-time 20 -w "\nHTTP_STATUS:%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/json" \
    -H "ngrok-skip-browser-warning: 1" \
    "${SERVER_URL}/api/v1/agent/jobs" 2>&1)
  CURL_EXIT=$?
  HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | sed 's/.*HTTP_STATUS://')
  RESPONSE=$(echo "$RESPONSE" | grep -v "HTTP_STATUS:")

  if [ $CURL_EXIT -ne 0 ] || [ "$HTTP_STATUS" != "200" ]; then
    log "WARN: Poll failed (curl exit $CURL_EXIT, HTTP $HTTP_STATUS): $RESPONSE"
    return
  fi

  # Check for empty array
  if [ "$RESPONSE" = "[]" ] || [ -z "$RESPONSE" ]; then
    return
  fi

  # Parse all jobs using awk — extract id and command pairs
  # JSON format: [{"id":"<id>","command":"<cmd>","label":"<lbl>"},...]
  # We pull each "id" and "command" value in order
  # Extract id and command_b64 (base64-encoded command avoids quote parsing issues)
  JOBS=$(echo "$RESPONSE" | awk -F'"' '{
    for(i=1;i<=NF;i++) {
      if($i=="id") id=$(i+2)
      if($i=="command_b64") { b64=$(i+2); print id "|" b64 }
    }
  }')

  if [ -z "$JOBS" ]; then
    return
  fi

  while IFS='|' read -r JOB_ID JOB_B64; do
    [ -z "$JOB_ID" ] && continue
    # Decode base64 command — safe from quote/special-char issues
    JOB_CMD=$(echo "$JOB_B64" | base64 -d 2>/dev/null)
    [ -z "$JOB_CMD" ] && { log "WARN: Could not decode command for job $JOB_ID"; continue; }
    log "Running job $JOB_ID: $JOB_CMD"

    # Execute and capture output to temp files
    STDOUT_FILE=$(mktemp /tmp/mdm-job-stdout.XXXXXX)
    STDERR_FILE=$(mktemp /tmp/mdm-job-stderr.XXXXXX)

    eval "$JOB_CMD" >"$STDOUT_FILE" 2>"$STDERR_FILE"
    EXIT_CODE=$?

    log "Job $JOB_ID exit_code=$EXIT_CODE"

    STDOUT_VAL=$(head -c 4096 "$STDOUT_FILE" | tr -dc '[:print:]' | sed 's/\\/\\\\/g; s/"/\\"/g')
    STDERR_VAL=$(head -c 4096 "$STDERR_FILE" | tr -dc '[:print:]' | sed 's/\\/\\\\/g; s/"/\\"/g')
    rm -f "$STDOUT_FILE" "$STDERR_FILE"

    curl -s --http1.1 --max-time 20 -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -H "ngrok-skip-browser-warning: 1" \
      -d "{\"exit_code\":${EXIT_CODE},\"stdout\":\"${STDOUT_VAL}\",\"stderr\":\"${STDERR_VAL}\"}" \
      "${SERVER_URL}/api/v1/agent/jobs/${JOB_ID}/result" >> "$LOG" 2>&1 || \
      log "WARN: Failed to post result for job $JOB_ID"

  done <<< "$JOBS"
}

# Main loop
while true; do
  poll_and_run
  sleep $POLL_INTERVAL
done
