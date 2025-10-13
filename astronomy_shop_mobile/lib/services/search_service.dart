import 'package:opentelemetry/api.dart' as otel;
import '../models/product.dart';
import 'http_service.dart';
import 'telemetry_service.dart';
import 'products_api_service.dart';

class SearchResult {
  final List<Product> products;
  final String query;
  final int totalResults;
  final Duration searchTime;
  final String source;

  const SearchResult({
    required this.products,
    required this.query,
    required this.totalResults,
    required this.searchTime,
    required this.source,
  });
}

class SearchService {
  static SearchService? _instance;
  
  final HttpService _httpService = HttpService.instance;
  final TelemetryService _telemetryService = TelemetryService.instance;
  final ProductsApiService _productsApi = ProductsApiService.instance;
  
  final Map<String, SearchResult> _searchCache = {};
  static const Duration _cacheTimeout = Duration(minutes: 5);
  final Map<String, DateTime> _cacheTimestamps = {};
  
  SearchService._internal();
  
  static SearchService get instance {
    _instance ??= SearchService._internal();
    return _instance!;
  }
  
  Future<SearchResult> searchProducts(
    String query, {
    String currencyCode = 'USD',
    int limit = 20,
    bool forceRefresh = false,
  }) async {
    final searchStartTime = DateTime.now();
    final tracer = _telemetryService.tracer;
    final span = tracer.startSpan('product_search');
    
    final normalizedQuery = query.trim().toLowerCase();
    
    span.setAttributes([
      otel.Attribute.fromString('search_query', query),
      otel.Attribute.fromString('normalized_query', normalizedQuery),
      otel.Attribute.fromString('currency_code', currencyCode),
      otel.Attribute.fromInt('limit', limit),
      otel.Attribute.fromString('session_id', _telemetryService.sessionId),
    ]);
    
    if (normalizedQuery.isEmpty) {
      span.setStatus(otel.StatusCode.error, 'Empty search query');
      span.end();
      throw ArgumentError('Search query cannot be empty');
    }
    
    try {
      // Check cache first
      if (!forceRefresh && _isCacheValid(normalizedQuery)) {
        span.addEvent('cache_hit');
        final cachedResult = _searchCache[normalizedQuery]!;
        
        span.setAttributes([
          otel.Attribute.fromInt('results_count', cachedResult.products.length),
          otel.Attribute.fromString('data_source', 'cache'),
          otel.Attribute.fromInt('search_duration_ms', cachedResult.searchTime.inMilliseconds),
        ]);
        
        _recordSearchMetrics(cachedResult, 'cache');
        span.end();
        return cachedResult;
      }
      
      span.addEvent('api_search_start');
      
      // Try API search first
      try {
        final apiResult = await _searchViaAPI(normalizedQuery, currencyCode, limit);
        final searchDuration = DateTime.now().difference(searchStartTime);
        
        final result = SearchResult(
          products: apiResult,
          query: query,
          totalResults: apiResult.length,
          searchTime: searchDuration,
          source: 'api',
        );
        
        // Cache the result
        _searchCache[normalizedQuery] = result;
        _cacheTimestamps[normalizedQuery] = DateTime.now();
        
        span.setAttributes([
          otel.Attribute.fromInt('results_count', result.products.length),
          otel.Attribute.fromString('data_source', 'api'),
          otel.Attribute.fromInt('search_duration_ms', searchDuration.inMilliseconds),
        ]);
        
        _recordSearchMetrics(result, 'api_success');
        span.setStatus(otel.StatusCode.ok);
        span.end();
        return result;
        
      } catch (apiError) {
        span.addEvent('api_search_failed');
        span.setAttributes([
          otel.Attribute.fromString('api_error', apiError.toString()),
        ]);
        
        // Fallback to local search
        span.addEvent('fallback_to_local_search');
        final localResult = await _searchLocally(normalizedQuery, currencyCode);
        final searchDuration = DateTime.now().difference(searchStartTime);
        
        final result = SearchResult(
          products: localResult,
          query: query,
          totalResults: localResult.length,
          searchTime: searchDuration,
          source: 'local_fallback',
        );
        
        // Cache the fallback result
        _searchCache[normalizedQuery] = result;
        _cacheTimestamps[normalizedQuery] = DateTime.now();
        
        span.setAttributes([
          otel.Attribute.fromInt('results_count', result.products.length),
          otel.Attribute.fromString('data_source', 'local_fallback'),
          otel.Attribute.fromInt('search_duration_ms', searchDuration.inMilliseconds),
        ]);
        
        _recordSearchMetrics(result, 'local_fallback');
        span.setStatus(otel.StatusCode.ok);
        span.end();
        return result;
      }
      
    } catch (e, stackTrace) {
      span.recordException(e, stackTrace: stackTrace);
      span.setStatus(otel.StatusCode.error, e.toString());
      
      _telemetryService.recordEvent('search_error', attributes: {
        'query': query,
        'error_message': e.toString(),
        'session_id': _telemetryService.sessionId,
      });
      
      span.end();
      rethrow;
    }
  }
  
