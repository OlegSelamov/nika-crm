import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/services/food_order_logic.dart';

void main() {
  test('modifiers change price, exclusions do not', () {
    final line = FoodOrderLogic.line(
      {'id': 5, 'name': 'Шаурма', 'retail_price': 1500, 'item_type': 'dish'},
      modifiers: [{'id': 3, 'name': 'Сыр', 'price_delta': 250}],
      exclusions: [{'item_id': 41, 'name': 'Лук'}],
    );
    expect(line['price'], 1750);
    expect((line['modifiers'] as List).single['id'], 3);
    expect((line['excluded_ingredients'] as List).single['id'], 41);
    expect(FoodOrderLogic.total([line]), 1750);
  });
  test('mandatory selections and maxima are enforced', () {
    const group = {'min_select': 1, 'max_select': 2, 'options': [
      {'id': 1}, {'id': 2}, {'id': 3},
    ]};
    expect(FoodOrderLogic.groupValid(group, <int>{}), false);
    expect(FoodOrderLogic.groupValid(group, {1, 2}), true);
    expect(FoodOrderLogic.groupValid(group, {1, 2, 3}), false);
  });
  test('server line totals are preserved', () {
    expect(FoodOrderLogic.total([{'price': 100, 'qty': 3, 'line_total': 305}]), 305);
  });
}
