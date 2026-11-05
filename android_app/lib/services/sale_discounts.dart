/// Consistent POS pricing for catalog and cashier-entered percentage discounts.
/// Catalog price remains unchanged; only the sale cart unit price is reduced.
int saleDiscountPercent(dynamic raw) {
  final value = double.tryParse('${raw ?? 0}') ?? 0;
  if (!value.isFinite || value < 0 || value > 100 || value != value.roundToDouble()) {
    return 0;
  }
  return value.toInt();
}

double saleDiscountedPrice(double original, int percent) {
  if (!original.isFinite || original < 0 || percent < 0 || percent > 100) {
    throw ArgumentError('Некорректная цена или скидка');
  }
  final cents = (original * 100).round();
  return (cents * (100 - percent) / 100).round() / 100;
}

double saleLineSaving(Map<String, dynamic> line, double chargedTotal) {
  final rawBase = double.tryParse('${line['base_price'] ?? ''}');
  final rawQty = double.tryParse('${line['qty'] ?? ''}');
  if (rawBase == null || rawQty == null ||
      !rawBase.isFinite || !rawQty.isFinite || rawBase < 0 || rawQty < 0) {
    return 0;
  }
  final oldTotal = rawBase * rawQty;
  return (oldTotal - chargedTotal).clamp(0, double.infinity).toDouble();
}


double saleGross(Map<String, dynamic> item) {
  final base = double.tryParse('${item['base_price'] ?? item['price'] ?? 0}') ?? 0;
  final qty = double.tryParse('${item['qty'] ?? 0}') ?? 0;
  const measured = {'кг', 'килограмм', 'килограммы', 'г', 'гр', 'грамм',
    'граммы', 'л', 'литр', 'литры', 'мл', 'миллилитр', 'миллилитры',
    'час', 'ч', 'часа', 'часов'};
  final gross = base * qty;
  return measured.contains('${item['unit'] ?? ''}'.toLowerCase())
      ? gross.roundToDouble()
      : (gross * 100).round() / 100;
}

void applySaleFixedDiscount(Map<String, dynamic> item, int discountCents) {
  final grossCents = (saleGross(item) * 100).round();
  final applied = discountCents.clamp(0, grossCents);
  final qty = double.tryParse('${item['qty'] ?? 1}') ?? 1;
  item['base_price'] = item['base_price'] ?? item['price'];
  item['discount_type'] = 'amount';
  item['discount_percent'] = null;
  item['discount_amount'] = applied / 100;
  item['line_total'] = (grossCents - applied) / 100;
  item['price'] = qty > 0 ? ((grossCents - applied) / qty).round() / 100 : 0;
}

/// Apply either a percentage or an exact tenge discount to one cart row
/// or distribute one fixed discount over the entire sale. No catalog prices
/// are overwritten, and the same snapshot is used by checkout and offline sync.
void applySaleCartDiscount(
  List<Map<String, dynamic>> cart, {
  int? index,
  required String mode,
  required double value,
}) {
  if (!value.isFinite || value < 0 || (mode != 'percent' && mode != 'amount')) {
    throw ArgumentError('Некорректная скидка');
  }
  if (mode == 'percent' && (value > 100 || value != value.roundToDouble())) {
    throw ArgumentError('Процент должен быть целым от 0 до 100');
  }
  final chosen = index == null ? cart : <Map<String, dynamic>>[cart[index]];
  if (chosen.isEmpty) return;
  if (mode == 'amount') {
    if ((value * 100 - (value * 100).round()).abs() > .000001) {
      throw ArgumentError('Точная сумма скидки должна быть в тенге и тиынах');
    }
    final cents = (value * 100).round();
    final originalCents = chosen.map((line) => (saleGross(line) * 100).round())
        .reduce((a, b) => a + b);
    if (cents > originalCents) {
      throw ArgumentError('Скидка превышает стоимость товаров');
    }
    var remaining = cents;
    for (var i = 0; i < chosen.length; i++) {
      final lineGross = (saleGross(chosen[i]) * 100).round();
      final share = i == chosen.length - 1 ? remaining
          : (cents * lineGross / (originalCents == 0 ? 1 : originalCents)).round();
      final applied = share.clamp(0, lineGross).clamp(0, remaining);
      remaining -= applied;
      applySaleFixedDiscount(chosen[i], applied);
    }
    return;
  }
  for (final item in chosen) {
    final base = double.tryParse('${item['base_price'] ?? item['price'] ?? 0}') ?? 0;
    item.remove('line_total');
    item.remove('discount_amount');
    item['base_price'] = base;
    item['discount_type'] = 'percent';
    item['discount_percent'] = value.toInt();
    item['price'] = saleDiscountedPrice(base, value.toInt());
  }
}

String saleDiscountLabel(Map<String, dynamic> item) {
  if (item['discount_type'] == 'amount') {
    final amount = double.tryParse('${item['discount_amount'] ?? 0}') ?? 0;
    return amount > 0 ? '−${amount.toStringAsFixed(2)} ₸' : '';
  }
  final percent = saleDiscountPercent(item['discount_percent']);
  return percent > 0 ? '−$percent%' : '';
}
