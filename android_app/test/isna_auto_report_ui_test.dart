import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/screens/isna_test_panel.dart';

void main() {
  testWidgets('real FNO loads existing accounting data without pasted JSON',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: IsnaTestPanel())),
    );
    final button = find.text('Сформировать ФНО из Nika Business');
    await tester.ensureVisible(button);
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(find.text('Загрузить данные из Nika'), findsOneWidget);
    expect(find.text('Полный JSON с code + fnoDto'), findsNothing);
    expect(find.byType(DropdownButtonFormField<String>), findsWidgets);
    expect(find.byType(DropdownButtonFormField<int>), findsOneWidget);
    await tester.tap(find.text('Отмена').last);
    await tester.pumpAndSettle();
    expect(find.text('Загрузить данные из Nika'), findsNothing);
  });
}
