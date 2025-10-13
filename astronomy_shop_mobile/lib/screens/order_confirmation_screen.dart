import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/checkout.dart';
import '../services/telemetry_service.dart';
import '../services/currency_service.dart';
import '../services/funnel_tracking_service.dart';
import '../widgets/cached_image.dart';

class OrderConfirmationScreen extends StatefulWidget {
  final Order order;

  const OrderConfirmationScreen({
    super.key,
    required this.order,
  });

  @override
  State<OrderConfirmationScreen> createState() => _OrderConfirmationScreenState();
}

class _OrderConfirmationScreenState extends State<OrderConfirmationScreen> {
  @override
  void initState() {
    super.initState();
    
    TelemetryService.instance.recordEvent('screen_view', attributes: {
      'screen_name': 'order_confirmation',
      'order_id': widget.order.orderId,
      'order_items_count': widget.order.items.length,
      'session_id': TelemetryService.instance.sessionId,
    });

    // Track funnel completion!
    FunnelTrackingService.instance.trackStage(
      FunnelStage.orderConfirmed,
      metadata: {
        'order_id': widget.order.orderId,
        'items_count': widget.order.items.length,
      },
    );

    // Track final conversion
    FunnelTrackingService.instance.trackConversion(
      FunnelStage.orderPlaced,
      FunnelStage.orderConfirmed,
      metadata: {
        'order_id': widget.order.orderId,
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) {
          _navigateToHome();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('🎉 Order Confirmed'),
          backgroundColor: Theme.of(context).colorScheme.primaryContainer,
          foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
          automaticallyImplyLeading: false,
          actions: [
            IconButton(
              icon: const Icon(Icons.close),
              onPressed: _navigateToHome,
            ),
          ],
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildSuccessMessage(),
              const SizedBox(height: 24),
              _buildOrderDetails(),
              const SizedBox(height: 24),
              _buildOrderItems(),
              const SizedBox(height: 24),
              _buildShippingInfo(),
              const SizedBox(height: 32),
              _buildActionButtons(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSuccessMessage() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Icon(
            Icons.check_circle,
            size: 64,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(height: 16),
          Text(
            'Order Placed Successfully!',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: Theme.of(context).colorScheme.onPrimaryContainer,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            'Thank you for shopping with us. Your order is being processed.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onPrimaryContainer,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildOrderDetails() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Order Details',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            _buildDetailRow('Order ID', widget.order.orderId),
            const SizedBox(height: 8),
            _buildDetailRow('Items', '${widget.order.items.length}'),
            const SizedBox(height: 8),
            Consumer<CurrencyService>(
              builder: (context, currencyService, child) {
                return _buildDetailRow(
                  'Shipping Cost',
                  widget.order.shippingCost.formattedAmount,
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        Text(
          value,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildOrderItems() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Order Items',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: widget.order.items.length,
              separatorBuilder: (context, index) => const Divider(),
              itemBuilder: (context, index) {
                final orderItem = widget.order.items[index];
                return _buildOrderItem(orderItem);
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOrderItem(OrderItem orderItem) {
    return Row(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: CachedImage(
            imageUrl: orderItem.item.product.imageUrl,
            width: 60,
            height: 60,
            fit: BoxFit.cover,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                orderItem.item.product.name,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                'Qty: ${orderItem.item.quantity}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
        Text(
          orderItem.cost.formattedAmount,
          style: Theme.of(context).textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
      ],
    );
  }

  Widget _buildShippingInfo() {
    final address = widget.order.shippingAddress;
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.local_shipping,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Text(
                  'Shipping Address',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              address.streetAddress,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            Text(
              '${address.city}, ${address.state} ${address.zipCode}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            Text(
              address.country,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionButtons() {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          height: 48,
          child: ElevatedButton.icon(
            onPressed: _navigateToHome,
            icon: const Icon(Icons.shopping_bag),
            label: const Text('Continue Shopping'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.primary,
              foregroundColor: Theme.of(context).colorScheme.onPrimary,
            ),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: OutlinedButton.icon(
            onPressed: _shareOrder,
            icon: const Icon(Icons.share),
            label: const Text('Share Order'),
          ),
        ),
      ],
    );
  }

  void _navigateToHome() {
    TelemetryService.instance.recordEvent('order_confirmation_continue_shopping', attributes: {
      'order_id': widget.order.orderId,
    });

    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  void _shareOrder() {
    TelemetryService.instance.recordEvent('order_confirmation_share', attributes: {
      'order_id': widget.order.orderId,
      'order_items_count': widget.order.items.length,
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Order details copied! 📋'),
        duration: Duration(seconds: 2),
      ),
    );
  }
}