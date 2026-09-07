import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'shift_detail_screen.dart';
import 'sale_detail_screen.dart';

class SalesHistoryScreen extends StatefulWidget {
  const SalesHistoryScreen({super.key});

  @override
  State<SalesHistoryScreen> createState() => _SalesHistoryScreenState();
}

class _SalesHistoryScreenState extends State<SalesHistoryScreen> {
  static const pageSize = 50;

  bool loading = true;
  int historyTab = 0;
  int documentFilter = 0;
  final List<Map<String, dynamic>> documentSales = [];
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
        ApiService.getSalesHistory(allHistory: true, page: 0, size: 100).catchError((_) => <dynamic>[]),
      ]);
      final historyResponse = Map<String, dynamic>.from(results[0] as Map);
      final loaded = _extractHistory(historyResponse['history']);
      final operations = List<dynamic>.from(results[1] as List)
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
      final docs = List<dynamic>.from(results[2] as List)
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
        documentSales
          ..clear()
          ..addAll(docs);
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

    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFF8F6FF), Color(0xFFF1F7FF), Color(0xFFF9FBFF)],
        ),
      ),
      child: RefreshIndicator(
      onRefresh: loadHistory,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(child: _historyTabs()),
          if (historyTab == 1) ..._documentSlivers() else ...[
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
        ],
      ),
    ),
    );
  }

  Widget _historyTabs() => Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
        child: Container(
          padding: const EdgeInsets.all(5),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(.9),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: AppColors.border),
            boxShadow: [BoxShadow(color: Colors.black.withOpacity(.04), blurRadius: 18, offset: const Offset(0, 7))],
          ),
          child: Row(children: [
            Expanded(child: _historyTabButton(0, 'Смены', Icons.point_of_sale_rounded)),
            Expanded(child: _historyTabButton(1, 'Документы', Icons.description_rounded)),
          ]),
        ),
      );

  Widget _historyTabButton(int index, String label, IconData icon) {
    final selected = historyTab == index;
    return InkWell(
      onTap: () => setState(() => historyTab = index),
      borderRadius: BorderRadius.circular(16),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          gradient: selected ? const LinearGradient(colors: [Color(0xFF7257FF), Color(0xFF8D62FF)]) : null,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, size: 18, color: selected ? Colors.white : AppColors.muted),
          const SizedBox(width: 7),
          Text(label, style: TextStyle(fontWeight: FontWeight.w800, color: selected ? Colors.white : AppColors.navy)),
        ]),
      ),
    );
  }

  List<Widget> _documentSlivers() {
    const names = ['Все', 'Счета', 'Накладные', 'Акты', 'ЭСФ'];
    return [
      SliverToBoxAdapter(
        child: SizedBox(
          height: 48,
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            scrollDirection: Axis.horizontal,
            itemCount: names.length,
            separatorBuilder: (_, __) => const SizedBox(width: 7),
            itemBuilder: (_, i) => ChoiceChip(
              label: Text(names[i]),
              selected: documentFilter == i,
              showCheckmark: false,
              onSelected: (_) => setState(() => documentFilter = i),
            ),
          ),
        ),
      ),
      const SliverToBoxAdapter(child: SizedBox(height: 10)),
      if (documentSales.isEmpty)
        const SliverFillRemaining(
          hasScrollBody: false,
          child: ScreenStateView(
            icon: Icons.description_outlined,
            title: 'Документов пока нет',
            message: 'Счета и документы по продажам будут собраны здесь.',
          ),
        )
      else
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
          sliver: SliverList.separated(
            itemCount: documentSales.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (_, i) => _documentSaleCard(documentSales[i]),
          ),
        ),
    ];
  }

  Widget _documentSaleCard(Map<String, dynamic> sale) {
    final id = sale['id'] ?? sale['sale_id'] ?? '—';
    final total = asDouble(sale['total'] ?? sale['amount']);
    final client = '${sale['client_name'] ?? sale['client'] ?? 'Частное лицо'}';
    final raw = '${sale['status'] ?? sale['payment_status'] ?? ''}'.toLowerCase();
    final invoice = '${sale['sale_type'] ?? sale['payment_method'] ?? ''}'.toLowerCase() == 'invoice' ||
        sale['invoice_number'] != null || raw.contains('счёт выставлен') || raw.contains('pending');
    final paid = raw.contains('paid') || raw.contains('оплачен') || raw.contains('success');
    final statusText = paid ? 'Оплачено' : (invoice ? 'Ожидает оплаты' : 'Проведено');
    final statusColor = paid ? AppColors.success : (invoice ? AppColors.warning : AppColors.primary);

    return Card(
      elevation: 0,
      color: Colors.white.withOpacity(.92),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22), side: const BorderSide(color: AppColors.border)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 46, height: 46,
              decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(14)),
              child: const Icon(Icons.description_rounded, color: AppColors.primary),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(invoice ? 'Счёт №${sale['invoice_number'] ?? id}' : 'Продажа №$id',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
              const SizedBox(height: 3),
              Text(client, maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.muted, fontSize: 12)),
            ])),
            StatusPill(statusText, color: statusColor),
          ]),
          const SizedBox(height: 13),
          Text(money(total), style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900)),
          const SizedBox(height: 12),
          Wrap(spacing: 7, runSpacing: 7, children: [
            _documentBadge(Icons.receipt_long_outlined, 'Счёт'),
            _documentBadge(Icons.local_shipping_outlined, 'Накладная'),
            _documentBadge(Icons.task_alt_rounded, 'Акт'),
            _documentBadge(Icons.description_outlined, 'Счёт-фактура'),
            _documentBadge(Icons.cloud_done_outlined, 'ЭСФ'),
          ]),
          const SizedBox(height: 13),
          Row(children: [
            Expanded(child: OutlinedButton.icon(
              onPressed: () async {
                final parsed = int.tryParse('$id');
                if (parsed == null) return;
                try {
                  final detail = await ApiService.getSale(parsed);
                  if (!mounted) return;
                  await showModalBottomSheet<bool>(
                    context: context,
                    isScrollControlled: true,
                    backgroundColor: Colors.transparent,
                    builder: (_) => _SaleActionsSheet(sale: detail),
                  );
                  if (mounted) await loadHistory();
                } catch (e) {
                  if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
                }
              },
              icon: const Icon(Icons.visibility_outlined, size: 18),
              label: const Text('Открыть'),
            )),
            const SizedBox(width: 8),
            Container(
              width: 48, height: 48,
              decoration: BoxDecoration(border: Border.all(color: AppColors.border), borderRadius: BorderRadius.circular(14)),
              child: const Icon(Icons.more_horiz_rounded),
            ),
          ]),
        ]),
      ),
    );
  }

  Widget _documentBadge(IconData icon, String label) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
        decoration: BoxDecoration(color: const Color(0xFFF6F4FF), borderRadius: BorderRadius.circular(11)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 15, color: AppColors.primary),
          const SizedBox(width: 5),
          Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700)),
        ]),
      );

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


