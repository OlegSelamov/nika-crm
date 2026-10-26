
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Foodservice-specific catalog. Retail ItemsScreen stays untouched.
class FoodCatalogScreen extends StatefulWidget {
  const FoodCatalogScreen({super.key});

  @override
  State<FoodCatalogScreen> createState() => _FoodCatalogScreenState();
}

class _FoodCatalogScreenState extends State<FoodCatalogScreen> {
  String kind = 'dish';
  String query = '';
  bool loading = true;
  bool more = false;
  int page = 1;
  String? error;
  List<Map<String, dynamic>> rows = [];

  static const kinds = <String, String>{
    'dish': 'Блюда',
    'product': 'Товары',
    'ingredient': 'Ингредиенты',
    'semi_finished': 'Полуфабрикаты',
  };
  static const names = <String, String>{
    'dish': 'Блюдо',
    'product': 'Товар',
    'ingredient': 'Ингредиент',
    'semi_finished': 'Полуфабрикат',
  };

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load({bool append = false}) async {
    if (mounted) setState(() { loading = true; error = null; });
    final targetKind = kind;
    final targetQuery = query;
    try {
      final targetPage = append ? page + 1 : 1;
      final data = await ApiService.foodMenu(
        type: targetKind, query: targetQuery, page: targetPage,
      );
      if (!mounted || targetKind != kind || targetQuery != query) return;
      setState(() {
        if (!append) rows.clear();
        rows.addAll((data['items'] as List? ?? [])
            .whereType<Map>()
            .map((v) => Map<String, dynamic>.from(v)));
        page = targetPage;
        more = data['has_more'] == true;
        loading = false;
      });
    } catch (e) {
      if (mounted) setState(() {
        error = readableError(e);
        loading = false;
      });
    }
  }

  Future<void> edit([Map<String, dynamic>? item]) async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      useSafeArea: true,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => FractionallySizedBox(
        heightFactor: .96,
        child: _FoodCatalogEditor(
          key: ValueKey(item?['id'] ?? 'new-$kind'),
          item: item, initialKind: item?['item_type']?.toString() ?? kind,
        ),
      ),
    );
    if (result == true && mounted) load();
  }

  Future<void> delete(Map<String, dynamic> item) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Удалить позицию?'),
        content: Text('«${item['name']}» будет удалена из каталога.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false),
              child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(c, true),
              child: const Text('Удалить')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.deleteItem(int.parse(item['id'].toString()));
      if (mounted) load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(readableError(e))));
    }
  }

  Widget photo(Map<String, dynamic> item) {
    final url = ApiService.catalogImageUrl(item['image']);
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Container(
        color: AppColors.primarySoft,
        width: 78, height: 78,
        child: url.isEmpty
            ? const Icon(Icons.restaurant_menu, color: AppColors.primary)
            : Image.network(url, fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const Icon(
                  Icons.image_not_supported_outlined, color: AppColors.muted)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Column(children: [
    SizedBox(height: 53, child: ListView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      children: [
        for (final entry in kinds.entries)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 5),
            child: ChoiceChip(
              label: Text(entry.value),
              selected: kind == entry.key,
              onSelected: (_) {
                if (kind == entry.key) return;
                setState(() { kind = entry.key; rows = []; more = false; });
                load();
              },
            ),
          ),
      ],
    )),
    Padding(
      padding: const EdgeInsets.fromLTRB(12, 5, 12, 9),
      child: Row(children: [
        Expanded(child: TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search), hintText: 'Поиск по каталогу',
            isDense: true,
          ),
          onSubmitted: (v) { query = v.trim(); load(); },
          textInputAction: TextInputAction.search,
        )),
        const SizedBox(width: 7),
        IconButton.filledTonal(
          onPressed: () => load(), icon: const Icon(Icons.refresh),
        ),
        const SizedBox(width: 5),
        IconButton.filled(
          onPressed: () => edit(), icon: const Icon(Icons.add),
          tooltip: 'Добавить позицию',
        ),
      ]),
    ),
    Expanded(child: loading && rows.isEmpty
        ? const Center(child: CircularProgressIndicator())
        : error != null && rows.isEmpty
            ? ScreenStateView(
                icon: Icons.error_outline, title: 'Каталог не загружен',
                message: error!, onAction: load)
            : RefreshIndicator(
                onRefresh: load,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(10, 4, 10, 80),
                  children: [
                    for (final item in rows)
                      Card(
                        margin: const EdgeInsets.only(bottom: 7),
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 6),
                          leading: photo(item),
                          title: Text('${item['name'] ?? ''}',
                            maxLines: 2, overflow: TextOverflow.ellipsis),
                          subtitle: Text(
                            '${item['category'] ?? 'Без категории'}'
                            '\n${names[item['item_type']] ?? 'Позиция'}'
                            '${kind == 'dish' || kind == 'product' ? ' · ${money(item['retail_price'])}' : ''}',
                          ),
                          isThreeLine: true,
                          onTap: () => edit(item),
                          trailing: PopupMenuButton<String>(
                            onSelected: (action) =>
                                action == 'edit' ? edit(item) : delete(item),
                            itemBuilder: (_) => const [
                              PopupMenuItem(value: 'edit', child: Text('Изменить')),
                              PopupMenuItem(value: 'delete', child: Text('Удалить')),
                            ],
                          ),
                        ),
                      ),
                    if (more) Center(child: TextButton(
                      onPressed: loading ? null : () => load(append: true),
                      child: const Text('Показать ещё'),
                    )),
                    if (rows.isEmpty) const Padding(
                      padding: EdgeInsets.all(24),
                      child: Center(child: Text('Позиции пока не добавлены')),
                    ),
                  ],
                ),
              )),
  ]);
}

