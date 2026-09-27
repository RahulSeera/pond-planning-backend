#!/usr/bin/env bash
# ==============================================================================
# watchdog.sh — Health Monitor & Auto-Restart Daemon for College Container
# Runs periodically (via cron or background loop) to ensure 100% uptime:
#   1. Tests /api/health endpoint
#   2. If server down or unresponsive, auto-restarts via start_server.sh
#   3. Cleans stale temp files from /tmp to protect 94% overlay disk
# ==============================================================================

PROJECT_DIR="/home/student/pond-project"
START_SCRIPT="$PROJECT_DIR/scripts/start_server.sh"
WATCHDOG_LOG="$PROJECT_DIR/watchdog.log"
HEALTH_URL="http://127.0.0.1:3000/api/health"

# 1. Clean temporary DEM files older than 30 mins to prevent disk pressure
find /tmp -maxdepth 1 -name "contour_dem_*" -type d -mmin +30 -exec rm -rf {} + 2>/dev/null || true
find /tmp -maxdepth 1 -name "area_dem_*" -type d -mmin +30 -exec rm -rf {} + 2>/dev/null || true
find /tmp -maxdepth 1 -name "point_dem_*.tif" -type f -mmin +30 -delete 2>/dev/null || true

# 2. Check if health endpoint returns HTTP 200 within 5 seconds
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 4 --max-time 6 "$HEALTH_URL" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    # Server is healthy
    exit 0
fi

# Startup grace period: importing the geospatial stack takes ~20 s on the container,
# and a probe during that window would kill a server that is still booting.
UV_PID=$(pgrep -f "uvicorn app.main:app.*3000" | head -1)
if [ -n "$UV_PID" ]; then
    UV_AGE=$(ps -o etimes= -p "$UV_PID" 2>/dev/null | tr -d ' ')
    if [ -n "$UV_AGE" ] && [ "$UV_AGE" -lt 90 ]; then
        exit 0
    fi
fi

echo "[$(date)] ALERT: Server health check failed (HTTP $HTTP_CODE). Initiating auto-restart..." >> "$WATCHDOG_LOG"

# 3. Kill any zombie or hung uvicorn processes on port 3000
pkill -9 -f "uvicorn app.main:app.*3000" 2>/dev/null || true
sleep 1

# 4. Restart server
bash "$START_SCRIPT" >> "$WATCHDOG_LOG" 2>&1
echo "[$(date)] Auto-restart sequence finished." >> "$WATCHDOG_LOG"
