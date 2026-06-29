#!/bin/bash
# Clean restart script - kills all processes and starts fresh

echo "========================================"
echo "OPENQUERY AI - CLEAN RESTART"
echo "========================================"
echo ""

echo "[1/5] Stopping all Python processes..."
# Kill from Windows side using taskkill (force kill all python.exe processes and children)
cmd.exe /c "taskkill /F /IM python.exe /T" 2>/dev/null || true
echo "  Waiting for processes to terminate..."
sleep 5

echo ""
echo "[2/5] Verifying all processes stopped..."
REMAINING=$(cmd.exe /c "tasklist /FI \"IMAGENAME eq python.exe\"" | grep -c "python.exe" || echo "0")
if [ "$REMAINING" != "0" ]; then
    echo "  WARNING: $REMAINING Python processes still running. Trying again..."
    cmd.exe /c "taskkill /F /IM python.exe /T" 2>/dev/null || true
    sleep 3
fi
echo "  All Python processes stopped."

echo ""
echo "[3/5] Cleaning cache and temp files..."
cd /mnt/c/users/madhu/documents/serper-search-app || exit 1
rm -rf __pycache__ 2>/dev/null || true
rm -rf pages/__pycache__ 2>/dev/null || true
echo "  Cache cleaned."

echo ""
echo "[4/5] Creating logs directory..."
mkdir -p logs
echo "  Logs directory ready."

echo ""
echo "[5/5] Starting backend on port 8000..."
nohup python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend started with PID: $BACKEND_PID"
sleep 3

echo ""
echo "[6/6] Starting frontend on port 8501..."
nohup python.exe -m streamlit run app.py --server.port 8501 --server.headless true > logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend started with PID: $FRONTEND_PID"

echo ""
echo "========================================"
echo "SERVICES STARTED SUCCESSFULLY!"
echo "========================================"
echo ""
echo "Backend:  http://localhost:8000 (or http://127.0.0.1:8000)"
echo "Frontend: http://localhost:8501 (or http://127.0.0.1:8501)"
echo ""
echo "View logs:"
echo "  Backend:  tail -f logs/backend.log"
echo "  Frontend: tail -f logs/frontend.log"
echo ""
echo "PIDs saved:"
echo "  Backend:  $BACKEND_PID"
echo "  Frontend: $FRONTEND_PID"
echo ""
echo "Note: Auto-reload is disabled for stability."
echo "      Run this script again after code changes."
echo ""