class _FoodCatalogEditor extends StatefulWidget {
  final Map<String, dynamic>? item;
  final String initialKind;

  const _FoodCatalogEditor({super.key, this.item, required this.initialKind});

  @override
  State<_FoodCatalogEditor> createState() => _FoodCatalogEditorState();
}

class _FoodCatalogEditorState extends State<_FoodCatalogEditor> {
  final name = TextEditingController();
  final category = TextEditingController();
  final unit = TextEditingController();
  final retail = TextEditingController();
  final purchase = TextEditingController();
  final opening = TextEditingController();
  final description = TextEditingController();
  final barcode = TextEditingController();
  final recipe = <int, TextEditingController>{};
  XFile? pickedPhoto;
  int? savedId;
  List<Map<String, dynamic>> ingredients = [];
  List<String> categories = [];
  late String kind;
  bool loading = true;
  bool saving = false;
  String? error;

  bool get hasRecipe => kind == 'dish' || kind == 'semi_finished';
  bool get isNew => widget.item == null;

  @override
  void initState() {
    super.initState();
    kind = widget.initialKind;
    savedId = widget.item == null ? null : int.tryParse(widget.item!['id'].toString());
    final item = widget.item ?? const <String, dynamic>{};
    name.text = (item['name'] ?? '').toString();
    category.text = (item['category'] ?? '').toString();
    unit.text = (item['unit'] ?? 'шт').toString();
    retail.text = (item['retail_price'] ?? '').toString();
    purchase.text = (item['purchase_price'] ?? '').toString();
    description.text = (item['description'] ?? '').toString();
    barcode.text = (item['barcode'] ?? '').toString();
    initialize();
  }

  Future<void> initialize() async {
    try {
      // Use the same source inventory as website recipe editor.
      final lists = await Future.wait([
        ApiService.getCategories(forceRemote: true),
        _allItems('ingredient'),
        _allItems('semi_finished'),
      ]);
      if (!mounted) return;
      for (final raw in lists[0]) {
        if (raw is Map && raw['name'] != null) {
          categories.add(raw['name'].toString());
        }
      }
      ingredients = [
        ...lists[1].whereType<Map>().map((v) => Map<String, dynamic>.from(v)),
        ...lists[2].whereType<Map>().map((v) => Map<String, dynamic>.from(v)),
      ];
      if (widget.item != null &&
          (kind == 'dish' || kind == 'semi_finished')) {
        final detail = await ApiService.foodRecipe(
            int.parse(widget.item!['id'].toString()));
        if (!mounted) return;
        for (final raw in detail['ingredients'] as List? ?? []) {
          if (raw is! Map) continue;
          final id = int.tryParse((raw['item_id'] ?? '').toString());
          if (id == null) continue;
          recipe[id] = TextEditingController(text: raw['quantity'].toString());
        }
      }
      if (mounted) setState(() => loading = false);
    } catch (e) {
      if (mounted) setState(() {
        error = readableError(e);
        loading = false;
      });
    }
  }

