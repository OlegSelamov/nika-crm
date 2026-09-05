import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'app_widgets.dart';

double stockNumber(dynamic value) => double.tryParse('${value ?? 0}') ?? 0;

String stockQuantity(dynamic value) {
  final number = stockNumber(value);
  if (number == number.roundToDouble()) return number.toInt().toString();
  return number.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '');
}

class StockStatusMeta {
  final String key;
  final String label;
  final Color color;
  final IconData icon;

  const StockStatusMeta(this.key, this.label, this.color, this.icon);
}

StockStatusMeta stockStatus(dynamic value) {
  final quantity = stockNumber(value);
  if (quantity <= 0) {
    return const StockStatusMeta('out', 'Нет в наличии', AppColors.danger, Icons.cancel_outlined);
  }
  if (quantity <= 5) {
    return const StockStatusMeta('low', 'Заканчивается', AppColors.warning, Icons.warning_amber_rounded);
  }
  return const StockStatusMeta('normal', 'В наличии', AppColors.success, Icons.check_circle_outline);
}

class MovementMeta {
  final String label;
  final String sign;
  final Color color;
  final IconData icon;

  const MovementMeta(this.label, this.sign, this.color, this.icon);
}

MovementMeta movementMeta(dynamic value) {
  switch ('${value ?? ''}') {
    case 'income':
      return const MovementMeta('Приход', '+', AppColors.success, Icons.south_rounded);
    case 'sale':
      return const MovementMeta('Продажа', '−', AppColors.primary, Icons.shopping_cart_outlined);
    case 'refund':
      return const MovementMeta('Возврат', '+', AppColors.warning, Icons.keyboard_return_rounded);
    case 'writeoff':
      return const MovementMeta('Списание', '−', AppColors.danger, Icons.remove_circle_outline);
    default:
      return const MovementMeta('Операция', '', AppColors.muted, Icons.swap_horiz_rounded);
  }
}

DateTime? parseStockDate(dynamic value) {
  final raw = '${value ?? ''}'.trim();
  if (raw.isEmpty) return null;
  final iso = DateTime.tryParse(raw);
  if (iso != null) return iso.isUtc ? iso.toLocal() : iso;

  final match = RegExp(
    r'^[A-Za-z]{3},\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})',
  ).firstMatch(raw);
  if (match == null) return null;
  const months = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12,
  };
  final month = months[match.group(2)];
  if (month == null) return null;
  return DateTime.utc(
    int.parse(match.group(3)!),
    month,
    int.parse(match.group(1)!),
    int.parse(match.group(4)!),
    int.parse(match.group(5)!),
    int.parse(match.group(6)!),
  ).toLocal();
}

String stockDateTime(dynamic value) {
  final date = parseStockDate(value);
  if (date == null) return '${value ?? '—'}';
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year} в ${two(date.hour)}:${two(date.minute)}';
}

Future<Map<String, dynamic>?> showStockProductPicker(
  BuildContext context, {
  required List<Map<String, dynamic>> items,
  int? selectedId,
}) =>
    showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => _StockProductPickerSheet(items: items, selectedId: selectedId),
    );

class _StockProductPickerSheet extends StatefulWidget {
  final List<Map<String, dynamic>> items;
  final int? selectedId;

  const _StockProductPickerSheet({required this.items, this.selectedId});

  @override
  State<_StockProductPickerSheet> createState() => _StockProductPickerSheetState();
}

class _StockProductPickerSheetState extends State<_StockProductPickerSheet> {
  final searchController = TextEditingController();
  String query = '';

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> get filtered {
    if (query.trim().isEmpty) return widget.items;
    final needle = query.trim().toLowerCase();
    return widget.items.where((item) {
      final haystack = [
        item['name'],
        item['category'],
        item['barcode'],
        item['gtin'],
        item['ntin'],
      ].join(' ').toLowerCase();
      return haystack.contains(needle);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final values = filtered;
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * .82,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 12, 10),
            child: Row(
              children: [
                const Expanded(
                  child: Text('Выберите товар', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                ),
                IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: TextField(
              controller: searchController,
              autofocus: true,
              onChanged: (value) => setState(() => query = value),
              decoration: const InputDecoration(
                hintText: 'Название, штрихкод, GTIN или NTIN',
                prefixIcon: Icon(Icons.search),
              ),
            ),
          ),
          Expanded(
            child: values.isEmpty
                ? const ScreenStateView(
                    icon: Icons.search_off_rounded,
                    title: 'Товар не найден',
                    message: 'Измените название или код товара.',
                  )
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                    itemCount: values.length,
                    itemBuilder: (_, index) {
                      final item = values[index];
                      final status = stockStatus(item['stock']);
                      final selected = item['id'] == widget.selectedId;
                      final name = '${item['name'] ?? ''}'.trim();
                      final code = [item['barcode'], item['gtin'], item['ntin']]
                          .map((value) => '${value ?? ''}'.trim())
                          .firstWhere((value) => value.isNotEmpty, orElse: () => '');
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        color: selected ? AppColors.primarySoft : AppColors.surface,
                        child: ListTile(
                          onTap: () => Navigator.pop(context, item),
                          leading: CircleAvatar(
                            backgroundColor: status.color.withOpacity(.12),
                            child: Text(
                              (name.isEmpty ? 'Т' : name.substring(0, 1)).toUpperCase(),
                              style: TextStyle(color: status.color, fontWeight: FontWeight.w800),
                            ),
                          ),
                          title: Text(name.isEmpty ? 'Без названия' : name, maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text(
                            code.isEmpty ? '${item['category'] ?? 'Без категории'}' : 'Код: $code',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          trailing: Text(
                            '${stockQuantity(item['stock'])} ${item['unit'] ?? ''}'.trim(),
                            style: TextStyle(color: status.color, fontWeight: FontWeight.w800),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
