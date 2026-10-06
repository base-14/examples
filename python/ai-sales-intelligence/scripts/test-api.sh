#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8000}"
# The pipeline makes up to four model calls per matching prospect. The default sample
# has one connection; set CONNECTIONS_CSV=data/sample-connections.csv for the full
# sample of ten, and raise PIPELINE_TIMEOUT if a run needs longer than the default.
CONNECTIONS_CSV="${CONNECTIONS_CSV:-data/sample-connections-verify-scout.csv}"
PIPELINE_TIMEOUT="${PIPELINE_TIMEOUT:-600}"

echo "Testing AI Sales Intelligence API at $BASE_URL"
echo "================================================"

echo -e "\n1. Health check..."
curl -s --max-time 10 "$BASE_URL/health" | jq .

echo -e "\n2. Creating campaign..."
CAMPAIGN=$(curl -s --max-time 10 -X POST "$BASE_URL/campaigns" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Campaign",
    "target_keywords": ["SaaS", "AI", "Cloud"],
    "target_titles": ["CTO", "VP Engineering", "Head of Platform"]
  }')
echo "$CAMPAIGN" | jq .
CAMPAIGN_ID=$(echo "$CAMPAIGN" | jq -r '.id')

echo -e "\n3. Importing connections..."
curl -s --max-time 10 -X POST "$BASE_URL/campaigns/$CAMPAIGN_ID/connections/import" \
  -F "file=@${CONNECTIONS_CSV}" | jq .

echo -e "\n4. Getting campaign..."
curl -s --max-time 10 "$BASE_URL/campaigns/$CAMPAIGN_ID" | jq .

echo -e "\n5. Running pipeline (this may take a while)..."
curl -s --max-time "$PIPELINE_TIMEOUT" -X POST "$BASE_URL/campaigns/$CAMPAIGN_ID/run" \
  -H "Content-Type: application/json" \
  -d '{
    "score_threshold": 50,
    "quality_threshold": 60
  }' | jq .

echo -e "\n6. Getting prospects..."
curl -s --max-time 10 "$BASE_URL/campaigns/$CAMPAIGN_ID/prospects" | jq .

echo -e "\nDone!"
