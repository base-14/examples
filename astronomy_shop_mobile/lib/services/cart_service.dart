import 'package:flutter/foundation.dart';
import '../models/cart_item.dart';
import '../models/product.dart';
import 'telemetry_service.dart';
import 'http_service.dart';
import 'funnel_tracking_service.dart';

class CartService extends ChangeNotifier {
  static CartService? _instance;
  static CartService get instance => _instance ??= CartService._();
  
  CartService._();

  final Map<String, CartItem> _items = {};
  final HttpService _httpService = HttpService.instance;
  
  bool _isLoading = false;
  String? _error;
  String? _userId;

  List<CartItem> get items => _items.values.toList();
  bool get isLoading => _isLoading;
  String? get error => _error;
  int get totalItems => _items.values.fold(0, (sum, item) => sum + item.quantity);
  double get totalPrice => _items.values.fold(0.0, (sum, item) => sum + item.totalPrice);
  String get formattedTotalPrice => '\$${totalPrice.toStringAsFixed(2)}';
  bool get isEmpty => _items.isEmpty;
  bool get isNotEmpty => _items.isNotEmpty;

  void initialize({String? userId}) {
    _userId = userId ?? 'anonymous-user';
    
    TelemetryService.instance.recordEvent('cart_initialize', attributes: {
      'user_id': _userId!,
      'session_id': TelemetryService.instance.sessionId,
    });
  }

  Future<void> addItem(Product product, {int quantity = 1}) async {
    _error = null;
    _isLoading = true;
    notifyListeners();

    try {
      TelemetryService.instance.recordEvent('cart_add_item', attributes: {
        'product_id': product.id,
        'product_name': product.name,
        'product_price': product.priceUsd,
        'quantity': quantity,
        'user_id': _userId ?? 'anonymous',
      });

      // Track funnel progression
      FunnelTrackingService.instance.trackStage(
        FunnelStage.addToCart,
        metadata: {
          'product_id': product.id,
          'product_name': product.name,
          'quantity': quantity,
          'cart_value': totalPrice + (product.priceUsd * quantity),
        },
      );

      // Track conversion from product view to add to cart
      FunnelTrackingService.instance.trackConversion(
        FunnelStage.productDetailView,
        FunnelStage.addToCart,
        metadata: {
          'product_id': product.id,
          'product_name': product.name,
        },
      );

      if (_items.containsKey(product.id)) {
        final existingItem = _items[product.id]!;
        _items[product.id] = existingItem.copyWith(
          quantity: existingItem.quantity + quantity,
        );
      } else {
        _items[product.id] = CartItem(
          productId: product.id,
          product: product,
          quantity: quantity,
        );
      }

      await _syncWithBackend();
      
    } catch (e) {
      _error = 'Failed to add item to cart: $e';
      
      TelemetryService.instance.recordEvent('cart_add_item_error', attributes: {
        'product_id': product.id,
        'error_message': e.toString(),
        'user_id': _userId ?? 'anonymous',
      });
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateItemQuantity(String productId, int newQuantity) async {
    if (!_items.containsKey(productId)) return;
    
    _error = null;
    _isLoading = true;
    notifyListeners();

    try {
      if (newQuantity <= 0) {
        await removeItem(productId);
        return;
      }

      final oldQuantity = _items[productId]!.quantity;
      _items[productId] = _items[productId]!.copyWith(quantity: newQuantity);

      TelemetryService.instance.recordEvent('cart_update_quantity', attributes: {
        'product_id': productId,
        'old_quantity': oldQuantity,
        'new_quantity': newQuantity,
        'user_id': _userId ?? 'anonymous',
      });

      await _syncWithBackend();
      
    } catch (e) {
      _error = 'Failed to update cart: $e';
      
      TelemetryService.instance.recordEvent('cart_update_error', attributes: {
        'product_id': productId,
        'error_message': e.toString(),
        'user_id': _userId ?? 'anonymous',
      });
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> removeItem(String productId) async {
    if (!_items.containsKey(productId)) return;
    
    _error = null;
    _isLoading = true;
    notifyListeners();

    try {
      final removedItem = _items.remove(productId);
      
      TelemetryService.instance.recordEvent('cart_remove_item', attributes: {
        'product_id': productId,
        'quantity_removed': removedItem?.quantity ?? 0,
        'user_id': _userId ?? 'anonymous',
      });

      await _syncWithBackend();
      
    } catch (e) {
      _error = 'Failed to remove item from cart: $e';
      
      TelemetryService.instance.recordEvent('cart_remove_error', attributes: {
        'product_id': productId,
        'error_message': e.toString(),
        'user_id': _userId ?? 'anonymous',
      });
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> clearCart() async {
    _error = null;
    _isLoading = true;
    notifyListeners();

    try {
      final itemCount = totalItems;
      _items.clear();
      
      TelemetryService.instance.recordEvent('cart_clear', attributes: {
        'items_cleared': itemCount,
        'user_id': _userId ?? 'anonymous',
      });

      await _syncWithBackend();
      
    } catch (e) {
      _error = 'Failed to clear cart: $e';
      
      TelemetryService.instance.recordEvent('cart_clear_error', attributes: {
        'error_message': e.toString(),
        'user_id': _userId ?? 'anonymous',
      });
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _syncWithBackend() async {
    if (_userId == null) return;

    try {
      // Note: OpenTelemetry Demo cart API only supports adding one item at a time
      // For now, we'll sync the most recently added item or skip if empty
      if (_items.isEmpty) return;
      
      // Get the most recently modified item (simple approach for demo)
      final lastItem = _items.values.last;
      
      final cartData = {
        'userId': _userId,
        'item': {
          'productId': lastItem.productId,
          'quantity': lastItem.quantity,
        },
      };

      final response = await _httpService.post(
        '/cart',
        body: cartData,
        headers: {
          'Content-Type': 'application/json',
        },
      );

      TelemetryService.instance.recordEvent('cart_sync_success', attributes: {
        'user_id': _userId!,
        'item_count': _items.length,
        'total_quantity': totalItems,
        'total_price': totalPrice,
        'response_status': response.statusCode,
        'synced_product_id': lastItem.productId,
        'synced_quantity': lastItem.quantity,
      });
      
    } catch (e) {
      TelemetryService.instance.recordEvent('cart_sync_error', attributes: {
        'user_id': _userId ?? 'anonymous',
        'error_message': e.toString(),
        'item_count': _items.length,
      });
    }
  }

  CartItem? getItem(String productId) {
    return _items[productId];
  }

  bool containsProduct(String productId) {
    return _items.containsKey(productId);
  }

  int getItemQuantity(String productId) {
    return _items[productId]?.quantity ?? 0;
  }

  @override
  void dispose() {
    _items.clear();
    super.dispose();
  }
}