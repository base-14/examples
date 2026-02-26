import 'package:flutter/material.dart';

class EnhancedLoadingWidget extends StatefulWidget {
  const EnhancedLoadingWidget({
    super.key,
    this.message,
    this.size = 48.0,
    this.color,
  });

  final String? message;
  final double size;
  final Color? color;

  @override
  State<EnhancedLoadingWidget> createState() => _EnhancedLoadingWidgetState();
}

class _EnhancedLoadingWidgetState extends State<EnhancedLoadingWidget>
    with TickerProviderStateMixin {
  late AnimationController _controller;
  late AnimationController _pulseController;
  late Animation<double> _fadeAnimation;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    )..repeat();
    
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.0, 0.5),
    ));

    _pulseAnimation = Tween<double>(
      begin: 0.8,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _pulseController,
      curve: Curves.easeInOut,
    ));
  }

  @override
  void dispose() {
    _controller.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: Listenable.merge([_controller, _pulseController]),
          builder: (context, child) {
            return Transform.scale(
              scale: _pulseAnimation.value,
              child: Container(
                width: widget.size + 16,
                height: widget.size + 16,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: (widget.color ?? Theme.of(context).colorScheme.primary)
                      .withValues(alpha: 0.1),
                ),
                child: Center(
                  child: SizedBox(
                    width: widget.size,
                    height: widget.size,
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(
                        widget.color ?? Theme.of(context).colorScheme.primary,
                      ),
                      strokeWidth: 3.0,
                      strokeCap: StrokeCap.round,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
        if (widget.message != null) ...[
          const SizedBox(height: 16),
          FadeTransition(
            opacity: _fadeAnimation,
            child: Text(
              widget.message!,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.w500,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ],
    );
  }
}

class ShimmerLoadingCard extends StatefulWidget {
  const ShimmerLoadingCard({
    super.key,
    this.height = 120,
    this.width = double.infinity,
    this.borderRadius,
  });

  final double height;
  final double width;
  final BorderRadius? borderRadius;

  @override
  State<ShimmerLoadingCard> createState() => _ShimmerLoadingCardState();
}

class _ShimmerLoadingCardState extends State<ShimmerLoadingCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _shimmerController;
  late Animation<double> _shimmerAnimation;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat();

    _shimmerAnimation = Tween<double>(
      begin: -2.0,
      end: 2.0,
    ).animate(CurvedAnimation(
      parent: _shimmerController,
      curve: Curves.easeInOut,
    ));
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final shimmerColors = isDark
        ? [
            Colors.grey[800]!,
            Colors.grey[700]!,
            Colors.grey[600]!,
            Colors.grey[700]!,
            Colors.grey[800]!,
          ]
        : [
            Colors.grey[300]!,
            Colors.grey[200]!,
            Colors.grey[100]!,
            Colors.grey[200]!,
            Colors.grey[300]!,
          ];

    return AnimatedBuilder(
      animation: _shimmerAnimation,
      builder: (context, child) {
        return Container(
          height: widget.height,
          width: widget.width,
          decoration: BoxDecoration(
            borderRadius: widget.borderRadius ?? BorderRadius.circular(12),
            gradient: LinearGradient(
              begin: Alignment(_shimmerAnimation.value - 1, 0),
              end: Alignment(_shimmerAnimation.value + 1, 0),
              colors: shimmerColors,
              stops: const [0.0, 0.2, 0.5, 0.8, 1.0],
            ),
          ),
        );
      },
    );
  }
}

class ProductCardShimmer extends StatelessWidget {
  const ProductCardShimmer({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 16.0),
      child: Container(
        padding: const EdgeInsets.all(20.0),
        child: Row(
          children: [
            const ShimmerLoadingCard(
              height: 90,
              width: 90,
              borderRadius: BorderRadius.all(Radius.circular(12)),
            ),
            const SizedBox(width: 20),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const ShimmerLoadingCard(height: 20, width: double.infinity),
                  const SizedBox(height: 8),
                  ShimmerLoadingCard(
                    height: 16,
                    width: MediaQuery.of(context).size.width * 0.3,
                  ),
                  const SizedBox(height: 12),
                  const ShimmerLoadingCard(height: 14, width: double.infinity),
                  const SizedBox(height: 4),
                  ShimmerLoadingCard(
                    height: 14,
                    width: MediaQuery.of(context).size.width * 0.7,
                  ),
                  const SizedBox(height: 12),
                  ShimmerLoadingCard(
                    height: 24,
                    width: MediaQuery.of(context).size.width * 0.25,
                    borderRadius: const BorderRadius.all(Radius.circular(20)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}