class _SaleActionsSheet extends StatefulWidget {
  final Map<String, dynamic> sale;
  const _SaleActionsSheet({required this.sale});

  @override
  State<_SaleActionsSheet> createState() => _SaleActionsSheetState();
}

class _SaleActionsSheetState extends State<_SaleActionsSheet> {
  bool paying = false;

  Map<String, dynamic> get sale => widget.sale;
  int get saleId => int.tryParse('${sale['id'] ?? sale['sale_id'] ?? ''}') ?? 0;
  bool get isInvoice => '${sale['sale_type'] ?? ''}' == 'invoice';
  bool get isPaid => '${sale['status'] ?? ''}' == 'Оплачено';

  Future<void> _markPaid() async {
    if (saleId <= 0 || paying) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        icon: const Icon(Icons.payments_rounded, color: AppColors.success, size: 36),
        title: const Text('Подтвердить оплату?'),
        content: Text('Счёт №${sale['sale_number'] ?? saleId} будет отмечен оплаченным. После этого станут доступны закрывающие документы.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Оплата получена')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => paying = true);
    try {
      final result = await ApiService.markInvoicePaid(saleId);
      if (!mounted) return;
      if (result['success'] != true) throw ApiException('${result['error'] ?? 'Не удалось подтвердить оплату'}');
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Оплата подтверждена')));
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    } finally {
      if (mounted) setState(() => paying = false);
    }
  }

  Future<void> _openSale() async {
    Navigator.pop(context);
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => SaleDetailScreen(saleId: saleId)),
    );
  }

  void _documentMessage(String label, {bool needsPaid = true}) {
    if (needsPaid && !isPaid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала подтвердите оплату счёта')),
      );
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$label привязан к продаже. Предпросмотр PDF подключим к общей модалке документов.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final total = asDouble(sale['total_amount'] ?? sale['total'] ?? sale['amount']);
    final number = sale['sale_number'] ?? saleId;
    return SafeArea(
      child: Container(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * .86),
        padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
        decoration: const BoxDecoration(
          color: Color(0xFFF8F8FD),
          borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
        ),
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Center(child: Container(width: 44, height: 5, decoration: BoxDecoration(color: AppColors.border, borderRadius: BorderRadius.circular(8)))),
            const SizedBox(height: 18),
            Row(children: [
              Expanded(child: Text(isInvoice ? 'Счёт №$number' : 'Продажа №$number', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900))),
              StatusPill(isPaid ? 'Оплачено' : '${sale['status'] ?? 'Проведено'}', color: isPaid ? AppColors.success : AppColors.warning),
            ]),
            const SizedBox(height: 5),
            Text(money(total), style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w900)),
            if (isInvoice && !isPaid) ...[
              const SizedBox(height: 16),
              SizedBox(width: double.infinity, child: FilledButton.icon(
                onPressed: paying ? null : _markPaid,
                icon: paying
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.payments_rounded),
                label: Text(paying ? 'Подтверждаем…' : 'Подтвердить оплату'),
              )),
            ],
            const SizedBox(height: 20),
            const Text('Документы и действия', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
            const SizedBox(height: 10),
            Wrap(spacing: 8, runSpacing: 8, children: [
              _SheetAction(Icons.receipt_long_outlined, 'Счёт', onTap: () => _documentMessage('Счёт', needsPaid: false)),
              _SheetAction(Icons.local_shipping_outlined, 'Накладная', onTap: () => _documentMessage('Накладная')),
              _SheetAction(Icons.task_alt_rounded, 'Акт', onTap: () => _documentMessage('Акт')),
              _SheetAction(Icons.description_outlined, 'Счёт-фактура', onTap: () => _documentMessage('Счёт-фактура')),
              _SheetAction(Icons.cloud_done_outlined, 'ЭСФ', onTap: () => _documentMessage('ЭСФ')),
              _SheetAction(Icons.undo_rounded, 'Возврат', onTap: _openSale),
            ]),
            const SizedBox(height: 16),
            SizedBox(width: double.infinity, child: OutlinedButton.icon(
              onPressed: _openSale,
              icon: const Icon(Icons.open_in_new_rounded),
              label: const Text('Открыть продажу полностью'),
            )),
          ]),
        ),
      ),
    );
  }
}

class _SheetAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  const _SheetAction(this.icon, this.label, {this.onTap});

  @override
  Widget build(BuildContext context) => Material(
    color: Colors.white,
    borderRadius: BorderRadius.circular(14),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 18, color: AppColors.primary),
          const SizedBox(width: 7),
          Text(label, style: const TextStyle(fontWeight: FontWeight.w700)),
        ]),
      ),
    ),
  );
}
