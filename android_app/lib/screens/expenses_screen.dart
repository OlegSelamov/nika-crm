import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class ExpensesScreen extends StatefulWidget {
  const ExpensesScreen({super.key});

  @override
  State<ExpensesScreen> createState() => _ExpensesScreenState();
}

class _ExpensesScreenState extends State<ExpensesScreen> {
  bool loading = true;
  String? error;
  Map<String, dynamic> data = {};

  List<dynamic> get items => List<dynamic>.from(data['items'] ?? const []);
  Map<String, dynamic> get summary => Map<String, dynamic>.from(data['summary'] ?? const {});

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await ApiService.mobileExpenses();
      if (mounted) setState(() => data = result);
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> save([Map<String, dynamic>? item]) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _ExpenseDialog(
        item: item,
        categories: List<String>.from(data['categories'] ?? const []),
        methods: List<String>.from(data['payment_methods'] ?? const []),
      ),
    );
    if (result == null) return;
    try {
      if (item == null) {
        await ApiService.createMobileExpense(result);
      } else {
        await ApiService.updateMobileExpense(item['id'] as int, result);
      }
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Future<void> remove(Map<String, dynamic> item) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Удалить расход?'),
        content: Text('${item['description']} · ${money(item['amount'])}'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Удалить')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.deleteMobileExpense(item['id'] as int);
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return ScreenStateView(icon: Icons.payments_outlined, title: 'Расходы недоступны', message: error!, onAction: load);
    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 30),
        children: [
          Row(children: [
            const Expanded(child: SectionTitle('Расходы', subtitle: 'Управление затратами')),
            FilledButton.icon(onPressed: () => save(), icon: const Icon(Icons.add_rounded), label: const Text('Добавить')),
          ]),
          const SizedBox(height: 14),
          SizedBox(
            height: 132,
            child: Row(children: [
              Expanded(child: MetricCard(title: 'Сегодня', value: money(summary['today']), icon: Icons.today_outlined, color: AppColors.danger)),
              const SizedBox(width: 10),
              Expanded(child: MetricCard(title: 'За месяц', value: money(summary['month']), icon: Icons.calendar_month_outlined, color: AppColors.warning)),
            ]),
          ),
          const SizedBox(height: 14),
          if (items.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(30), child: Center(child: Text('Расходов пока нет', style: TextStyle(color: AppColors.muted)))))
          else
            ...items.map((raw) {
              final item = Map<String, dynamic>.from(raw as Map);
              final automatic = item['is_automatic'] == true;
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20),
                    onTap: automatic ? null : () => save(item),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Container(
                          width: 44, height: 44,
                          decoration: BoxDecoration(color: AppColors.danger.withOpacity(.1), borderRadius: BorderRadius.circular(14)),
                          child: const Icon(Icons.arrow_downward_rounded, color: AppColors.danger),
                        ),
                        const SizedBox(width: 12),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Expanded(child: Text('${item['description']}', style: const TextStyle(fontWeight: FontWeight.w800))),
                            Text(money(item['amount']), style: const TextStyle(color: AppColors.danger, fontWeight: FontWeight.w900)),
                          ]),
                          const SizedBox(height: 6),
                          Text('${item['category']} · ${item['payment_method']}', style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                          const SizedBox(height: 8),
                          Wrap(spacing: 7, children: [
                            StatusPill('${item['date_label']}', color: AppColors.muted),
                            if (automatic) const StatusPill('Автоматический', color: AppColors.primary),
                          ]),
                        ])),
                        if (!automatic)
                          PopupMenuButton<String>(
                            onSelected: (value) => value == 'edit' ? save(item) : remove(item),
                            itemBuilder: (_) => const [
                              PopupMenuItem(value: 'edit', child: Text('Изменить')),
                              PopupMenuItem(value: 'delete', child: Text('Удалить')),
                            ],
                          ),
                      ]),
                    ),
                  ),
                ),
              );
            }),
        ],
      ),
    );
  }
}

class _ExpenseDialog extends StatefulWidget {
  final Map<String, dynamic>? item;
  final List<String> categories;
  final List<String> methods;
  const _ExpenseDialog({required this.item, required this.categories, required this.methods});

  @override
  State<_ExpenseDialog> createState() => _ExpenseDialogState();
}

class _ExpenseDialogState extends State<_ExpenseDialog> {
  late final TextEditingController description;
  late final TextEditingController amount;
  late final TextEditingController comment;
  late final TextEditingController date;
  late String category;
  late String method;

  @override
  void initState() {
    super.initState();
    description = TextEditingController(text: '${widget.item?['description'] ?? ''}');
    amount = TextEditingController(text: widget.item == null ? '' : '${widget.item?['amount'] ?? ''}');
    comment = TextEditingController(text: '${widget.item?['comment'] ?? ''}');
    date = TextEditingController(text: '${widget.item?['date'] ?? DateTime.now().toIso8601String().substring(0, 10)}');
    category = '${widget.item?['category'] ?? (widget.categories.isNotEmpty ? widget.categories.first : '')}';
    method = '${widget.item?['payment_method'] ?? (widget.methods.isNotEmpty ? widget.methods.first : '')}';
  }

  @override
  void dispose() {
    description.dispose(); amount.dispose(); comment.dispose(); date.dispose(); super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.item == null ? 'Новый расход' : 'Изменить расход'),
    content: SingleChildScrollView(child: SizedBox(width: 420, child: Column(mainAxisSize: MainAxisSize.min, children: [
      DropdownButtonFormField<String>(
        value: widget.categories.contains(category) ? category : null,
        decoration: const InputDecoration(labelText: 'Категория *'),
        items: widget.categories.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
        onChanged: (v) => setState(() => category = v ?? ''),
      ),
      const SizedBox(height: 10),
      TextField(controller: description, decoration: const InputDecoration(labelText: 'Описание *')),
      const SizedBox(height: 10),
      TextField(controller: amount, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Сумма *', suffixText: '₸')),
      const SizedBox(height: 10),
      DropdownButtonFormField<String>(
        value: widget.methods.contains(method) ? method : null,
        decoration: const InputDecoration(labelText: 'Способ оплаты *'),
        items: widget.methods.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
        onChanged: (v) => setState(() => method = v ?? ''),
      ),
      const SizedBox(height: 10),
      TextField(
        controller: date,
        readOnly: true,
        decoration: const InputDecoration(labelText: 'Дата *', suffixIcon: Icon(Icons.calendar_month_outlined)),
        onTap: () async {
          final selected = await showDatePicker(context: context, firstDate: DateTime(2020), lastDate: DateTime(2100), initialDate: DateTime.tryParse(date.text) ?? DateTime.now());
          if (selected != null) date.text = selected.toIso8601String().substring(0, 10);
        },
      ),
      const SizedBox(height: 10),
      TextField(controller: comment, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Комментарий')),
    ]))),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
      FilledButton(
        onPressed: () {
          if (description.text.trim().isEmpty || double.tryParse(amount.text.replaceAll(',', '.')) == null || category.isEmpty || method.isEmpty) return;
          Navigator.pop(context, {
            'category': category,
            'description': description.text.trim(),
            'amount': amount.text.replaceAll(',', '.'),
            'payment_method': method,
            'date': date.text,
            'comment': comment.text.trim(),
          });
        },
        child: const Text('Сохранить'),
      ),
    ],
  );
}
