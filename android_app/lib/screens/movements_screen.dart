import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/stock_widgets.dart';

class MovementsScreen extends StatefulWidget {
  final String initialType;

  const MovementsScreen({super.key, this.initialType = 'all'});

  @override
  State<MovementsScreen> createState() => _MovementsScreenState();
}

class _MovementsScreenState extends State<MovementsScreen> {
  final searchController = TextEditingController();
  bool loading = true;
  String? error;
  List<Map<String, dynamic>> rows = [];
  late String typeFilter;
  String sort = 'date-desc';
  DateTime? dateFrom;
  DateTime? dateTo;

  @override
  void initState() {
    super.initState();
    typeFilter = const ['all', 'income', 'sale', 'refund', 'writeoff'].contains(widget.initialType)
        ? widget.initialType
        : 'all';
    loadData();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  Future<void> loadData() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.getStockMovements();
      if (!mounted) return;
      setState(() {
        rows = data.map((item) => Map<String, dynamic>.from(item as Map)).toList();
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  int _count(String type) => rows.where((row) => type == 'all' || row['movement_type'] == type).length;

  double _sum(String type) => rows
      .where((row) => row['movement_type'] == type)
      .fold<double>(0, (sum, row) => sum + stockNumber(row['total']));

  List<Map<String, dynamic>> get filteredRows {
    final needle = searchController.text.trim().toLowerCase();
    final result = rows.where((row) {
      final meta = movementMeta(row['movement_type']);
      final matchesSearch = needle.isEmpty || '${row['item_name'] ?? ''} ${meta.label} ${row['comment'] ?? ''}'.toLowerCase().contains(needle);
      final matchesType = typeFilter == 'all' || row['movement_type'] == typeFilter;
      final date = parseStockDate(row['created_at']);
      final day = date == null ? null : DateTime(date.year, date.month, date.day);
      final matchesFrom = dateFrom == null || (day != null && !day.isBefore(dateFrom!));
      final matchesTo = dateTo == null || (day != null && !day.isAfter(dateTo!));
      return matchesSearch && matchesType && matchesFrom && matchesTo;
    }).toList();

    result.sort((a, b) {
      switch (sort) {
        case 'date-asc':
          return (parseStockDate(a['created_at']) ?? DateTime(1970)).compareTo(parseStockDate(b['created_at']) ?? DateTime(1970));
        case 'sum-desc':
          return stockNumber(b['total']).compareTo(stockNumber(a['total']));
        case 'sum-asc':
          return stockNumber(a['total']).compareTo(stockNumber(b['total']));
        case 'name':
          return '${a['item_name'] ?? ''}'.toLowerCase().compareTo('${b['item_name'] ?? ''}'.toLowerCase());
        default:
          return (parseStockDate(b['created_at']) ?? DateTime(1970)).compareTo(parseStockDate(a['created_at']) ?? DateTime(1970));
      }
    });
    return result;
  }

  Future<void> _pickDate(bool from) async {
    final selected = await showDatePicker(
      context: context,
      initialDate: (from ? dateFrom : dateTo) ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (selected == null) return;
    setState(() {
      if (from) {
        dateFrom = selected;
      } else {
        dateTo = selected;
      }
    });
  }

  void _resetFilters() {
    searchController.clear();
    setState(() {
      typeFilter = 'all';
      sort = 'date-desc';
      dateFrom = null;
      dateTo = null;
    });
  }

  String _shortDate(DateTime? value) {
    if (value == null) return 'Не выбрана';
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(value.day)}.${two(value.month)}.${value.year}';
  }

  Widget _metric(String title, String value, IconData icon, Color color, {String? note}) => SizedBox(
        width: 158,
        child: MetricCard(title: title, value: value, icon: icon, color: color, note: note),
      );

  Widget _typeChip(String value) {
    final meta = value == 'all'
        ? const MovementMeta('Все', '', AppColors.primary, Icons.swap_horiz_rounded)
        : movementMeta(value);
    return ChoiceChip(
      selected: typeFilter == value,
      onSelected: (_) => setState(() => typeFilter = value),
      avatar: Icon(meta.icon, size: 17, color: typeFilter == value ? AppColors.primary : meta.color),
      label: Text('${meta.label} ${_count(value)}'),
    );
  }

  Widget _movementCard(Map<String, dynamic> row) {
    final meta = movementMeta(row['movement_type']);
    final comment = '${row['comment'] ?? ''}'.trim();
    return Card(
      margin: const EdgeInsets.only(bottom: 9),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          children: [
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: meta.color.withOpacity(.12),
                  child: Icon(meta.icon, color: meta.color),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${row['item_name'] ?? 'Без названия'}', style: const TextStyle(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 3),
                      Text(stockDateTime(row['created_at']), style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                    ],
                  ),
                ),
                StatusPill(meta.label, color: meta.color),
              ],
            ),
            const Divider(height: 24),
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Количество', style: TextStyle(color: AppColors.muted, fontSize: 11)),
                      Text('${meta.sign}${stockQuantity(row['quantity'])}', style: TextStyle(color: meta.color, fontWeight: FontWeight.w900, fontSize: 16)),
                    ],
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      const Text('Сумма операции', style: TextStyle(color: AppColors.muted, fontSize: 11)),
                      Text(money(row['total']), style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
                    ],
                  ),
                ),
              ],
            ),
            if (comment.isNotEmpty) ...[
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(comment, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Движение товара')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? ScreenStateView(icon: Icons.swap_horiz_rounded, title: 'Движения недоступны', message: error!, onAction: loadData)
              : AdaptiveContent(
                  child: RefreshIndicator(
                    onRefresh: loadData,
                    child: ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
                      children: [
                        const SectionTitle('История операций', subtitle: 'Приходы, продажи, возвраты и списания товаров'),
                        const SizedBox(height: 14),
                        Container(
                          padding: const EdgeInsets.all(13),
                          decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(16)),
                          child: const Row(
                            children: [
                              Icon(Icons.info_outline, color: AppColors.primary),
                              SizedBox(width: 10),
                              Expanded(child: Text('Движения услуг здесь не учитываются — журнал относится только к складским товарам.', style: TextStyle(fontSize: 13))),
                            ],
                          ),
                        ),
                        const SizedBox(height: 14),
                        SizedBox(
                          height: 142,
                          child: ListView(
                            scrollDirection: Axis.horizontal,
                            children: [
                              _metric('Всего движений', '${rows.length}', Icons.swap_horiz_rounded, AppColors.primary),
                              const SizedBox(width: 10),
                              _metric('Приходы', '${_count('income')}', Icons.south_rounded, AppColors.success, note: money(_sum('income'))),
                              const SizedBox(width: 10),
                              _metric('Продажи', '${_count('sale')}', Icons.shopping_cart_outlined, AppColors.primary, note: money(_sum('sale'))),
                              const SizedBox(width: 10),
                              _metric('Возвраты', '${_count('refund')}', Icons.keyboard_return_rounded, AppColors.warning, note: money(_sum('refund'))),
                              const SizedBox(width: 10),
                              _metric('Списания', '${_count('writeoff')}', Icons.remove_circle_outline, AppColors.danger, note: money(_sum('writeoff'))),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),
                        SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            children: [
                              _typeChip('all'),
                              const SizedBox(width: 8),
                              _typeChip('income'),
                              const SizedBox(width: 8),
                              _typeChip('sale'),
                              const SizedBox(width: 8),
                              _typeChip('refund'),
                              const SizedBox(width: 8),
                              _typeChip('writeoff'),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: searchController,
                          onChanged: (_) => setState(() {}),
                          decoration: const InputDecoration(
                            hintText: 'Товар, операция или комментарий',
                            prefixIcon: Icon(Icons.search),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(child: _dateButton('Дата от', dateFrom, () => _pickDate(true))),
                            const SizedBox(width: 10),
                            Expanded(child: _dateButton('Дата до', dateTo, () => _pickDate(false))),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: sort,
                                decoration: const InputDecoration(labelText: 'Сортировка'),
                                items: const [
                                  DropdownMenuItem(value: 'date-desc', child: Text('Сначала новые')),
                                  DropdownMenuItem(value: 'date-asc', child: Text('Сначала старые')),
                                  DropdownMenuItem(value: 'sum-desc', child: Text('Сумма ↓')),
                                  DropdownMenuItem(value: 'sum-asc', child: Text('Сумма ↑')),
                                  DropdownMenuItem(value: 'name', child: Text('По товару')),
                                ],
                                onChanged: (value) => setState(() => sort = value ?? 'date-desc'),
                              ),
                            ),
                            const SizedBox(width: 10),
                            OutlinedButton.icon(onPressed: _resetFilters, icon: const Icon(Icons.restart_alt), label: const Text('Сбросить')),
                          ],
                        ),
                        const SizedBox(height: 20),
                        SectionTitle('Операции', subtitle: 'Показано ${filteredRows.length} из ${rows.length}'),
                        const SizedBox(height: 10),
                        if (filteredRows.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 38),
                            child: Center(child: Text('Операции по выбранным условиям не найдены', style: TextStyle(color: AppColors.muted))),
                          )
                        else
                          ...filteredRows.map(_movementCard),
                      ],
                    ),
                  ),
                ),
    );
  }

  Widget _dateButton(String label, DateTime? value, VoidCallback onTap) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: InputDecorator(
          decoration: InputDecoration(labelText: label, suffixIcon: const Icon(Icons.calendar_month_outlined)),
          child: Text(_shortDate(value), style: TextStyle(color: value == null ? AppColors.muted : AppColors.text)),
        ),
      );
}
