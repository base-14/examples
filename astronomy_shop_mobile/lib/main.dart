import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:provider/provider.dart';

import 'models/product.dart';
import 'screens/cart_screen.dart';
import 'screens/performance_debug_screen.dart';
import 'screens/product_detail_screen.dart';
import 'screens/search_screen.dart';
import 'services/app_lifecycle_observer.dart';
import 'services/cart_service.dart';
import 'services/config_service.dart';
import 'services/currency_service.dart';
import 'services/error_handler_service.dart';
import 'services/funnel_tracking_service.dart';
import 'services/image_cache_service.dart';
import 'services/performance_service.dart';
import 'services/products_api_service.dart';
import 'services/telemetry_service.dart';
import 'widgets/cached_image.dart';
import 'widgets/currency_selector.dart';
import 'widgets/enhanced_loading.dart';
import 'widgets/error_boundary.dart';
import 'widgets/recommendations_section.dart';

void main() async {
  // Ensure Flutter binding is initialized
  WidgetsFlutterBinding.ensureInitialized();

  // Load environment variables
  await dotenv.load(fileName: '.env');

  // Initialize and validate configuration
  try {
    ConfigService.instance.validateConfiguration();
  } catch (e) {
    if (kDebugMode) {
      print('Configuration Error: $e');
      print('Please check your .env file configuration');
    }
    // Continue with defaults in demo mode, but warn about misconfiguration
  }

  // Initialize OpenTelemetry first
  await TelemetryService.instance.initialize();

  // Initialize funnel tracking with session ID
  FunnelTrackingService.instance.initialize(TelemetryService.instance.sessionId);

  // Initialize error handling after telemetry
  ErrorHandlerService.instance.initialize();

  // Initialize CartService
  CartService.instance.initialize();

  // Initialize CurrencyService
  CurrencyService.instance.initialize();

  // Initialize PerformanceService
  PerformanceService.instance.initialize();

  // Initialize ImageCacheService
  await ImageCacheService.instance.initialize();

  // Start the app
  runApp(const AstronomyShopApp());
}

class AstronomyShopApp extends StatelessWidget {
  const AstronomyShopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<CartService>(
          create: (_) => CartService.instance,
        ),
        ChangeNotifierProvider<CurrencyService>(
          create: (_) => CurrencyService.instance,
        ),
      ],
      child: AppErrorBoundary(
        child: MaterialApp(
          title: 'Astronomy Shop Mobile',
          theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFF1A1B4B), // Deep space blue
              brightness: Brightness.light,
            ),
            useMaterial3: true,
            appBarTheme: const AppBarTheme(
              centerTitle: true,
              elevation: 0,
              scrolledUnderElevation: 4,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.vertical(bottom: Radius.circular(16)),
              ),
            ),
            cardTheme: const CardThemeData(
              elevation: 2,
              margin: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                elevation: 2,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
            inputDecorationTheme: InputDecorationTheme(
              filled: true,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
            ),
            chipTheme: ChipThemeData(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),
            ),
          ),
          home: const ProductListScreen(),
        ),
      ),
    );
  }
}

class ProductListScreen extends StatefulWidget {
  const ProductListScreen({super.key});

  @override
  State<ProductListScreen> createState() => _ProductListScreenState();
}

class _ProductListScreenState extends State<ProductListScreen> {
  late final AppLifecycleObserver _lifecycleObserver;
  final ProductsApiService _productsApi = ProductsApiService.instance;

  List<Product> _products = [];
  bool _isLoading = true;
  String? _errorMessage;
  bool _isRefreshing = false;

