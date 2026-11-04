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
}
