import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/product.dart';
import '../services/currency_service.dart';
import '../services/search_service.dart';
import '../services/telemetry_service.dart';
import '../widgets/cached_image.dart';
import 'product_detail_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final SearchService _searchService = SearchService.instance;
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  
  List<Product> _searchResults = [];
  List<String> _suggestions = [];
  bool _isSearching = false;
  bool _showSuggestions = false;
  String? _currentQuery;
  String? _errorMessage;
  SearchResult? _lastSearchResult;

  @override
  void initState() {
    super.initState();
    
    TelemetryService.instance.recordEvent('screen_view', attributes: {
      'screen_name': 'search',
      'session_id': TelemetryService.instance.sessionId,
    });

    _searchController.addListener(_onSearchChanged);
    _searchFocus.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    _searchController.removeListener(_onSearchChanged);
    _searchFocus.removeListener(_onFocusChanged);
    _searchController.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    final query = _searchController.text;
    
    if (query.isEmpty) {
      setState(() {
        _suggestions = [];
        _showSuggestions = false;
        _searchResults = [];
        _currentQuery = null;
        _errorMessage = null;
      });
      return;
    }

    if (query.length >= 2) {
      setState(() {
        _suggestions = _searchService.getSearchSuggestions(query);
        _showSuggestions = _suggestions.isNotEmpty && _searchFocus.hasFocus;
      });
    }
  }

  void _onFocusChanged() {
    setState(() {
      _showSuggestions = _searchFocus.hasFocus && 
          _suggestions.isNotEmpty && 
          _searchController.text.length >= 2;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🔍 Search Products'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
      ),
      body: Column(
        children: [
          _buildSearchBar(),
          if (_showSuggestions) _buildSuggestions(),
          Expanded(child: _buildContent()),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: Theme.of(context).shadowColor.withValues(alpha: 0.1),
            offset: const Offset(0, 2),
            blurRadius: 4,
          ),
        ],
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _searchController,
              focusNode: _searchFocus,
              decoration: InputDecoration(
                hintText: 'Search for telescopes, planets, stars...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchController.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: _clearSearch,
                      )
                    : null,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
              ),
              textInputAction: TextInputAction.search,
              onSubmitted: _performSearch,
            ),
          ),
          const SizedBox(width: 12),
          ElevatedButton(
            onPressed: _searchController.text.isEmpty 
                ? null 
                : () => _performSearch(_searchController.text),
            style: ElevatedButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.primary,
              foregroundColor: Theme.of(context).colorScheme.onPrimary,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            ),
            child: _isSearching 
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Search'),
          ),
        ],
      ),
    );
  }

  Widget _buildSuggestions() {
    return Container(
      color: Theme.of(context).colorScheme.surface,
      child: Column(
        children: [
          const Divider(height: 1),
          ListView.builder(
            shrinkWrap: true,
            itemCount: _suggestions.length,
            itemBuilder: (context, index) {
              final suggestion = _suggestions[index];
              return ListTile(
                dense: true,
                leading: Icon(
                  Icons.search,
                  size: 20,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
                title: Text(suggestion),
                onTap: () => _selectSuggestion(suggestion),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    if (_currentQuery == null) {
      return _buildEmptyState();
    }

    if (_isSearching) {
      return _buildLoadingState();
    }

    if (_errorMessage != null) {
      return _buildErrorState();
    }

    if (_searchResults.isEmpty) {
      return _buildNoResultsState();
    }

    return _buildSearchResults();
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.search,
            size: 64,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 16),
          Text(
            'Search for products',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          Text(
            'Find telescopes, models, posters and more',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(
            'Searching for "$_currentQuery"...',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.error_outline,
            size: 64,
            color: Theme.of(context).colorScheme.error,
          ),
          const SizedBox(height: 16),
          Text(
            'Search failed',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          Text(
            _errorMessage!,
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: () => _performSearch(_currentQuery!),
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }

  Widget _buildNoResultsState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.search_off,
            size: 64,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 16),
          Text(
            'No results found',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          Text(
            'Try different keywords for "$_currentQuery"',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            children: [
              'telescope',
              'star',
              'planet',
              'model',
              'poster'
            ].map((suggestion) => ActionChip(
              label: Text(suggestion),
              onPressed: () => _selectSuggestion(suggestion),
            )).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchResults() {
    return Column(
      children: [
        _buildResultsHeader(),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: _searchResults.length,
            itemBuilder: (context, index) {
              final product = _searchResults[index];
              return _buildProductCard(product, index);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildResultsHeader() {
    final duration = _lastSearchResult?.searchTime;
    final source = _lastSearchResult?.source;
    
    return Container(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Text(
            '${_searchResults.length} results for "$_currentQuery"',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          const Spacer(),
          if (duration != null)
            Text(
              '(${duration.inMilliseconds}ms${source != null ? ', $source' : ''})',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildProductCard(Product product, int index) {
    return Consumer<CurrencyService>(
      builder: (context, currencyService, child) {
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: InkWell(
            onTap: () => _onProductTap(product, index),
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: CachedImage(
                      imageUrl: product.imageUrl,
                      width: 80,
                      height: 80,
                      fit: BoxFit.cover,
                      cacheKey: 'search_${product.id}',
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          product.name,
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 4),
                        if (product.categories.isNotEmpty)
                          Text(
                            product.categories.join(', '),
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Theme.of(context).colorScheme.onSurfaceVariant,
                            ),
                          ),
                        const SizedBox(height: 8),
                        Text(
                          currencyService.formatPrice(product.priceUsd),
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: Theme.of(context).colorScheme.primary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _performSearch(String query) async {
    if (query.trim().isEmpty) return;

    setState(() {
      _isSearching = true;
      _showSuggestions = false;
      _currentQuery = query;
      _errorMessage = null;
    });

    _searchFocus.unfocus();
    _searchService.recordSearchQuery(query);

    try {
      final result = await _searchService.searchProducts(query);
      
      setState(() {
        _searchResults = result.products;
        _lastSearchResult = result;
        _isSearching = false;
      });

      if (result.products.isEmpty) {
        _searchService.recordNoResults(query);
      }

    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _searchResults = [];
        _isSearching = false;
      });
    }
  }

  void _selectSuggestion(String suggestion) {
    _searchController.text = suggestion;
    _performSearch(suggestion);
  }

  void _clearSearch() {
    _searchController.clear();
    setState(() {
      _searchResults = [];
      _suggestions = [];
      _showSuggestions = false;
      _currentQuery = null;
      _errorMessage = null;
      _lastSearchResult = null;
    });
  }

  void _onProductTap(Product product, int index) {
    if (_currentQuery != null) {
      _searchService.recordSearchResultClick(product, _currentQuery!, index);
    }

    TelemetryService.instance.recordEvent('product_tap', attributes: {
      'product_id': product.id,
      'product_name': product.name,
      'source': 'search',
      'search_query': _currentQuery ?? '',
      'result_position': index,
      'screen_name': 'search',
    });

    Navigator.push<void>(
      context,
      MaterialPageRoute<void>(
        builder: (context) => ProductDetailScreen(product: product),
      ),
    );
  }
}