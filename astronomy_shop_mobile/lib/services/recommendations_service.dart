import 'package:opentelemetry/api.dart' as otel;

import '../models/product.dart';
import 'cart_service.dart';
import 'http_service.dart';
import 'telemetry_service.dart';

class RecommendationsService {
  RecommendationsService._internal();

  static RecommendationsService? _instance;

  final HttpService _httpService = HttpService.instance;
  final TelemetryService _telemetryService = TelemetryService.instance;

  List<Product>? _cachedRecommendations;
  DateTime? _lastFetch;
  static const Duration _cacheTimeout = Duration(minutes: 10);
  
  static RecommendationsService get instance {
    _instance ??= RecommendationsService._internal();
    return _instance!;
  }
  
  Future<List<Product>> getRecommendations({
    String? userId,
    List<String>? productIds,
    String currencyCode = 'USD',
    bool forceRefresh = false,
  }) async {
    final tracer = _telemetryService.tracer;
    final span = tracer.startSpan('recommendations_get');
    
    span.setAttributes([
      otel.Attribute.fromString('user_id', userId ?? 'anonymous'),
      otel.Attribute.fromString('currency_code', currencyCode),
      otel.Attribute.fromString('session_id', _telemetryService.sessionId),
      otel.Attribute.fromInt('product_ids_count', productIds?.length ?? 0),
      otel.Attribute.fromString('force_refresh', forceRefresh.toString()),
    ]);
    
    try {
      if (!forceRefresh && _isCacheValid()) {
        span.addEvent('cache_hit');
        span.setAttributes([
          otel.Attribute.fromInt('recommendations_count', _cachedRecommendations!.length),
          otel.Attribute.fromString('data_source', 'cache'),
        ]);
        
        span.end();
        return _cachedRecommendations!;
      }
      
      span.addEvent('api_call_start');
      
      final queryParams = <String, String>{
        'sessionId': userId ?? _telemetryService.sessionId,
        'currencyCode': currencyCode,
      };
      
      if (productIds != null && productIds.isNotEmpty) {
        // OpenTelemetry Demo API expects productIds as multiple query params
        for (int i = 0; i < productIds.length; i++) {
          queryParams['productIds[$i]'] = productIds[i];
        }
      }
      
      final response = await _httpService.get<List<dynamic>>(
        '/recommendations',
        queryParams: queryParams,
      );
      
      span.setAttributes([
        otel.Attribute.fromInt('http_status_code', response.statusCode),
        otel.Attribute.fromInt('http_duration_ms', response.duration.inMilliseconds),
        otel.Attribute.fromString('http_success', response.isSuccess.toString()),
      ]);
      
      if (response.isSuccess && response.data != null) {
        final recommendations = (response.data as List)
            .map((json) => Product.fromJson(json as Map<String, dynamic>))
            .toList();
        
        _cachedRecommendations = recommendations;
        _lastFetch = DateTime.now();
        
        span.setAttributes([
          otel.Attribute.fromInt('recommendations_count', recommendations.length),
          otel.Attribute.fromString('data_source', 'api'),
        ]);
        
        span.addEvent('recommendations_loaded', attributes: [
          otel.Attribute.fromInt('count', recommendations.length),
        ]);
        
        _recordRecommendationMetrics(recommendations, 'api_success');
        
        span.setStatus(otel.StatusCode.ok);
        span.end();
        return recommendations;
        
      } else {
        final errorMessage = response.errorMessage ?? 'Unknown API error';
        
        span.setAttributes([
          otel.Attribute.fromString('error_message', errorMessage),
          otel.Attribute.fromString('error_type', 'api_error'),
        ]);
        
        span.setStatus(otel.StatusCode.error, errorMessage);
        
        if (_cachedRecommendations != null) {
          span.addEvent('fallback_to_cache');
          span.end();
          return _cachedRecommendations!;
        }
        
        span.addEvent('fallback_to_trending');
        final trendingProducts = await _getFallbackRecommendations();
        _cachedRecommendations = trendingProducts;
        _lastFetch = DateTime.now();
        
        _recordRecommendationMetrics(trendingProducts, 'api_fallback');
        
        span.end();
        return trendingProducts;
      }
      
    } catch (e, stackTrace) {
      span.recordException(e, stackTrace: stackTrace);
      span.setStatus(otel.StatusCode.error, e.toString());
      
      if (_cachedRecommendations != null) {
        span.addEvent('fallback_to_cache');
        span.end();
        return _cachedRecommendations!;
      }
      
      span.addEvent('fallback_to_trending');
      final trendingProducts = await _getFallbackRecommendations();
      _cachedRecommendations = trendingProducts;
      _lastFetch = DateTime.now();
      
      _recordRecommendationMetrics(trendingProducts, 'exception_fallback');
      
      span.end();
      return trendingProducts;
    }
  }
  
