#!/bin/bash
# =============================================================================
# Multi-Agent Runtime - Export Database Data
# Usage: ./export_data.sh [output_file]
# =============================================================================

set -e

# Configuration
DB_NAME="${DB_NAME:-maruntime}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-$(whoami)}"
OUTPUT_FILE="${1:-exported_data_$(date +%Y%m%d_%H%M%S).sql}"

echo "=== Multi-Agent Runtime Data Export ==="
echo "Database: $DB_NAME @ $DB_HOST:$DB_PORT"
echo "Output: $OUTPUT_FILE"
echo ""

# Export tables in dependency order
TABLES=(
    "system_prompts"
    "agent_templates"
    "template_versions"
    "tools"
    "agent_instances"
    "sessions"
    "session_messages"
    "sources"
    "artifacts"
    "tool_executions"
)

# Create header
cat > "$OUTPUT_FILE" << 'EOF'
-- =============================================================================
-- Multi-Agent Runtime - Exported Data
-- Generated: $(date)
-- =============================================================================

-- Disable FK checks during import
SET session_replication_role = replica;

EOF

# Export each table
for table in "${TABLES[@]}"; do
    echo "Exporting $table..."
    
    # Check if table has data
    count=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM $table" 2>/dev/null | tr -d ' ')
    
    if [ "$count" -gt "0" ]; then
        echo "-- Table: $table ($count rows)" >> "$OUTPUT_FILE"
        pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
            --table="$table" \
            --data-only \
            --column-inserts \
            --no-owner \
            --no-privileges \
            >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    else
        echo "-- Table: $table (empty)" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
done

# Add footer
cat >> "$OUTPUT_FILE" << 'EOF'

-- Re-enable FK checks
SET session_replication_role = DEFAULT;

-- Update sequences if needed
-- SELECT setval('table_id_seq', (SELECT MAX(id) FROM table));

-- =============================================================================
-- Done
-- =============================================================================
EOF

echo ""
echo "=== Export completed: $OUTPUT_FILE ==="
echo "Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
