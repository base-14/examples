import '../services/currency_service.dart';
import 'cart_item.dart';
import 'product.dart';

class Address {
  final String streetAddress;
  final String city;
  final String state;
  final String country;
  final String zipCode;

  const Address({
    required this.streetAddress,
    required this.city,
    required this.state,
    required this.country,
    required this.zipCode,
  });

  Map<String, dynamic> toJson() => {
    'street_address': streetAddress,
    'city': city,
    'state': state,
    'country': country,
    'zip_code': zipCode,
  };

  factory Address.fromJson(Map<String, dynamic> json) => Address(
    streetAddress: json['street_address'] ?? '',
    city: json['city'] ?? '',
    state: json['state'] ?? '',
    country: json['country'] ?? '',
    zipCode: json['zip_code'] ?? '',
  );
}

class CreditCardInfo {
  final String creditCardNumber;
  final int creditCardCvv;
  final int creditCardExpirationYear;
  final int creditCardExpirationMonth;

  const CreditCardInfo({
    required this.creditCardNumber,
    required this.creditCardCvv,
    required this.creditCardExpirationYear,
    required this.creditCardExpirationMonth,
  });

  Map<String, dynamic> toJson() => {
    'credit_card_number': creditCardNumber,
    'credit_card_cvv': creditCardCvv,
    'credit_card_expiration_year': creditCardExpirationYear,
    'credit_card_expiration_month': creditCardExpirationMonth,
  };

  factory CreditCardInfo.fromJson(Map<String, dynamic> json) => CreditCardInfo(
    creditCardNumber: json['credit_card_number'] ?? '',
    creditCardCvv: json['credit_card_cvv'] ?? 0,
    creditCardExpirationYear: json['credit_card_expiration_year'] ?? 0,
    creditCardExpirationMonth: json['credit_card_expiration_month'] ?? 0,
  );
}

class PlaceOrderRequest {
  final String userId;
  final String userCurrency;
  final Address address;
  final String email;
  final CreditCardInfo creditCard;

  const PlaceOrderRequest({
    required this.userId,
    required this.userCurrency,
    required this.address,
    required this.email,
    required this.creditCard,
  });

  Map<String, dynamic> toJson() => {
    'user_id': userId,
    'user_currency': userCurrency,
    'address': address.toJson(),
    'email': email,
    'credit_card': creditCard.toJson(),
  };
}

class PlaceOrderResponse {
  final Order order;

  const PlaceOrderResponse({
    required this.order,
  });

  factory PlaceOrderResponse.fromJson(Map<String, dynamic> json) => PlaceOrderResponse(
    order: Order.fromJson(json['order'] ?? {}),
  );
}

class Order {
  final String orderId;
  final Address shippingAddress;
  final Money shippingCost;
  final List<OrderItem> items;

  const Order({
    required this.orderId,
    required this.shippingAddress,
    required this.shippingCost,
    required this.items,
  });

  factory Order.fromJson(Map<String, dynamic> json) => Order(
    orderId: json['orderId'] ?? '',
    shippingAddress: Address.fromJson(json['shippingAddress'] ?? {}),
    shippingCost: Money.fromJson(json['shippingCost'] ?? {}),
    items: (json['items'] as List? ?? [])
        .map((item) => OrderItem.fromJson(item))
        .toList(),
  );
}

class OrderItem {
  final CartItem item;
  final Money cost;

  const OrderItem({
    required this.item,
    required this.cost,
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) {
    final itemJson = json['item'] ?? {};
    final productJson = itemJson['product'] ?? {};
    final product = Product.fromJson(productJson);
    
    return OrderItem(
      item: CartItem.fromJson(itemJson, product),
      cost: Money.fromJson(json['cost'] ?? {}),
    );
  }
}