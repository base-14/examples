-- Grant CREATE DATABASE permission to rails user
GRANT ALL PRIVILEGES ON *.* TO 'rails'@'%';
FLUSH PRIVILEGES;

-- Create test database if it doesn't exist
CREATE DATABASE IF NOT EXISTS rails_app_test DEFAULT CHARACTER SET utf8mb4;
