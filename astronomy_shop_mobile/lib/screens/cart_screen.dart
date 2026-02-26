import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/cart_item.dart';
import '../services/cart_service.dart';
import '../services/currency_service.dart';
import '../services/funnel_tracking_service.dart';
import '../services/performance_service.dart';
import '../services/telemetry_service.dart';
import '../widgets/cached_image.dart';
import '../widgets/enhanced_loading.dart';
import 'checkout_screen.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({super.key});

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  @override
  void initState() {
    super.initState();
    
    final cartService = Provider.of<CartService>(context, listen: false);
    
    TelemetryService.instance.recordEvent('screen_view', attributes: {
      'screen_name': 'cart',
      'cart_item_count': cartService.totalItems,
      'cart_total_price': cartService.totalPrice,
      'cart_is_empty': cartService.isEmpty,
    });

    // Track funnel stage
    FunnelTrackingService.instance.trackStage(
      FunnelStage.cartView,
      metadata: {
        'cart_items': cartService.totalItems,
        'cart_value': cartService.totalPrice,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🛒 Your Cart'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
      ),
      body: Consumer<CartService>(
        builder: (context, cartService, child) {
          if (cartService.isLoading) {
            return const Center(
              child: EnhancedLoadingWidget(
                message: 'Updating your cart...',
                size: 48,
              ),
            );
          }

          if (cartService.isEmpty) {
            return _buildEmptyCart(context);
          }

          return Column(
            children: [
              // Cart Items
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.all(16.0),
                  itemCount: cartService.items.length,
                  itemBuilder: (context, index) {
                    final item = cartService.items[index];
                    return CartItemCard(
                      item: item,
                      onQuantityChanged: (newQuantity) {
                        _onQuantityChanged(cartService, item, newQuantity);
                      },
                      onRemove: () {
                        _onRemoveItem(cartService, item);
                      },
                    );
                  },
                ),
              ),
              
              // Cart Summary
              Container(
                padding: const EdgeInsets.all(16.0),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(16),
                    topRight: Radius.circular(16),
                  ),
                ),
                child: Column(
                  children: [
                    // Summary Row
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Total Items: ${cartService.totalItems}',
                              style: Theme.of(context).textTheme.bodyLarge,
                            ),
                            Consumer<CurrencyService>(
                              builder: (context, currencyService, child) {
                                double totalUsd = 0.0;
                                for (final item in cartService.items) {
                                  totalUsd += item.product.priceUsd * item.quantity;
                                }
                                final formattedTotal = currencyService.formatPrice(totalUsd, currency: currencyService.selectedCurrency);
                                return Text(
                                  'Total: $formattedTotal',
                                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                    fontWeight: FontWeight.bold,
                                    color: Theme.of(context).colorScheme.primary,
                                  ),
                                );
                              },
                            ),
                          ],
                        ),
                      ],
                    ),
                    
                    const SizedBox(height: 16),
                    
                    // Action Buttons
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () => _onClearCart(cartService),
                            style: OutlinedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                            ),
                            child: const Text('Clear Cart'),
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          flex: 2,
                          child: ElevatedButton(
                            onPressed: () => _onCheckout(cartService),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Theme.of(context).colorScheme.primary,
                              foregroundColor: Theme.of(context).colorScheme.onPrimary,
                              padding: const EdgeInsets.symmetric(vertical: 12),
                            ),
                            child: const Text(
                              'Proceed to Checkout',
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildEmptyCart(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(32),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.3),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.shopping_cart_outlined,
                size: 80,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 32),
            Text(
              'Your Cart Awaits',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Text(
              'Discover amazing telescopes, space models, and astronomy collectibles. Your journey to the stars starts here!',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                height: 1.5,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 40),
            Column(
              children: [
                ElevatedButton.icon(
                  onPressed: _onContinueShopping,
                  icon: const Icon(Icons.explore),
                  label: const Text('Explore Products'),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                  ),
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: () {
                    TelemetryService.instance.recordEvent('empty_cart_search_tap');
                    Navigator.pushNamed(context, '/search');
                  },
                  icon: const Icon(Icons.search),
                  label: const Text('Search Products'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _onQuantityChanged(CartService cartService, CartItem item, int newQuantity) {
    PerformanceService.instance.startOperation('cart_quantity_update');
    
    TelemetryService.instance.recordEvent('cart_quantity_change', attributes: {
      'product_id': item.productId,
      'product_name': item.product.name,
      'old_quantity': item.quantity,
      'new_quantity': newQuantity,
      'screen_name': 'cart',
    });

    cartService.updateItemQuantity(item.productId, newQuantity);
    
    PerformanceService.instance.endOperation('cart_quantity_update', metadata: {
      'product_id': item.productId,
      'quantity_change': newQuantity - item.quantity,
    });
  }

  void _onRemoveItem(CartService cartService, CartItem item) {
    TelemetryService.instance.recordEvent('cart_remove_item_ui', attributes: {
      'product_id': item.productId,
      'product_name': item.product.name,
      'quantity_removed': item.quantity,
      'item_value': item.totalPrice,
      'screen_name': 'cart',
    });

    cartService.removeItem(item.productId);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${item.product.name} removed from cart'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  void _onClearCart(CartService cartService) {
    final itemCount = cartService.totalItems;
    final totalValue = cartService.totalPrice;

    TelemetryService.instance.recordEvent('cart_clear_initiated', attributes: {
      'items_count': itemCount,
      'total_value': totalValue,
      'screen_name': 'cart',
    });

    showDialog<void>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('Clear Cart'),
          content: Text('Are you sure you want to remove all $itemCount items from your cart?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: () {
                cartService.clearCart();
                Navigator.of(context).pop();
                
                TelemetryService.instance.recordEvent('cart_cleared_confirmed', attributes: {
                  'items_cleared': itemCount,
                  'value_cleared': totalValue,
                  'screen_name': 'cart',
                });

                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Cart cleared successfully'),
                    behavior: SnackBarBehavior.floating,
                  ),
                );
              },
              child: const Text('Clear'),
            ),
          ],
        );
      },
    );
  }

  void _onCheckout(CartService cartService) {
    if (cartService.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Your cart is empty!'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    TelemetryService.instance.recordEvent('checkout_initiated', attributes: {
      'cart_item_count': cartService.totalItems,
      'cart_total_price': cartService.totalPrice,
      'screen_name': 'cart',
    });

    // Track funnel progression to checkout
    FunnelTrackingService.instance.trackStage(
      FunnelStage.checkoutStart,
      metadata: {
        'cart_items': cartService.totalItems,
        'cart_value': cartService.totalPrice,
      },
    );

    // Track conversion from cart to checkout
    FunnelTrackingService.instance.trackConversion(
      FunnelStage.cartView,
      FunnelStage.checkoutStart,
      metadata: {
        'cart_value': cartService.totalPrice,
      },
    );

    Navigator.push<void>(
      context,
      MaterialPageRoute<void>(
        builder: (context) => const CheckoutScreen(),
      ),
    );
  }

  void _onContinueShopping() {
    TelemetryService.instance.recordEvent('continue_shopping', attributes: {
      'screen_name': 'cart',
      'cart_was_empty': true,
    });

    Navigator.of(context).pop();
  }
}

