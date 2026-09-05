import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/stock_widgets.dart';
import 'movements_screen.dart';
import 'scanner_screen.dart';

class WriteoffScreen extends StatefulWidget {
  const WriteoffScreen({super.key});

  @override
  State<WriteoffScreen> createState() => _WriteoffScreenState();
}

class _WriteoffScreenState extends State<WriteoffScreen> {
  static const reasons = [
    'Истёк срок годности',
    'Повреждение товара',
    'Брак',
    'Недостача',
    'Использовано для нужд компании',
    'Другое',
  ];

  final formKey = GlobalKey<FormState>();
  final qtyController = TextEditingController();
  final commentController = TextEditingController();
  List<Map<String, dynamic>> items = [];
  Map<String, dynamic>? selectedItem;
  String? reason;
  String? autoReason;
  bool loading = true;
  bool saving = false;
  String? error;

  @override
  void initState() {
    super.initState();
    qtyController.addListener(_refreshSummary);
    loadItems();
  }

  @override
  void dispose() {
    qtyController.dispose();
    commentController.dispose();
    super.dispose();
  }

  void _refreshSummary() {
    if (mounted) setState(() {});
  }

  Future<void> loadItems() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.getStock();
      if (!mounted) return;
      setState(() {
        items = data.map((item) => Map<String, dynamic>.from(item as Map)).toList();
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  void _selectItem(Map<String, dynamic> item) {
    setState(() => selectedItem = item);
    qtyController.clear();
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

  double get currentStock => stockNumber(selectedItem?['stock']);
  double get quantity => stockNumber(qtyController.text.replaceAll(',', '.'));
  double get remaining => currentStock - quantity;
  bool get exceedsStock => quantity > currentStock;

  void _setQuickQuantity(double value) {
    qtyController.text = stockQuantity(value.clamp(0, currentStock));
  }

  void _setReason(String? value) {
    setState(() => reason = value);
    if (value == null || value == 'Другое') return;
    if (commentController.text.trim().isEmpty || commentController.text == autoReason) {
      commentController.text = value;
      autoReason = value;
    }
  }

  Future<void> save() async {
    if (selectedItem == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Сначала выберите товар')));
      return;
    }
    if (!formKey.currentState!.validate() || saving) return;
    if (currentStock <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('У выбранного товара нет доступного остатка')));
      return;
    }
    if (exceedsStock) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Нельзя списать больше текущего остатка')));
      return;
    }
    setState(() => saving = true);
    try {
      await ApiService.stockWriteoff(
        itemId: stockNumber(selectedItem!['id']).toInt(),
        quantity: quantity,
        comment: commentController.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Списание проведено')));
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
                    'Доступно: ${stockQuantity(item['stock'])} ${item['unit'] ?? ''}',
                    style: TextStyle(color: status.color, fontSize: 12, fontWeight: FontWeight.w700),
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
        title: const Text('Списание товара'),
        actions: [
          IconButton(
            tooltip: 'История списаний',
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const MovementsScreen(initialType: 'writeoff'))),
            icon: const Icon(Icons.history_rounded),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? ScreenStateView(icon: Icons.remove_circle_outline, title: 'Товары недоступны', message: error!, onAction: loadItems)
              : AdaptiveContent(
                  child: Form(
                    key: formKey,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
                      children: [
                        const SectionTitle('Новое списание', subtitle: 'Списание сразу уменьшит фактический остаток товара'),
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
                            child: Text('В каталоге пока нет товаров. Услуги для списания не показываются.', style: TextStyle(color: AppColors.muted)),
                          ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: qtyController,
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          decoration: InputDecoration(
                            labelText: 'Количество для списания',
                            suffixText: '${selectedItem?['unit'] ?? ''}',
                            errorText: exceedsStock ? 'Превышает доступный остаток' : null,
                          ),
                          validator: (value) => stockNumber((value ?? '').replaceAll(',', '.')) <= 0 ? 'Количество должно быть больше нуля' : null,
                        ),
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            ActionChip(label: const Text('1'), onPressed: selectedItem == null ? null : () => _setQuickQuantity(1)),
                            ActionChip(label: const Text('5'), onPressed: selectedItem == null ? null : () => _setQuickQuantity(5)),
                            ActionChip(label: const Text('10'), onPressed: selectedItem == null ? null : () => _setQuickQuantity(10)),
                            ActionChip(label: const Text('Весь остаток'), onPressed: selectedItem == null ? null : () => _setQuickQuantity(currentStock)),
                          ],
                        ),
                        const SizedBox(height: 16),
                        DropdownButtonFormField<String>(
                          value: reason,
                          decoration: const InputDecoration(labelText: 'Причина списания'),
                          items: reasons.map((value) => DropdownMenuItem(value: value, child: Text(value, overflow: TextOverflow.ellipsis))).toList(),
                          onChanged: _setReason,
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: commentController,
                          maxLines: 3,
                          onChanged: (_) => autoReason = null,
                          decoration: const InputDecoration(labelText: 'Комментарий или причина *', hintText: 'Подробно опишите причину списания'),
                          validator: (value) => value == null || value.trim().isEmpty ? 'Укажите причину списания' : null,
                        ),
                        const SizedBox(height: 16),
                        Card(
                          color: exceedsStock ? const Color(0xFFFFEEEE) : AppColors.primarySoft,
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Row(
                              children: [
                                Expanded(child: _summaryValue('Текущий остаток', stockQuantity(currentStock))),
                                Expanded(child: _summaryValue('Будет списано', stockQuantity(quantity))),
                                Expanded(child: _summaryValue('Останется', stockQuantity(remaining), accent: true, danger: remaining < 0)),
                              ],
                            ),
                          ),
                        ),
                        if (exceedsStock) ...[
                          const SizedBox(height: 10),
                          const Text('Количество списания превышает доступный остаток.', style: TextStyle(color: AppColors.danger, fontWeight: FontWeight.w700)),
                        ],
                        const SizedBox(height: 18),
                        ElevatedButton.icon(
                          onPressed: saving ? null : save,
                          icon: saving
                              ? const SizedBox(width: 19, height: 19, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                              : const Icon(Icons.remove_circle_outline),
                          label: const Text('Списать товар'),
                        ),
                      ],
                    ),
                  ),
                ),
    );
  }

  Widget _summaryValue(String label, String value, {bool accent = false, bool danger = false}) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 10)),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: danger ? AppColors.danger : accent ? AppColors.primary : AppColors.text,
              fontWeight: FontWeight.w900,
              fontSize: accent ? 16 : 14,
            ),
          ),
        ],
      );
}
