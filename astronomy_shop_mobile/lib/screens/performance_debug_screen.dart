import 'package:flutter/material.dart';

import '../services/image_cache_service.dart';
import '../services/performance_service.dart';
import '../services/telemetry_service.dart';
import '../widgets/cached_image.dart';

class PerformanceDebugScreen extends StatefulWidget {
  const PerformanceDebugScreen({super.key});

  @override
  State<PerformanceDebugScreen> createState() => _PerformanceDebugScreenState();
}

class _PerformanceDebugScreenState extends State<PerformanceDebugScreen> {
  final TelemetryService _telemetryService = TelemetryService.instance;
  final ImageCacheService _imageCacheService = ImageCacheService.instance;
  final PerformanceService _performanceService = PerformanceService.instance;

  @override
  void initState() {
    super.initState();
    _telemetryService.recordEvent('performance_debug_screen_opened');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🔧 Performance Debug'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildBatterySection(),
            const SizedBox(height: 24),
            _buildTelemetrySection(),
            const SizedBox(height: 24),
            _buildImageCacheSection(),
            const SizedBox(height: 24),
            _buildPerformanceSection(),
            const SizedBox(height: 24),
            _buildTestSection(),
          ],
        ),
      ),
    );
  }

  Widget _buildBatterySection() {
    final batteryInfo = _telemetryService.getBatteryInfo();
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.battery_full, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Battery Awareness',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _buildInfoRow('Battery Level', '${(batteryInfo['battery_level'] * 100).toInt()}%'),
            _buildInfoRow('Low Power Mode', batteryInfo['is_low_power_mode'].toString()),
            _buildInfoRow('Sampling Rate', '${(batteryInfo['sampling_rate'] * 100).toInt()}%'),
            _buildInfoRow('Low Battery Threshold', '${(batteryInfo['low_battery_threshold'] * 100).toInt()}%'),
            _buildInfoRow('Critical Battery Threshold', '${(batteryInfo['critical_battery_threshold'] * 100).toInt()}%'),
          ],
        ),
      ),
    );
  }

  Widget _buildTelemetrySection() {
    final batchInfo = _telemetryService.getBatchInfo();
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.analytics, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Telemetry Batching',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _buildInfoRow('Current Batch Size', batchInfo['current_batch_size'].toString()),
            _buildInfoRow('Max Batch Size', batchInfo['max_batch_size'].toString()),
            _buildInfoRow('Flush Interval', '${batchInfo['batch_flush_interval_seconds']}s'),
            _buildInfoRow('Is Flushing', batchInfo['is_flushing'].toString()),
            _buildInfoRow('Timer Active', batchInfo['timer_active'].toString()),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: () {
                _telemetryService.forceBatchFlush();
                setState(() {});
              },
              child: const Text('Force Batch Flush'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImageCacheSection() {
    final cacheInfo = _imageCacheService.getCacheInfo();
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.cached, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Image Cache',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _buildInfoRow('Cached Items', cacheInfo['memory_cache_items'].toString()),
            _buildInfoRow('Memory Usage', '${cacheInfo['memory_usage_mb']} MB'),
            _buildInfoRow('Max Memory', '${cacheInfo['max_memory_cache_mb']} MB'),
            if (cacheInfo['cache_directory'] != null)
              _buildInfoRow('Cache Directory', cacheInfo['cache_directory'] as String),
            const SizedBox(height: 8),
            Row(
              children: [
                ElevatedButton(
                  onPressed: () {
                    _imageCacheService.clearMemoryCache();
                    setState(() {});
                  },
                  child: const Text('Clear Memory'),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: () async {
                    await _imageCacheService.clearDiskCache();
                    setState(() {});
                  },
                  child: const Text('Clear Disk'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPerformanceSection() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.speed, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Performance Metrics',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: () {
                _performanceService.recordMemoryUsage();
                setState(() {});
              },
              child: const Text('Record Memory Usage'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTestSection() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.science, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Performance Tests',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: _runTelemetryTest,
              child: const Text('Test Telemetry Sampling'),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _runImageCacheTest,
              child: const Text('Test Image Caching'),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _runBatchingTest,
              child: const Text('Test Batching Performance'),
            ),
            const SizedBox(height: 16),
            const Text('Image Cache Test:'),
            const SizedBox(height: 8),
            SizedBox(
              height: 100,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: 10,
                itemBuilder: (context, index) {
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: CachedImage(
                      imageUrl: 'https://picsum.photos/100/100?random=$index',
                      width: 80,
                      height: 80,
                      cacheKey: 'test_$index',
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(
              value,
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.end,
            ),
          ),
        ],
      ),
    );
  }

  void _runTelemetryTest() {
    _telemetryService.recordEvent('performance_test_start', attributes: {
      'test_type': 'telemetry_sampling',
    });

    for (int i = 0; i < 100; i++) {
      _telemetryService.recordEvent('test_event_$i', attributes: {
        'iteration': i,
        'batch_test': true,
      });
    }

    _telemetryService.recordEvent('performance_test_complete', attributes: {
      'test_type': 'telemetry_sampling',
      'events_generated': 100,
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Telemetry test completed - 100 events generated')),
    );
  }

  void _runImageCacheTest() async {
    _telemetryService.recordEvent('performance_test_start', attributes: {
      'test_type': 'image_caching',
    });

    final testUrls = List.generate(20, (index) => 
        'https://picsum.photos/200/200?random=${index + 100}');

    int cacheHits = 0;
    int cacheMisses = 0;

    for (final url in testUrls) {
      final stopwatch = Stopwatch()..start();
      await _imageCacheService.getImage(url);
      stopwatch.stop();

      if (stopwatch.elapsedMilliseconds < 50) {
        cacheHits++;
      } else {
        cacheMisses++;
      }
    }

    _telemetryService.recordEvent('performance_test_complete', attributes: {
      'test_type': 'image_caching',
      'cache_hits': cacheHits,
      'cache_misses': cacheMisses,
      'total_images': testUrls.length,
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Image cache test: $cacheHits hits, $cacheMisses misses')),
      );
      setState(() {});
    }
  }

  void _runBatchingTest() {
    _telemetryService.recordEvent('performance_test_start', attributes: {
      'test_type': 'batching_performance',
    });

    final stopwatch = Stopwatch()..start();

    for (int i = 0; i < 200; i++) {
      _telemetryService.recordEvent('batch_test_event', attributes: {
        'event_number': i,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      });
    }

    stopwatch.stop();

    _telemetryService.recordEvent('performance_test_complete', attributes: {
      'test_type': 'batching_performance',
      'events_generated': 200,
      'duration_ms': stopwatch.elapsedMilliseconds,
    }, immediate: true);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Batching test: 200 events in ${stopwatch.elapsedMilliseconds}ms'),
      ),
    );

    setState(() {});
  }
}