  Future<List<Product>> _searchViaAPI(String query, String currencyCode, int limit) async {
    final requestBody = {
      'query': query,
      'currencyCode': currencyCode,
      'limit': limit,
    };
    
    final response = await _httpService.post<Map<String, dynamic>>(
      '/search/products',
      body: requestBody,
      fromJson: (json) => json,
    );
    
    if (response.isSuccess && response.data != null) {
      final results = response.data!['products'] as List? ?? [];
      return results
          .map((json) => Product.fromJson(json as Map<String, dynamic>))
          .toList();
    } else {
      throw Exception('Search API failed: ${response.errorMessage}');
    }
  }
  
  Future<List<Product>> _searchLocally(String query, String currencyCode) async {
    final allProducts = await _productsApi.getProducts(currencyCode: currencyCode);
    
    return allProducts.where((product) {
      final searchIn = [
        product.name.toLowerCase(),
        product.description.toLowerCase(),
        ...product.categories.map((c) => c.toLowerCase()),
      ];
      
      return searchIn.any((field) => field.contains(query));
    }).toList();
  }
  
  List<String> getSearchSuggestions(String query) {
    if (query.length < 2) return [];
    
    final suggestions = <String>[];
    final lowerQuery = query.toLowerCase();
    
    // Common astronomy search terms
    final commonTerms = [
      'telescope', 'star', 'planet', 'moon', 'solar', 'galaxy', 'nebula',
      'constellation', 'asteroid', 'comet', 'meteorite', 'observatory',
      'vintage', 'model', 'poster', 'helmet', 'replica',
    ];
    
    for (final term in commonTerms) {
      if (term.startsWith(lowerQuery) && term != lowerQuery) {
        suggestions.add(term);
      }
    }
    
    return suggestions.take(5).toList();
  }
  
  void recordSearchQuery(String query) {
    _telemetryService.recordEvent('search_query_entered', attributes: {
      'query': query,
      'query_length': query.length,
      'session_id': _telemetryService.sessionId,
    });
  }
  
  void recordSearchResultClick(Product product, String query, int position) {
    _telemetryService.recordEvent('search_result_clicked', attributes: {
      'product_id': product.id,
      'product_name': product.name,
      'search_query': query,
      'result_position': position,
      'price_usd': product.priceUsd,
      'session_id': _telemetryService.sessionId,
    });
  }
  
  void recordNoResults(String query) {
    _telemetryService.recordEvent('search_no_results', attributes: {
      'query': query,
      'query_length': query.length,
      'session_id': _telemetryService.sessionId,
    });
  }
  
  void _recordSearchMetrics(SearchResult result, String source) {
    _telemetryService.recordEvent('search_metrics', attributes: {
      'query': result.query,
      'results_count': result.totalResults,
      'search_duration_ms': result.searchTime.inMilliseconds,
      'data_source': source,
      'has_results': result.products.isNotEmpty,
      'average_price': result.products.isNotEmpty
          ? result.products.fold(0.0, (sum, p) => sum + p.priceUsd) / result.products.length
          : 0.0,
      'categories': result.products
          .expand((p) => p.categories)
          .toSet()
          .join(','),
      'session_id': _telemetryService.sessionId,
    });
  }
  
  bool _isCacheValid(String query) {
    final cachedResult = _searchCache[query];
    final timestamp = _cacheTimestamps[query];
    
    if (cachedResult == null || timestamp == null) {
      return false;
    }
    
    final now = DateTime.now();
    return now.difference(timestamp) < _cacheTimeout;
  }
  
  void clearCache() {
    _searchCache.clear();
    _cacheTimestamps.clear();
    
    _telemetryService.recordEvent('search_cache_cleared');
  }
  
  Map<String, dynamic> getCacheInfo() {
    return {
      'cached_queries': _searchCache.length,
      'cache_keys': _searchCache.keys.toList(),
      'oldest_cache_age_minutes': _cacheTimestamps.values.isNotEmpty
          ? DateTime.now().difference(_cacheTimestamps.values.first).inMinutes
          : 0,
    };
  }
}