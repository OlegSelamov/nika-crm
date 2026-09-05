import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/stock_widgets.dart';
import 'income_screen.dart';
import 'movements_screen.dart';
import 'writeoff_screen.dart';

class StockScreen extends StatefulWidget {
  const StockScreen({super.key});

  @override
  State<StockScreen> createState() => _StockScreenState();
}

class _StockScreenState extends State<StockScreen> {
  final searchController = TextEditingController();
  bool loading = true;
  String? error;
  List<Map<String, dynamic>> items = [];
  String statusFilter = 'all';
  String categoryFilter = 'all';
  String sort = 'name';

  @override
  void initState() {
    super.initState();
    loadStock();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  Future<void> loadStock() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.getStock();
      if (!mounted) return;
      setState(() {
        items = data.map((item) => Map<String, dynamic>.from(item as Map)).toList();
        if (categoryFilter != 'all' && !categories.contains(categoryFilter)) categoryFilter = 'all';
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  List<String> get categories {
    final values = items
        .map((item) => '${item['category'] ?? ''}'.trim())
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList()..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
    return values;
  }

  int _statusCount(String key) => items.where((item) => key == 'all' || stockStatus(item['stock']).key == key).length;

  List<Map<String, dynamic>> get filteredItems {
    final needle = searchController.text.trim().toLowerCase();
    final result = items.where((item) {
      final matchesSearch = needle.isEmpty || [
        item['name'], item['category'], item['unit'], item['barcode'], item['gtin'], item['ntin'],
      ].join(' ').toLowerCase().contains(needle);
      final matchesCategory = categoryFilter == 'all' || '${item['category'] ?? ''}' == categoryFilter;
      final matchesStatus = statusFilter == 'all' || stockStatus(item['stock']).key == statusFilter;
      return matchesSearch && matchesCategory && matchesStatus;
    }).toList();

    result.sort((a, b) {
      final nameA = '${a['name'] ?? ''}'.toLowerCase();
      final nameB = '${b['name'] ?? ''}'.toLowerCase();
      switch (sort) {
        case 'stock-asc':
          return stockNumber(a['stock']).compareTo(stockNumber(b['stock']));
        case 'stock-desc':
          return stockNumber(b['stock']).compareTo(stockNumber(a['stock']));
        case 'retail-asc':
          return stockNumber(a['retail_price']).compareTo(stockNumber(b['retail_price']));
        case 'retail-desc':
          return stockNumber(b['retail_price']).compareTo(stockNumber(a['retail_price']));
        default:
          return nameA.compareTo(nameB);
      }
    });
    return result;
  }

  double get purchaseValue => items.fold<double>(0, (sum, item) => sum + stockNumber(item['stock']) * stockNumber(item['purchase_price']));
  double get retailValue => items.fold<double>(0, (sum, item) => sum + stockNumber(item['stock']) * stockNumber(item['retail_price']));

  Future<void> _openOperation(Widget screen, {bool refreshAfter = false}) async {
    final changed = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => screen));
    if (refreshAfter && changed == true) await loadStock();
  }

  Widget _metric(String title, String value, IconData icon, Color color) => SizedBox(
        width: 158,
        child: MetricCard(title: title, value: value, icon: icon, color: color),
      );

  Widget _statusChip(String value, String label) => ChoiceChip(
        selected: statusFilter == value,
        onSelected: (_) => setState(() => statusFilter = value),
        label: Text('$label ${_statusCount(value)}'),
      );

  Widget _stockCard(Map<String, dynamic> item) {
    final status = stockStatus(item['stock']);
    final unit = '${item['unit'] ?? ''}';
    final barcode = '${item['barcode'] ?? ''}'.trim();
    final quantity = stockNumber(item['stock']);
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(color: status.color.withOpacity(.12), borderRadius: BorderRadius.circular(15)),
                  child: Icon(Icons.inventory_2_outlined, color: status.color),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${item['name'] ?? 'Без названия'}', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                      const SizedBox(height: 3),
                      Text('${item['category'] ?? 'Без категории'}${barcode.isEmpty ? '' : ' · $barcode'}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                    ],
                  ),
                ),
                StatusPill(status.label, color: status.color),
              ],
            ),
            const Divider(height: 28),
            Wrap(
              spacing: 22,
              runSpacing: 12,
              children: [
                _detail('Остаток', '${stockQuantity(quantity)} $unit'.trim(), status.color),
                _detail('Закупочная цена', money(item['purchase_price']), AppColors.text),
                _detail('Розничная цена', money(item['retail_price']), AppColors.text),
                _detail('Стоимость остатка', money(quantity * stockNumber(item['purchase_price'])), AppColors.primary),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _detail(String label, String value, Color color) => SizedBox(
        width: 145,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 11)),
            const SizedBox(height: 3),
            Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w800)),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(icon: Icons.warehouse_outlined, title: 'Склад недоступен', message: error!, onAction: loadStock);
    }

    final visible = filteredItems;
    return AdaptiveContent(
      child: RefreshIndicator(
        onRefresh: loadStock,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
          children: [
            const SectionTitle('Склад', subtitle: 'Остатки и операции только по товарам'),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(13),
              decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(16)),
              child: const Row(
                children: [
                  Icon(Icons.info_outline, color: AppColors.primary),
                  SizedBox(width: 10),
                  Expanded(child: Text('Услуги не имеют складского остатка и не участвуют в приходах и списаниях.', style: TextStyle(color: AppColors.text, fontSize: 13))),
                ],
              ),
            ),
            const SizedBox(height: 14),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  ElevatedButton.icon(
                    onPressed: () => _openOperation(const IncomeScreen(), refreshAfter: true),
                    icon: const Icon(Icons.add_box_outlined),
                    label: const Text('Приход товара'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: () => _openOperation(const WriteoffScreen(), refreshAfter: true),
                    icon: const Icon(Icons.remove_circle_outline),
                    label: const Text('Списание'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: () => _openOperation(const MovementsScreen()),
                    icon: const Icon(Icons.swap_horiz_rounded),
                    label: const Text('Движение товара'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 136,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  _metric('Всего товаров', '${items.length}', Icons.inventory_2_outlined, AppColors.primary),
                  const SizedBox(width: 10),
                  _metric('В наличии', '${_statusCount('normal')}', Icons.check_circle_outline, AppColors.success),
                  const SizedBox(width: 10),
                  _metric('Заканчиваются', '${_statusCount('low')}', Icons.warning_amber_rounded, AppColors.warning),
                  const SizedBox(width: 10),
                  _metric('Нет в наличии', '${_statusCount('out')}', Icons.cancel_outlined, AppColors.danger),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: _valueCard('Закупочная стоимость', purchaseValue, AppColors.cyan)),
                const SizedBox(width: 10),
                Expanded(child: _valueCard('Розничная стоимость', retailValue, AppColors.primary)),
              ],
            ),
            const SizedBox(height: 18),
            TextField(
              controller: searchController,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                hintText: 'Название, категория или код товара',
                prefixIcon: Icon(Icons.search),
              ),
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _statusChip('all', 'Все'),
                  const SizedBox(width: 8),
                  _statusChip('normal', 'В наличии'),
                  const SizedBox(width: 8),
                  _statusChip('low', 'Заканчиваются'),
                  const SizedBox(width: 8),
                  _statusChip('out', 'Нет в наличии'),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: categoryFilter,
                    decoration: const InputDecoration(labelText: 'Категория'),
                    items: [
                      const DropdownMenuItem(value: 'all', child: Text('Все категории')),
                      ...categories.map((value) => DropdownMenuItem(value: value, child: Text(value, overflow: TextOverflow.ellipsis))),
                    ],
                    onChanged: (value) => setState(() => categoryFilter = value ?? 'all'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: sort,
                    decoration: const InputDecoration(labelText: 'Сортировка'),
                    items: const [
                      DropdownMenuItem(value: 'name', child: Text('По названию')),
                      DropdownMenuItem(value: 'stock-asc', child: Text('Остаток ↑')),
                      DropdownMenuItem(value: 'stock-desc', child: Text('Остаток ↓')),
                      DropdownMenuItem(value: 'retail-asc', child: Text('Цена ↑')),
                      DropdownMenuItem(value: 'retail-desc', child: Text('Цена ↓')),
                    ],
                    onChanged: (value) => setState(() => sort = value ?? 'name'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            SectionTitle('Остатки', subtitle: 'Показано ${visible.length} из ${items.length}'),
            const SizedBox(height: 10),
            if (visible.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 36),
                child: Center(child: Text('Товары по выбранным условиям не найдены', style: TextStyle(color: AppColors.muted))),
              )
            else
              ...visible.map(_stockCard),
          ],
        ),
      ),
    );
  }

  Widget _valueCard(String label, double value, Color color) => Card(
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.account_balance_wallet_outlined, color: color),
              const SizedBox(height: 12),
              Text(
                money(value),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 3),
              Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 11)),
            ],
          ),
        ),
      );
}
