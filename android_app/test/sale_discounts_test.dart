import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/services/sale_discounts.dart';

void main() {
  test('catalog offer keeps reference price and discounts exactly once', () {
    expect(saleDiscountPercent('10'), 10);
    expect(saleDiscountedPrice(2000, 10), 1800);
    expect(saleDiscountedPrice(2000, 25), 1500);
    expect(saleDiscountedPrice(2000, 0), 2000);
  });

  test('invalid percentages do not create invalid sale prices', () {
    expect(saleDiscountPercent('-1'), 0);
    expect(saleDiscountPercent('101'), 0);
    expect(saleDiscountPercent('not a number'), 0);
    expect(() => saleDiscountedPrice(1000, 101), throwsArgumentError);
  });

  test('cart shows actual customer savings', () {
    expect(saleLineSaving({
      'base_price': 1500,
      'qty': 2,
      'price': 1275,
      'discount_percent': 15,
    }, 2550), 450);
    expect(saleLineSaving({'price': 300, 'qty': 1}, 300), 0);
  });
  test('tenge discount is exact for a single product', () {
    final cart = <Map<String, dynamic>>[
      {'base_price': 2000.0, 'price': 2000.0, 'qty': 1.0, 'unit': 'шт'}
    ];
    applySaleCartDiscount(cart, mode: 'amount', value: 250);
    expect(cart.single['price'], 1750.0);
    expect(cart.single['line_total'], 1750.0);
    expect(cart.single['discount_amount'], 250.0);
    expect(saleLineSaving(cart.single, cart.single['line_total'] as double), 250);
  });

  test('fixed receipt discount distributed without losing tenge', () {
    final cart = <Map<String, dynamic>>[
      {'base_price': 1000.0, 'price': 1000.0, 'qty': 2.0, 'unit': 'шт'},
      {'base_price': 1000.0, 'price': 1000.0, 'qty': 1.0, 'unit': 'шт'},
    ];
    applySaleCartDiscount(cart, mode: 'amount', value: 50);
    final saved = cart.fold<double>(0, (sum, item) => sum + (item['discount_amount'] as double));
    expect(saved, 50);
    final total = cart.fold<double>(0, (sum, item) => sum + (item['line_total'] as double));
    expect(total, 2950);
  });

  test('percent discount replaces previous fixed discount, not stacks', () {
    final cart = <Map<String, dynamic>>[
      {'base_price': 2000.0, 'price': 2000.0, 'qty': 1.0, 'unit': 'шт'},
    ];
    applySaleCartDiscount(cart, mode: 'amount', value: 500);
    applySaleCartDiscount(cart, mode: 'percent', value: 10);
    expect(cart.single['price'], 1800);
    expect(cart.single['line_total'], isNull);
    expect(cart.single['discount_type'], 'percent');
  });

  test('discount cannot exceed basket amount', () {
    final cart = <Map<String, dynamic>>[
      {'price': 100.0, 'qty': 1.0, 'unit': 'шт'}
    ];
    expect(() => applySaleCartDiscount(cart, mode: 'amount', value: 200), throwsArgumentError);
  });

}
