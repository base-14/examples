import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../models/checkout.dart';
import '../services/cart_service.dart';
import '../services/currency_service.dart';
import '../services/funnel_tracking_service.dart';
import '../services/http_service.dart';
import '../services/telemetry_service.dart';
import 'order_confirmation_screen.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({super.key});

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _streetController = TextEditingController();
  final _cityController = TextEditingController();
  final _stateController = TextEditingController();
  final _countryController = TextEditingController();
  final _zipController = TextEditingController();
  final _cardNumberController = TextEditingController();
  final _cvvController = TextEditingController();
  final _expMonthController = TextEditingController();
  final _expYearController = TextEditingController();

  bool _isProcessing = false;

  @override
  void initState() {
    super.initState();
    
    TelemetryService.instance.recordEvent('screen_view', attributes: {
      'screen_name': 'checkout',
      'session_id': TelemetryService.instance.sessionId,
    });

    _prefillDemoData();
  }

  void _prefillDemoData() {
    _emailController.text = 'flutter@example.com';
    _streetController.text = '1600 Amphitheatre Parkway';
    _cityController.text = 'Mountain View';
    _stateController.text = 'CA';
    _countryController.text = 'United States';
    _zipController.text = '94043';
    _cardNumberController.text = '4111-1111-1111-1111';
    _cvvController.text = '123';
    _expMonthController.text = '12';
    _expYearController.text = '2025';
  }

  @override
  void dispose() {
    _emailController.dispose();
    _streetController.dispose();
    _cityController.dispose();
    _stateController.dispose();
    _countryController.dispose();
    _zipController.dispose();
    _cardNumberController.dispose();
    _cvvController.dispose();
    _expMonthController.dispose();
    _expYearController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🛒 Checkout'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
      ),
      body: Form(
        key: _formKey,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildOrderSummary(),
              const SizedBox(height: 24),
              _buildEmailSection(),
              const SizedBox(height: 24),
              _buildShippingSection(),
              const SizedBox(height: 24),
              _buildPaymentSection(),
              const SizedBox(height: 32),
              _buildPlaceOrderButton(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildOrderSummary() {
    return Consumer2<CartService, CurrencyService>(
      builder: (context, cartService, currencyService, child) {
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Order Summary',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '${cartService.totalItems} items',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Total:',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      currencyService.formatPrice(cartService.totalPrice),
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildEmailSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Contact Information',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _emailController,
          decoration: const InputDecoration(
            labelText: 'Email Address',
            hintText: 'Enter your email',
            prefixIcon: Icon(Icons.email),
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.emailAddress,
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please enter your email';
            }
            if (!RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(value)) {
              return 'Please enter a valid email';
            }
            return null;
          },
        ),
      ],
    );
  }

  Widget _buildShippingSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Shipping Address',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _streetController,
          decoration: const InputDecoration(
            labelText: 'Street Address',
            hintText: 'Enter your address',
            prefixIcon: Icon(Icons.home),
            border: OutlineInputBorder(),
          ),
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please enter your street address';
            }
            return null;
          },
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              flex: 2,
              child: TextFormField(
                controller: _cityController,
                decoration: const InputDecoration(
                  labelText: 'City',
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter city';
                  }
                  return null;
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextFormField(
                controller: _stateController,
                decoration: const InputDecoration(
                  labelText: 'State',
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter state';
                  }
                  return null;
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              flex: 2,
              child: TextFormField(
                controller: _countryController,
                decoration: const InputDecoration(
                  labelText: 'Country',
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter country';
                  }
                  return null;
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextFormField(
                controller: _zipController,
                decoration: const InputDecoration(
                  labelText: 'ZIP Code',
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter ZIP code';
                  }
                  return null;
                },
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildPaymentSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Payment Information',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _cardNumberController,
          decoration: const InputDecoration(
            labelText: 'Card Number',
            hintText: '1234-5678-9012-3456',
            prefixIcon: Icon(Icons.credit_card),
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(16),
          ],
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please enter card number';
            }
            if (value.length < 13) {
              return 'Please enter a valid card number';
            }
            return null;
          },
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextFormField(
                controller: _expMonthController,
                decoration: const InputDecoration(
                  labelText: 'Exp Month',
                  hintText: 'MM',
                  border: OutlineInputBorder(),
                ),
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(2),
                ],
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Required';
                  }
                  final month = int.tryParse(value);
                  if (month == null || month < 1 || month > 12) {
                    return 'Invalid month';
                  }
                  return null;
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextFormField(
                controller: _expYearController,
                decoration: const InputDecoration(
                  labelText: 'Exp Year',
                  hintText: 'YYYY',
                  border: OutlineInputBorder(),
                ),
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(4),
                ],
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Required';
                  }
                  final year = int.tryParse(value);
                  if (year == null || year < DateTime.now().year) {
                    return 'Invalid year';
                  }
                  return null;
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextFormField(
                controller: _cvvController,
                decoration: const InputDecoration(
                  labelText: 'CVV',
                  hintText: '123',
                  border: OutlineInputBorder(),
                ),
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(4),
                ],
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Required';
                  }
                  if (value.length < 3) {
                    return 'Invalid CVV';
                  }
                  return null;
                },
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildPlaceOrderButton() {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton(
        onPressed: _isProcessing ? null : _onPlaceOrder,
        style: ElevatedButton.styleFrom(
          backgroundColor: Theme.of(context).colorScheme.primary,
          foregroundColor: Theme.of(context).colorScheme.onPrimary,
        ),
        child: _isProcessing
            ? const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  SizedBox(width: 12),
                  Text('Processing Order...'),
                ],
              )
            : const Text(
                'Place Order',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
      ),
    );
  }

  void _onPlaceOrder() async {
    if (!_formKey.currentState!.validate()) {
      TelemetryService.instance.recordEvent('checkout_validation_failed');

      // Track drop-off due to validation failure
      FunnelTrackingService.instance.trackDropOff(
        reason: 'validation_failed',
        metadata: {'stage': 'checkout_form'},
      );
      return;
    }

    // Track that info was entered successfully
    FunnelTrackingService.instance.trackStage(
      FunnelStage.checkoutInfoEntered,
      metadata: {'form_validated': true},
    );

    setState(() {
      _isProcessing = true;
    });

    try {
      final cartService = Provider.of<CartService>(context, listen: false);
      final currencyService = Provider.of<CurrencyService>(context, listen: false);

      TelemetryService.instance.recordEvent('checkout_place_order_started', attributes: {
        'cart_item_count': cartService.totalItems,
        'cart_total_price': cartService.totalPrice,
        'currency': currencyService.selectedCurrency.code,
        'session_id': TelemetryService.instance.sessionId,
      });

      final address = Address(
        streetAddress: _streetController.text,
        city: _cityController.text,
        state: _stateController.text,
        country: _countryController.text,
        zipCode: _zipController.text,
      );

      final creditCard = CreditCardInfo(
        creditCardNumber: _cardNumberController.text.replaceAll('-', ''),
        creditCardCvv: int.parse(_cvvController.text),
        creditCardExpirationYear: int.parse(_expYearController.text),
        creditCardExpirationMonth: int.parse(_expMonthController.text),
      );

      final request = PlaceOrderRequest(
        userId: TelemetryService.instance.sessionId,
        userCurrency: currencyService.selectedCurrency.code,
        address: address,
        email: _emailController.text,
        creditCard: creditCard,
      );

      final response = await HttpService.instance.post<Map<String, dynamic>>(
        '/checkout',
        body: request.toJson(),
        fromJson: (json) => json,
      );

      if (response.isSuccess && response.data != null) {
        final orderResponse = PlaceOrderResponse.fromJson(response.data!);
        
        TelemetryService.instance.recordEvent('checkout_place_order_success', attributes: {
          'order_id': orderResponse.order.orderId,
          'total_amount': cartService.totalPrice,
          'currency': currencyService.selectedCurrency.code,
          'items_count': cartService.totalItems,
        });

        // Track funnel completion stages
        FunnelTrackingService.instance.trackStage(
          FunnelStage.orderPlaced,
          metadata: {
            'order_id': orderResponse.order.orderId,
            'order_value': cartService.totalPrice,
            'items_count': cartService.totalItems,
          },
        );

        // Track conversion from checkout to order
        FunnelTrackingService.instance.trackConversion(
          FunnelStage.checkoutStart,
          FunnelStage.orderPlaced,
          metadata: {
            'order_value': cartService.totalPrice,
          },
        );

        if (mounted) {
          Navigator.pushReplacement<void, void>(
            context,
            MaterialPageRoute<void>(
              builder: (context) => OrderConfirmationScreen(order: orderResponse.order),
            ),
          );
        }

        cartService.clearCart();

      } else {
        TelemetryService.instance.recordEvent('checkout_place_order_failed', attributes: {
          'error_message': response.errorMessage ?? 'Unknown error',
          'status_code': response.statusCode,
        });

        // Track drop-off due to order failure
        FunnelTrackingService.instance.trackDropOff(
          reason: 'order_failed',
          metadata: {
            'error': response.errorMessage ?? 'Unknown error',
            'status_code': response.statusCode,
          },
        );

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Order failed: ${response.errorMessage ?? "Please try again"}'),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      }

    } catch (e) {
      TelemetryService.instance.recordEvent('checkout_place_order_exception', attributes: {
        'error_message': e.toString(),
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Order failed: $e'),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isProcessing = false;
        });
      }
    }
  }
}