import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/product.dart';
import '../services/cart_service.dart';
import '../services/currency_service.dart';
import '../services/funnel_tracking_service.dart';
import '../services/performance_service.dart';
import '../services/telemetry_service.dart';
import '../widgets/cached_image.dart';

class ProductDetailScreen extends StatefulWidget {
  const ProductDetailScreen({
    super.key,
    required this.product,
  });

  final Product product;

  @override
  State<ProductDetailScreen> createState() => _ProductDetailScreenState();
}

class _ProductDetailScreenState extends State<ProductDetailScreen> {
  @override
  void initState() {
    super.initState();
    
    // Record screen view event with product details
    TelemetryService.instance.recordEvent('screen_view', attributes: {
      'screen_name': 'product_detail',
      'product_id': widget.product.id,
      'product_name': widget.product.name,
      'product_price': widget.product.priceUsd,
    });

    // Track funnel progression
    FunnelTrackingService.instance.trackStage(
      FunnelStage.productDetailView,
      metadata: {
        'product_id': widget.product.id,
        'product_name': widget.product.name,
        'product_price': widget.product.priceUsd,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.product.name),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Product Image with hero animation
            Hero(
              tag: 'product_image_${widget.product.id}',
              child: Container(
                width: double.infinity,
                height: 320,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: Theme.of(context).shadowColor.withValues(alpha: 0.15),
                      offset: const Offset(0, 8),
                      blurRadius: 24,
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: CachedImage(
                    imageUrl: widget.product.imageUrl,
                    width: double.infinity,
                    height: 320,
                    fit: BoxFit.cover,
                    cacheKey: 'product_detail_${widget.product.id}',
                    errorWidget: Container(
                      width: double.infinity,
                      height: 320,
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primaryContainer,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            _getProductIcon(widget.product.categories),
                            size: 120,
                            color: Theme.of(context).colorScheme.onPrimaryContainer.withValues(alpha: 0.7),
                          ),
                          const SizedBox(height: 24),
                          Text(
                            'Image not available',
                            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                              color: Theme.of(context).colorScheme.onPrimaryContainer,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
            
            const SizedBox(height: 24),
            
            // Product Name
            Text(
              widget.product.name,
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            
            const SizedBox(height: 8),
            
            // Product Price
            Consumer<CurrencyService>(
              builder: (context, currencyService, child) {
                return Text(
                  widget.product.getFormattedPrice(currencyService),
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: Theme.of(context).colorScheme.primary,
                    fontWeight: FontWeight.bold,
                  ),
                );
              },
            ),
            
            const SizedBox(height: 16),
            
            // Categories
            if (widget.product.categories.isNotEmpty) ...[
              Text(
                'Categories',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: widget.product.categories.map((category) {
                  return Chip(
                    label: Text(
                      category.toUpperCase(),
                      style: const TextStyle(fontSize: 12),
                    ),
                    backgroundColor: Theme.of(context).colorScheme.secondaryContainer,
                    labelStyle: TextStyle(
                      color: Theme.of(context).colorScheme.onSecondaryContainer,
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 24),
            ],
            
            // Product Description
            Text(
              'Description',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              widget.product.description.isNotEmpty
                  ? widget.product.description
                  : 'No description available for this product.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            
            const SizedBox(height: 32),
            
            // Action Buttons
            Consumer<CartService>(
              builder: (context, cartService, child) {
                final isInCart = cartService.containsProduct(widget.product.id);
                final quantity = cartService.getItemQuantity(widget.product.id);
                
                return Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: cartService.isLoading 
                          ? null 
                          : () => _onAddToCartPressed(cartService),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Theme.of(context).colorScheme.primary,
                          foregroundColor: Theme.of(context).colorScheme.onPrimary,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                        ),
                        child: cartService.isLoading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Icon(Icons.add_shopping_cart, size: 20),
                                const SizedBox(width: 8),
                                Text(
                                  isInCart ? 'Add More ($quantity in cart)' : 'Add to Cart',
                                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                                ),
                              ],
                            ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    OutlinedButton(
                      onPressed: _onSharePressed,
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
                      ),
                      child: const Icon(Icons.share),
                    ),
                  ],
                );
              },
            ),
            
            const SizedBox(height: 16),
            
            // Product ID (for development/demo purposes)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Product Details',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'ID: ${widget.product.id}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
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

  Future<void> _onAddToCartPressed(CartService cartService) async {
    PerformanceService.instance.startOperation('add_to_cart');
    
    await cartService.addItem(widget.product);
    
    if (!mounted) return;
    
    if (cartService.error != null) {
      PerformanceService.instance.endOperation('add_to_cart', metadata: {
        'success': false,
        'product_id': widget.product.id,
        'error': cartService.error,
      });
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to add to cart: ${cartService.error}'),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    } else {
      final quantity = cartService.getItemQuantity(widget.product.id);
      
      PerformanceService.instance.endOperation('add_to_cart', metadata: {
        'success': true,
        'product_id': widget.product.id,
        'final_quantity': quantity,
      });
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Added ${widget.product.name} to cart! ($quantity total) 🛒'),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
      );
    }
  }

  void _onSharePressed() {
    // Record share event
    TelemetryService.instance.recordEvent('product_share', attributes: {
      'product_id': widget.product.id,
      'product_name': widget.product.name,
      'screen_name': 'product_detail',
    });
    
    // Show share confirmation (in real app, would open share dialog)
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Sharing ${widget.product.name}! 📤'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}