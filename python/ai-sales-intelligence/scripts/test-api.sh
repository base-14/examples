#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8000}"

echo "Testing AI Sales Intelligence API at $BASE_URL"
echo "================================================"

echo -e "\n1. Health check..."
curl -s "$BASE_URL/health" | jq .

echo -e "\n2. Creating campaign..."
CAMPAIGN=$(curl -s -X POST "$BASE_URL/campaigns" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Campaign",
    "target_keywords": ["SaaS", "AI", "Cloud"],
    "target_titles": ["CTO", "VP Engineering", "Head of Platform"]
  }')
echo "$CAMPAIGN" | jq .
CAMPAIGN_ID=$(echo "$CAMPAIGN" | jq -r '.id')

echo -e "\n3. Importing connections..."
curl -s -X POST "$BASE_URL/connections/import" \
  -F "file=@data/sample-connections.csv" | jq .

echo -e "\n4. Getting campaign..."
curl -s "$BASE_URL/campaigns/$CAMPAIGN_ID" | jq .

echo -e "\n5. Running pipeline (this may take a while)..."
curl -s -X POST "$BASE_URL/campaigns/$CAMPAIGN_ID/run" \
  -H "Content-Type: application/json" \
  -d '{
    "score_threshold": 50,
    "quality_threshold": 60
  }' | jq .

echo -e "\n6. Getting prospects..."
curl -s "$BASE_URL/campaigns/$CAMPAIGN_ID/prospects" | jq .

echo -e "\nDone!"
