-- Bootstrap a read-only monitoring login + grants for the OTel sqlserverreceiver.
-- Idempotent: safe to re-run.
--
-- Run as: sqlcmd -S sqlserver -U sa -P "$MSSQL_SA_PASSWORD" -C
--                 -v MONITOR_PASSWORD="$SQLSERVER_PASSWORD"
--                 -i 01-create-monitor-user.sql

USE [master];
GO

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'otel_monitor')
BEGIN
    DECLARE @sql nvarchar(max) =
        N'CREATE LOGIN [otel_monitor] WITH PASSWORD = N''' + REPLACE(N'$(MONITOR_PASSWORD)', N'''', N'''''') + N''', CHECK_POLICY = ON;';
    EXEC sp_executesql @sql;
END
GO

-- SQL Server 2022 introduced the more granular VIEW SERVER PERFORMANCE STATE.
-- Older versions need VIEW SERVER STATE. Granting both is harmless on 2022+.
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'otel_monitor')
BEGIN
    GRANT VIEW SERVER PERFORMANCE STATE TO [otel_monitor];
    GRANT VIEW ANY DATABASE TO [otel_monitor];
END
GO

-- Verify
SELECT name, type_desc, is_disabled
FROM sys.server_principals
WHERE name = N'otel_monitor';
GO
