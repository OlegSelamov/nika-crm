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
