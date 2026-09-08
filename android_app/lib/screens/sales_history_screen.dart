import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'shift_detail_screen.dart';
import 'sale_detail_screen.dart';
import 'sale_document_preview_screen.dart';

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

  List<Map<String, dynamic>> _saleItems(Map<String, dynamic> sale) {
    for (final key in const ['items', 'sale_items', 'positions', 'cart']) {
      final raw = sale[key];
      if (raw is List) {
        return raw.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
      }
    }
    return const [];
  }

  bool _isServiceItem(Map<String, dynamic> item) {
    final type = '${item['item_type'] ?? item['type'] ?? item['product_type'] ?? ''}'.toLowerCase();
    return type == 'service' || type.contains('услуг');
  }

  bool _isRefundSale(Map<String, dynamic> sale) {
    final raw = '${sale['status'] ?? sale['operation_type'] ?? sale['type'] ?? ''}'.toLowerCase();
    return sale['is_refunded'] == true || sale['refunded'] == true ||
        raw.contains('refund') || raw.contains('возврат');
  }

  List<_SaleDocumentAction> _documentsFor(Map<String, dynamic> sale) {
    final items = _saleItems(sale);
    final explicitHasServices = sale['has_services'] == true;
    final explicitHasProducts = sale['has_products'] == true;
    final hasServices = explicitHasServices || items.any(_isServiceItem);
    final hasProducts = explicitHasProducts || items.any((e) => !_isServiceItem(e));
    final knownComposition = explicitHasServices || explicitHasProducts || items.isNotEmpty;
    final invoice = '${sale['sale_type'] ?? sale['payment_method'] ?? ''}'.toLowerCase() == 'invoice' ||
        sale['invoice_number'] != null;
    final refunded = _isRefundSale(sale);

    final docs = <_SaleDocumentAction>[];
    if (refunded) {
      docs.add(const _SaleDocumentAction('refund-receipt', 'Чек возврата', Icons.receipt_long_rounded));
    } else if (!invoice) {
      docs.add(const _SaleDocumentAction('receipt', 'Чек', Icons.receipt_long_rounded));
    }
    if (invoice) {
      docs.add(const _SaleDocumentAction('invoice', 'Счёт', Icons.request_quote_rounded, needsPaid: false));
    }

    // Та же матрица документов, что и на вебе:
    // услуга -> АВР; товар -> накладная; смешанная -> оба.
    if (!knownComposition || hasProducts) {
      docs.add(const _SaleDocumentAction('nakladnaya', 'Накладная', Icons.local_shipping_outlined));
    }
    if (!knownComposition || hasServices) {
      docs.add(const _SaleDocumentAction('act', 'АВР', Icons.task_alt_rounded));
    }
    docs.add(const _SaleDocumentAction('schet-factura', 'Счёт-фактура', Icons.description_outlined));
    docs.add(const _SaleDocumentAction('esf', 'ЭСФ', Icons.cloud_done_outlined));
    return docs;
  }

  String _saleDateTime(Map<String, dynamic> sale) {
    final raw = sale['created_at'] ?? sale['sale_date'] ?? sale['date'] ??
        sale['createdAt'] ?? sale['timestamp'];
    if (raw == null) return 'Дата формирования не указана';
    if (raw is num) {
      final ms = raw.toInt() < 100000000000 ? raw.toInt() * 1000 : raw.toInt();
      final dt = DateTime.fromMillisecondsSinceEpoch(ms).toLocal();
      return _formatDocumentDate(dt);
    }
    final dt = DateTime.tryParse('$raw');
    return dt == null ? '$raw' : _formatDocumentDate(dt.toLocal());
  }

  String _formatDocumentDate(DateTime dt) {
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(dt.day)}.${two(dt.month)}.${dt.year} • ${two(dt.hour)}:${two(dt.minute)}';
  }

  Future<Map<String, dynamic>> _detailFor(Map<String, dynamic> sale) async {
    final id = int.tryParse('${sale['id'] ?? sale['sale_id'] ?? ''}');
    if (id == null) return sale;
    try {
      return await ApiService.getSale(id);
    } catch (_) {
      return sale;
    }
  }

  Future<void> _openCardDocument(
    Map<String, dynamic> sale,
    _SaleDocumentAction doc,
  ) async {
    final detail = await _detailFor(sale);
    if (!mounted) return;
    final id = int.tryParse('${detail['id'] ?? detail['sale_id'] ?? sale['id'] ?? sale['sale_id'] ?? ''}');
    if (id == null) return;
    final raw = '${detail['status'] ?? sale['status'] ?? ''}'.toLowerCase();
    final paid = raw.contains('paid') || raw.contains('оплачен') || raw.contains('success');
    if (doc.needsPaid && !paid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала подтвердите оплату счёта')),
      );
      return;
    }
    if (doc.type == 'esf') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ЭСФ готовим отдельно: мобильная подпись будет подключена после доступа.')),
      );
      return;
    }
    if (doc.type == 'refund-receipt' || doc.type == 'receipt') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => SaleDetailScreen(saleId: id)),
      );
      return;
    }
    final number = detail['sale_number'] ?? detail['invoice_number'] ?? id;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => SaleDocumentPreviewScreen(
          saleId: id,
          documentType: doc.type,
          title: '${doc.label} №$number',
          fileName: '${doc.type.replaceAll('-', '_')}_$number',
        ),
      ),
    );
  }

  Future<void> _openRefund(Map<String, dynamic> sale) async {
    final id = int.tryParse('${sale['id'] ?? sale['sale_id'] ?? ''}');
    if (id == null) return;
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => SaleDetailScreen(saleId: id)),
    );
    if (mounted) await loadHistory();
  }

  Widget _documentSaleCard(Map<String, dynamic> sale) {
    final id = sale['id'] ?? sale['sale_id'] ?? '—';
    final total = asDouble(sale['total'] ?? sale['total_amount'] ?? sale['amount']);
    final client = '${sale['client_name'] ?? sale['client'] ?? 'Частное лицо'}';
    final raw = '${sale['status'] ?? sale['payment_status'] ?? ''}'.toLowerCase();
    final invoice = '${sale['sale_type'] ?? sale['payment_method'] ?? ''}'.toLowerCase() == 'invoice' ||
        sale['invoice_number'] != null || raw.contains('счёт выставлен') || raw.contains('pending');
    final paid = raw.contains('paid') || raw.contains('оплачен') || raw.contains('success');
    final refunded = _isRefundSale(sale);
    final statusText = refunded ? 'Возврат' : paid ? 'Оплачено' : (invoice ? 'Ожидает оплаты' : 'Проведено');
    final statusColor = refunded ? AppColors.danger : paid ? AppColors.success : (invoice ? AppColors.warning : AppColors.primary);
    final docs = _documentsFor(sale);

    return Card(
      elevation: 0,
      color: Colors.white.withOpacity(.94),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: const BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Color(0xFFECE7FF), Color(0xFFF1F6FF)]),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(refunded ? Icons.assignment_return_rounded : Icons.description_rounded,
                  color: refunded ? AppColors.danger : AppColors.primary),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                refunded
                    ? 'Возврат №$id'
                    : invoice ? 'Счёт №${sale['invoice_number'] ?? id}' : 'Продажа №$id',
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 3),
              Text(client, maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              const SizedBox(height: 4),
              Row(children: [
                const Icon(Icons.schedule_rounded, size: 14, color: AppColors.muted),
                const SizedBox(width: 4),
                Text(_saleDateTime(sale),
                    style: const TextStyle(color: AppColors.muted, fontSize: 11, fontWeight: FontWeight.w600)),
              ]),
            ])),
            const SizedBox(width: 8),
            StatusPill(statusText, color: statusColor),
          ]),
          const SizedBox(height: 14),
          Text(money(total), style: const TextStyle(fontSize: 23, fontWeight: FontWeight.w900)),
          const SizedBox(height: 13),
          Wrap(
            spacing: 7,
            runSpacing: 7,
            children: docs.map((doc) => _documentBadge(
              doc.icon,
              doc.label,
              onTap: () => _openCardDocument(sale, doc),
            )).toList(),
          ),
          const SizedBox(height: 10),
          Row(children: [
            if (invoice && !paid)
              Expanded(
                child: FilledButton.icon(
                  onPressed: () async {
                    final detail = await _detailFor(sale);
                    if (!mounted) return;
                    final changed = await showModalBottomSheet<bool>(
                      context: context,
                      isScrollControlled: true,
                      backgroundColor: Colors.transparent,
                      builder: (_) => _SaleActionsSheet(sale: detail),
                    );
                    if (changed == true && mounted) await loadHistory();
                  },
                  icon: const Icon(Icons.payments_rounded, size: 18),
                  label: const Text('Подтвердить оплату'),
                ),
              )
            else if (!refunded)
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _openRefund(sale),
                  icon: const Icon(Icons.undo_rounded, size: 18),
                  label: const Text('Возврат'),
                ),
              ),
          ]),
        ]),
      ),
    );
  }

  Widget _documentBadge(
    IconData icon,
    String label, {
    VoidCallback? onTap,
  }) => Material(
        color: const Color(0xFFF6F4FF),
        borderRadius: BorderRadius.circular(11),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(11),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(icon, size: 15, color: AppColors.primary),
              const SizedBox(width: 5),
              Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
            ]),
          ),
        ),
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


