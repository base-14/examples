import 'package:flutter/foundation.dart';

import 'http_service.dart';
import 'telemetry_service.dart';

class Currency {
  const Currency({
    required this.code,
    required this.name,
    required this.symbol,
  });

  final String code;
  final String name;
  final String symbol;
}

class Money {
  const Money({
    required this.currencyCode,
    required this.units,
    required this.nanos,
  });

  factory Money.fromUsd(double usdAmount) {
    final units = usdAmount.floor();
    final nanos = ((usdAmount - units) * 1000000000).round();
    return Money(
      currencyCode: 'USD',
      units: units,
      nanos: nanos,
    );
  }

  factory Money.fromJson(Map<String, dynamic> json) => Money(
    currencyCode: (json['currencyCode'] as String?) ?? 'USD',
    units: (json['units'] as int?) ?? 0,
    nanos: (json['nanos'] as int?) ?? 0,
  );

  final String currencyCode;
  final int units;
  final int nanos;

  double get amount => units + (nanos / 1000000000);

  String get formattedAmount {
    final currency = CurrencyService.currencies.firstWhere(
      (c) => c.code == currencyCode,
      orElse: () => Currency(code: currencyCode, name: currencyCode, symbol: currencyCode),
    );
    return '${currency.symbol}${amount.toStringAsFixed(2)}';
  }

  Map<String, dynamic> toJson() => {
    'currencyCode': currencyCode,
    'units': units,
    'nanos': nanos,
  };
}

class CurrencyService extends ChangeNotifier {
  CurrencyService._();

  static CurrencyService? _instance;
  static CurrencyService get instance => _instance ??= CurrencyService._();

  static const List<Currency> currencies = [
    Currency(code: 'USD', name: 'US Dollar', symbol: '\$'),
    Currency(code: 'INR', name: 'Indian Rupee', symbol: '₹'),
    Currency(code: 'EUR', name: 'Euro', symbol: '€'),
    Currency(code: 'CAD', name: 'Canadian Dollar', symbol: 'C\$'),
    Currency(code: 'GBP', name: 'British Pound', symbol: '£'),
    Currency(code: 'JPY', name: 'Japanese Yen', symbol: '¥'),
  ];

  final HttpService _httpService = HttpService.instance;

  Currency _selectedCurrency = currencies[0]; // Default to USD
  List<String> _supportedCurrencies = [];
  bool _isLoading = false;
  String? _error;

  Currency get selectedCurrency => _selectedCurrency;
  List<String> get supportedCurrencies => _supportedCurrencies;
  bool get isLoading => _isLoading;
  String? get error => _error;

  void initialize() {
    TelemetryService.instance.recordEvent('currency_service_initialize', attributes: {
      'default_currency': _selectedCurrency.code,
      'session_id': TelemetryService.instance.sessionId,
    });

    _loadSupportedCurrencies();
  }

  Future<void> _loadSupportedCurrencies() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _httpService.get<List<dynamic>>(
        '/currency',
      );

      if (response.isSuccess && response.data != null) {
        _supportedCurrencies = List<String>.from(response.data!);

        TelemetryService.instance.recordEvent('currency_supported_loaded', attributes: {
          'currencies_count': _supportedCurrencies.length,
          'currencies': _supportedCurrencies.join(','),
        });
      } else {
        _error = response.errorMessage ?? 'Failed to load supported currencies';

        TelemetryService.instance.recordEvent('currency_supported_error', attributes: {
          'error_message': _error!,
          'status_code': response.statusCode,
        });
      }

    } catch (e) {
      _error = 'Failed to load currencies: $e';

      TelemetryService.instance.recordEvent('currency_load_exception', attributes: {
        'error_message': e.toString(),
      });
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void selectCurrency(Currency currency) {
    if (_selectedCurrency.code == currency.code) return;

    final previousCurrency = _selectedCurrency.code;
    _selectedCurrency = currency;

    TelemetryService.instance.recordEvent('currency_changed', attributes: {
      'previous_currency': previousCurrency,
      'new_currency': currency.code,
      'currency_name': currency.name,
      'session_id': TelemetryService.instance.sessionId,
    });

    notifyListeners();
  }

  Future<Money?> convertMoney(Money sourceMoney, String targetCurrency) async {
    if (sourceMoney.currencyCode == targetCurrency) {
      return sourceMoney;
    }

    try {
      final requestBody = {
        'from': sourceMoney.toJson(),
        'toCode': targetCurrency,
      };

      final response = await _httpService.post<Map<String, dynamic>>(
        '/currency/convert',
        body: requestBody,
        fromJson: (json) => json,
      );

      if (response.isSuccess && response.data != null) {
        final convertedMoney = Money.fromJson(response.data!);

        TelemetryService.instance.recordEvent('currency_conversion_success', attributes: {
          'from_currency': sourceMoney.currencyCode,
          'to_currency': targetCurrency,
          'from_amount': sourceMoney.amount,
          'to_amount': convertedMoney.amount,
          'conversion_rate': convertedMoney.amount / sourceMoney.amount,
        });

        return convertedMoney;
      } else {
        TelemetryService.instance.recordEvent('currency_conversion_error', attributes: {
          'from_currency': sourceMoney.currencyCode,
          'to_currency': targetCurrency,
          'error_message': response.errorMessage ?? 'Unknown error',
          'status_code': response.statusCode,
        });

        return null;
      }

    } catch (e) {
      TelemetryService.instance.recordEvent('currency_conversion_exception', attributes: {
        'from_currency': sourceMoney.currencyCode,
        'to_currency': targetCurrency,
        'error_message': e.toString(),
      });

      return null;
    }
  }

  String formatPrice(double usdPrice, {Currency? currency}) {
    currency ??= _selectedCurrency;

    if (currency.code == 'USD') {
      return '${currency.symbol}${usdPrice.toStringAsFixed(2)}';
    }

    return '${currency.symbol}${(usdPrice * _getConversionRate(currency.code)).toStringAsFixed(2)}';
  }

  double _getConversionRate(String currencyCode) {
    switch (currencyCode) {
      case 'INR': return 88.1;
      case 'EUR': return 0.85;
      case 'CAD': return 1.35;
      case 'GBP': return 0.75;
      case 'JPY': return 110.0;
      default: return 1.0;
    }
  }

  double convertPrice(double usdPrice, {Currency? currency}) {
    currency ??= _selectedCurrency;

    if (currency.code == 'USD') {
      return usdPrice;
    }

    return usdPrice * _getConversionRate(currency.code);
  }
}