#!/bin/bash
#
# TFA Start Script - Starts both backend API and frontend UI
#
# Usage:
#   ./start.sh           # Start both backend and UI
#   ./start.sh backend   # Start only backend
#   ./start.sh ui        # Start only UI
#   ./start.sh stop      # Stop all services
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=${BACKEND_PORT:-8000}
UI_PORT=${UI_PORT:-5173}
BACKEND_HOST=${BACKEND_HOST:-0.0.0.0}
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$PROJECT_DIR/.pids"

# Create PID directory
mkdir -p "$PID_DIR"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_env() {
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        if [ -f "$PROJECT_DIR/.env.example" ]; then
            log_warn ".env file not found. Copy from .env.example and configure:"
            log_warn "  cp .env.example .env"
            log_warn "  # Edit .env with your ReportPortal credentials"
        else
            log_error ".env file not found"
        fi
    else
        # Load environment variables
        set -a
        source "$PROJECT_DIR/.env"
        set +a
        log_success "Environment loaded from .env"
    fi
}

start_backend() {
    log_info "Starting TFA Backend on port $BACKEND_PORT..."
    
    cd "$PROJECT_DIR"
    
    # Check if already running
    if [ -f "$PID_DIR/backend.pid" ]; then
        local pid=$(cat "$PID_DIR/backend.pid")
        if kill -0 "$pid" 2>/dev/null; then
            log_warn "Backend already running (PID: $pid)"
            return 0
        fi
    fi
    
    # Start backend
    python main.py serve --host "$BACKEND_HOST" --port "$BACKEND_PORT" > "$PROJECT_DIR/logs/backend.log" 2>&1 &
    local pid=$!
    echo $pid > "$PID_DIR/backend.pid"
    
    # Wait for startup
    sleep 2
    
    if kill -0 "$pid" 2>/dev/null; then
        log_success "Backend started (PID: $pid)"
        log_info "  API: http://localhost:$BACKEND_PORT"
        log_info "  Docs: http://localhost:$BACKEND_PORT/docs"
    else
        log_error "Backend failed to start. Check logs/backend.log"
        return 1
    fi
}

start_ui() {
    log_info "Starting TFA UI on port $UI_PORT..."
    
    cd "$PROJECT_DIR/ui"
    
    # Check if already running
    if [ -f "$PID_DIR/ui.pid" ]; then
        local pid=$(cat "$PID_DIR/ui.pid")
        if kill -0 "$pid" 2>/dev/null; then
            log_warn "UI already running (PID: $pid)"
            return 0
        fi
    fi
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        log_info "Installing UI dependencies..."
        npm install
    fi
    
    # Start UI dev server
    npm run dev > "$PROJECT_DIR/logs/ui.log" 2>&1 &
    local pid=$!
    echo $pid > "$PID_DIR/ui.pid"
    
    # Wait for startup
    sleep 3
    
    if kill -0 "$pid" 2>/dev/null; then
        log_success "UI started (PID: $pid)"
        log_info "  URL: http://localhost:$UI_PORT"
    else
        log_error "UI failed to start. Check logs/ui.log"
        return 1
    fi
}

stop_service() {
    local name=$1
    local pid_file="$PID_DIR/$name.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 1
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            log_success "$name stopped"
        else
            log_warn "$name not running"
        fi
        rm -f "$pid_file"
    else
        log_warn "$name PID file not found"
    fi
}

stop_all() {
    log_info "Stopping all services..."
    stop_service "ui"
    stop_service "backend"
    log_success "All services stopped"
}

status() {
    echo ""
    echo "TFA Service Status"
    echo "=================="
    
    if [ -f "$PID_DIR/backend.pid" ]; then
        local pid=$(cat "$PID_DIR/backend.pid")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "Backend:  ${GREEN}Running${NC} (PID: $pid) - http://localhost:$BACKEND_PORT"
        else
            echo -e "Backend:  ${RED}Stopped${NC}"
        fi
    else
        echo -e "Backend:  ${RED}Stopped${NC}"
    fi
    
    if [ -f "$PID_DIR/ui.pid" ]; then
        local pid=$(cat "$PID_DIR/ui.pid")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "UI:       ${GREEN}Running${NC} (PID: $pid) - http://localhost:$UI_PORT"
        else
            echo -e "UI:       ${RED}Stopped${NC}"
        fi
    else
        echo -e "UI:       ${RED}Stopped${NC}"
    fi
    echo ""
}

show_help() {
    echo ""
    echo "TFA Start Script"
    echo "================"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  (none)    Start both backend and UI"
    echo "  backend   Start only backend API server"
    echo "  ui        Start only frontend UI"
    echo "  stop      Stop all services"
    echo "  status    Show service status"
    echo "  logs      Tail logs from both services"
    echo "  help      Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  BACKEND_PORT  Backend port (default: 8000)"
    echo "  UI_PORT       UI port (default: 5173)"
    echo "  BACKEND_HOST  Backend host (default: 0.0.0.0)"
    echo ""
    echo "Examples:"
    echo "  ./start.sh                    # Start everything"
    echo "  ./start.sh backend            # Start only backend"
    echo "  BACKEND_PORT=9000 ./start.sh  # Use custom port"
    echo ""
}

tail_logs() {
    log_info "Tailing logs (Ctrl+C to stop)..."
    tail -f "$PROJECT_DIR/logs/backend.log" "$PROJECT_DIR/logs/ui.log" 2>/dev/null || log_warn "No logs found"
}

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# Main
case "${1:-all}" in
    backend)
        check_env
        start_backend
        ;;
    ui)
        start_ui
        ;;
    stop)
        stop_all
        ;;
    status)
        status
        ;;
    logs)
        tail_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    all|"")
        echo ""
        echo "=========================================="
        echo "  TFA - Test Failure Analyzer"
        echo "=========================================="
        echo ""
        check_env
        start_backend
        start_ui
        echo ""
        echo "=========================================="
        log_success "TFA is running!"
        echo ""
        echo "  Backend API: http://localhost:$BACKEND_PORT"
        echo "  Swagger UI:  http://localhost:$BACKEND_PORT/docs"
        echo "  Frontend:    http://localhost:$UI_PORT"
        echo ""
        echo "  Stop with: ./start.sh stop"
        echo "  Logs with: ./start.sh logs"
        echo "=========================================="
        echo ""
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
