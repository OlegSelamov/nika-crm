import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/screens/dashboard_screen.dart';

Map<String, dynamic> totals(int revenue) => {
  'success': true,
  'date': '2026-11-07',
  'revenue': revenue,
  'sales_count': revenue ~/ 1000,
  'net_profit': revenue ~/ 2,
  'average_check': 1000,
};

Widget screen({
  required Future<Map<String, dynamic>> Function() fresh,
  required Future<Map<String, dynamic>?> Function() cached,
  required Future<Map<String, dynamic>> Function() shift,
  int refreshToken = 0,
}) {
  return MaterialApp(
    home: Scaffold(
      body: DashboardScreen(
        refreshToken: refreshToken,
        fetchDashboard: fresh,
        readCachedDashboard: cached,
        fetchShift: shift,
      ),
    ),
  );
}

void main() {
  testWidgets('Cached totals appear before slow server and unrelated reKassa',
      (tester) async {
    final fresh = Completer<Map<String, dynamic>>();
    final delayedShift = Completer<Map<String, dynamic>>();
    await tester.pumpWidget(screen(
      fresh: () => fresh.future,
      cached: () async => totals(1000),
      shift: () => delayedShift.future,
    ));
    await tester.pump();
    expect(find.text('1 000 ₸'), findsWidgets);
    expect(find.textContaining('Обновляем показатели'), findsOneWidget);
    expect(find.text('Смена: —'), findsOneWidget);

    fresh.complete(totals(2500));
    await tester.pump();
    await tester.pump();
    expect(find.text('2 500 ₸'), findsOneWidget);
    expect(find.textContaining('Обновляем показатели'), findsNothing);
    // Fiscal-provider status was never needed to show the new revenue.
    expect(delayedShift.isCompleted, isFalse);
  });

  testWidgets('Opening home again fetches fresh totals without hiding cards',
      (tester) async {
    var callCount = 0;
    final second = Completer<Map<String, dynamic>>();
    final delayedShift = Completer<Map<String, dynamic>>();
    Future<Map<String, dynamic>> fresh() {
      callCount++;
      return callCount == 1 ? Future.value(totals(1000)) : second.future;
    }
    Future<Map<String, dynamic>?> cached() async => totals(1000);
    Future<Map<String, dynamic>> shift() => delayedShift.future;

    await tester.pumpWidget(screen(fresh: fresh, cached: cached, shift: shift));
    await tester.pump();
    await tester.pump();
    expect(find.text('1 000 ₸'), findsWidgets);
    await tester.pumpWidget(screen(
      fresh: fresh, cached: cached, shift: shift, refreshToken: 1,
    ));
    await tester.pump();
    expect(callCount, 2);
    expect(find.text('1 000 ₸'), findsWidgets);
    second.complete(totals(3000));
    await tester.pump();
    await tester.pump();
    expect(find.text('3 000 ₸'), findsOneWidget);
  });

  testWidgets('Temporary network error does not blank previously seen totals',
      (tester) async {
    final server = Completer<Map<String, dynamic>>();
    final delayedShift = Completer<Map<String, dynamic>>();
    await tester.pumpWidget(screen(
      fresh: () => server.future,
      cached: () async => totals(1000),
      shift: () => delayedShift.future,
    ));
    await tester.pump();
    server.completeError(Exception('Temporary network outage'));
    await tester.pump();
    await tester.pump();
    expect(find.text('1 000 ₸'), findsWidgets);
    expect(find.textContaining('Показаны сохранённые данные'), findsOneWidget);
  });
}
