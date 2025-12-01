#!/bin/bash

set -e

BASE_URL="http://localhost:8080"

echo "========================================="
echo "Testing Go 1.19 + Gin + PostgreSQL API"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "1. Testing Health Check..."
HEALTH=$(curl -s "$BASE_URL/api/health")
echo "Response: $HEALTH"
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓${NC} Health check passed"
else
    echo -e "${RED}✗${NC} Health check failed"
    exit 1
fi
echo ""

echo "2. Creating User 1 (Alice)..."
USER1=$(curl -s -X POST "$BASE_URL/api/users" \
    -H "Content-Type: application/json" \
    -d '{"email": "alice@example.com", "name": "Alice Smith", "bio": "Software Engineer"}')
echo "Response: $USER1"
USER1_ID=$(echo "$USER1" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
if [ -n "$USER1_ID" ]; then
    echo -e "${GREEN}✓${NC} User 1 created with ID: $USER1_ID"
else
    echo -e "${RED}✗${NC} Failed to create user 1"
    exit 1
fi
echo ""

echo "3. Creating User 2 (Bob)..."
USER2=$(curl -s -X POST "$BASE_URL/api/users" \
    -H "Content-Type: application/json" \
    -d '{"email": "bob@example.com", "name": "Bob Johnson", "bio": "Product Manager"}')
echo "Response: $USER2"
USER2_ID=$(echo "$USER2" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
if [ -n "$USER2_ID" ]; then
    echo -e "${GREEN}✓${NC} User 2 created with ID: $USER2_ID"
else
    echo -e "${RED}✗${NC} Failed to create user 2"
    exit 1
fi
echo ""

echo "4. Listing All Users..."
USERS=$(curl -s "$BASE_URL/api/users")
echo "Response: $USERS"
if echo "$USERS" | grep -q "Alice Smith"; then
    echo -e "${GREEN}✓${NC} Users list retrieved"
else
    echo -e "${RED}✗${NC} Failed to list users"
    exit 1
fi
echo ""

echo "5. Getting User 1 by ID..."
USER_GET=$(curl -s "$BASE_URL/api/users/$USER1_ID")
echo "Response: $USER_GET"
if echo "$USER_GET" | grep -q "Alice Smith"; then
    echo -e "${GREEN}✓${NC} User retrieved successfully"
else
    echo -e "${RED}✗${NC} Failed to get user"
    exit 1
fi
echo ""

echo "6. Updating User 1..."
USER_UPDATE=$(curl -s -X PUT "$BASE_URL/api/users/$USER1_ID" \
    -H "Content-Type: application/json" \
    -d '{"name": "Alice Cooper", "bio": "Senior Software Engineer"}')
echo "Response: $USER_UPDATE"
if echo "$USER_UPDATE" | grep -q "Alice Cooper"; then
    echo -e "${GREEN}✓${NC} User updated successfully"
else
    echo -e "${RED}✗${NC} Failed to update user"
    exit 1
fi
echo ""

echo "7. Deleting User 2..."
DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/api/users/$USER2_ID")
echo "Response: $DELETE_RESPONSE"
if echo "$DELETE_RESPONSE" | grep -q "deleted successfully"; then
    echo -e "${GREEN}✓${NC} User deleted successfully"
else
    echo -e "${RED}✗${NC} Failed to delete user"
    exit 1
fi
echo ""

echo "8. Verifying User 2 is deleted..."
GET_DELETED=$(curl -s "$BASE_URL/api/users/$USER2_ID")
if echo "$GET_DELETED" | grep -q "not found"; then
    echo -e "${GREEN}✓${NC} User deletion verified"
else
    echo -e "${RED}✗${NC} User still exists"
    exit 1
fi
echo ""

echo "========================================="
echo -e "${GREEN}All API Tests Passed! ✓${NC}"
echo "========================================="
