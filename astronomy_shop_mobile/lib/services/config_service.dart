import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Simplified configuration service for managing environment variables
///
/// Security Notes:
/// - All sensitive configuration values are loaded from environment variables
/// - Never hardcode API keys, secrets, or endpoints in this file
/// - For production: Use HTTPS endpoints exclusively
/// - See SECURITY.md for production deployment guidelines
class ConfigService {
  ConfigService._internal();

  static ConfigService? _instance;

  static ConfigService get instance {
    _instance ??= ConfigService._internal();
    return _instance!;
  }

  // API Configuration
  String get apiBaseUrl {
    return dotenv.env['API_BASE_URL'] ?? 'http://localhost:8080/api';
  }

  // App Configuration (used by TelemetryService)
  String get serviceName => dotenv.env['SERVICE_NAME'] ?? 'astronomy-shop-mobile';
  String get serviceVersion => dotenv.env['SERVICE_VERSION'] ?? '1.0.0';
  String get environment => dotenv.env['ENVIRONMENT'] ?? 'development';

  // OTLP Configuration (used by TelemetryService)
  String get otlpEndpoint {
    final endpoint = dotenv.env['OTLP_ENDPOINT'];
    if (endpoint == null || endpoint.isEmpty) {
      throw ConfigurationException('OTLP_ENDPOINT is required');
    }
    return endpoint;
  }

  String get otlpTracesExporter {
    return dotenv.env['OTLP_TRACES_EXPORTER'] ?? 'v1/traces';
  }

  String get otlpMetricsExporter {
    return dotenv.env['OTLP_METRICS_EXPORTER'] ?? 'v1/metrics';
  }

  String get otlpLogsExporter {
    return dotenv.env['OTLP_LOGS_EXPORTER'] ?? 'v1/logs';
  }

  // Scout/OIDC Configuration (optional, used by TelemetryService)
  String? get scoutClientId => dotenv.env['SCOUT_CLIENT_ID'];
  String? get scoutClientSecret => dotenv.env['SCOUT_CLIENT_SECRET'];
  String? get scoutTokenUrl => dotenv.env['SCOUT_TOKEN_URL'];
  String? get scoutEndpoint => dotenv.env['SCOUT_ENDPOINT'];

  bool get isScoutConfigured {
    return scoutClientId != null &&
           scoutClientSecret != null &&
           scoutTokenUrl != null &&
           scoutEndpoint != null;
  }

  /// Validate configuration on initialization
  void validateConfiguration() {
    try {
      // Basic validation - just check that required fields exist
      if (apiBaseUrl.isEmpty) {
        throw ConfigurationException('API_BASE_URL is required');
      }

      if (otlpEndpoint.isEmpty) {
        throw ConfigurationException('OTLP_ENDPOINT is required');
      }

      // Simple warning for demo setup using HTTP
      if (kDebugMode) {
        final apiUri = Uri.parse(apiBaseUrl);
        Uri.parse(otlpEndpoint); // validate OTLP endpoint URI

        if (apiUri.scheme == 'http') {
          debugPrint('[CONFIG WARNING] Using HTTP for API: $apiBaseUrl');
          debugPrint('[CONFIG WARNING] For production, use HTTPS endpoints');
        }

        debugPrint('[CONFIG] Environment: $environment');
        debugPrint('[CONFIG] API Base URL: $apiBaseUrl');
        debugPrint('[CONFIG] OTLP Endpoint: $otlpEndpoint');
      }

    } catch (e) {
      if (kDebugMode) {
        debugPrint('[CONFIG ERROR] Configuration validation failed: $e');
      }
      rethrow;
    }
  }
}

/// Exception thrown when configuration is invalid
class ConfigurationException implements Exception {
  ConfigurationException(this.message);

  final String message;

  @override
  String toString() => 'ConfigurationException: $message';
}

/// Exception thrown when security requirements are violated
class SecurityException implements Exception {
  SecurityException(this.message);

  final String message;

  @override
  String toString() => 'SecurityException: $message';
}