class _SaleDocumentAction {
  final String type;
  final String label;
  final IconData icon;
  final bool needsPaid;
  const _SaleDocumentAction(this.type, this.label, this.icon, {this.needsPaid = true});
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

  Future<void> _openDocument(
    String type,
    String label, {
    bool needsPaid = true,
  }) async {
    if (needsPaid && !isPaid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала подтвердите оплату счёта')),
      );
      return;
    }
    if (saleId <= 0) return;
    final number = sale['sale_number'] ?? saleId;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => SaleDocumentPreviewScreen(
          saleId: saleId,
          documentType: type,
          title: '$label №$number',
          fileName: '${type.replaceAll('-', '_')}_$number',
        ),
      ),
    );
  }

  void _esfMessage() {
    if (!isPaid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала подтвердите оплату счёта')),
      );
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('ЭСФ требует отдельного подписания ЭЦП. Подключим его к существующему сценарию ЕСФ следующим шагом.')),
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
              _SheetAction(Icons.receipt_long_outlined, 'Счёт', onTap: () => _openDocument('invoice', 'Счёт', needsPaid: false)),
              _SheetAction(Icons.local_shipping_outlined, 'Накладная', onTap: () => _openDocument('nakladnaya', 'Накладная')),
              _SheetAction(Icons.task_alt_rounded, 'Акт', onTap: () => _openDocument('act', 'Акт')),
              _SheetAction(Icons.description_outlined, 'Счёт-фактура', onTap: () => _openDocument('schet-factura', 'Счёт-фактура')),
              _SheetAction(Icons.cloud_done_outlined, 'ЭСФ', onTap: _esfMessage),
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
