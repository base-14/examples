#!/bin/bash

# Function to display script usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Generate hashed passwords for RabbitMQ users"
    echo ""
    echo "Options:"
    echo "  -p, --password PASSWORD    Password to hash"
    echo "  -u, --user USERNAME       Username (for reference only)"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 -u telemetry_user -p mySecurePassword123"
    echo "  $0 --password mySecurePassword123"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -p|--password)
            PASSWORD="$2"
            shift
            shift
            ;;
        -u|--user)
            USERNAME="$2"
            shift
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if password is provided
if [ -z "$PASSWORD" ]; then
    echo "Error: Password is required"
    show_usage
    exit 1
fi

# If running outside container, use docker to generate hash
if ! command -v rabbitmqctl &> /dev/null; then
    echo "rabbitmqctl not found locally, using Docker..."
    HASH=$(docker run --rm rabbitmq:3-management rabbitmqctl hash_password "$PASSWORD")
else
    HASH=$(rabbitmqctl hash_password "$PASSWORD")
fi

# Format output
echo "----------------------------------------"
if [ ! -z "$USERNAME" ]; then
    echo "Username: $USERNAME"
fi
echo "Password hash: $HASH"
echo ""
echo "For definitions.json:"
echo "{
  \"name\": \"${USERNAME:-your_username}\",
  \"password_hash\": \"$HASH\",
  \"hashing_algorithm\": \"rabbit_password_hashing_sha256\",
  \"tags\": []
}"
echo "----------------------------------------"