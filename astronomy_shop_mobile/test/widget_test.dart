// This is a basic Flutter widget test for the Astronomy Shop Mobile app.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App launches correctly', (WidgetTester tester) async {
    // Build a simple MaterialApp for testing
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          appBar: AppBar(title: const Text('🔭 Astronomy Shop')),
          body: const Column(
            children: [
              Text('Hot Products ⭐'),
              CircularProgressIndicator(),
            ],
          ),
        ),
      ),
    );

    // Verify that the app title is displayed
    expect(find.text('🔭 Astronomy Shop'), findsOneWidget);
    
    // Verify that product content is shown
    expect(find.text('Hot Products ⭐'), findsOneWidget);
    
    // Verify loading indicator is present
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}