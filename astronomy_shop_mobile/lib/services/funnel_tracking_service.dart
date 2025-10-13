import 'dart:async';
import 'package:flutter/foundation.dart';
import 'telemetry_service.dart';

enum FunnelStage {
  appLaunch('app_launch', 'App Launch', 0),
  productListView('product_list_view', 'Product List Viewed', 1),
  productDetailView('product_detail_view', 'Product Detail Viewed', 2),
  addToCart('add_to_cart', 'Added to Cart', 3),
  cartView('cart_view', 'Cart Viewed', 4),
  checkoutStart('checkout_start', 'Checkout Started', 5),
  checkoutInfoEntered('checkout_info_entered', 'Checkout Info Entered', 6),
  orderPlaced('order_placed', 'Order Placed', 7),
  orderConfirmed('order_confirmed', 'Order Confirmed', 8);

  final String eventName;
  final String displayName;
  final int order;

  const FunnelStage(this.eventName, this.displayName, this.order);
}

class FunnelTrackingService {
  static FunnelTrackingService? _instance;

  FunnelStage? _currentStage;
  FunnelStage? _previousStage;
  DateTime? _stageEntryTime;
  final Map<FunnelStage, DateTime> _stageTimestamps = {};
  final Map<FunnelStage, int> _stageVisitCount = {};
  final List<FunnelStage> _sessionJourney = [];

  String? _currentSessionId;
  String? _currentTraceId;

  Timer? _abandonmentTimer;
  static const Duration _abandonmentThreshold = Duration(minutes: 5);

  FunnelTrackingService._internal();

  static FunnelTrackingService get instance {
    _instance ??= FunnelTrackingService._internal();
    return _instance!;
  }

  void initialize(String sessionId) {
    _currentSessionId = sessionId;
    _currentTraceId = TelemetryService.instance.startTrace('user_funnel');

    trackStage(FunnelStage.appLaunch);

    if (kDebugMode) {
      print('🎯 Funnel tracking initialized with session: ${sessionId.substring(0, 8)}...');
    }
  }

  void trackStage(FunnelStage stage, {Map<String, Object>? metadata}) {
    final now = DateTime.now();

    _cancelAbandonmentTimer();

    final timeInPreviousStage = _calculateTimeInStage();

    _previousStage = _currentStage;
    _currentStage = stage;
    _stageEntryTime = now;
    _stageTimestamps[stage] = now;

    _stageVisitCount[stage] = (_stageVisitCount[stage] ?? 0) + 1;
    _sessionJourney.add(stage);

    final isProgression = _previousStage != null &&
                          stage.order > _previousStage!.order;
    final isRegression = _previousStage != null &&
                         stage.order < _previousStage!.order;
    final isRevisit = _stageVisitCount[stage]! > 1;

    final eventAttributes = <String, Object>{
      'funnel.stage': stage.eventName,
      'funnel.stage_name': stage.displayName,
      'funnel.stage_order': stage.order,
      'funnel.session_id': _currentSessionId ?? 'unknown',
      'funnel.is_progression': isProgression,
      'funnel.is_regression': isRegression,
      'funnel.is_revisit': isRevisit,
      'funnel.visit_count': _stageVisitCount[stage]!,
      'funnel.journey_length': _sessionJourney.length,
      'funnel.stage_path': '${_previousStage?.eventName ?? 'start'} -> ${stage.eventName}',
      'funnel.journey_type': isProgression ? 'forward' : (isRegression ? 'backward' : 'revisit'),
    };

    if (_previousStage != null) {
      eventAttributes['funnel.previous_stage'] = _previousStage!.eventName;
      eventAttributes['funnel.previous_stage_name'] = _previousStage!.displayName;
      if (timeInPreviousStage != null) {
        eventAttributes['funnel.time_in_previous_stage_ms'] = timeInPreviousStage;
      }
    }

    final sessionDuration = _calculateSessionDuration();
    if (sessionDuration != null) {
      eventAttributes['funnel.session_duration_ms'] = sessionDuration;
    }

    eventAttributes['funnel.completion_rate'] = _calculateCompletionRate();

    if (metadata != null) {
      eventAttributes.addAll(metadata);
    }

    TelemetryService.instance.recordEvent(
      'funnel_stage_transition',
      attributes: eventAttributes,
      parentOperation: 'user_funnel'
    );

    if (stage == FunnelStage.cartView ||
        stage == FunnelStage.checkoutStart) {
      _startAbandonmentTimer(stage);
    }

    if (kDebugMode) {
      final arrow = isProgression ? '→' : (isRegression ? '←' : '↺');
      print('🎯 Funnel: ${_previousStage?.displayName ?? 'Start'} $arrow ${stage.displayName}');
    }
  }

  void trackConversion(FunnelStage fromStage, FunnelStage toStage, {Map<String, Object>? metadata}) {
    final timeToConvert = _calculateTimeBetweenStages(fromStage, toStage);

    final eventAttributes = <String, Object>{
      'funnel.conversion_from': fromStage.eventName,
      'funnel.conversion_to': toStage.eventName,
      'funnel.conversion_from_name': fromStage.displayName,
      'funnel.conversion_to_name': toStage.displayName,
      'funnel.session_id': _currentSessionId ?? 'unknown',
    };

    if (timeToConvert != null) {
      eventAttributes['funnel.time_to_convert_ms'] = timeToConvert;
    }

    if (metadata != null) {
      eventAttributes.addAll(metadata);
    }

    TelemetryService.instance.recordEvent(
      'funnel_conversion',
      attributes: eventAttributes,
      parentOperation: 'user_funnel'
    );
  }

