import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'category_management_screen.dart';
import 'scanner_screen.dart';

class AddItemScreen extends StatefulWidget {
  final Map<String, dynamic>? item;

  const AddItemScreen({super.key, this.item});

  bool get isEditing => item != null;

  @override
  State<AddItemScreen> createState() => _AddItemScreenState();
}

class _AddItemScreenState extends State<AddItemScreen> {
  final _formKey = GlobalKey<FormState>();
  final nameController = TextEditingController();
  final barcodeController = TextEditingController();
  final purchaseController = TextEditingController();
  final wholesaleController = TextEditingController();
  final retailController = TextEditingController();
  final discountController = TextEditingController();
  final qtyController = TextEditingController();
  final descriptionController = TextEditingController();
  final gtinController = TextEditingController();
  final ntinController = TextEditingController();

  String itemType = 'product';
  String unit = 'шт';
  String category = '';
  double categoryMarkup = 0;
  String serviceSaleMode = 'order';
  String _priceCalculationSource = 'purchase';
  bool _suppressPriceCalculation = false;
  bool isMarked = false;
  bool loading = false;
  bool categoriesLoading = true;
  List<Map<String, dynamic>> categories = [];

  static const units = [
    'шт', 'пар', 'компл', 'набор', 'упак', 'пач', 'кор', 'бут', 'кан', 'рул',
    'кг', 'г', 'т', 'л', 'мл', 'м', 'см', 'мм', 'м²', 'м³',
    'час', 'день', 'неделя', 'месяц', 'год', 'смена',
    'услуга', 'человек', 'место', 'пассажир', 'рейс', 'тур',
  ];

  @override
  void initState() {
    super.initState();
    final item = widget.item;
    if (item != null) {
      itemType = item['item_type'] == 'service' ? 'service' : 'product';
      nameController.text = '${item['name'] ?? ''}';
      barcodeController.text = '${item['barcode'] ?? ''}';
      purchaseController.text = _number(item['purchase_price']);
      wholesaleController.text = _number(item['wholesale_price']);
      retailController.text = _number(item['retail_price']);
      discountController.text = _number(item['discount_percent']);
      qtyController.text = _number(item['quantity']);
      descriptionController.text = '${item['description'] ?? ''}';
      gtinController.text = '${item['gtin'] ?? ''}';
      ntinController.text = '${item['ntin'] ?? ''}';
      isMarked = item['is_marked'] == true;
      serviceSaleMode = ['order', 'booking', 'request'].contains(item['service_sale_mode'])
          ? '${item['service_sale_mode']}'
          : 'order';
      final itemUnit = '${item['unit'] ?? ''}';
      unit = units.contains(itemUnit) ? itemUnit : (itemType == 'service' ? 'услуга' : 'шт');
      category = '${item['category'] ?? ''}';
    } else {
      qtyController.text = '0';
      purchaseController.text = '0';
      wholesaleController.text = '0';
      retailController.text = '0';
      discountController.text = '0';
    }
    purchaseController.addListener(_onPurchaseChanged);
    retailController.addListener(_onRetailChanged);
    _loadCategories();
  }

  static String _number(dynamic value) {
    final number = double.tryParse('${value ?? 0}') ?? 0;
    return number == number.roundToDouble() ? number.toInt().toString() : number.toString();
  }

  @override
  void dispose() {
    nameController.dispose();
    barcodeController.dispose();
    purchaseController.dispose();
    wholesaleController.dispose();
    retailController.dispose();
    discountController.dispose();
    qtyController.dispose();
    descriptionController.dispose();
    gtinController.dispose();
    ntinController.dispose();
    super.dispose();
  }

  double _categoryMarkup(String categoryName, List<Map<String, dynamic>> values) {
    for (final item in values) {
      if ('${item['name'] ?? ''}' == categoryName) {
        return double.tryParse('${item['markup_percent'] ?? 0}') ?? 0;
      }
    }
    return 0;
  }

  String _formatMarkup(double value) =>
      value == value.roundToDouble() ? value.toInt().toString() : value.toString();

