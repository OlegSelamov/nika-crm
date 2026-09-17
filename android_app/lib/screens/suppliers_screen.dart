import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/supplier_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class SuppliersScreen extends StatefulWidget {
  const SuppliersScreen({super.key});

  @override
  State<SuppliersScreen> createState() => _SuppliersScreenState();
}

class _SuppliersScreenState extends State<SuppliersScreen> {
  bool loading = true;
  bool saving = false;
  String? error;
  List<Map<String, dynamic>> suppliers = [];

  @override
  void initState() {
    super.initState();
    loadSuppliers();
  }

  Future<void> loadSuppliers() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final data = await SupplierService.getSuppliers();
      if (!mounted) return;
      setState(() {
        suppliers = data;
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = e is ApiException ? e.message : e.toString();
        loading = false;
      });
    }
  }

  Future<void> _openSupplierDialog([Map<String, dynamic>? supplier]) async {
    final name = TextEditingController(text: '${supplier?['name'] ?? ''}');
    final binIin = TextEditingController(text: '${supplier?['bin_iin'] ?? ''}');
    final contact = TextEditingController(text: '${supplier?['contact_name'] ?? ''}');
    final phone = TextEditingController(text: '${supplier?['phone'] ?? ''}');
    final email = TextEditingController(text: '${supplier?['email'] ?? ''}');
    final address = TextEditingController(text: '${supplier?['address'] ?? ''}');
    final comment = TextEditingController(text: '${supplier?['comment'] ?? ''}');
    final formKey = GlobalKey<FormState>();

    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setModalState) => Padding(
            padding: EdgeInsets.fromLTRB(
              16,
              16,
              16,
              MediaQuery.of(context).viewInsets.bottom + 24,
            ),
            child: Form(
              key: formKey,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      supplier == null ? 'Новый поставщик' : 'Редактировать поставщика',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: name,
                      autofocus: true,
                      decoration: const InputDecoration(labelText: 'Название *'),
                      validator: (value) => (value ?? '').trim().isEmpty ? 'Укажите название' : null,
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: binIin,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'БИН / ИИН'),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: contact,
                      decoration: const InputDecoration(labelText: 'Контактное лицо'),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(labelText: 'Телефон'),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: email,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(labelText: 'Email'),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: address,
                      decoration: const InputDecoration(labelText: 'Адрес'),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: comment,
                      maxLines: 3,
                      decoration: const InputDecoration(labelText: 'Комментарий'),
                    ),
                    const SizedBox(height: 18),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: saving
                            ? null
                            : () async {
                                if (!formKey.currentState!.validate()) return;
                                setModalState(() => saving = true);
                                try {
                                  final data = <String, dynamic>{
                                    'name': name.text.trim(),
                                    'bin_iin': binIin.text.trim(),
                                    'contact_name': contact.text.trim(),
                                    'phone': phone.text.trim(),
                                    'email': email.text.trim(),
                                    'address': address.text.trim(),
                                    'comment': comment.text.trim(),
                                  };
                                  if (supplier == null) {
                                    await SupplierService.createSupplier(data);
                                  } else {
                                    await SupplierService.updateSupplier(
                                      int.parse('${supplier['id']}'),
                                      data,
                                    );
                                  }
                                  if (!context.mounted) return;
                                  Navigator.pop(context, true);
                                } catch (e) {
                                  if (!context.mounted) return;
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(content: Text(e is ApiException ? e.message : e.toString())),
                                  );
                                } finally {
                                  if (context.mounted) setModalState(() => saving = false);
                                }
                              },
                        icon: saving
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            : const Icon(Icons.save_outlined),
                        label: Text(supplier == null ? 'Добавить поставщика' : 'Сохранить'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );

    name.dispose();
    binIin.dispose();
    contact.dispose();
    phone.dispose();
    email.dispose();
    address.dispose();
    comment.dispose();

    if (saved == true) {
      await loadSuppliers();
      if (mounted) Navigator.pop(context, true);
    }
  }

  Future<void> _deleteSupplier(Map<String, dynamic> supplier) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Удалить поставщика?'),
        content: Text('«${supplier['name'] ?? ''}» будет удалён из активного списка. История приходов сохранится.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Удалить')),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await SupplierService.deleteSupplier(int.parse('${supplier['id']}'));
      await loadSuppliers();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e is ApiException ? e.message : e.toString())),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Поставщики'),
        actions: [
          IconButton(
            tooltip: 'Добавить поставщика',
            onPressed: () => _openSupplierDialog(),
            icon: const Icon(Icons.person_add_alt_1_outlined),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? ScreenStateView(
                  icon: Icons.local_shipping_outlined,
                  title: 'Поставщики недоступны',
                  message: error!,
                  onAction: loadSuppliers,
                )
              : RefreshIndicator(
                  onRefresh: loadSuppliers,
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
                    children: [
                      const SectionTitle(
                        'Поставщики',
                        subtitle: 'Можно привязывать к приходу товара, но это необязательно',
                      ),
                      const SizedBox(height: 14),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          onPressed: () => _openSupplierDialog(),
                          icon: const Icon(Icons.add),
                          label: const Text('Добавить поставщика'),
                        ),
                      ),
                      const SizedBox(height: 16),
                      if (suppliers.isEmpty)
                        const Card(
                          child: Padding(
                            padding: EdgeInsets.all(22),
                            child: Text(
                              'Поставщиков пока нет. Приход товара всё равно можно проводить без поставщика.',
                              style: TextStyle(color: AppColors.muted),
                            ),
                          ),
                        )
                      else
                        ...suppliers.map((supplier) {
                          final binIin = '${supplier['bin_iin'] ?? ''}'.trim();
                          final phone = '${supplier['phone'] ?? ''}'.trim();
                          return Card(
                            margin: const EdgeInsets.only(bottom: 10),
                            child: ListTile(
                              leading: const CircleAvatar(
                                backgroundColor: AppColors.primarySoft,
                                child: Icon(Icons.local_shipping_outlined, color: AppColors.primary),
                              ),
                              title: Text(
                                '${supplier['name'] ?? 'Поставщик'}',
                                style: const TextStyle(fontWeight: FontWeight.w800),
                              ),
                              subtitle: Text(
                                [
                                  if (binIin.isNotEmpty) 'БИН/ИИН $binIin',
                                  if (phone.isNotEmpty) phone,
                                ].join(' · ').isEmpty
                                    ? 'Без дополнительных данных'
                                    : [
                                        if (binIin.isNotEmpty) 'БИН/ИИН $binIin',
                                        if (phone.isNotEmpty) phone,
                                      ].join(' · '),
                              ),
                              onTap: () => _openSupplierDialog(supplier),
                              trailing: IconButton(
                                tooltip: 'Удалить',
                                onPressed: () => _deleteSupplier(supplier),
                                icon: const Icon(Icons.delete_outline),
                              ),
                            ),
                          );
                        }),
                    ],
                  ),
                ),
    );
  }
}