  Future<List<dynamic>> _allItems(String type) async {
    final all = <dynamic>[];
    for (int p = 1; p <= 100; p++) {
      final result = await ApiService.foodMenu(type: type, page: p);
      all.addAll(result['items'] as List? ?? []);
      if (result['has_more'] != true) break;
    }
    return all;
  }

  @override
  void dispose() {
    for (final c in [name, category, unit, retail, purchase,
      opening, description, barcode, ...recipe.values]) { c.dispose(); }
    super.dispose();
  }

  double? parseValue(TextEditingController field) =>
      double.tryParse(field.text.trim().replaceAll(',', '.'));

  void setKind(String next) {
    if (kind == next) return;
    setState(() {
      kind = next;
      if (kind == 'ingredient') retail.text = '0';
    });
  }

  Future<void> selectIngredient() async {
    final selected = await showModalBottomSheet<int>(
      context: context, showDragHandle: true,
      builder: (ctx) => SafeArea(child: ListView(
        children: [
          const ListTile(title: Text('Добавить ингредиент в техкарту')),
          for (final item in ingredients)
            if (!recipe.containsKey(int.tryParse(item['id'].toString())) &&
                item['id'].toString() != widget.item?['id'].toString())
              ListTile(title: Text('${item['name']}'),
                subtitle: Text('${item['unit'] ?? 'шт'} · ${item['item_type'] == 'ingredient' ? 'Ингредиент' : 'Полуфабрикат'}'),
                onTap: () => Navigator.pop(ctx, int.parse(item['id'].toString()))),
        ],
      )),
    );
    if (selected == null || !mounted) return;
    setState(() => recipe[selected] = TextEditingController(text: '1'));
  }

