import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  late DateTimeRange period;
  bool loading = true;
  String? error;
  Map<String, dynamic> data = {};

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    period = DateTimeRange(start: DateTime(now.year, now.month, 1), end: now);
    loadAnalytics();
  }

  String _date(DateTime value) =>
      '${value.year}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';

  String _short(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}.${value.month.toString().padLeft(2, '0')}.${value.year}';

  Future<void> loadAnalytics() async {
    if (mounted) setState(() => error = null);
    try {
      final result = await ApiService.analytics(
        dateFrom: _date(period.start),
        dateTo: _date(period.end),
      );
      if (!mounted) return;
      setState(() {
        data = result;
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = readableError(e);
        loading = false;
      });
    }
  }

  Future<void> _selectPeriod() async {
    final selected = await showDateRangePicker(
      context: context,
      initialDateRange: period,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      helpText: 'Период аналитики',
      saveText: 'Применить',
    );
    if (selected == null) return;
    setState(() {
      period = selected;
      loading = true;
    });
    await loadAnalytics();
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.query_stats_rounded,
        title: 'Аналитика недоступна',
        message: error!,
        onAction: loadAnalytics,
      );
    }

    final topClients = List<dynamic>.from(data['top_clients'] ?? const []);
    final topItems = List<dynamic>.from(data['top_items'] ?? const []);
    final revenue = asDouble(data['revenue']);
    final profit = asDouble(data['profit']);
    final payments = <Map<String, dynamic>>[
      {'label': 'Наличные', 'value': asDouble(data['cash']), 'color': AppColors.success},
      {'label': 'Карта', 'value': asDouble(data['card']), 'color': AppColors.cyan},
      {'label': 'Kaspi', 'value': asDouble(data['kaspi']), 'color': AppColors.primary},
    ];

    return RefreshIndicator(
      onRefresh: loadAnalytics,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
        children: [
          Card(
            child: InkWell(
              onTap: _selectPeriod,
              borderRadius: BorderRadius.circular(20),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    const Icon(Icons.calendar_month_rounded, color: AppColors.primary),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Период', style: TextStyle(color: AppColors.muted, fontSize: 12)),
                          const SizedBox(height: 3),
                          Text(
                            '${_short(period.start)} — ${_short(period.end)}',
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.tune_rounded, color: AppColors.muted),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          ResponsiveGrid(
            minItemWidth: 190,
            minColumns: 2,
            maxColumns: 4,
            childAspectRatio: 1.22,
            children: [
              MetricCard(
                title: 'Чистая выручка',
                value: money(revenue),
                icon: Icons.payments_outlined,
                color: AppColors.primary,
              ),
              MetricCard(
                title: 'Прибыль',
                value: money(profit),
                icon: Icons.trending_up_rounded,
                color: profit >= 0 ? AppColors.success : AppColors.danger,
              ),
              MetricCard(
                title: 'Продаж',
                value: '${asDouble(data['sales_count']).round()}',
                icon: Icons.receipt_long_outlined,
                color: AppColors.cyan,
              ),
              MetricCard(
                title: 'Средний чек',
                value: money(data['average_check']),
                icon: Icons.shopping_cart_outlined,
                color: AppColors.warning,
              ),
            ],
          ),
          const SizedBox(height: 24),
          const SectionTitle('Способы оплаты'),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: payments.map((payment) {
                  final value = payment['value'] as double;
                  final ratio = revenue <= 0
                      ? 0.0
                      : (value / revenue).clamp(0.0, 1.0).toDouble();
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text(payment['label'] as String)),
                            Text(money(value), style: const TextStyle(fontWeight: FontWeight.w800)),
                          ],
                        ),
                        const SizedBox(height: 7),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(99),
                          child: LinearProgressIndicator(
                            value: ratio,
                            minHeight: 7,
                            color: payment['color'] as Color,
                            backgroundColor: AppColors.border,
                          ),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          if (topItems.isNotEmpty) ...[
            const SizedBox(height: 24),
            const SectionTitle('Топ товаров'),
            const SizedBox(height: 12),
            _ranking(topItems, 'name'),
          ],
          if (topClients.isNotEmpty) ...[
            const SizedBox(height: 24),
            const SectionTitle('Топ клиентов'),
            const SizedBox(height: 12),
            _ranking(topClients, 'full_name'),
          ],
        ],
      ),
    );
  }

  Widget _ranking(List<dynamic> values, String nameKey) {
    return Card(
      child: Column(
        children: values.take(10).toList().asMap().entries.map((entry) {
          final item = Map<String, dynamic>.from(entry.value as Map);
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: AppColors.primarySoft,
              foregroundColor: AppColors.primary,
              child: Text('${entry.key + 1}', style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
            title: Text('${item[nameKey] ?? 'Без названия'}', maxLines: 1, overflow: TextOverflow.ellipsis),
            trailing: Text(money(item['total']), style: const TextStyle(fontWeight: FontWeight.w800)),
          );
        }).toList(),
      ),
    );
  }
}
