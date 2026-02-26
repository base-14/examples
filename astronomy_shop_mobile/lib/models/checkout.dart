import '../services/currency_service.dart';
import 'cart_item.dart';
import 'product.dart';

class Address {
  const Address({
    required this.streetAddress,
    required this.city,
    required this.state,
    required this.country,
    required this.zipCode,
  });

  factory Address.fromJson(Map<String, dynamic> json) => Address(
    streetAddress: (json['street_address'] as String?) ?? '',
    city: (json['city'] as String?) ?? '',
    state: (json['state'] as String?) ?? '',
    country: (json['country'] as String?) ?? '',
    zipCode: (json['zip_code'] as String?) ?? '',
  );

  final String streetAddress;
  final String city;
  final String state;
  final String country;
  final String zipCode;

  Map<String, dynamic> toJson() => {
    'street_address': streetAddress,
    'city': city,
    'state': state,
    'country': country,
    'zip_code': zipCode,
  };
}

class CreditCardInfo {
  const CreditCardInfo({
    required this.creditCardNumber,
    required this.creditCardCvv,
    required this.creditCardExpirationYear,
    required this.creditCardExpirationMonth,
  });

  factory CreditCardInfo.fromJson(Map<String, dynamic> json) => CreditCardInfo(
    creditCardNumber: (json['credit_card_number'] as String?) ?? '',
    creditCardCvv: (json['credit_card_cvv'] as int?) ?? 0,
    creditCardExpirationYear: (json['credit_card_expiration_year'] as int?) ?? 0,
    creditCardExpirationMonth: (json['credit_card_expiration_month'] as int?) ?? 0,
  );

  final String creditCardNumber;
  final int creditCardCvv;
  final int creditCardExpirationYear;
  final int creditCardExpirationMonth;

  Map<String, dynamic> toJson() => {
    'credit_card_number': creditCardNumber,
    'credit_card_cvv': creditCardCvv,
    'credit_card_expiration_year': creditCardExpirationYear,
    'credit_card_expiration_month': creditCardExpirationMonth,
  };
}

class PlaceOrderRequest {
  const PlaceOrderRequest({
    required this.userId,
    required this.userCurrency,
    required this.address,
    required this.email,
    required this.creditCard,
  });

  final String userId;
  final String userCurrency;
  final Address address;
  final String email;
  final CreditCardInfo creditCard;

  Map<String, dynamic> toJson() => {
    'user_id': userId,
    'user_currency': userCurrency,
    'address': address.toJson(),
    'email': email,
    'credit_card': creditCard.toJson(),
  };
}

class PlaceOrderResponse {
  const PlaceOrderResponse({
    required this.order,
  });

  factory PlaceOrderResponse.fromJson(Map<String, dynamic> json) => PlaceOrderResponse(
    order: Order.fromJson((json['order'] as Map<String, dynamic>?) ?? {}),
  );

  final Order order;
}

class Order {
  const Order({
    required this.orderId,
    required this.shippingAddress,
    required this.shippingCost,
    required this.items,
  });

  factory Order.fromJson(Map<String, dynamic> json) => Order(
    orderId: (json['orderId'] as String?) ?? '',
    shippingAddress: Address.fromJson((json['shippingAddress'] as Map<String, dynamic>?) ?? {}),
    shippingCost: Money.fromJson((json['shippingCost'] as Map<String, dynamic>?) ?? {}),
    items: (json['items'] as List? ?? [])
        .map((item) => OrderItem.fromJson(item as Map<String, dynamic>))
        .toList(),
  );

  final String orderId;
  final Address shippingAddress;
  final Money shippingCost;
  final List<OrderItem> items;
}

class OrderItem {
  const OrderItem({
    required this.item,
    required this.cost,
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) {
    final itemJson = (json['item'] as Map<String, dynamic>?) ?? {};
    final productJson = (itemJson['product'] as Map<String, dynamic>?) ?? {};
    final product = Product.fromJson(productJson);

    return OrderItem(
      item: CartItem.fromJson(itemJson, product),
      cost: Money.fromJson((json['cost'] as Map<String, dynamic>?) ?? {}),
    );
  }

  final CartItem item;
  final Money cost;
}
