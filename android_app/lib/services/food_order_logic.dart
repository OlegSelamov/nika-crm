class FoodOrderLogic {
  static double number(dynamic value) =>
      double.tryParse((value ?? 0).toString().replaceAll(',', '.')) ?? 0;

  static double total(List<Map<String, dynamic>> cart) =>
      cart.fold<double>(0, (sum, item) =>
          sum + number(item['line_total'] ?? number(item['price']) * number(item['qty'] ?? 1)));

  static bool groupValid(Map<String, dynamic> group, Set<int> selected) {
    final options = (group['options'] as List? ?? []).map((o) => Map<String, dynamic>.from(o as Map));
    final count = options.where((o) => selected.contains(int.tryParse(o['id'].toString()) ?? -1)).length;
    final minimum = number(group['min_select']).toInt();
    final maximum = number(group['max_select']).toInt();
    return count >= minimum && (maximum <= 0 || count <= maximum);
  }

  static Map<String, dynamic> line(
    Map<String, dynamic> item, {
    List<Map<String, dynamic>> modifiers = const [],
    List<Map<String, dynamic>> exclusions = const [],
  }) {
    final extra = modifiers.fold<double>(0,
        (sum, m) => sum + number(m['price_delta']));
    return {
      'id': item['id'],
      'name': item['name'] ?? 'Блюдо',
      'price': number(item['retail_price'] ?? item['price']) + extra,
      'qty': 1,
      'unit': item['unit'] ?? 'шт',
      'item_type': item['item_type'] ?? 'product',
      'gtin': item['gtin'] ?? '',
      'ntin': item['ntin'] ?? '',
      'modifiers': modifiers.map((m) => {
        'id': m['id'], 'name': m['name'], 'price_delta': number(m['price_delta']),
      }).toList(),
      'excluded_ingredients': exclusions.map((e) => {
        'id': e['item_id'] ?? e['id'], 'name': e['name'] ?? '',
      }).toList(),
    };
  }
}
