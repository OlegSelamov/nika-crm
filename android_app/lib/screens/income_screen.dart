import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/stock_widgets.dart';
import 'movements_screen.dart';
import 'scanner_screen.dart';

class IncomeScreen extends StatefulWidget {
  const IncomeScreen({super.key});

  @override
  State<IncomeScreen> createState() => _IncomeScreenState();
}

class _IncomeScreenState extends State<IncomeScreen> {
  final formKey = GlobalKey<FormState>();
  final qtyController = TextEditingController();
  final priceController = TextEditingController();
  final commentController = TextEditingController();
  List<Map<String, dynamic>> items = [];
  List<Map<String, dynamic>> recent = [];
  Map<String, dynamic>? selectedItem;
  bool loading = true;
  bool saving = false;
  String? error;

  @override
  void initState() {
    super.initState();
    qtyController.addListener(_refreshSummary);
    priceController.addListener(_refreshSummary);
    loadData();
  }

  @override
  void dispose() {
    qtyController.dispose();
    priceController.dispose();
    commentController.dispose();
    super.dispose();
  }

  void _refreshSummary() {
    if (mounted) setState(() {});
  }

  Future<void> loadData() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final results = await Future.wait([
        ApiService.getStock(),
        ApiService.getStockMovements(),
      ]);
      if (!mounted) return;
      final stock = results[0].map((item) => Map<String, dynamic>.from(item as Map)).toList();
      final movements = results[1]
          .map((item) => Map<String, dynamic>.from(item as Map))
          .where((item) => item['movement_type'] == 'income')
          .take(30)
          .toList();
      setState(() {
        items = stock;
        recent = movements;
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  void _selectItem(Map<String, dynamic> item) {
    setState(() => selectedItem = item);
    final previousPrice = stockNumber(item['purchase_price']);
    if (previousPrice > 0) priceController.text = stockQuantity(previousPrice);
  }

  Future<void> _pickItem() async {
    final picked = await showStockProductPicker(
      context,
      items: items,
      selectedId: selectedItem == null ? null : stockNumber(selectedItem!['id']).toInt(),
    );
    if (picked != null) _selectItem(picked);
  }

  Future<void> scanBarcode() async {
    final barcode = await Navigator.push(context, MaterialPageRoute(builder: (_) => const ScannerScreen()));
    if (barcode == null || !mounted) return;
    final code = barcode.toString().trim();
    Map<String, dynamic>? found;
    for (final item in items) {
      if ([item['barcode'], item['gtin'], item['ntin']].any((value) => '${value ?? ''}'.trim() == code)) {
        found = item;
        break;
      }
    }
    if (found == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Товар с кодом $code не найден')));
      return;
    }
    _selectItem(found);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Найден товар: ${found['name']}')));
  }

  double get quantity => stockNumber(qtyController.text.replaceAll(',', '.'));
  double get price => stockNumber(priceController.text.replaceAll(',', '.'));
  double get total => quantity * price;

  Future<void> save() async {
    if (selectedItem == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Сначала выберите товар')));
      return;
    }
    if (!formKey.currentState!.validate() || saving) return;
    setState(() => saving = true);
    try {
      await ApiService.stockIncome(
        itemId: stockNumber(selectedItem!['id']).toInt(),
        quantity: quantity,
        price: price,
        comment: commentController.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Приход проведён')));
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Widget _selectedProduct() {
    final item = selectedItem!;
    final status = stockStatus(item['stock']);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: status.color.withOpacity(.12),
              child: Icon(Icons.inventory_2_outlined, color: status.color),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${item['name'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w800)),
                  Text(
                    'Текущий остаток: ${stockQuantity(item['stock'])} ${item['unit'] ?? ''}',
                    style: const TextStyle(color: AppColors.muted, fontSize: 12),
                  ),
                ],
              ),
            ),
            IconButton(onPressed: _pickItem, icon: const Icon(Icons.edit_outlined)),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Приход товара'),
        actions: [
          IconButton(
            tooltip: 'Движение товара',
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const MovementsScreen(initialType: 'income'))),
            icon: const Icon(Icons.history_rounded),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? ScreenStateView(icon: Icons.add_box_outlined, title: 'Товары недоступны', message: error!, onAction: loadData)
              : AdaptiveContent(
                  child: Form(
                    key: formKey,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
                      children: [
                        const SectionTitle('Новое поступление', subtitle: 'Остаток увеличится, операция попадёт в движение товара'),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(
                              child: ElevatedButton.icon(
                                onPressed: items.isEmpty ? null : _pickItem,
                                icon: const Icon(Icons.search),
                                label: Text(selectedItem == null ? 'Выбрать товар' : 'Сменить товар'),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton.filledTonal(onPressed: scanBarcode, icon: const Icon(Icons.qr_code_scanner)),
                          ],
                        ),
                        if (selectedItem != null) ...[
                          const SizedBox(height: 12),
                          _selectedProduct(),
                        ],
                        if (items.isEmpty)
                          const Padding(
                            padding: EdgeInsets.only(top: 12),
                            child: Text('В каталоге пока нет товаров. Услуги для прихода не показываются.', style: TextStyle(color: AppColors.muted)),
                          ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: qtyController,
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: InputDecoration(labelText: 'Количество', suffixText: '${selectedItem?['unit'] ?? ''}'),
                                validator: (value) => stockNumber((value ?? '').replaceAll(',', '.')) <= 0 ? 'Больше нуля' : null,
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: TextFormField(
                                controller: priceController,
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: const InputDecoration(labelText: 'Закупочная цена', suffixText: '₸'),
                                validator: (value) => stockNumber((value ?? '').replaceAll(',', '.')) < 0 ? 'Не меньше нуля' : null,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: commentController,
                          maxLines: 3,
                          decoration: const InputDecoration(labelText: 'Комментарий', hintText: 'Поставщик, накладная или примечание'),
                        ),
                        const SizedBox(height: 16),
                        Card(
                          color: AppColors.primarySoft,
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Row(
                              children: [
                                Expanded(child: _summaryValue('Количество', stockQuantity(quantity))),
                                Expanded(child: _summaryValue('Цена', money(price))),
                                Expanded(child: _summaryValue('Итого приход', money(total), accent: true)),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 18),
                        ElevatedButton.icon(
                          onPressed: saving ? null : save,
                          icon: saving
                              ? const SizedBox(width: 19, height: 19, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                              : const Icon(Icons.check_circle_outline),
                          label: const Text('Провести приход'),
                        ),
                        const SizedBox(height: 28),
                        SectionTitle('Последние приходы', subtitle: '${recent.length} операций'),
                        const SizedBox(height: 10),
                        if (recent.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 24),
                            child: Center(child: Text('Приходов пока нет', style: TextStyle(color: AppColors.muted))),
                          )
                        else
                          ...recent.take(10).map(_historyCard),
                      ],
                    ),
                  ),
                ),
    );
  }

  Widget _summaryValue(String label, String value, {bool accent = false}) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 10)),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: accent ? AppColors.primary : AppColors.text, fontWeight: FontWeight.w900, fontSize: accent ? 15 : 13),
          ),
        ],
      );

  Widget _historyCard(Map<String, dynamic> row) => Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: ListTile(
          leading: const CircleAvatar(
            backgroundColor: Color(0xFFE9F8F1),
            child: Icon(Icons.south_rounded, color: AppColors.success),
          ),
          title: Text('${row['item_name'] ?? 'Товар'}', style: const TextStyle(fontWeight: FontWeight.w700)),
          subtitle: Text('${stockQuantity(row['quantity'])} × ${money(row['price'])} · ${stockDateTime(row['created_at'])}'),
          trailing: Text(money(row['total']), style: const TextStyle(fontWeight: FontWeight.w900, color: AppColors.success)),
        ),
      );
}
