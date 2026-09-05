import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onOpenSection;

  const DashboardScreen({super.key, this.onOpenSection});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool loading = true;
  String? error;
  Map<String, dynamic> dashboard = {};
  Map<String, dynamic> analytics = {};
  Map<String, dynamic> shift = {};
  int unread = 0;

  @override
  void initState() {
    super.initState();
    loadData();
  }

  Future<void> loadData() async {
    if (mounted) setState(() => error = null);
    try {
      final results = await Future.wait<dynamic>([
        ApiService.dashboard(),
        ApiService.analytics().catchError((_) => <String, dynamic>{}),
        ApiService.shiftStatus().catchError((_) => <String, dynamic>{}),
        ApiService.notifications().catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      setState(() {
        dashboard = Map<String, dynamic>.from(results[0]);
        analytics = Map<String, dynamic>.from(results[1]);
        shift = Map<String, dynamic>.from(results[2]);
        unread = int.tryParse('${results[3]['unread_count'] ?? 0}') ?? 0;
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

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.cloud_off_rounded,
        title: 'Не удалось загрузить главную',
        message: error!,
        onAction: loadData,
      );
    }

    final shiftOpen = shift['shift_open'] == true;
    final today = dashboard['today'] ?? analytics['revenue'] ?? 0;
    final salesToday = dashboard['sales_today'] ?? 0;

    return RefreshIndicator(
      onRefresh: loadData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
        children: [
          Container(
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [AppColors.navy, AppColors.navySoft, Color(0xFF44359B)],
              ),
              borderRadius: BorderRadius.circular(26),
              boxShadow: [
                BoxShadow(
                  color: AppColors.navy.withOpacity(.18),
                  blurRadius: 24,
                  offset: const Offset(0, 12),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Expanded(
                      child: Text(
                        'Сегодня',
                        style: TextStyle(color: Colors.white70, fontSize: 14),
                      ),
                    ),
                    StatusPill(
                      shiftOpen
                          ? 'Смена №${shift['shift_number'] ?? '—'} открыта'
                          : 'Смена закрыта',
                      color: shiftOpen ? const Color(0xFF73E2B8) : Colors.white70,
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                const Text(
                  'Чистая выручка',
                  style: TextStyle(color: Colors.white70, fontSize: 14),
                ),
                const SizedBox(height: 5),
                Text(
                  money(today),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 34,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -1,
                  ),
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    _heroFact(Icons.receipt_long_rounded, '$salesToday', 'продаж'),
                    const SizedBox(width: 22),
                    _heroFact(
                      Icons.trending_up_rounded,
                      money(analytics['profit'] ?? 0),
                      'прибыль',
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionTitle('Ключевые показатели', subtitle: 'Данные обновляются с сайта'),
          const SizedBox(height: 12),
          ResponsiveGrid(
            minItemWidth: 190,
            minColumns: 2,
            maxColumns: 4,
            childAspectRatio: 1.25,
            children: [
              MetricCard(
                title: 'Средний чек',
                value: money(analytics['average_check'] ?? 0),
                icon: Icons.shopping_bag_outlined,
                color: AppColors.primary,
              ),
              MetricCard(
                title: 'Клиентов',
                value: '${dashboard['clients'] ?? 0}',
                icon: Icons.people_alt_outlined,
                color: AppColors.cyan,
              ),
              MetricCard(
                title: 'Товаров и услуг',
                value: '${dashboard['items'] ?? 0}',
                icon: Icons.inventory_2_outlined,
                color: AppColors.warning,
              ),
              MetricCard(
                title: 'Уведомления',
                value: '$unread',
                icon: Icons.notifications_none_rounded,
                color: unread > 0 ? AppColors.danger : AppColors.success,
                note: unread > 0 ? 'требуют внимания' : 'всё прочитано',
              ),
            ],
          ),
          const SizedBox(height: 24),
          const SectionTitle('Быстрые действия'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _quickAction(
                  icon: Icons.point_of_sale_rounded,
                  title: 'Новая продажа',
                  color: AppColors.primary,
                  onTap: () => widget.onOpenSection?.call(1),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _quickAction(
                  icon: Icons.history_rounded,
                  title: 'История',
                  color: AppColors.cyan,
                  onTap: () => widget.onOpenSection?.call(2),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _heroFact(IconData icon, String value, String label) {
    return Expanded(
      child: Row(
        children: [
          Icon(icon, color: Colors.white70, size: 20),
          const SizedBox(width: 8),
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800),
                ),
                Text(label, style: const TextStyle(color: Colors.white60, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _quickAction({
    required IconData icon,
    required String title,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: color.withOpacity(.12),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: Icon(icon, color: color),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.text),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
