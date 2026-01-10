#!/bin/bash
# Run tests with PostgreSQL backend
#
# Usage:
#   ./scripts/run_tests_postgres.sh                    # Run all tests
#   ./scripts/run_tests_postgres.sh test_chat_memory   # Run specific test file
#   ./scripts/run_tests_postgres.sh --no-docker        # Skip Docker, use existing DB

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 Running tests with PostgreSQL${NC}"

# Check if --no-docker flag is set
USE_DOCKER=true
TEST_ARGS=""
for arg in "$@"; do
    if [ "$arg" == "--no-docker" ]; then
        USE_DOCKER=false
    else
        TEST_ARGS="$TEST_ARGS $arg"
    fi
done

# Database URL
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://test:test@localhost:5433/test_maruntime}"

if [ "$USE_DOCKER" = true ]; then
    echo -e "${YELLOW}📦 Starting PostgreSQL test container...${NC}"
    docker compose -f docker-compose.test.yml up -d
    
    # Wait for PostgreSQL to be ready
    echo -e "${YELLOW}⏳ Waiting for PostgreSQL...${NC}"
    for i in {1..30}; do
        if docker compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U test -d test_maruntime > /dev/null 2>&1; then
            echo -e "${GREEN}✅ PostgreSQL is ready${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}❌ PostgreSQL failed to start${NC}"
            docker compose -f docker-compose.test.yml logs postgres-test
            exit 1
        fi
        sleep 1
    done
    
    # Enable pg_trgm extension
    echo -e "${YELLOW}🔧 Enabling pg_trgm extension...${NC}"
    docker compose -f docker-compose.test.yml exec -T postgres-test psql -U test -d test_maruntime -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" > /dev/null 2>&1 || true
fi

# Run migrations
echo -e "${YELLOW}🔄 Running migrations...${NC}"
export DATABASE_URL="$TEST_DATABASE_URL"
.venv/bin/python -m alembic upgrade head

# Run tests
echo -e "${GREEN}🧪 Running tests...${NC}"
if [ -n "$TEST_ARGS" ]; then
    .venv/bin/python -m pytest tests/$TEST_ARGS -v --tb=short
else
    .venv/bin/python -m pytest tests/test_chat_memory_service.py -v --tb=short
fi

TEST_EXIT_CODE=$?

if [ "$USE_DOCKER" = true ]; then
    echo -e "${YELLOW}🧹 Cleaning up test database...${NC}"
    # Reset database for next run
    docker compose -f docker-compose.test.yml exec -T postgres-test psql -U test -d test_maruntime -c "
        DROP SCHEMA public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO test;
    " > /dev/null 2>&1 || true
    
    # Optionally stop container (uncomment if you want to stop after tests)
    # docker compose -f docker-compose.test.yml down -v
fi

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed${NC}"
fi

exit $TEST_EXIT_CODE
