import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class CategoryManagementScreen extends StatefulWidget {
  final String initialType;

  const CategoryManagementScreen({super.key, this.initialType = 'product'});

  @override
  State<CategoryManagementScreen> createState() => _CategoryManagementScreenState();
}

class _CategoryManagementScreenState extends State<CategoryManagementScreen> {
  bool loading = true;
  String? error;
  late String type;
  List<Map<String, dynamic>> categories = [];

  @override
  void initState() {
    super.initState();
    type = widget.initialType == 'service' ? 'service' : 'product';
    load();
  }

  Future<void> load() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.getCategories(type: type);
      if (!mounted) return;
      setState(() {
        categories = data.map((item) => Map<String, dynamic>.from(item as Map)).toList();
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  Future<void> _edit([Map<String, dynamic>? category]) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _CategoryEditorDialog(
        type: type,
        category: category,
      ),
    );
    if (saved == true && mounted) await load();
  }

  Future<void> _delete(Map<String, dynamic> category) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Удалить категорию?'),
        content: Text('Категория «${category['name']}» будет удалена.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Удалить')),
        ],
      ),
    ) ?? false;
    if (!confirmed) return;
    try {
      await ApiService.deleteCategory(category['id'] as int);
      await load();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Категории')),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => _edit(),
          icon: const Icon(Icons.add),
          label: const Text('Добавить'),
        ),
        body: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'product', label: Text('Товары'), icon: Icon(Icons.inventory_2_outlined)),
                  ButtonSegment(value: 'service', label: Text('Услуги'), icon: Icon(Icons.design_services_outlined)),
                ],
                selected: {type},
                onSelectionChanged: (value) {
                  setState(() => type = value.first);
                  load();
                },
              ),
            ),
            Expanded(
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : error != null
                      ? ScreenStateView(icon: Icons.category_outlined, title: 'Категории недоступны', message: error!, onAction: load)
                      : RefreshIndicator(
                          onRefresh: load,
                          child: categories.isEmpty
                              ? ListView(
                                  physics: const AlwaysScrollableScrollPhysics(),
                                  children: const [Padding(padding: EdgeInsets.all(36), child: Center(child: Text('Категорий пока нет')))],
                                )
                              : ListView.builder(
                                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 100),
                                  itemCount: categories.length,
                                  itemBuilder: (_, index) {
                                    final category = categories[index];
                                    return Card(
                                      margin: const EdgeInsets.only(bottom: 8),
                                      child: ListTile(
                                        leading: CircleAvatar(
                                          backgroundColor: type == 'service' ? AppColors.cyan.withOpacity(.12) : AppColors.primarySoft,
                                          child: Icon(type == 'service' ? Icons.design_services_outlined : Icons.inventory_2_outlined),
                                        ),
                                        title: Text('${category['name'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w700)),
                                        subtitle: type == 'product' ? Text('Наценка: ${category['markup_percent'] ?? 0}%') : const Text('Категория услуг'),
                                        trailing: PopupMenuButton<String>(
                                          onSelected: (value) => value == 'edit' ? _edit(category) : _delete(category),
                                          itemBuilder: (_) => const [
                                            PopupMenuItem(value: 'edit', child: Text('Изменить')),
                                            PopupMenuItem(value: 'delete', child: Text('Удалить')),
                                          ],
                                        ),
                                      ),
                                    );
                                  },
                                ),
                        ),
            ),
          ],
        ),
      );
}

class _CategoryEditorDialog extends StatefulWidget {
  final String type;
  final Map<String, dynamic>? category;

  const _CategoryEditorDialog({required this.type, this.category});

  @override
  State<_CategoryEditorDialog> createState() => _CategoryEditorDialogState();
}

class _CategoryEditorDialogState extends State<_CategoryEditorDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController nameController;
  late final TextEditingController markupController;
  bool saving = false;

  bool get isProduct => widget.type == 'product';

  @override
  void initState() {
    super.initState();
    nameController = TextEditingController(text: '${widget.category?['name'] ?? ''}');
    markupController = TextEditingController(text: '${widget.category?['markup_percent'] ?? 0}');
  }

  @override
  void dispose() {
    nameController.dispose();
    markupController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() || saving) return;
    setState(() => saving = true);
    try {
      final markup = isProduct
          ? double.tryParse(markupController.text.replaceAll(',', '.')) ?? 0
          : 0.0;
      if (widget.category == null) {
        await ApiService.createCategory(
          name: nameController.text.trim(),
          type: widget.type,
          markup: markup,
        );
      } else {
        await ApiService.updateCategory(
          widget.category!['id'] as int,
          name: nameController.text.trim(),
          type: widget.type,
          markup: markup,
        );
      }
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(readableError(error))),
      );
      setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.category == null ? 'Новая категория' : 'Изменить категорию'),
        content: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: nameController,
                autofocus: true,
                textInputAction: isProduct ? TextInputAction.next : TextInputAction.done,
                decoration: const InputDecoration(labelText: 'Название категории'),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Укажите название категории'
                    : null,
                onFieldSubmitted: (_) {
                  if (!isProduct) _save();
                },
              ),
              if (isProduct) ...[
                const SizedBox(height: 16),
                TextFormField(
                  controller: markupController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  textInputAction: TextInputAction.done,
                  decoration: const InputDecoration(
                    labelText: 'Процент наценки',
                    suffixText: '%',
                    helperText: 'Используется для автоматического расчёта цен',
                  ),
                  validator: (value) {
                    final markup = double.tryParse((value ?? '').replaceAll(',', '.'));
                    if (markup == null) return 'Укажите процент числом';
                    if (markup < 0) return 'Процент не может быть отрицательным';
                    return null;
                  },
                  onFieldSubmitted: (_) => _save(),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: saving ? null : () => Navigator.pop(context, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: saving ? null : _save,
            child: saving
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Сохранить'),
          ),
        ],
      );
}
