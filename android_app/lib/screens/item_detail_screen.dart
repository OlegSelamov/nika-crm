import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'add_item_screen.dart';

class ItemDetailScreen extends StatefulWidget {
  final Map<String, dynamic> item;

  const ItemDetailScreen({super.key, required this.item});

  @override
  State<ItemDetailScreen> createState() => _ItemDetailScreenState();
}

class _ItemDetailScreenState extends State<ItemDetailScreen> {
  late Map<String, dynamic> item;

  bool get isService => item['item_type'] == 'service';

  @override
  void initState() {
    super.initState();
    item = Map<String, dynamic>.from(widget.item);
  }

  String value(String key) {
    final text = '${item[key] ?? ''}'.trim();
    return text.isEmpty ? '—' : text;
  }

  Future<void> _edit() async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => AddItemScreen(item: item)),
    );
    if (changed == true && mounted) Navigator.pop(context, true);
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Удалить ${isService ? 'услугу' : 'товар'}?'),
        content: Text('«${item['name']}» будет удалено из каталога.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Удалить')),
        ],
      ),
    ) ?? false;
    if (!confirmed) return;
    try {
      await ApiService.deleteItem(item['id'] as int);
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Widget _row(String label, String text, IconData icon) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, color: AppColors.muted, size: 20),
          const SizedBox(width: 10),
          SizedBox(width: 122, child: Text(label, style: const TextStyle(color: AppColors.muted))),
          Expanded(child: Text(text, style: const TextStyle(fontWeight: FontWeight.w600))),
        ]),
      );

  String _serviceMode() {
    switch (item['service_sale_mode']) {
      case 'booking': return 'Онлайн-запись';
      case 'request': return 'Оставить заявку';
      default: return 'Заказать онлайн';
    }
  }

  @override
  Widget build(BuildContext context) {
    final image = '${item['image'] ?? ''}';
    return Scaffold(
      appBar: AppBar(
        title: Text(isService ? 'Услуга' : 'Товар'),
        actions: [
          PopupMenuButton<String>(
            onSelected: (value) => value == 'edit' ? _edit() : _delete(),
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'edit', child: Text('Изменить')),
              PopupMenuItem(value: 'delete', child: Text('Удалить')),
            ],
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    width: 82,
                    height: 82,
                    decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(18)),
                    child: image.isNotEmpty
                        ? ClipRRect(
                            borderRadius: BorderRadius.circular(18),
                            child: Image.network('${ApiService.baseUrl}$image', fit: BoxFit.cover, errorBuilder: (_, __, ___) => Icon(isService ? Icons.design_services : Icons.inventory_2, color: AppColors.primary, size: 34)),
                          )
                        : Icon(isService ? Icons.design_services : Icons.inventory_2, color: AppColors.primary, size: 34),
                  ),
                  const SizedBox(width: 14),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(value('name'), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 5),
                    Text(value('category'), style: const TextStyle(color: AppColors.muted)),
                    const SizedBox(height: 8),
                    Text(money(item['retail_price']), style: const TextStyle(color: AppColors.primary, fontSize: 20, fontWeight: FontWeight.w900)),
                  ])),
                ]),
                const Divider(height: 30),
                _row('Тип', isService ? 'Услуга' : 'Товар', Icons.sell_outlined),
                _row('Штрихкод', value('barcode'), Icons.qr_code_2),
                _row('Единица', value('unit'), Icons.straighten),
                _row('Категория', value('category'), Icons.category_outlined),
                _row(isService ? 'Стоимость' : 'Закупочная цена', money(item['purchase_price']), Icons.shopping_cart_outlined),
                _row('Оптовая цена', money(item['wholesale_price']), Icons.inventory_outlined),
                _row(isService ? 'Цена услуги' : 'Розничная цена', money(item['retail_price']), Icons.payments_outlined),
                _row('Скидка', '${item['discount_percent'] ?? 0}%', Icons.percent),
                if (isService)
                  _row('Продажа', _serviceMode(), Icons.language)
                else ...[
                  _row('Остаток', '${item['quantity'] ?? 0} ${item['unit'] ?? ''}', Icons.warehouse_outlined),
                  _row('GTIN', value('gtin'), Icons.numbers),
                  _row('NTIN', value('ntin'), Icons.numbers_outlined),
                  _row('Маркировка', item['is_marked'] == true ? 'Маркируемый товар' : 'Обычный товар', Icons.verified_outlined),
                ],
                _row('Описание', value('description'), Icons.notes_outlined),
              ]),
            ),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(onPressed: _edit, icon: const Icon(Icons.edit_outlined), label: const Text('Изменить')),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _delete,
            icon: const Icon(Icons.delete_outline, color: AppColors.danger),
            label: const Text('Удалить', style: TextStyle(color: AppColors.danger)),
          ),
        ],
      ),
    );
  }
}
