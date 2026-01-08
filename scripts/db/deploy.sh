#!/bin/bash
# =============================================================================
# Multi-Agent Runtime - Database Deployment Script
# Usage: ./deploy.sh [init|seed|migrate|full|backup]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration (override with environment variables)
DB_NAME="${DB_NAME:-maruntime}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-$(whoami)}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Build connection string
if [ -n "$DB_PASSWORD" ]; then
    export PGPASSWORD="$DB_PASSWORD"
fi
PSQL_CMD="psql -h $DB_HOST -p $DB_PORT -U $DB_USER"

# Check PostgreSQL connection
check_connection() {
    log_info "Checking PostgreSQL connection..."
    if $PSQL_CMD -d postgres -c "SELECT 1" > /dev/null 2>&1; then
        log_info "PostgreSQL connection: OK"
        return 0
    else
        log_error "Cannot connect to PostgreSQL at $DB_HOST:$DB_PORT"
        return 1
    fi
}

# Create database if not exists
create_database() {
    log_info "Creating database '$DB_NAME' if not exists..."
    if $PSQL_CMD -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
        log_info "Database '$DB_NAME' already exists"
    else
        $PSQL_CMD -d postgres -c "CREATE DATABASE $DB_NAME"
        log_info "Database '$DB_NAME' created"
    fi
}

# Initialize schema
init_schema() {
    log_info "Initializing database schema..."
    $PSQL_CMD -d "$DB_NAME" -f "$SCRIPT_DIR/init_schema.sql"
    log_info "Schema initialized successfully"
}

# Seed data
seed_data() {
    log_info "Seeding initial data..."
    $PSQL_CMD -d "$DB_NAME" -f "$SCRIPT_DIR/seed_data.sql"
    log_info "Data seeded successfully"
}

# Run Alembic migrations
run_migrations() {
    log_info "Running Alembic migrations..."
    cd "$PROJECT_ROOT"
    
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
    
    # Set DATABASE_URL for Alembic
    export DATABASE_URL="postgresql+asyncpg://$DB_USER${DB_PASSWORD:+:$DB_PASSWORD}@$DB_HOST:$DB_PORT/$DB_NAME"
    
    alembic upgrade head
    log_info "Migrations completed"
}

# Backup database
backup_database() {
    BACKUP_FILE="backup_${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql"
    log_info "Creating backup: $BACKUP_FILE"
    
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --no-owner \
        --no-privileges \
        > "$BACKUP_FILE"
    
    log_info "Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
}

# Show help
show_help() {
    echo "Multi-Agent Runtime - Database Deployment"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  init      - Initialize schema (drops existing tables)"
    echo "  seed      - Insert seed data"
    echo "  migrate   - Run Alembic migrations"
    echo "  full      - Full deployment: create DB + init + seed"
    echo "  backup    - Create database backup"
    echo "  status    - Check connection and show tables"
    echo ""
    echo "Environment variables:"
    echo "  DB_NAME     - Database name (default: maruntime)"
    echo "  DB_HOST     - Database host (default: localhost)"
    echo "  DB_PORT     - Database port (default: 5432)"
    echo "  DB_USER     - Database user (default: current user)"
    echo "  DB_PASSWORD - Database password (default: empty)"
    echo ""
    echo "Examples:"
    echo "  $0 full                          # Local deployment"
    echo "  DB_HOST=prod.db.com $0 migrate   # Remote migration"
}

# Show status
show_status() {
    check_connection || exit 1
    
    log_info "Database: $DB_NAME"
    echo ""
    
    # Check if database exists
    if ! $PSQL_CMD -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
        log_warn "Database '$DB_NAME' does not exist"
        return
    fi
    
    # Show tables
    log_info "Tables:"
    $PSQL_CMD -d "$DB_NAME" -c "\dt"
    
    # Show Alembic version
    log_info "Migration version:"
    $PSQL_CMD -d "$DB_NAME" -c "SELECT * FROM alembic_version" 2>/dev/null || echo "No alembic_version table"
}

# Main
case "${1:-help}" in
    init)
        check_connection
        init_schema
        ;;
    seed)
        check_connection
        seed_data
        ;;
    migrate)
        check_connection
        run_migrations
        ;;
    full)
        check_connection
        create_database
        init_schema
        seed_data
        log_info "Full deployment completed!"
        ;;
    backup)
        check_connection
        backup_database
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
