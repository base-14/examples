import 'product.dart';

class CartItem {
  const CartItem({
    required this.productId,
    required this.product,
    required this.quantity,
  });

  factory CartItem.fromJson(Map<String, dynamic> json, Product product) {
    return CartItem(
      productId: json['productId']?.toString() ?? '',
      product: product,
      quantity: (json['quantity'] as num?)?.toInt() ?? 1,
    );
  }

  final String productId;
  final Product product;
  final int quantity;

  CartItem copyWith({
    int? quantity,
  }) {
    return CartItem(
      productId: productId,
      product: product,
      quantity: quantity ?? this.quantity,
    );
  }

  double get totalPrice => product.priceUsd * quantity;

  String get formattedTotalPrice => '\$${totalPrice.toStringAsFixed(2)}';

  Map<String, dynamic> toJson() {
    return {
      'productId': productId,
      'quantity': quantity,
    };
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is CartItem &&
        other.productId == productId &&
        other.quantity == quantity;
  }

  @override
  int get hashCode => Object.hash(productId, quantity);

  @override
  String toString() {
    return 'CartItem(productId: $productId, quantity: $quantity, totalPrice: $formattedTotalPrice)';
  }
}