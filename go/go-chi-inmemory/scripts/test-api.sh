#!/bin/bash

set -e

BASE_URL="http://localhost:8080"

echo "========================================="
echo "Testing Parking Lot API"
echo "========================================="
echo ""

echo "1. Testing Health Check..."
HEALTH=$(curl -s "$BASE_URL/health")
echo "Response: $HEALTH"
if echo "$HEALTH" | grep -q "healthy"; then
    echo "✓ Health check passed"
else
    echo "✗ Health check failed"
    exit 1
fi
echo ""

echo "2. Creating Parking Lot (capacity: 6)..."
CREATE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/parking-lot" \
    -H "Content-Type: application/json" \
    -d '{"capacity": 6}')
echo "Response: $CREATE_RESPONSE"
if echo "$CREATE_RESPONSE" | grep -q "success"; then
    echo "✓ Parking lot created"
else
    echo "✗ Failed to create parking lot"
    exit 1
fi
echo ""

echo "3. Parking Vehicle 1 (KA-01-HH-1234, White)..."
PARK1=$(curl -s -X POST "$BASE_URL/api/parking-lot/park" \
    -H "Content-Type: application/json" \
    -d '{"registration": "KA-01-HH-1234", "color": "White"}')
echo "Response: $PARK1"
if echo "$PARK1" | grep -q "success"; then
    echo "✓ Vehicle 1 parked"
else
    echo "✗ Failed to park vehicle 1"
    exit 1
fi
echo ""

echo "4. Parking Vehicle 2 (KA-01-HH-9999, Black)..."
PARK2=$(curl -s -X POST "$BASE_URL/api/parking-lot/park" \
    -H "Content-Type: application/json" \
    -d '{"registration": "KA-01-HH-9999", "color": "Black"}')
echo "Response: $PARK2"
if echo "$PARK2" | grep -q "success"; then
    echo "✓ Vehicle 2 parked"
else
    echo "✗ Failed to park vehicle 2"
    exit 1
fi
echo ""

echo "5. Parking Vehicle 3 (KA-01-BB-0001, Red)..."
PARK3=$(curl -s -X POST "$BASE_URL/api/parking-lot/park" \
    -H "Content-Type: application/json" \
    -d '{"registration": "KA-01-BB-0001", "color": "Red"}')
echo "Response: $PARK3"
if echo "$PARK3" | grep -q "success"; then
    echo "✓ Vehicle 3 parked"
else
    echo "✗ Failed to park vehicle 3"
    exit 1
fi
echo ""

echo "6. Getting Parking Lot Status..."
STATUS=$(curl -s "$BASE_URL/api/parking-lot/status")
echo "Response: $STATUS"
if echo "$STATUS" | grep -q "occupied"; then
    echo "✓ Status retrieved"
else
    echo "✗ Failed to get status"
    exit 1
fi
echo ""

echo "7. Finding Vehicle by Registration (KA-01-HH-9999)..."
FIND=$(curl -s "$BASE_URL/api/parking-lot/find/KA-01-HH-9999")
echo "Response: $FIND"
if echo "$FIND" | grep -q "KA-01-HH-9999"; then
    echo "✓ Vehicle found"
else
    echo "✗ Failed to find vehicle"
    exit 1
fi
echo ""

echo "8. Vehicle Leaving Slot 2..."
LEAVE=$(curl -s -X POST "$BASE_URL/api/parking-lot/leave" \
    -H "Content-Type: application/json" \
    -d '{"slot_number": 2}')
echo "Response: $LEAVE"
if echo "$LEAVE" | grep -q "success"; then
    echo "✓ Vehicle left successfully"
else
    echo "✗ Failed to leave slot"
    exit 1
fi
echo ""

echo "9. Getting Updated Status..."
STATUS2=$(curl -s "$BASE_URL/api/parking-lot/status")
echo "Response: $STATUS2"
if echo "$STATUS2" | grep -q "occupied"; then
    echo "✓ Updated status retrieved"
else
    echo "✗ Failed to get updated status"
    exit 1
fi
echo ""

echo "10. Testing Metrics Endpoint..."
METRICS=$(curl -s "$BASE_URL/metrics")
if echo "$METRICS" | grep -q "go_"; then
    echo "✓ Metrics endpoint working"
else
    echo "✗ Metrics endpoint failed"
    exit 1
fi
echo ""

echo "========================================="
echo "All API Tests Passed! ✓"
echo "========================================="
