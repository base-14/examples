import 'dart:convert';
import 'package:opentelemetry/api.dart' as otel;
import '../models/product.dart';
import 'http_service.dart';
import 'telemetry_service.dart';

class ProductsApiService {
  static ProductsApiService? _instance;
  
  final HttpService _httpService = HttpService.instance;
  final TelemetryService _telemetryService = TelemetryService.instance;
  
  // Cache for performance
  List<Product>? _cachedProducts;
  DateTime? _lastFetch;
  static const Duration _cacheTimeout = Duration(minutes: 5);
  
  ProductsApiService._internal();
  
  static ProductsApiService get instance {
    _instance ??= ProductsApiService._internal();
    return _instance!;
  }
  
  Future<List<Product>> getProducts({
    String currencyCode = 'USD',
    bool forceRefresh = false,
  }) async {
    final tracer = _telemetryService.tracer;

    // Start a new trace for this operation
    _telemetryService.startTrace('load_products');

    final span = tracer.startSpan('products_api_get_all');
    
    span.setAttributes([
      otel.Attribute.fromString('currency_code', currencyCode),
      otel.Attribute.fromString('session.id', _telemetryService.sessionId),
      otel.Attribute.fromString('force_refresh', forceRefresh.toString()),
    ]);
    
    try {
      // Check cache first (unless force refresh)
      if (!forceRefresh && _isCacheValid()) {
        span.addEvent('cache_hit');
        span.setAttributes([
          otel.Attribute.fromInt('product_count', _cachedProducts!.length),
          otel.Attribute.fromString('data_source', 'cache'),
        ]);
        
        span.end();
        return _cachedProducts!;
      }
      
      // Make API call
      span.addEvent('api_call_start');
      
      final response = await _httpService.get(
        '/products',
        queryParams: {'currencyCode': currencyCode},
      );
      
      span.setAttributes([
        otel.Attribute.fromInt('http_status_code', response.statusCode),
        otel.Attribute.fromInt('http_duration_ms', response.duration.inMilliseconds),
        otel.Attribute.fromString('http_success', response.isSuccess.toString()),
      ]);
      
      if (response.isSuccess && response.rawResponse.isNotEmpty) {
        // Parse JSON directly from raw response
        final dynamic jsonData = jsonDecode(response.rawResponse);
        final List<dynamic> jsonList = jsonData is List ? jsonData : <dynamic>[];
        
        final products = jsonList
            .map((json) => Product.fromJson(json as Map<String, dynamic>))
            .toList();
        
        // Update cache
        _cachedProducts = products;
        _lastFetch = DateTime.now();
        
        span.setAttributes([
          otel.Attribute.fromInt('product_count', products.length),
          otel.Attribute.fromString('data_source', 'api'),
        ]);
        
        span.addEvent('products_loaded', attributes: [
          otel.Attribute.fromInt('count', products.length),
        ]);
        
        
        span.setStatus(otel.StatusCode.ok);
        span.end();
        return products;
        
      } else {
        // API error
        final errorMessage = response.errorMessage ?? 'Unknown API error';
        
        span.setAttributes([
          otel.Attribute.fromString('error_message', errorMessage),
          otel.Attribute.fromString('error_type', 'api_error'),
        ]);
        
        span.setStatus(otel.StatusCode.error, errorMessage);
        
        // Try to return cached data as fallback
        if (_cachedProducts != null) {
          span.addEvent('fallback_to_cache');
          span.setAttributes([
            otel.Attribute.fromString('fallback_reason', 'api_error'),
          ]);
          
          span.end();
          return _cachedProducts!;
        }
        
        // Fallback to hardcoded products for development/CORS issues
        span.addEvent('fallback_to_hardcoded');
        span.setAttributes([
          otel.Attribute.fromString('fallback_reason', 'api_error_no_cache'),
        ]);
        
        final hardcodedProducts = Product.getHardcodedProducts();
        _cachedProducts = hardcodedProducts;
        _lastFetch = DateTime.now();
        
        span.end();
        return hardcodedProducts;
      }
      
    } catch (e, stackTrace) {
      span.recordException(e, stackTrace: stackTrace);
      span.setStatus(otel.StatusCode.error, e.toString());
      
      // Try cached data as last resort
      if (_cachedProducts != null) {
        span.addEvent('fallback_to_cache');
        span.setAttributes([
          otel.Attribute.fromString('fallback_reason', 'exception'),
        ]);
        
        span.end();
        return _cachedProducts!;
      }
      
      // Final fallback to hardcoded products
      span.addEvent('fallback_to_hardcoded');
      span.setAttributes([
        otel.Attribute.fromString('fallback_reason', 'exception_no_cache'),
      ]);
      
      final hardcodedProducts = Product.getHardcodedProducts();
      _cachedProducts = hardcodedProducts;
      _lastFetch = DateTime.now();
      
      span.end();
      return hardcodedProducts;
    }
  }
  
  Future<Product?> getProduct(
    String productId, {
    String currencyCode = 'USD',
  }) async {
    final tracer = _telemetryService.tracer;
    final span = tracer.startSpan('products_api_get_single');
    
    span.setAttributes([
      otel.Attribute.fromString('product_id', productId),
      otel.Attribute.fromString('currency_code', currencyCode),
      otel.Attribute.fromString('session.id', _telemetryService.sessionId),
    ]);
    
    try {
      // First try to find in cache
      if (_cachedProducts != null) {
        final cachedProduct = _cachedProducts!
            .where((product) => product.id == productId)
            .firstOrNull;
        
        if (cachedProduct != null) {
          span.addEvent('found_in_cache');
          span.setStatus(otel.StatusCode.ok);
          span.end();
          return cachedProduct;
        }
      }
      
      // Not in cache, make API call (future implementation)
      // For now, get all products and filter
      final products = await getProducts(currencyCode: currencyCode);
      final product = products
          .where((product) => product.id == productId)
          .firstOrNull;
      
      span.setAttributes([
        otel.Attribute.fromString('found', product != null ? 'true' : 'false'),
      ]);
      
      if (product != null) {
        span.addEvent('product_found');
        span.setStatus(otel.StatusCode.ok);
      } else {
        span.addEvent('product_not_found');
        span.setStatus(otel.StatusCode.error, 'Product not found');
      }
      
      span.end();
      return product;
      
    } catch (e, stackTrace) {
      span.recordException(e, stackTrace: stackTrace);
      span.setStatus(otel.StatusCode.error, e.toString());
      span.end();
      rethrow;
    }
  }
  
  void clearCache() {
    final tracer = _telemetryService.tracer;
    final span = tracer.startSpan('products_cache_clear');
    
    _cachedProducts = null;
    _lastFetch = null;
    
    span.addEvent('cache_cleared');
    span.end();
  }
  
  bool _isCacheValid() {
    if (_cachedProducts == null || _lastFetch == null) {
      return false;
    }
    
    final now = DateTime.now();
    return now.difference(_lastFetch!) < _cacheTimeout;
  }
  
  Map<String, dynamic> getCacheInfo() {
    return {
      'has_cache': _cachedProducts != null,
      'cache_size': _cachedProducts?.length ?? 0,
      'last_fetch': _lastFetch?.toIso8601String(),
      'is_valid': _isCacheValid(),
    };
  }
}