  void trackDropOff({String? reason, Map<String, Object>? metadata}) {
    if (_currentStage == null) return;

    final timeInStage = _calculateTimeInStage();

    final eventAttributes = <String, Object>{
      'funnel.drop_off_stage': _currentStage!.eventName,
      'funnel.drop_off_stage_name': _currentStage!.displayName,
      'funnel.drop_off_stage_order': _currentStage!.order,
      'funnel.session_id': _currentSessionId ?? 'unknown',
      'funnel.journey_stages_completed': _sessionJourney.length,
    };

    if (timeInStage != null) {
      eventAttributes['funnel.time_before_drop_off_ms'] = timeInStage;
    }

    if (reason != null) {
      eventAttributes['funnel.drop_off_reason'] = reason;
    }

    final sessionDuration = _calculateSessionDuration();
    if (sessionDuration != null) {
      eventAttributes['funnel.total_session_duration_ms'] = sessionDuration;
    }

    if (metadata != null) {
      eventAttributes.addAll(metadata);
    }

    TelemetryService.instance.recordEvent(
      'funnel_drop_off',
      attributes: eventAttributes,
      parentOperation: 'user_funnel'
    );

    if (kDebugMode) {
      print('🎯 Funnel drop-off at: ${_currentStage!.displayName}${reason != null ? ' (Reason: $reason)' : ''}');
    }
  }

  void trackAbandonment(FunnelStage stage, {Map<String, Object>? metadata}) {
    final timeInStage = _calculateTimeInStage();

    final eventAttributes = <String, Object>{
      'funnel.abandonment_stage': stage.eventName,
      'funnel.abandonment_stage_name': stage.displayName,
      'funnel.abandonment_threshold_ms': _abandonmentThreshold.inMilliseconds,
      'funnel.session_id': _currentSessionId ?? 'unknown',
    };

    if (timeInStage != null) {
      eventAttributes['funnel.time_in_stage_before_abandonment_ms'] = timeInStage;
    }

    if (metadata != null) {
      eventAttributes.addAll(metadata);
    }

    TelemetryService.instance.recordEvent(
      'funnel_abandonment',
      attributes: eventAttributes,
      parentOperation: 'user_funnel'
    );

    if (kDebugMode) {
      print('⚠️ Funnel abandonment detected at: ${stage.displayName}');
    }
  }

  void _startAbandonmentTimer(FunnelStage stage) {
    _abandonmentTimer = Timer(_abandonmentThreshold, () {
      trackAbandonment(stage);
    });
  }

  void _cancelAbandonmentTimer() {
    _abandonmentTimer?.cancel();
    _abandonmentTimer = null;
  }

  int? _calculateTimeInStage() {
    if (_stageEntryTime == null) return null;
    return DateTime.now().difference(_stageEntryTime!).inMilliseconds;
  }

  int? _calculateTimeBetweenStages(FunnelStage fromStage, FunnelStage toStage) {
    final fromTime = _stageTimestamps[fromStage];
    final toTime = _stageTimestamps[toStage];

    if (fromTime == null || toTime == null) return null;
    return toTime.difference(fromTime).inMilliseconds;
  }

  int? _calculateSessionDuration() {
    if (_stageTimestamps.isEmpty) return null;

    final firstStage = _stageTimestamps[FunnelStage.appLaunch];
    if (firstStage == null) return null;

    return DateTime.now().difference(firstStage).inMilliseconds;
  }

  double _calculateCompletionRate() {
    if (_currentStage == null) return 0.0;
    return (_currentStage!.order + 1) / FunnelStage.values.length;
  }

  Map<String, dynamic> getFunnelAnalytics() {
    return {
      'current_stage': _currentStage?.displayName,
      'previous_stage': _previousStage?.displayName,
      'stages_visited': _stageVisitCount.keys.map((s) => s.displayName).toList(),
      'journey_path': _sessionJourney.map((s) => s.displayName).toList(),
      'total_stages_visited': _sessionJourney.length,
      'unique_stages_visited': _stageVisitCount.length,
      'completion_rate': _calculateCompletionRate(),
      'session_duration_ms': _calculateSessionDuration(),
      'revisits': _stageVisitCount.entries
          .where((e) => e.value > 1)
          .map((e) => {'stage': e.key.displayName, 'count': e.value})
          .toList(),
    };
  }

  void reset() {
    _currentStage = null;
    _previousStage = null;
    _stageEntryTime = null;
    _stageTimestamps.clear();
    _stageVisitCount.clear();
    _sessionJourney.clear();
    _cancelAbandonmentTimer();

    if (_currentTraceId != null) {
      TelemetryService.instance.endTrace('user_funnel');
      _currentTraceId = null;
    }
  }

  void dispose() {
    _cancelAbandonmentTimer();
    reset();
  }
}