  @override
  void initState() {
    super.initState();

    // Initialize app lifecycle observer
    _lifecycleObserver = AppLifecycleObserver();
    WidgetsBinding.instance.addObserver(_lifecycleObserver);

    // Load products from API
    _loadProducts();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(_lifecycleObserver);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🔭 Astronomy Shop'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
        actions: [
          const CurrencyButton(),
          Consumer<CartService>(
            builder: (context, cartService, child) {
              return Stack(
                children: [
                  IconButton(
                    icon: const Icon(Icons.shopping_cart),
                    onPressed: () {
                      TelemetryService.instance.recordEvent('cart_badge_tapped', attributes: {
                        'cart_item_count': cartService.totalItems,
                        'cart_total_price': cartService.totalPrice,
                        'screen_name': 'product_list',
                      });

                      Navigator.push<void>(
                        context,
                        MaterialPageRoute<void>(
                          builder: (context) => const CartScreen(),
                        ),
                      );
                    },
                  ),
                  if (cartService.totalItems > 0)
                    Positioned(
                      right: 6,
                      top: 6,
                      child: Container(
                        padding: const EdgeInsets.all(2),
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.error,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        constraints: const BoxConstraints(
                          minWidth: 20,
                          minHeight: 20,
                        ),
                        child: Text(
                          '${cartService.totalItems}',
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.onError,
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () {
              TelemetryService.instance.recordEvent('search_button_tapped', attributes: {
                'screen_name': 'product_list',
              });

              Navigator.push<void>(
                context,
                MaterialPageRoute<void>(
                  builder: (context) => const SearchScreen(),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _refreshProducts,
          ),
          if (kDebugMode)
            IconButton(
              icon: const Icon(Icons.settings),
              onPressed: () {
                Navigator.push<void>(
                  context,
                  MaterialPageRoute<void>(
                    builder: (context) => const PerformanceDebugScreen(),
                  ),
                );
              },
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refreshProducts,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header section
            Container(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Hot Products ⭐',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _isLoading
                        ? 'Loading amazing astronomy equipment...'
                        : 'Discover amazing astronomy equipment and collectibles',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),

            // Content area
            Expanded(
              child: _buildContent(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    if (_isLoading) {
      return Column(
        children: [
          const SizedBox(height: 40),
          const EnhancedLoadingWidget(
            message: 'Loading amazing astronomy products...',
            size: 56,
          ),
          const SizedBox(height: 40),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: 5,
              itemBuilder: (context, index) => const ProductCardShimmer(),
            ),
          ),
        ],
      );
    }

    if (_errorMessage != null) {
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
              'Failed to load products',
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
              onPressed: _loadProducts,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (_products.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.3),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.visibility,
                  size: 80,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'No Astronomy Products Found',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                'We\'re currently updating our stellar inventory. Please check back soon for amazing astronomy equipment and collectibles!',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 32),
              ElevatedButton.icon(
                onPressed: _loadProducts,
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh Catalog'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return CustomScrollView(
      slivers: [
        // Recommendations section
        const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.only(top: 16, bottom: 24),
            child: RecommendationsSection(),
          ),
        ),

        // Products section header
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Row(
              children: [
                Icon(
                  Icons.inventory_2,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Text(
                  'All Products',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                Text(
                  '${_products.length} items',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ),

        // Products list
        SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              final product = _products[index];
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                child: ProductCard(
                  product: product,
                  onTap: () => _onProductTapped(product),
                ),
              );
            },
            childCount: _products.length,
          ),
        ),
      ],
    );
  }

  Future<void> _loadProducts() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    PerformanceService.instance.startOperation('load_products');

    try {
      final products = await _productsApi.getProducts();

      setState(() {
        _products = products;
        _isLoading = false;
      });

      PerformanceService.instance.endOperation('load_products', metadata: {
        'product_count': products.length,
        'success': true,
      });

      // Record screen view event with actual data
      TelemetryService.instance.recordEvent('screen_view', attributes: {
        'screen_name': 'product_list',
        'product_count': products.length,
        'data_source': 'api',
      }, parentOperation: 'load_products');

      // Track funnel stage
      FunnelTrackingService.instance.trackStage(
        FunnelStage.productListView,
        metadata: {'product_count': products.length},
      );

    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });

      PerformanceService.instance.endOperation('load_products', metadata: {
        'success': false,
        'error': e.toString(),
      });

      // Record error event
      TelemetryService.instance.recordEvent('product_load_error', attributes: {
        'error_message': e.toString(),
        'screen_name': 'product_list',
      });
    }
  }

  Future<void> _refreshProducts() async {
    if (_isRefreshing) return;

    setState(() {
      _isRefreshing = true;
    });

    // Record refresh event
    TelemetryService.instance.recordEvent('product_refresh', attributes: {
      'screen_name': 'product_list',
      'current_product_count': _products.length,
    });

    try {
      final products = await _productsApi.getProducts(forceRefresh: true);

      setState(() {
        _products = products;
        _errorMessage = null;
      });

    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
      });
    } finally {
      setState(() {
        _isRefreshing = false;
      });
    }
  }

  void _onProductTapped(Product product) {
    // Start trace for product navigation
    TelemetryService.instance.startTrace('view_product');

    // Record product tap event for navigation tracking
    TelemetryService.instance.recordEvent('product_tap', attributes: {
      'product_id': product.id,
      'product_name': product.name,
      'product_price': product.priceUsd,
      'screen_name': 'product_list',
    }, parentOperation: 'view_product');

    // Navigate to product detail screen
    Navigator.push<void>(
      context,
      MaterialPageRoute<void>(
        builder: (context) => ProductDetailScreen(product: product),
      ),
    );
  }
}

class ProductCard extends StatefulWidget {
  const ProductCard({
    super.key,
    required this.product,
    required this.onTap,
  });

  final Product product;
  final VoidCallback onTap;

  @override
  State<ProductCard> createState() => _ProductCardState();
}

class _ProductCardState extends State<ProductCard> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 150),
      vsync: this,
    );
    _scaleAnimation = Tween<double>(
      begin: 1.0,
      end: 0.95,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _scaleAnimation,
      builder: (context, child) {
        return Transform.scale(
          scale: _scaleAnimation.value,
          child: Card(
            margin: const EdgeInsets.only(bottom: 16.0),
            child: InkWell(
              onTap: widget.onTap,
              onTapDown: (_) => _animationController.forward(),
              onTapUp: (_) => _animationController.reverse(),
              onTapCancel: () => _animationController.reverse(),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.all(20.0),
                child: Row(
                  children: [
                    // Product image with hero animation
                    Hero(
                      tag: 'product_image_${widget.product.id}',
                      child: Container(
                        width: 90,
                        height: 90,
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.primaryContainer,
                          borderRadius: BorderRadius.circular(12),
                          boxShadow: [
                            BoxShadow(
                              color: Theme.of(context).shadowColor.withValues(alpha: 0.1),
                              offset: const Offset(0, 2),
                              blurRadius: 8,
                            ),
                          ],
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: CachedImage(
                            imageUrl: widget.product.imageUrl,
                            width: 90,
                            height: 90,
                            fit: BoxFit.cover,
                            cacheKey: 'product_${widget.product.id}',
                            errorWidget: Icon(
                              _getProductIcon(widget.product.categories),
                              size: 48,
                              color: Theme.of(context).colorScheme.onPrimaryContainer,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 20),

                    // Product details with improved hierarchy
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            widget.product.name,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                              height: 1.3,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 6),
                          if (widget.product.categories.isNotEmpty)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.5),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                widget.product.categories.first,
                                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                  color: Theme.of(context).colorScheme.primary,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          const SizedBox(height: 8),
                          Text(
                            widget.product.description,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Theme.of(context).colorScheme.onSurfaceVariant,
                              height: 1.4,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 12),
                          Consumer<CurrencyService>(
                            builder: (context, currencyService, child) {
                              return Container(
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                decoration: BoxDecoration(
                                  color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Text(
                                  widget.product.getFormattedPrice(currencyService),
                                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                    color: Theme.of(context).colorScheme.primary,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              );
                            },
                          ),
                        ],
                      ),
                    ),

                    // Enhanced arrow with subtle animation
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.3),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        Icons.arrow_forward_ios,
                        size: 16,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  IconData _getProductIcon(List<String> categories) {
    if (categories.contains('telescopes')) return Icons.visibility;
    if (categories.contains('models')) return Icons.public;
    if (categories.contains('posters')) return Icons.image;
    if (categories.contains('replicas')) return Icons.rocket_launch;
    if (categories.contains('specimens')) return Icons.science;
    return Icons.stars;
  }
}