class CartItemCard extends StatelessWidget {
  const CartItemCard({
    super.key,
    required this.item,
    required this.onQuantityChanged,
    required this.onRemove,
  });

  final CartItem item;
  final void Function(int) onQuantityChanged;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 16.0),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Product Image
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(8),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: CachedImage(
                  imageUrl: item.product.imageUrl,
                  width: 80,
                  height: 80,
                  fit: BoxFit.cover,
                  cacheKey: 'cart_${item.product.id}',
                  errorWidget: Icon(
                    _getProductIcon(item.product.categories),
                    size: 40,
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
                ),
              ),
            ),
            
            const SizedBox(width: 16),
            
            // Product Details
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.product.name,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Consumer<CurrencyService>(
                    builder: (context, currencyService, child) {
                      return Text(
                        item.product.getFormattedPrice(currencyService),
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 8),
                  Consumer<CurrencyService>(
                    builder: (context, currencyService, child) {
                      final itemTotalUsd = item.product.priceUsd * item.quantity;
                      final totalPrice = currencyService.formatPrice(itemTotalUsd, currency: currencyService.selectedCurrency);
                      return Text(
                        'Total: $totalPrice',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
            
            const SizedBox(width: 16),
            
            // Quantity Controls
            Column(
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      onPressed: () {
                        if (item.quantity > 1) {
                          onQuantityChanged(item.quantity - 1);
                        }
                      },
                      icon: const Icon(Icons.remove_circle_outline),
                      iconSize: 20,
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      decoration: BoxDecoration(
                        border: Border.all(color: Theme.of(context).colorScheme.outline),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        '${item.quantity}',
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    IconButton(
                      onPressed: () => onQuantityChanged(item.quantity + 1),
                      icon: const Icon(Icons.add_circle_outline),
                      iconSize: 20,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                TextButton.icon(
                  onPressed: onRemove,
                  icon: const Icon(Icons.delete_outline, size: 16),
                  label: const Text('Remove'),
                  style: TextButton.styleFrom(
                    foregroundColor: Theme.of(context).colorScheme.error,
                  ),
                ),
              ],
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
}