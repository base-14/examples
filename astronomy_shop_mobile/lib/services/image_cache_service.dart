import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'telemetry_service.dart';

class ImageCacheService {
  ImageCacheService._internal();

  static ImageCacheService? _instance;

  final Map<String, Uint8List> _memoryCache = {};
  final Map<String, DateTime> _cacheTimestamps = {};

  static const int _maxMemoryCacheSize = 50 * 1024 * 1024; // 50MB
  static const int _maxMemoryCacheItems = 100;
  static const Duration _cacheExpiration = Duration(hours: 24);

  int _currentMemoryUsage = 0;
  Directory? _cacheDirectory;
  
  static ImageCacheService get instance {
    _instance ??= ImageCacheService._internal();
    return _instance!;
  }
  
  Future<void> initialize() async {
    try {
      if (!kIsWeb) {
        final tempDir = await getTemporaryDirectory();
        _cacheDirectory = Directory('${tempDir.path}/image_cache');
        
        if (!_cacheDirectory!.existsSync()) {
          _cacheDirectory!.createSync(recursive: true);
        }
      }
    } catch (e) {
      // Ignore initialization errors
    }
  }
  
  String _generateCacheKey(String url) {
    final bytes = utf8.encode(url);
    final digest = md5.convert(bytes);
    return digest.toString();
  }
  
  Future<Uint8List?> getImage(String url, {bool batteryAware = true}) async {
    final cacheKey = _generateCacheKey(url);
    final telemetry = TelemetryService.instance;
    final batteryInfo = telemetry.getBatteryInfo();
    
    final batteryLevel = batteryInfo['battery_level'] as double;
    if (batteryAware && batteryLevel < 0.15) {
      telemetry.recordEvent('image_cache_battery_skip', attributes: {
        'url': url,
        'battery_level': batteryLevel,
      });
      return null;
    }
    
    try {
      final cached = _getFromMemoryCache(cacheKey);
      if (cached != null) {
        telemetry.recordEvent('image_cache_hit', attributes: {
          'cache_type': 'memory',
          'url': url,
          'size_bytes': cached.length,
        });
        return cached;
      }
      
      if (!kIsWeb && _cacheDirectory != null) {
        final diskCached = await _getFromDiskCache(cacheKey);
        if (diskCached != null) {
          _addToMemoryCache(cacheKey, diskCached);
          telemetry.recordEvent('image_cache_hit', attributes: {
            'cache_type': 'disk',
            'url': url,
            'size_bytes': diskCached.length,
          });
          return diskCached;
        }
      }
      
      final downloadedImage = await _downloadImage(url);
      if (downloadedImage != null) {
        _addToMemoryCache(cacheKey, downloadedImage);
        if (!kIsWeb && _cacheDirectory != null) {
          _saveToDiskCache(cacheKey, downloadedImage);
        }
        
        telemetry.recordEvent('image_cache_download', attributes: {
          'url': url,
          'size_bytes': downloadedImage.length,
          'battery_level': batteryLevel,
        });
      }
      
      return downloadedImage;
      
    } catch (e) {
      telemetry.recordEvent('image_cache_error', attributes: {
        'url': url,
        'error': e.toString(),
      });
      return null;
    }
  }
  
  Uint8List? _getFromMemoryCache(String cacheKey) {
    final cached = _memoryCache[cacheKey];
    final timestamp = _cacheTimestamps[cacheKey];
    
    if (cached != null && timestamp != null) {
      if (DateTime.now().difference(timestamp) < _cacheExpiration) {
        _cacheTimestamps[cacheKey] = DateTime.now();
        return cached;
      } else {
        _removeFromMemoryCache(cacheKey);
      }
    }
    
    return null;
  }
  
  void _addToMemoryCache(String cacheKey, Uint8List data) {
    while ((_currentMemoryUsage + data.length > _maxMemoryCacheSize) ||
           (_memoryCache.length >= _maxMemoryCacheItems)) {
      _evictOldestItem();
    }
    
    _memoryCache[cacheKey] = data;
    _cacheTimestamps[cacheKey] = DateTime.now();
    _currentMemoryUsage += data.length;
  }
  
  void _removeFromMemoryCache(String cacheKey) {
    final data = _memoryCache.remove(cacheKey);
    _cacheTimestamps.remove(cacheKey);
    if (data != null) {
      _currentMemoryUsage -= data.length;
    }
  }
  
  void _evictOldestItem() {
    if (_cacheTimestamps.isEmpty) return;
    
    String? oldestKey;
    DateTime? oldestTime;
    
    for (final entry in _cacheTimestamps.entries) {
      if (oldestTime == null || entry.value.isBefore(oldestTime)) {
        oldestTime = entry.value;
        oldestKey = entry.key;
      }
    }
    
    if (oldestKey != null) {
      _removeFromMemoryCache(oldestKey);
    }
  }
  
  Future<Uint8List?> _getFromDiskCache(String cacheKey) async {
    try {
      final file = File('${_cacheDirectory!.path}/$cacheKey');
      if (file.existsSync()) {
        final stat = file.statSync();
        if (DateTime.now().difference(stat.modified) < _cacheExpiration) {
          return file.readAsBytesSync();
        } else {
          file.deleteSync();
        }
      }
    } catch (e) {
      // Ignore initialization errors
    }
    return null;
  }
  
  Future<void> _saveToDiskCache(String cacheKey, Uint8List data) async {
    try {
      final file = File('${_cacheDirectory!.path}/$cacheKey');
      await file.writeAsBytes(data);
    } catch (e) {
      // Ignore initialization errors
    }
  }
  
  Future<Uint8List?> _downloadImage(String url) async {
    try {
      final batteryInfo = TelemetryService.instance.getBatteryInfo();
      
      if ((batteryInfo['battery_level'] as double) < 0.10) {
        return null;
      }
      
      final client = http.Client();
      try {
        final response = await client.get(
          Uri.parse(url),
          headers: {'User-Agent': 'AstronomyShop/1.0'},
        ).timeout(const Duration(seconds: 10));
        
        if (response.statusCode == 200) {
          return response.bodyBytes;
        }
      } finally {
        client.close();
      }
    } catch (e) {
      // Ignore initialization errors
    }
    return null;
  }
  
  void clearMemoryCache() {
    _memoryCache.clear();
    _cacheTimestamps.clear();
    _currentMemoryUsage = 0;
    
    TelemetryService.instance.recordEvent('image_cache_cleared', attributes: {
      'cache_type': 'memory',
    });
  }
  
  Future<void> clearDiskCache() async {
    try {
      if (!kIsWeb && _cacheDirectory != null && _cacheDirectory!.existsSync()) {
        await _cacheDirectory!.delete(recursive: true);
        _cacheDirectory!.createSync(recursive: true);
        
        TelemetryService.instance.recordEvent('image_cache_cleared', attributes: {
          'cache_type': 'disk',
        });
      }
    } catch (e) {
      // Ignore initialization errors
    }
  }
  
  Map<String, dynamic> getCacheInfo() {
    return {
      'memory_cache_items': _memoryCache.length,
      'memory_usage_bytes': _currentMemoryUsage,
      'memory_usage_mb': (_currentMemoryUsage / (1024 * 1024)).toStringAsFixed(2),
      'max_memory_cache_mb': (_maxMemoryCacheSize / (1024 * 1024)).toStringAsFixed(2),
      'cache_directory': _cacheDirectory?.path,
    };
  }
}