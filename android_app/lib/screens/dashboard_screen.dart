import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onOpenSection;
  final int refreshToken;

  // Optional loaders allow a deterministic refresh regression test without
  // talking to the network, fiscal provider or a real customer account.
  final Future<Map<String, dynamic>?> Function()? readCachedDashboard;
  final Future<Map<String, dynamic>> Function()? fetchDashboard;
  final Future<Map<String, dynamic>> Function()? fetchShift;

  const DashboardScreen({
    super.key,
    this.onOpenSection,
    this.refreshToken = 0,
    this.readCachedDashboard,
    this.fetchDashboard,
    this.fetchShift,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool loading = true;
  bool refreshing = false;
  bool showingCached = false;
  String? error;
  Map<String, dynamic> dashboard = {};
  Map<String, dynamic> shift = {};
  int _requestGeneration = 0;

  @override
  void initState() {
    super.initState();
    unawaited(loadData());
  }

  @override
  void didUpdateWidget(covariant DashboardScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.refreshToken != oldWidget.refreshToken) {
      unawaited(loadData());
    }
  }

  @override
  void dispose() {
    _requestGeneration++;
    super.dispose();
  }

  // The remote reKassa status may be delayed by the provider or unavailable
  // for a company. It must NEVER hold back the revenue dashboard.
  Future<void> _loadShift(int generation) async {
    try {
      final status = await (widget.fetchShift?.call() ??
          ApiService.shiftStatus(timeout: const Duration(seconds: 5)));
      if (!mounted || generation != _requestGeneration) return;
      setState(() => shift = status['success'] == true ? status : {});
    } catch (_) {
      if (!mounted || generation != _requestGeneration) return;
      setState(() => shift = {});
    }
  }

  Future<void> loadData() async {
    final generation = ++_requestGeneration;
    if (!mounted) return;
    setState(() {
      error = null;
      refreshing = true;
      if (dashboard.isEmpty) loading = true;
    });

    // Read the company-scoped, same-day snapshot first so even on a slow
    // connection the home screen shows the last real values immediately.
    // Every entry/refresh still starts a real server request below.
    unawaited(_loadShift(generation));
    if (dashboard.isEmpty) {
      try {
        final cached = await (widget.readCachedDashboard?.call() ??
            ApiService.cachedDashboard());
        if (!mounted || generation != _requestGeneration) return;
        if (cached != null && cached['success'] == true) {
          setState(() {
            dashboard = cached;
            loading = false;
            showingCached = true;
          });
        }
      } catch (_) {
        // A corrupt/unavailable local snapshot should never stop the network.
      }
    }
    if (!mounted || generation != _requestGeneration) return;

    try {
      final fresh = await (widget.fetchDashboard?.call() ??
          ApiService.dashboard(forceRemote: true, allowCachedOnFailure: false));
      if (!mounted || generation != _requestGeneration) return;
      if (fresh['success'] != true) {
        throw const ApiException('Сервер не вернул актуальные показатели');
      }
      setState(() {
        dashboard = fresh;
        loading = false;
        refreshing = false;
        showingCached = false;
        error = null;
      });
    } catch (e) {
      if (!mounted || generation != _requestGeneration) return;
      setState(() {
        error = readableError(e);
        loading = false;
        refreshing = false;
        showingCached = dashboard.isNotEmpty;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null && dashboard.isEmpty) {
      return ScreenStateView(
        icon: Icons.cloud_off_rounded,
        title: 'Не удалось загрузить главную',
        message: error!,
        onAction: loadData,
      );
    }

    final shiftOpen = shift['shift_open'] == true;
    final revenueToday = dashboard['revenue'] ?? dashboard['today'] ?? 0;
    final salesToday = dashboard['sales_count'] ?? dashboard['sales_today'] ?? 0;
    final returnsCount = dashboard['returns_count'] ?? 0;

    return RefreshIndicator(
      onRefresh: loadData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
        children: [
          if (refreshing || showingCached) ...[
            Row(children: [
              if (refreshing)
                const SizedBox(
                  width: 13, height: 13,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                const Icon(Icons.cloud_off_outlined,
                    size: 16, color: AppColors.warning),
              const SizedBox(width: 8),
              Expanded(child: Text(
                refreshing
                    ? 'Обновляем показатели…'
                    : 'Показаны сохранённые данные · нет связи с сервером',
                style: const TextStyle(fontSize: 12, color: AppColors.muted),
              )),
            ]),
            const SizedBox(height: 10),
          ],
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
                      shift['success'] != true
                          ? 'Смена: —'
                          : shiftOpen
                              ? 'Смена №${shift['shift_number'] ?? '—'} открыта'
                              : 'Смена закрыта',
                      color: shiftOpen ? const Color(0xFF73E2B8) : Colors.white70,
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                const Text(
                  'Выручка',
                  style: TextStyle(color: Colors.white70, fontSize: 14),
                ),
                const SizedBox(height: 5),
                Text(
                  money(revenueToday),
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
                      money(dashboard['net_profit'] ?? 0),
                      'чистая прибыль',
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionTitle('Сегодня', subtitle: 'С 00:00 до текущего момента'),
          const SizedBox(height: 12),
          ResponsiveGrid(
            minItemWidth: 190,
            minColumns: 2,
            maxColumns: 4,
            childAspectRatio: 1.25,
            children: [
              MetricCard(
                title: 'Средний чек',
                value: money(dashboard['average_check'] ?? 0),
                icon: Icons.receipt_long_outlined,
                color: AppColors.primary,
              ),
              MetricCard(
                title: 'Закупки',
                value: money(dashboard['purchase_total'] ?? 0),
                icon: Icons.shopping_cart_outlined,
                color: AppColors.cyan,
                note: 'приход товара',
              ),
              MetricCard(
                title: 'Прочие расходы',
                value: money(dashboard['operating_expenses'] ?? 0),
                icon: Icons.account_balance_wallet_outlined,
                color: AppColors.warning,
                note: 'без закупок',
              ),
              MetricCard(
                title: 'Возвраты',
                value: money(dashboard['returns_total'] ?? 0),
                icon: Icons.undo_rounded,
                color: AppColors.danger,
                note: '$returnsCount операций',
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
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: Theme.of(context).colorScheme.onSurface,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