  Future<List<Product>> getCartBasedRecommendations() async {
    final cartService = CartService.instance;
    final cartItems = cartService.items;
    
    if (cartItems.isEmpty) {
      return getRecommendations();
    }
    
    final productIds = cartItems.map((item) => item.productId).toList();
    
    _telemetryService.recordEvent('recommendations_cart_based', attributes: {
      'cart_items_count': cartItems.length,
      'product_ids': productIds.join(','),
    });
    
    return getRecommendations(
      userId: _telemetryService.sessionId,
      productIds: productIds,
    );
  }
  
  void recordRecommendationClick(Product product, int position) {
    _telemetryService.recordEvent('recommendation_clicked', attributes: {
      'product_id': product.id,
      'product_name': product.name,
      'position': position,
      'price_usd': product.priceUsd,
      'session_id': _telemetryService.sessionId,
    });
  }
  
  void recordRecommendationImpression(List<Product> products) {
    _telemetryService.recordEvent('recommendations_viewed', attributes: {
      'recommendations_count': products.length,
      'product_ids': products.map((p) => p.id).join(','),
      'session_id': _telemetryService.sessionId,
    });
  }
  
  Future<List<Product>> _getFallbackRecommendations() async {
    final allProducts = Product.getHardcodedProducts();
    allProducts.shuffle();
    return allProducts.take(4).toList();
  }
  
  void _recordRecommendationMetrics(List<Product> recommendations, String source) {
    final totalPrice = recommendations.fold(0.0, (sum, p) => sum + p.priceUsd);
    final averagePrice = recommendations.isNotEmpty ? totalPrice / recommendations.length : 0.0;
    final allCategories = recommendations.expand((p) => p.categories).toSet();
    
    _telemetryService.recordEvent('recommendations_metrics', attributes: {
      'count': recommendations.length,
      'source': source,
      'average_price': averagePrice,
      'total_value': totalPrice,
      'unique_categories': allCategories.length,
      'categories': allCategories.join(','),
      'price_range_min': recommendations.isNotEmpty 
          ? recommendations.map((p) => p.priceUsd).reduce((a, b) => a < b ? a : b)
          : 0.0,
      'price_range_max': recommendations.isNotEmpty
          ? recommendations.map((p) => p.priceUsd).reduce((a, b) => a > b ? a : b)
          : 0.0,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
      'session_id': _telemetryService.sessionId,
    });
  }
  
  bool _isCacheValid() {
    if (_cachedRecommendations == null || _lastFetch == null) {
      return false;
    }
    
    final now = DateTime.now();
    return now.difference(_lastFetch!) < _cacheTimeout;
  }
  
  void clearCache() {
    final tracer = _telemetryService.tracer;
    final span = tracer.startSpan('recommendations_cache_clear');
    
    _cachedRecommendations = null;
    _lastFetch = null;
    
    span.addEvent('cache_cleared');
    span.end();
  }
  
  Map<String, dynamic> getCacheInfo() {
    return {
      'has_cache': _cachedRecommendations != null,
      'cache_size': _cachedRecommendations?.length ?? 0,
      'last_fetch': _lastFetch?.toIso8601String(),
      'is_valid': _isCacheValid(),
    };
  }
}