  String _roundPrice(double value) => value.ceil().toString();

  void _replaceControllerText(TextEditingController controller, String text) {
    if (controller.text == text) return;
    _suppressPriceCalculation = true;
    controller.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    _suppressPriceCalculation = false;
  }

  void _calculatePurchasePrice() {
    if (_suppressPriceCalculation || itemType == 'service') return;
    final retail = _double(retailController);
    if (retail <= 0) {
      _replaceControllerText(purchaseController, '');
      return;
    }
    final divisor = 1 + categoryMarkup / 100;
    final purchase = divisor > 0 ? retail / divisor : retail;
    _replaceControllerText(purchaseController, _roundPrice(purchase));
  }

  void _calculateRetailPrice() {
    if (_suppressPriceCalculation || itemType == 'service') return;
    final purchase = _double(purchaseController);
    if (purchase <= 0) {
      _replaceControllerText(retailController, '');
      return;
    }
    final retail = purchase * (1 + categoryMarkup / 100);
    _replaceControllerText(retailController, _roundPrice(retail));
  }

  void _recalculatePricesByLastSource() {
    if (_priceCalculationSource == 'retail') {
      _calculatePurchasePrice();
    } else {
      _calculateRetailPrice();
    }
  }

  void _onPurchaseChanged() {
    if (_suppressPriceCalculation || itemType == 'service') return;
    _priceCalculationSource = 'purchase';
    _calculateRetailPrice();
  }

  void _onRetailChanged() {
    if (_suppressPriceCalculation || itemType == 'service') return;
    _priceCalculationSource = 'retail';
    _calculatePurchasePrice();
  }

  Future<void> _loadCategories({bool recalculatePrices = false}) async {
    if (mounted) setState(() => categoriesLoading = true);
    try {
      final data = await ApiService.getCategories(type: itemType);
      if (!mounted) return;
      final loaded = data.map((item) => Map<String, dynamic>.from(item as Map)).toList();
      if (category.isNotEmpty && !loaded.any((item) => item['name'] == category)) {
        loaded.insert(0, {'id': 0, 'name': category, 'category_type': itemType, 'markup_percent': 0});
      }
      setState(() {
        categories = loaded;
        categoryMarkup = itemType == 'product' ? _categoryMarkup(category, loaded) : 0;
        categoriesLoading = false;
      });
      if (recalculatePrices) _recalculatePricesByLastSource();
    } catch (_) {
      if (mounted) setState(() => categoriesLoading = false);
    }
  }

  void _setType(String type) {
    if (itemType == type) return;
    setState(() {
      itemType = type;
      category = '';
      categoryMarkup = 0;
      if (type == 'service') {
        unit = 'услуга';
        isMarked = false;
        gtinController.clear();
        ntinController.clear();
      } else if (unit == 'услуга') {
        unit = 'шт';
      }
    });
    _loadCategories();
  }

