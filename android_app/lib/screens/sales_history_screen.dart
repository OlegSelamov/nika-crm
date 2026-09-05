import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'shift_detail_screen.dart';

class SalesHistoryScreen extends StatefulWidget {
  const SalesHistoryScreen({super.key});

  @override
  State<SalesHistoryScreen> createState() => _SalesHistoryScreenState();
}

class _SalesHistoryScreenState extends State<SalesHistoryScreen> {
  static const pageSize = 50;

  bool loading = true;
  bool loadingMore = false;
  bool hasMore = false;
  int page = 0;
  String? error;
  String? historyWarning;
  Map<String, dynamic> status = {};
  final List<Map<String, dynamic>> currentOperations = [];
  final List<Map<String, dynamic>> closedShifts = [];

  @override
  void initState() {
    super.initState();
    loadHistory();
  }

  Future<void> loadHistory() async {
    if (mounted) {
      setState(() {
        loading = true;
        error = null;
        historyWarning = null;
      });
    }

    try {
      final loadedStatus = await ApiService.shiftStatus();
      final openedShift = _shiftFromStatus(loadedStatus);
      final isOpen = loadedStatus['shift_open'] == true;
      final number = shiftNumberFrom(openedShift);
      final serial = shiftSerialFrom(openedShift);
      final results = await Future.wait<dynamic>([
        ApiService.shiftHistory(page: 0, size: pageSize).catchError(
          (e) => <String, dynamic>{'_error': readableError(e)},
        ),
        isOpen && number != null
            ? ApiService.getSalesHistory(
                shiftNumber: number,
                serialNumber: serial.isEmpty ? null : serial,
                page: 0,
                size: pageSize,
              ).catchError((_) => <dynamic>[])
            : Future<dynamic>.value(<dynamic>[]),
      ]);
      final historyResponse = Map<String, dynamic>.from(results[0] as Map);
      final loaded = _extractHistory(historyResponse['history']);
      final operations = List<dynamic>.from(results[1] as List)
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
      if (!mounted) return;
      setState(() {
        status = Map<String, dynamic>.from(loadedStatus);
        currentOperations
          ..clear()
          ..addAll(operations);
        closedShifts
          ..clear()
          ..addAll(loaded);
        _sortAndDeduplicate();
        page = 0;
        hasMore = historyResponse['has_more'] == true ||
            (historyResponse['_error'] == null && loaded.length >= pageSize);
        historyWarning = (historyResponse['_error'] ??
                historyResponse['warning'])
            ?.toString();
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

  Future<void> loadMore() async {
    if (loadingMore || !hasMore) return;
    setState(() => loadingMore = true);
    try {
      final nextPage = page + 1;
      final response = await ApiService.shiftHistory(
        page: nextPage,
        size: pageSize,
      );
      final loaded = _extractHistory(response['history']);
      if (!mounted) return;
      setState(() {
        closedShifts.addAll(loaded);
        _sortAndDeduplicate();
        page = nextPage;
        hasMore = response['has_more'] == true || loaded.length >= pageSize;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => loadingMore = false);
    }
  }

  List<Map<String, dynamic>> _extractHistory(dynamic raw) {
    dynamic source = raw;
    if (source is Map) {
      for (final key in const ['content', 'items', 'shifts', 'data']) {
        if (source[key] is List) {
          source = source[key];
          break;
        }
      }
    }
    if (source is! List) return [];
    return source
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .where((item) => shiftNumberFrom(item) != null)
        .toList();
  }

  void _sortAndDeduplicate() {
    final unique = <String, Map<String, dynamic>>{};
    for (final item in closedShifts) {
      final number = shiftNumberFrom(item);
      unique['$number'] = item;
    }
    closedShifts
      ..clear()
      ..addAll(unique.values)
      ..sort((a, b) => _timeValue(shiftCloseTimeFrom(b)).compareTo(
            _timeValue(shiftCloseTimeFrom(a)),
          ));
  }

  int _timeValue(dynamic value) {
    if (value is num) {
      final raw = value.toInt();
      return raw < 100000000000 ? raw * 1000 : raw;
    }
    return DateTime.tryParse('${value ?? ''}')?.millisecondsSinceEpoch ?? 0;
  }

  bool get shiftIsOpen => status['shift_open'] == true;

  Map<String, dynamic> _shiftFromStatus(Map<String, dynamic> source) {
    final raw = source['shift'];
    final result = raw is Map
        ? Map<String, dynamic>.from(raw)
        : <String, dynamic>{};
    result['shiftNumber'] ??= source['shift_number'];
    result['serialNumber'] ??=
        source['serial_number'] ?? source['znm'] ?? source['serialNumber'];
    result['openShiftTime'] ??=
        source['open_shift_time'] ?? source['openShiftTime'];
    return result;
  }

  Map<String, dynamic> get currentShift => _shiftFromStatus(status);

  Map<String, dynamic> get cashRegister {
    final raw = status['cash_register'];
    return raw is Map
        ? Map<String, dynamic>.from(raw)
        : <String, dynamic>{};
  }

  Future<void> _openShift(
    Map<String, dynamic> shift, {
    required bool isOpen,
  }) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ShiftDetailScreen(
          shift: shift,
          cashRegister: cashRegister,
          isOpen: isOpen,
        ),
      ),
    );
    if (mounted && isOpen) await loadHistory();
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.history_toggle_off_rounded,
        title: 'История не загрузилась',
        message: error!,
        onAction: loadHistory,
      );
    }

    return RefreshIndicator(
      onRefresh: loadHistory,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.fromLTRB(16, 14, 16, 10),
              child: SectionTitle(
                'Текущая смена',
                subtitle: 'Продажи и возвраты с момента открытия кассы',
              ),
            ),
          ),
          SliverToBoxAdapter(child: _currentShiftCard()),
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.fromLTRB(16, 26, 16, 10),
              child: SectionTitle(
                'Закрытые смены',
                subtitle: 'Чеки и Z‑отчёты сгруппированы по сменам',
              ),
            ),
          ),
          if (historyWarning != null)
            SliverToBoxAdapter(child: _historyWarning()),
          if (closedShifts.isEmpty)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: ScreenStateView(
                icon: Icons.inventory_2_outlined,
                title: 'Закрытых смен пока нет',
                message: 'После закрытия кассы смена появится в этом разделе.',
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              sliver: SliverList.separated(
                itemCount: closedShifts.length,
                separatorBuilder: (_, __) => const SizedBox(height: 10),
                itemBuilder: (_, index) => _closedShiftCard(closedShifts[index]),
              ),
            ),
          if (hasMore)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                child: OutlinedButton.icon(
                  onPressed: loadingMore ? null : loadMore,
                  icon: loadingMore
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.expand_more_rounded),
                  label: Text(loadingMore ? 'Загрузка…' : 'Показать ещё'),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _currentShiftCard() {
    if (!shiftIsOpen) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Row(children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: AppColors.muted.withOpacity(.1),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(
                  Icons.lock_clock_outlined,
                  color: AppColors.muted,
                ),
              ),
              const SizedBox(width: 13),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Смена не открыта',
                      style: TextStyle(fontWeight: FontWeight.w800),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Новые чеки появятся после открытия смены',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ]),
          ),
        ),
      );
    }

    final shift = currentShift;
    final number = shiftNumberFrom(shift) ?? status['shift_number'] ?? '—';
    final tickets = shiftTicketCountFrom(shift) ?? currentOperations.length;
    final revenue = shiftRevenueFrom(shift) ?? _currentRevenue();
    final opened = shiftOpenTimeFrom(shift);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _openShift(shift, isOpen: true),
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Row(children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: AppColors.success.withOpacity(.11),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: const Icon(
                  Icons.point_of_sale_rounded,
                  color: AppColors.success,
                ),
              ),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(
                        child: Text(
                          'Смена №$number',
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                      const StatusPill('Открыта', color: AppColors.success),
                    ]),
                    const SizedBox(height: 6),
                    Text(
                      opened == null
                          ? 'Идёт сейчас'
                          : 'Открыта ${shiftDateLabel(opened)}',
                      style: const TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                    if (tickets != null || revenue != null) ...[
                      const SizedBox(height: 7),
                      Text(
                        [
                          if (revenue != null) money(revenue),
                          if (tickets != null) 'Чеков: $tickets',
                        ].join('  •  '),
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 6),
              const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
            ]),
          ),
        ),
      ),
    );
  }

  double? _currentRevenue() {
    if (currentOperations.isEmpty) return null;
    var total = 0.0;
    for (final operation in currentOperations) {
      final refunded = operation['is_refunded'] == true ||
          '${operation['status']}' == 'Возврат';
      final amount = asDouble(operation['total']);
      total += refunded ? -amount : amount;
    }
    return total;
  }

  Widget _closedShiftCard(Map<String, dynamic> shift) {
    final number = shiftNumberFrom(shift) ?? '—';
    final revenue = shiftRevenueFrom(shift);
    final tickets = shiftTicketCountFrom(shift);
    final opened = shiftOpenTimeFrom(shift);
    final closed = shiftCloseTimeFrom(shift);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => _openShift(shift, isOpen: false),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                color: AppColors.primarySoft,
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Icon(
                Icons.inventory_2_outlined,
                color: AppColors.primary,
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                      child: Text(
                        'Смена №$number',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                    if (revenue != null)
                      Text(
                        money(revenue),
                        style: const TextStyle(fontWeight: FontWeight.w900),
                      ),
                  ]),
                  const SizedBox(height: 5),
                  Text(
                    _periodLabel(opened, closed),
                    style: const TextStyle(color: AppColors.muted, fontSize: 12),
                  ),
                  const SizedBox(height: 7),
                  Wrap(
                    spacing: 12,
                    runSpacing: 5,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(
                            Icons.receipt_long_outlined,
                            size: 15,
                            color: AppColors.muted,
                          ),
                          const SizedBox(width: 5),
                          Text(
                            tickets == null
                                ? 'Чеки внутри смены'
                                : 'Чеков: $tickets',
                            style: const TextStyle(
                              color: AppColors.muted,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                      const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.summarize_outlined,
                            size: 15,
                            color: AppColors.primary,
                          ),
                          SizedBox(width: 5),
                          Text(
                            'Z‑отчёт',
                            style: TextStyle(
                              color: AppColors.primary,
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 6),
            const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
          ]),
        ),
      ),
    );
  }

  String _periodLabel(dynamic opened, dynamic closed) {
    if (opened != null && closed != null) {
      return '${shiftDateLabel(opened)} — ${shiftDateLabel(closed)}';
    }
    if (closed != null) return 'Закрыта ${shiftDateLabel(closed)}';
    if (opened != null) return 'Открыта ${shiftDateLabel(opened)}';
    return 'Закрытая смена';
  }

  Widget _historyWarning() => Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppColors.warning.withOpacity(.1),
            borderRadius: BorderRadius.circular(14),
          ),
          child: const Row(children: [
            Icon(Icons.info_outline_rounded, color: AppColors.warning),
            SizedBox(width: 9),
            Expanded(
              child: Text(
                'Архив закрытых смен временно недоступен. Потяните экран вниз, чтобы повторить.',
                style: TextStyle(fontSize: 12),
              ),
            ),
          ]),
        ),
      );
}
