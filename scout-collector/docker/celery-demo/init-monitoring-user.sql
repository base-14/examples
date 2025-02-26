-- Create monitoring user with appropriate permissions
CREATE USER otel_monitor WITH PASSWORD 'monitor123';

-- Grant necessary monitoring permissions
GRANT pg_monitor TO otel_monitor;

-- Additional specific permissions for monitoring
GRANT SELECT ON pg_stat_database TO otel_monitor;
GRANT SELECT ON pg_stat_all_tables TO otel_monitor;
GRANT SELECT ON pg_stat_activity TO otel_monitor;
GRANT SELECT ON pg_stat_replication TO otel_monitor;

-- Allow monitoring user to connect to the database
GRANT CONNECT ON DATABASE task_db TO otel_monitor;
ALTER USER otel_monitor SET statement_timeout = '30s';