  Future<void> save() async {
    if (saving || loading) return;
    if (name.text.trim().isEmpty) {
      setState(() => error = 'Введите название');
      return;
    }
    final salePrice = parseValue(retail) ?? 0;
    final buyPrice = parseValue(purchase) ?? 0;
    final initial = parseValue(opening) ?? 0;
    if (salePrice < 0 || buyPrice < 0 || initial < 0) {
      setState(() => error = 'Цена и количество не могут быть отрицательными');
      return;
    }
    final lines = <Map<String, dynamic>>[];
    if (hasRecipe) {
      for (final entry in recipe.entries) {
        final value = parseValue(entry.value);
        if (value == null || value <= 0) {
          setState(() => error = 'Количество ингредиента должно быть больше 0');
          return;
        }
        lines.add({'item_id': entry.key, 'quantity': value});
      }
    }
    setState(() { saving = true; error = null; });
    try {
      final result = await ApiService.saveFoodCatalogItem({
        'item_type': kind,
        'name': name.text.trim(),
        'category': category.text.trim(),
        'unit': unit.text.trim().isEmpty ? 'шт' : unit.text.trim(),
        'retail_price': salePrice,
        'purchase_price': buyPrice,
        'description': description.text.trim(),
        'barcode': barcode.text.trim(),
        if (isNew) 'opening_quantity': initial,
        'recipe': lines,
      }, id: savedId);
      if (result['success'] != true) {
        throw ApiException((result['error'] ?? 'Не удалось сохранить').toString());
      }
      savedId = int.parse(result['id'].toString());
      if (pickedPhoto != null) {
        await ApiService.uploadFoodCatalogImage(savedId!, pickedPhoto!.path);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> pickPhoto() async {
    try {
      final file = await ImagePicker().pickImage(
        source: ImageSource.gallery, imageQuality: 82, maxWidth: 1600);
      if (file != null && mounted) setState(() => pickedPhoto = file);
    } catch (e) {
      if (mounted) setState(() => error = 'Не удалось выбрать фото: $e');
    }
  }

  Widget field(String label, TextEditingController ctrl,
      {bool number = false, int lines = 1}) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: TextField(
      controller: ctrl,
      keyboardType: number ? const TextInputType.numberWithOptions(decimal: true)
        : lines > 1 ? TextInputType.multiline : TextInputType.text,
      maxLines: lines,
      decoration: InputDecoration(labelText: label, isDense: true),
    ),
  );

  @override
  Widget build(BuildContext context) => Column(children: [
    Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(children: [
        Expanded(child: Text(widget.item == null
          ? 'Новая позиция' : 'Редактирование',
          style: Theme.of(context).textTheme.titleLarge)),
        IconButton(onPressed: () => Navigator.pop(context),
          icon: const Icon(Icons.close)),
      ]),
    ),
    if (loading) const LinearProgressIndicator(),
    Expanded(child: ListView(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 22),
      children: [
        if (error != null) Card(child: Padding(
          padding: const EdgeInsets.all(12),
          child: Text(error!, style: const TextStyle(color: Colors.redAccent)),
        )),
        DropdownButtonFormField<String>(
          value: kind,
          decoration: const InputDecoration(labelText: 'Тип позиции'),
          items: _FoodCatalogScreenState.kinds.entries.map((e) =>
            DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
          onChanged: saving ? null : (v) { if (v != null) setKind(v); },
        ),
        const SizedBox(height: 12),
        field('Название', name),
        field('Категория', category),
        if (categories.isNotEmpty)
          SizedBox(height: 38, child: ListView(
            scrollDirection: Axis.horizontal,
            children: [
              for (final value in categories.take(80))
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ActionChip(label: Text(value),
                    onPressed: () => setState(() => category.text = value)),
                ),
            ],
          )),
        const SizedBox(height: 8),
        field('Единица измерения (шт, кг, г, л)', unit),
        if (kind != 'ingredient')
          field('Цена продажи, ₸', retail, number: true),
        field('Закупочная цена, ₸', purchase, number: true),
        if (isNew && (kind == 'ingredient' || kind == 'product'))
          field('Начальный остаток', opening, number: true),
        if (kind == 'product') field('Штрихкод', barcode),
        field('Описание', description, lines: 3),
        Card(child: ListTile(
          leading: pickedPhoto != null
            ? Image.file(File(pickedPhoto!.path), width: 70, height: 70,
                fit: BoxFit.cover)
            : widget.item != null &&
                ApiService.catalogImageUrl(widget.item!['image']).isNotEmpty
              ? Image.network(ApiService.catalogImageUrl(widget.item!['image']),
                  width: 70, height: 70, fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const Icon(Icons.broken_image_outlined))
              : const Icon(Icons.add_photo_alternate_outlined, size: 45),
          title: const Text('Фотография позиции'),
          subtitle: const Text('Общая с сайтом Nika Business'),
          trailing: IconButton(onPressed: pickPhoto,
            icon: const Icon(Icons.photo_library_outlined)),
          onTap: pickPhoto,
        )),
        if (kind == 'dish' && savedId != null)
          OutlinedButton.icon(
            onPressed: loading || saving ? null : () async {
              await showModalBottomSheet<void>(
                context: context, showDragHandle: true, useSafeArea: true,
                isScrollControlled: true,
                builder: (_) => FractionallySizedBox(heightFactor: .96,
                  child: _FoodModifiersEditor(itemId: savedId!)),
              );
            },
            icon: const Icon(Icons.tune), label: const Text('Модификаторы блюда'),
          ),
        if (hasRecipe) ...[
          const Divider(height: 30),
          Text('Технологическая карта',
            style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text('Состав на одну порцию или единицу. При оплате ингредиенты спишутся по техкарте.'),
          for (final entry in recipe.entries.toList())
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(ingredients.where((i) => i['id'].toString() ==
                    entry.key.toString()).map((i) =>
                    i['name'].toString()).firstOrNull ?? 'Ингредиент №${entry.key}'),
              subtitle: TextField(
                controller: entry.value,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(
                    labelText: 'Количество на единицу'),
              ),
              trailing: IconButton(
                onPressed: () => setState(() {
                  recipe.remove(entry.key)?.dispose();
                }),
                icon: const Icon(Icons.delete_outline),
              ),
            ),
          OutlinedButton.icon(
            onPressed: loading ? null : selectIngredient,
            icon: const Icon(Icons.add),
            label: const Text('Добавить ингредиент'),
          ),
        ],
        const SizedBox(height: 36),
      ],
    )),
    SafeArea(top: false, child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: SizedBox(width: double.infinity, child: FilledButton.icon(
        onPressed: loading || saving ? null : save,
        icon: const Icon(Icons.save_outlined),
        label: Text(saving ? 'Сохраняем…' : 'Сохранить'),
      )),
    )),
  ]);
}


/// Modifier groups saved through the same PUT endpoint as the website.
class _FoodModifiersEditor extends StatefulWidget {
  final int itemId;
  const _FoodModifiersEditor({required this.itemId});

  @override
  State<_FoodModifiersEditor> createState() => _FoodModifiersEditorState();
}

