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
    final bankName = TextEditingController(text: '${supplier?['bank_name'] ?? ''}');
    final iban = TextEditingController(text: '${supplier?['iban'] ?? ''}');
    final bic = TextEditingController(text: '${supplier?['bic'] ?? ''}');
    final kbe = TextEditingController(text: '${supplier?['kbe'] ?? ''}');
    final knp = TextEditingController(text: '${supplier?['knp'] ?? ''}');
    final paymentPurpose = TextEditingController(text: '${supplier?['payment_purpose'] ?? ''}');
    final comment = TextEditingController(text: '${supplier?['comment'] ?? ''}');
    final formKey = GlobalKey<FormState>();

    String digitsOnly(String value) => value.replaceAll(RegExp(r'\D'), '');
    String compactUpper(String value) =>
        value.replaceAll(RegExp(r'\s+'), '').toUpperCase();

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
                      maxLength: 12,
                      decoration: const InputDecoration(
                        labelText: 'БИН / ИИН',
                        counterText: '',
                      ),
                      validator: (value) {
                        final v = digitsOnly(value ?? '');
                        if (v.isNotEmpty && v.length != 12) {
                          return 'БИН / ИИН должен содержать 12 цифр';
                        }
                        return null;
                      },
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
                    const SizedBox(height: 20),
                    Row(
                      children: const [
                        Icon(Icons.account_balance_outlined, size: 20),
                        SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Банковские реквизиты',
                            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Эти данные будут автоматически подставляться в «Мои Банки» при оплате поставщику.',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: bankName,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Банк',
                        hintText: 'Например: Alatau City Bank',
                        prefixIcon: Icon(Icons.account_balance_outlined),
                      ),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: iban,
                      textCapitalization: TextCapitalization.characters,
                      maxLength: 20,
                      decoration: const InputDecoration(
                        labelText: 'IBAN',
                        hintText: 'KZ...',
                        counterText: '',
                        prefixIcon: Icon(Icons.credit_card_outlined),
                      ),
                      validator: (value) {
                        final v = compactUpper(value ?? '');
                        if (v.isEmpty) return null;
                        if (!RegExp(r'^KZ[0-9A-Z]{18}
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
                                    'bank_name': bankName.text.trim(),
                                    'iban': compactUpper(iban.text),
                                    'bic': compactUpper(bic.text),
                                    'kbe': digitsOnly(kbe.text).substring(
                                      0,
                                      digitsOnly(kbe.text).length > 2
                                          ? 2
                                          : digitsOnly(kbe.text).length,
                                    ),
                                    'knp': digitsOnly(knp.text).substring(
                                      0,
                                      digitsOnly(knp.text).length > 3
                                          ? 3
                                          : digitsOnly(knp.text).length,
                                    ),
                                    'payment_purpose': paymentPurpose.text.trim(),
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
    bankName.dispose();
    iban.dispose();
    bic.dispose();
    kbe.dispose();
    knp.dispose();
    paymentPurpose.dispose();
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
                          final supplierIban = '${supplier['iban'] ?? ''}'.trim();
                          final supplierBic = '${supplier['bic'] ?? ''}'.trim();
                          final bankReady = supplierIban.isNotEmpty && supplierBic.isNotEmpty;
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
                                        if (bankReady) 'Реквизиты для оплаты заполнены',
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
).hasMatch(v)) {
                          return 'Укажите IBAN Казахстана: KZ + 18 символов';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: bic,
                      textCapitalization: TextCapitalization.characters,
                      maxLength: 11,
                      decoration: const InputDecoration(
                        labelText: 'БИК / SWIFT',
                        hintText: 'Например: TSESKZKA',
                        counterText: '',
                      ),
                      validator: (value) {
                        final v = compactUpper(value ?? '');
                        if (v.isEmpty) return null;
                        if (!RegExp(r'^[0-9A-Z]{8}([0-9A-Z]{3})?
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
).hasMatch(v)) {
                          return 'БИК / SWIFT должен содержать 8 или 11 символов';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 10),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: kbe,
                            keyboardType: TextInputType.number,
                            maxLength: 2,
                            decoration: const InputDecoration(
                              labelText: 'КБЕ',
                              hintText: '17',
                              counterText: '',
                            ),
                            validator: (value) {
                              final v = digitsOnly(value ?? '');
                              if (v.isNotEmpty && v.length != 2) {
                                return '2 цифры';
                              }
                              return null;
                            },
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: TextFormField(
                            controller: knp,
                            keyboardType: TextInputType.number,
                            maxLength: 3,
                            decoration: const InputDecoration(
                              labelText: 'КНП',
                              hintText: '710',
                              counterText: '',
                            ),
                            validator: (value) {
                              final v = digitsOnly(value ?? '');
                              if (v.isNotEmpty && v.length != 3) {
                                return '3 цифры';
                              }
                              return null;
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: paymentPurpose,
                      maxLines: 2,
                      decoration: const InputDecoration(
                        labelText: 'Назначение платежа по умолчанию',
                        hintText: 'Например: Оплата за товар согласно счёту',
                      ),
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
