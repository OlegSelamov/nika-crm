import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'add_item_screen.dart';
import 'category_management_screen.dart';
import 'item_detail_screen.dart';
import 'scanner_screen.dart';

class ItemsScreen extends StatefulWidget {
  const ItemsScreen({super.key});

  @override
  State<ItemsScreen> createState() => _ItemsScreenState();
}

class _ItemsScreenState extends State<ItemsScreen> {
  bool loading = true;
  String? error;
  String selectedType = 'all';
  String selectedCategory = 'all';
  List<Map<String, dynamic>> items = [];
  List<Map<String, dynamic>> categories = [];
  final searchController = TextEditingController();

  List<Map<String, dynamic>> get filtered {
    final query = searchController.text.trim().toLowerCase();
    return items.where((item) {
      final type = item['item_type'] == 'service' ? 'service' : 'product';
      if (selectedType != 'all' && type != selectedType) return false;
      if (selectedCategory != 'all' && '${item['category'] ?? ''}' != selectedCategory) return false;
      if (query.isEmpty) return true;
      return [item['name'], item['barcode'], item['gtin'], item['ntin'], item['category']]
          .map((value) => '${value ?? ''}'.toLowerCase())
          .join(' ')
          .contains(query);
    }).toList();
  }

  @override
  void initState() {
    super.initState();
    loadItems();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  Future<void> loadItems() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final results = await Future.wait([
        ApiService.getItems(),
        ApiService.getCategories(),
      ]);
      if (!mounted) return;
      setState(() {
        items = results[0].map((item) => Map<String, dynamic>.from(item as Map)).toList();
        categories = results[1].map((item) => Map<String, dynamic>.from(item as Map)).toList();
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  List<String> get visibleCategories {
    final values = categories
        .where((item) => selectedType == 'all' || '${item['category_type'] ?? 'product'}' == selectedType)
        .map((item) => '${item['name'] ?? ''}')
        .where((name) => name.isNotEmpty)
        .toSet()
        .toList()..sort();
    return values;
  }

  void _setType(String type) {
    setState(() {
      selectedType = type;
      if (selectedCategory != 'all' && !visibleCategories.contains(selectedCategory)) {
        selectedCategory = 'all';
      }
    });
  }

  Future<void> _add() async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const AddItemScreen()),
    );
    if (changed == true) loadItems();
  }

  Future<void> _open(Map<String, dynamic> item) async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
    );
    if (changed == true) loadItems();
  }

  Future<void> _edit(Map<String, dynamic> item) async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => AddItemScreen(item: item)),
    );
    if (changed == true) loadItems();
  }

  Future<void> _delete(Map<String, dynamic> item) async {
    final service = item['item_type'] == 'service';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Удалить ${service ? 'услугу' : 'товар'}?'),
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
      await loadItems();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Future<void> _scanBarcode() async {
    final barcode = await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ScannerScreen()),
    );
    if (barcode == null) return;
    searchController.text = barcode.toString();
    setState(() {});
  }

  Future<void> _manageCategories() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => CategoryManagementScreen(
          initialType: selectedType == 'service' ? 'service' : 'product',
        ),
      ),
    );
    loadItems();
  }

  Widget _typePill(bool service) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(
          color: (service ? AppColors.cyan : AppColors.primary).withOpacity(.1),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          service ? 'Услуга' : 'Товар',
          style: TextStyle(color: service ? AppColors.cyan : AppColors.primary, fontSize: 11, fontWeight: FontWeight.w800),
        ),
      );

  Widget _card(Map<String, dynamic> item) {
    final service = item['item_type'] == 'service';
    final image = '${item['image'] ?? ''}';
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () => _open(item),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 70,
              height: 70,
              decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(16)),
              child: image.isNotEmpty
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Image.network('${ApiService.baseUrl}$image', fit: BoxFit.cover, errorBuilder: (_, __, ___) => Icon(service ? Icons.design_services : Icons.inventory_2, color: AppColors.primary)),
                    )
                  : Icon(service ? Icons.design_services : Icons.inventory_2, color: AppColors.primary, size: 30),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(child: Text('${item['name'] ?? ''}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800))),
                  const SizedBox(width: 6),
                  _typePill(service),
                ]),
                const SizedBox(height: 5),
                Text('${item['category'] ?? 'Без категории'} • ${item['unit'] ?? 'шт'}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                if ('${item['barcode'] ?? ''}'.isNotEmpty)
                  Text('Штрихкод: ${item['barcode']}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                const SizedBox(height: 7),
                Row(children: [
                  Text(money(item['retail_price']), style: const TextStyle(color: AppColors.primary, fontSize: 16, fontWeight: FontWeight.w900)),
                  if (!service) ...[
                    const SizedBox(width: 12),
                    Text('Остаток: ${item['quantity'] ?? 0}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                  ],
                ]),
              ]),
            ),
            PopupMenuButton<String>(
              onSelected: (value) => value == 'edit' ? _edit(item) : _delete(item),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'edit', child: Text('Изменить')),
                PopupMenuItem(value: 'delete', child: Text('Удалить')),
              ],
            ),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.inventory_2_outlined,
        title: 'Каталог недоступен',
        message: error!,
        onAction: loadItems,
      );
    }
    final rows = filtered;
    final categoryValues = visibleCategories;
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: SegmentedButton<String>(
          segments: [
            ButtonSegment(value: 'all', label: Text('Все ${items.length}')),
            ButtonSegment(value: 'product', label: Text('Товары ${items.where((item) => item['item_type'] != 'service').length}')),
            ButtonSegment(value: 'service', label: Text('Услуги ${items.where((item) => item['item_type'] == 'service').length}')),
          ],
          selected: {selectedType},
          onSelectionChanged: (value) => _setType(value.first),
        ),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: searchController,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                hintText: 'Название, штрихкод, GTIN или NTIN',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(onPressed: _scanBarcode, icon: const Icon(Icons.qr_code_scanner)),
              ),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filledTonal(onPressed: _manageCategories, icon: const Icon(Icons.category_outlined), tooltip: 'Категории'),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: DropdownButtonFormField<String>(
          value: selectedCategory,
          decoration: const InputDecoration(labelText: 'Категория'),
          items: [
            const DropdownMenuItem(value: 'all', child: Text('Все категории')),
            ...categoryValues.map((value) => DropdownMenuItem(value: value, child: Text(value))),
          ],
          onChanged: (value) => setState(() => selectedCategory = value ?? 'all'),
        ),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
        child: SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(onPressed: _add, icon: const Icon(Icons.add_box_outlined), label: const Text('Добавить позицию')),
        ),
      ),
      Expanded(
        child: RefreshIndicator(
          onRefresh: loadItems,
          child: rows.isEmpty
              ? ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  children: const [Padding(padding: EdgeInsets.all(36), child: Center(child: Text('Позиции не найдены')))],
                )
              : ListView.builder(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
                  itemCount: rows.length,
                  itemBuilder: (_, index) => _card(rows[index]),
                ),
        ),
      ),
    ]);
  }
}