  Future<void> _openCategories() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => CategoryManagementScreen(initialType: itemType)),
    );
    if (mounted) _loadCategories(recalculatePrices: true);
  }

  void _selectCategory(String? value) {
    final selected = value ?? '';
    setState(() {
      category = selected;
      categoryMarkup = itemType == 'product' ? _categoryMarkup(selected, categories) : 0;
    });
    _recalculatePricesByLastSource();
  }

  Future<void> _scanBarcode() async {
    final barcode = await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ScannerScreen()),
    );
    if (barcode == null) return;
    barcodeController.text = barcode.toString();
    await _lookupBarcode();
  }

  Future<void> _lookupBarcode() async {
    final barcode = barcodeController.text.trim();
    if (barcode.isEmpty) return;
    setState(() => loading = true);
    try {
      final info = await ApiService.getBarcodeInfo(barcode, itemType: itemType);
      if (!mounted) return;
      if (info['found'] == true) {
        if (nameController.text.trim().isEmpty) nameController.text = '${info['name'] ?? ''}';
        if (category.isEmpty && '${info['category'] ?? ''}'.isNotEmpty) {
          category = '${info['category']}';
          categoryMarkup = itemType == 'product' ? _categoryMarkup(category, categories) : 0;
        }
        if (retailController.text == '0' && info['price'] != null) retailController.text = _number(info['price']);
        if (itemType == 'product') {
          gtinController.text = '${info['gtin'] ?? gtinController.text}';
          ntinController.text = '${info['ntin'] ?? ntinController.text}';
          isMarked = info['is_marked'] == true;
          final measure = '${info['measure'] ?? ''}';
          if (units.contains(measure)) unit = measure;
        }
        setState(() {});
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Данные позиции найдены')));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(itemType == 'service' ? 'Услуга не найдена' : 'Товар не найден в НацКаталоге')));
      }
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  double _double(TextEditingController controller) =>
      double.tryParse(controller.text.replaceAll(',', '.')) ?? 0;

  Map<String, dynamic> get _payload => {
        'name': nameController.text.trim(),
        'barcode': barcodeController.text.trim(),
        'purchase_price': _double(purchaseController),
        'wholesale_price': _double(wholesaleController),
        'retail_price': _double(retailController),
        'discount_percent': _double(discountController).round(),
        'quantity': _double(qtyController),
        'category': category,
        'unit': unit,
        'description': descriptionController.text.trim(),
        'gtin': itemType == 'product' ? gtinController.text.trim() : '',
        'ntin': itemType == 'product' ? ntinController.text.trim() : '',
        'is_marked': itemType == 'product' && isMarked,
        'item_type': itemType,
        'service_sale_mode': itemType == 'service' ? serviceSaleMode : null,
      };

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => loading = true);
    try {
      if (widget.isEditing) {
        await ApiService.updateItem(widget.item!['id'] as int, _payload);
      } else {
        await ApiService.createItem(
          name: nameController.text.trim(),
          barcode: barcodeController.text.trim(),
          purchasePrice: _double(purchaseController),
          wholesalePrice: _double(wholesaleController),
          retailPrice: _double(retailController),
          discountPercent: _double(discountController).round(),
          quantity: _double(qtyController),
          category: category,
          unit: unit,
          description: descriptionController.text.trim(),
          gtin: gtinController.text.trim(),
          ntin: ntinController.text.trim(),
          isMarked: isMarked,
          itemType: itemType,
          serviceSaleMode: serviceSaleMode,
        );
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.isEditing ? 'Изменения сохранены' : itemType == 'service' ? 'Услуга добавлена' : 'Товар добавлен')),
      );
      Navigator.pop(context, true);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Widget _field(
    String label,
    TextEditingController controller, {
    TextInputType type = TextInputType.text,
    int maxLines = 1,
    bool readOnly = false,
    String? Function(String?)? validator,
    Widget? suffixIcon,
  }) =>
      TextFormField(
        controller: controller,
        keyboardType: type,
        maxLines: maxLines,
        readOnly: readOnly,
        validator: validator,
        decoration: InputDecoration(labelText: label, suffixIcon: suffixIcon),
      );

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.isEditing ? 'Изменить позицию' : 'Добавить позицию')),
        body: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'product', label: Text('Товар'), icon: Icon(Icons.inventory_2_outlined)),
                  ButtonSegment(value: 'service', label: Text('Услуга'), icon: Icon(Icons.design_services_outlined)),
                ],
                selected: {itemType},
                onSelectionChanged: (value) => _setType(value.first),
              ),
              if (itemType == 'service') ...[
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  value: serviceSaleMode,
                  decoration: const InputDecoration(labelText: 'Продажа на витрине'),
                  items: const [
                    DropdownMenuItem(value: 'order', child: Text('Заказать онлайн')),
                    DropdownMenuItem(value: 'booking', child: Text('Онлайн-запись')),
                    DropdownMenuItem(value: 'request', child: Text('Оставить заявку')),
                  ],
                  onChanged: (value) => setState(() => serviceSaleMode = value ?? 'order'),
                ),
              ],
              const SizedBox(height: 16),
              Row(children: [
                Expanded(child: _field('Штрихкод', barcodeController, type: TextInputType.number, suffixIcon: IconButton(icon: const Icon(Icons.search), onPressed: loading ? null : _lookupBarcode))),
                const SizedBox(width: 8),
                IconButton.filledTonal(onPressed: loading ? null : _scanBarcode, icon: const Icon(Icons.qr_code_scanner)),
              ]),
              const SizedBox(height: 16),
              _field(
                itemType == 'service' ? 'Наименование услуги *' : 'Название товара *',
                nameController,
                validator: (value) => value == null || value.trim().isEmpty ? 'Укажите название' : null,
              ),
              const SizedBox(height: 16),
              _field(itemType == 'service' ? 'Описание услуги' : 'Описание товара', descriptionController, maxLines: 4),
              const SizedBox(height: 16),
              Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: categories.any((item) => '${item['name']}' == category) ? category : null,
                    decoration: InputDecoration(
                      labelText: 'Категория',
                      helperText: categoriesLoading
                          ? 'Загрузка…'
                          : itemType == 'product' && category.isNotEmpty
                              ? 'Наценка категории: ${_formatMarkup(categoryMarkup)}%'
                              : null,
                    ),
                    items: categories.map((item) {
                      final name = '${item['name']}';
                      final markup = double.tryParse('${item['markup_percent'] ?? 0}') ?? 0;
                      return DropdownMenuItem(
                        value: name,
                        child: Text(
                          itemType == 'product' ? '$name (${_formatMarkup(markup)}%)' : name,
                          overflow: TextOverflow.ellipsis,
                        ),
                      );
                    }).toList(),
                    onChanged: _selectCategory,
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(onPressed: _openCategories, icon: const Icon(Icons.category_outlined)),
              ]),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                value: unit,
                decoration: const InputDecoration(labelText: 'Единица измерения'),
                items: units.map((value) => DropdownMenuItem(value: value, child: Text(value))).toList(),
                onChanged: (value) => setState(() => unit = value ?? 'шт'),
              ),
              if (itemType == 'product') ...[
                const SizedBox(height: 16),
                _field('GTIN', gtinController),
                const SizedBox(height: 16),
                _field('NTIN', ntinController),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Маркируемый товар'),
                  subtitle: Text(isMarked ? 'Маркировка обязательна' : 'Обычный товар'),
                  value: isMarked,
                  onChanged: (value) => setState(() => isMarked = value),
                ),
              ],
              const SizedBox(height: 8),
              _field(itemType == 'service' ? 'Закупочная стоимость, ₸' : 'Закупочная цена, ₸', purchaseController, type: const TextInputType.numberWithOptions(decimal: true)),
              const SizedBox(height: 16),
              _field('Оптовая цена, ₸', wholesaleController, type: const TextInputType.numberWithOptions(decimal: true)),
              const SizedBox(height: 16),
              _field(itemType == 'service' ? 'Цена услуги, ₸ *' : 'Розничная цена, ₸ *', retailController, type: const TextInputType.numberWithOptions(decimal: true)),
              const SizedBox(height: 16),
              _field('Скидка, %', discountController, type: TextInputType.number),
              if (itemType == 'product') ...[
                const SizedBox(height: 16),
                _field(
                  widget.isEditing ? 'Текущий остаток' : 'Начальный остаток',
                  qtyController,
                  type: const TextInputType.numberWithOptions(decimal: true),
                  readOnly: widget.isEditing,
                ),
                if (widget.isEditing)
                  const Padding(
                    padding: EdgeInsets.only(top: 6),
                    child: Text('Остаток изменяется через складские операции.', style: TextStyle(color: AppColors.muted, fontSize: 12)),
                  ),
              ],
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: loading ? null : _save,
                icon: loading
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                    : const Icon(Icons.save_outlined),
                label: Text(widget.isEditing ? 'Сохранить изменения' : itemType == 'service' ? 'Сохранить услугу' : 'Сохранить товар'),
              ),
            ],
          ),
        ),
      );
}
