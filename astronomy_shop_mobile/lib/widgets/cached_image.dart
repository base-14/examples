import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../services/image_cache_service.dart';
import '../services/performance_service.dart';

class CachedImage extends StatefulWidget {
  const CachedImage({
    super.key,
    required this.imageUrl,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.errorWidget,
    this.placeholder,
    this.cacheKey,
    this.batteryAware = true,
  });

  final String imageUrl;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Widget? errorWidget;
  final Widget? placeholder;
  final String? cacheKey;
  final bool batteryAware;

  @override
  State<CachedImage> createState() => _CachedImageState();
}

class _CachedImageState extends State<CachedImage> {
  late String _operationId;
  bool _operationEnded = false;
  Uint8List? _imageData;
  bool _isLoading = true;
  String? _error;
  
  @override
  void initState() {
    super.initState();
    _operationId = 'image_load_${widget.cacheKey ?? widget.imageUrl.hashCode}';
    PerformanceService.instance.startOperation(_operationId);
    _loadImage();
  }

  void _endOperation(Map<String, dynamic> metadata) {
    if (!_operationEnded) {
      _operationEnded = true;
      PerformanceService.instance.endOperation(_operationId, metadata: metadata);
    }
  }
  
  Future<void> _loadImage() async {
    try {
      final imageData = await ImageCacheService.instance.getImage(
        widget.imageUrl,
        batteryAware: widget.batteryAware,
      );
      
      if (mounted) {
        setState(() {
          _imageData = imageData;
          _isLoading = false;
          _error = imageData == null ? 'Failed to load image' : null;
        });
        
        _endOperation({
          'success': imageData != null,
          'image_url': widget.imageUrl,
          'cache_key': widget.cacheKey,
          'size_bytes': imageData?.length ?? 0,
          'battery_aware': widget.batteryAware,
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = e.toString();
        });
        
        _endOperation({
          'success': false,
          'image_url': widget.imageUrl,
          'error': e.toString(),
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return widget.placeholder ?? Container(
        width: widget.width,
        height: widget.height,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primaryContainer,
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Center(
          child: CircularProgressIndicator(),
        ),
      );
    }
    
    if (_error != null || _imageData == null) {
      return widget.errorWidget ?? Container(
        width: widget.width,
        height: widget.height,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primaryContainer,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(
          Icons.broken_image,
          size: (widget.width != null && widget.height != null) 
              ? (widget.width! + widget.height!) / 4 
              : 40,
          color: Theme.of(context).colorScheme.onPrimaryContainer,
        ),
      );
    }
    
    return AnimatedOpacity(
      opacity: _imageData != null ? 1 : 0,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
      child: Image.memory(
        _imageData!,
        width: widget.width,
        height: widget.height,
        fit: widget.fit,
      ),
    );
  }
}