class _FoodModifiersEditorState extends State<_FoodModifiersEditor> {
  List<Map<String, dynamic>> groups = [];
  List<Map<String, dynamic>> ingredientItems = [];
  bool loading = true;
  bool saving = false;
  String? error;

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    try {
      final groupData = await ApiService.foodModifiers(widget.itemId);
      final items = <Map<String, dynamic>>[];
      for (final type in ['ingredient', 'semi_finished']) {
        for (int page = 1; page <= 100; page++) {
          final data = await ApiService.foodMenu(type: type, page: page);
          items.addAll((data['items'] as List? ?? [])
            .whereType<Map>().map((v) => Map<String, dynamic>.from(v)));
          if (data['has_more'] != true) break;
        }
      }
      if (!mounted) return;
      setState(() {
        groups = (groupData['groups'] as List? ?? [])
          .whereType<Map>().map((g) {
            final copy = Map<String, dynamic>.from(g);
            copy['options'] = (g['options'] as List? ?? [])
              .whereType<Map>().map((o) => Map<String, dynamic>.from(o)).toList();
            return copy;
          }).toList();
        ingredientItems = items;
        loading = false;
      });
    } catch (e) {
      if (mounted) setState(() { error = readableError(e); loading = false; });
    }
  }

  Future<void> save() async {
    if (saving) return;
    setState(() { saving = true; error = null; });
    try {
      final payload = <Map<String, dynamic>>[];
      for (final group in groups) {
        final groupName = (group['name'] ?? '').toString().trim();
        if (groupName.isEmpty) throw const ApiException('Укажите название группы');
        final min = int.tryParse('${group['min_select'] ?? 0}') ?? 0;
        final max = int.tryParse('${group['max_select'] ?? 1}') ?? 1;
        if (min < 0 || max < 1 || max < min) {
          throw const ApiException('Проверьте минимальное и максимальное количество');
        }
        final options = <Map<String, dynamic>>[];
        for (final o in group['options'] as List? ?? []) {
          final option = Map<String, dynamic>.from(o as Map);
          final optionName = (option['name'] ?? '').toString().trim();
          if (optionName.isEmpty) throw const ApiException('Укажите название модификатора');
          final price = double.tryParse((option['price_delta'] ?? '0')
            .toString().replaceAll(',', '.'));
          if (price == null) throw const ApiException('Проверьте цену модификатора');
          final qty = double.tryParse((option['ingredient_quantity'] ?? '0')
            .toString().replaceAll(',', '.'));
          if (qty == null || qty < 0) {
            throw const ApiException('Некорректное количество ингредиента');
          }
          options.add({
            'name': optionName,
            'price_delta': price,
            'ingredient_item_id': option['ingredient_item_id'],
            'ingredient_quantity': qty,
          });
        }
        payload.add({
          'name': groupName, 'min_select': min, 'max_select': max,
          'options': options,
        });
      }
      final result = await ApiService.saveFoodModifiers(widget.itemId, payload);
      if (result['success'] != true) {
        throw ApiException((result['message'] ?? 'Не удалось сохранить').toString());
      }
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  void addGroup() => setState(() => groups.add({
    'name': '', 'min_select': 0, 'max_select': 1,
    'options': <Map<String, dynamic>>[],
  }));

  @override
  Widget build(BuildContext context) => Column(children: [
    Padding(padding: const EdgeInsets.fromLTRB(16, 4, 10, 10),
      child: Row(children: [
        Expanded(child: Text('Модификаторы',
          style: Theme.of(context).textTheme.titleLarge)),
        IconButton(icon: const Icon(Icons.close),
          onPressed: () => Navigator.pop(context)),
      ])),
    if (loading) const LinearProgressIndicator(),
    Expanded(child: ListView(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
      children: [
        if (error != null) Padding(padding: const EdgeInsets.all(8),
          child: Text(error!, style: const TextStyle(color: Colors.redAccent))),
        const Padding(padding: EdgeInsets.all(8),
          child: Text('Группы дополнений и исключений доступны при заказе блюда. '
            'Если модификатор содержит ингредиент, его количество учитывается '
            'при списании по техкарте.')),
        for (int gi = 0; gi < groups.length; gi++)
          Card(
            key: ValueKey('g-$gi'),
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(children: [
                Row(children: [
                  Expanded(child: Text('Группа ${gi + 1}',
                    style: Theme.of(context).textTheme.titleMedium)),
                  IconButton(
                    onPressed: () => setState(() => groups.removeAt(gi)),
                    icon: const Icon(Icons.delete_outline)),
                ]),
                TextFormField(
                  initialValue: (groups[gi]['name'] ?? '').toString(),
                  decoration: const InputDecoration(labelText: 'Название группы'),
                  onChanged: (v) => groups[gi]['name'] = v,
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(child: TextFormField(
                    initialValue: '${groups[gi]['min_select'] ?? 0}',
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Мин. выбор'),
                    onChanged: (v) => groups[gi]['min_select'] = v,
                  )),
                  const SizedBox(width: 10),
                  Expanded(child: TextFormField(
                    initialValue: '${groups[gi]['max_select'] ?? 1}',
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Макс. выбор'),
                    onChanged: (v) => groups[gi]['max_select'] = v,
                  )),
                ]),
                const SizedBox(height: 10),
                for (int oi = 0;
                  oi < (groups[gi]['options'] as List).length; oi++)
                  Builder(builder: (ctx) {
                    final option = Map<String, dynamic>.from(
                      (groups[gi]['options'] as List)[oi] as Map);
                    final rawIng = option['ingredient_item_id'];
                    final ingId = int.tryParse((rawIng ?? '').toString());
                    return Card(
                      key: ValueKey('o-$gi-$oi'),
                      color: Theme.of(context).colorScheme.surfaceContainer,
                      child: Padding(padding: const EdgeInsets.all(10),
                        child: Column(children: [
                          Row(children: [
                            Expanded(child: Text('Вариант ${oi + 1}')),
                            IconButton(
                              icon: const Icon(Icons.remove_circle_outline),
                              onPressed: () => setState(() =>
                                (groups[gi]['options'] as List).removeAt(oi)),
                            ),
                          ]),
                          TextFormField(
                            initialValue: (option['name'] ?? '').toString(),
                            decoration: const InputDecoration(
                              labelText: 'Название дополнения'),
                            onChanged: (v) =>
                              (groups[gi]['options'] as List)[oi]['name'] = v,
                          ),
                          const SizedBox(height: 8),
                          TextFormField(
                            initialValue: '${option['price_delta'] ?? 0}',
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true, signed: true),
                            decoration: const InputDecoration(
                              labelText: 'Изменение цены, ₸'),
                            onChanged: (v) =>
                              (groups[gi]['options'] as List)[oi]['price_delta'] = v,
                          ),
                          const SizedBox(height: 8),
                          DropdownButtonFormField<int?>(
                            value: ingId != null &&
                                ingredientItems.any((i) =>
                                  i['id'].toString() == ingId.toString())
                              ? ingId : null,
                            isExpanded: true,
                            decoration: const InputDecoration(
                              labelText: 'Ингредиент (необязательно)'),
                            items: [
                              const DropdownMenuItem<int?>(
                                value: null, child: Text('Без ингредиента')),
                              ...ingredientItems.map((i) => DropdownMenuItem<int?>(
                                value: int.tryParse(i['id'].toString()),
                                child: Text('${i['name']}', overflow: TextOverflow.ellipsis),
                              )),
                            ],
                            onChanged: (v) => (groups[gi]['options'] as List)[oi]
                              ['ingredient_item_id'] = v,
                          ),
                          const SizedBox(height: 8),
                          TextFormField(
                            initialValue:
                              '${option['ingredient_quantity'] ?? 0}',
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true),
                            decoration: const InputDecoration(
                              labelText: 'Норма ингредиента на порцию'),
                            onChanged: (v) => (groups[gi]['options'] as List)[oi]
                              ['ingredient_quantity'] = v,
                          ),
                        ]),
                      ),
                    );
                  }),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => setState(() =>
                    (groups[gi]['options'] as List).add(
                      <String, dynamic>{
                        'name': '', 'price_delta': 0,
                        'ingredient_item_id': null,
                        'ingredient_quantity': 0,
                      })),
                  icon: const Icon(Icons.add),
                  label: const Text('Добавить вариант'),
                ),
              ]),
            ),
          ),
        OutlinedButton.icon(
          onPressed: loading ? null : addGroup,
          icon: const Icon(Icons.add_circle_outline),
          label: const Text('Добавить группу модификаторов'),
        ),
      ],
    )),
    SafeArea(top: false, child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: SizedBox(width: double.infinity, child: FilledButton.icon(
        onPressed: saving || loading ? null : save,
        icon: const Icon(Icons.save),
        label: Text(saving ? 'Сохранение…' : 'Сохранить модификаторы'),
      )),
    )),
  ]);
}
