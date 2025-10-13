import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/currency_service.dart';
import '../services/telemetry_service.dart';

class CurrencySelector extends StatelessWidget {
  const CurrencySelector({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<CurrencyService>(
      builder: (context, currencyService, child) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          decoration: BoxDecoration(
            border: Border.all(
              color: Theme.of(context).colorScheme.outline.withValues(alpha: 0.5),
            ),
            borderRadius: BorderRadius.circular(8),
          ),
          child: DropdownButton<Currency>(
            value: currencyService.selectedCurrency,
            icon: Icon(
              Icons.keyboard_arrow_down,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            elevation: 8,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w500,
            ),
            underline: Container(), // Remove default underline
            onChanged: (Currency? newCurrency) {
              if (newCurrency != null) {
                currencyService.selectCurrency(newCurrency);
                
                TelemetryService.instance.recordEvent('currency_selector_changed', attributes: {
                  'previous_currency': currencyService.selectedCurrency.code,
                  'new_currency': newCurrency.code,
                  'new_currency_name': newCurrency.name,
                  'selector_location': 'dropdown',
                });
              }
            },
            items: CurrencyService.currencies.map<DropdownMenuItem<Currency>>((Currency currency) {
              return DropdownMenuItem<Currency>(
                value: currency,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      currency.symbol,
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(currency.code),
                  ],
                ),
              );
            }).toList(),
          ),
        );
      },
    );
  }
}

class CurrencySelectorDialog extends StatelessWidget {
  const CurrencySelectorDialog({super.key});

  static Future<void> show(BuildContext context) async {
    TelemetryService.instance.recordEvent('currency_selector_dialog_opened', attributes: {
      'current_currency': Provider.of<CurrencyService>(context, listen: false).selectedCurrency.code,
    });

    await showDialog(
      context: context,
      builder: (BuildContext context) => const CurrencySelectorDialog(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CurrencyService>(
      builder: (context, currencyService, child) {
        return AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.currency_exchange),
              SizedBox(width: 8),
              Text('Select Currency'),
            ],
          ),
          content: SizedBox(
            width: double.minPositive,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Choose your preferred currency for price display',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 16),
                ...CurrencyService.currencies.map((currency) => 
                  _buildCurrencyOption(context, currency, currencyService),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                TelemetryService.instance.recordEvent('currency_selector_dialog_cancelled', attributes: {
                  'selected_currency': currencyService.selectedCurrency.code,
                });
                Navigator.of(context).pop();
              },
              child: const Text('Done'),
            ),
          ],
        );
      },
    );
  }

  Widget _buildCurrencyOption(BuildContext context, Currency currency, CurrencyService currencyService) {
    final isSelected = currencyService.selectedCurrency.code == currency.code;
    
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () {
          currencyService.selectCurrency(currency);
          
          TelemetryService.instance.recordEvent('currency_selector_dialog_selected', attributes: {
            'previous_currency': currencyService.selectedCurrency.code,
            'new_currency': currency.code,
            'new_currency_name': currency.name,
            'selector_location': 'dialog',
          });
          
          Navigator.of(context).pop();
        },
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: isSelected 
                ? Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.5)
                : null,
            border: Border.all(
              color: isSelected 
                  ? Theme.of(context).colorScheme.primary
                  : Theme.of(context).colorScheme.outline.withValues(alpha: 0.3),
            ),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Center(
                  child: Text(
                    currency.symbol,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      currency.code,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: isSelected 
                            ? Theme.of(context).colorScheme.primary
                            : null,
                      ),
                    ),
                    Text(
                      currency.name,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              if (isSelected)
                Icon(
                  Icons.check_circle,
                  color: Theme.of(context).colorScheme.primary,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class CurrencyButton extends StatelessWidget {
  const CurrencyButton({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<CurrencyService>(
      builder: (context, currencyService, child) {
        return IconButton(
          icon: Stack(
            children: [
              Icon(
                Icons.currency_exchange,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
              Positioned(
                right: 0,
                bottom: 0,
                child: Container(
                  padding: const EdgeInsets.all(2),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primary,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    currencyService.selectedCurrency.code,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onPrimary,
                      fontSize: 8,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ],
          ),
          onPressed: () => CurrencySelectorDialog.show(context),
          tooltip: 'Change Currency (${currencyService.selectedCurrency.code})',
        );
      },
    );
  }
}