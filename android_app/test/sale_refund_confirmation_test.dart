import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/services/sale_refund_confirmation.dart';

void main() {
  test('manual Kaspi tender with no transaction can use fiscal-only mode', () {
    expect(isManualKaspiSale({
      'sale_type': 'kaspi',
      'kaspi_transaction_id': null,
    }), isTrue);
    expect(isManualKaspiSale({
      'sale_type': 'kaspi',
      'kaspi_transaction_id': '  ',
    }), isTrue);
  });

  test('actual Kaspi POS transaction is never classified as manual', () {
    expect(isManualKaspiSale({
      'sale_type': 'kaspi',
      'kaspi_transaction_id': 'TX-123',
    }), isFalse);
  });

  test('cash and card refunds never use the Kaspi manual flag', () {
    for (final payment in ['cash', 'card', 'invoice']) {
      expect(isManualKaspiSale({
        'sale_type': payment,
        'kaspi_transaction_id': null,
      }), isFalse);
    }
  });
}
