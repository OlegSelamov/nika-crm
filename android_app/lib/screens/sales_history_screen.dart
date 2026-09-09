import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'shift_detail_screen.dart';
import 'sale_detail_screen.dart';
import 'sale_document_preview_screen.dart';
import 'check_screen.dart';
import 'refund_check_screen.dart';

class SalesHistoryScreen extends StatefulWidget {
  const SalesHistoryScreen({super.key});

  @override
  State<SalesHistoryScreen> createState() => _SalesHistoryScreenState();
}

class _SalesHistoryScreenState extends State<SalesHistoryScreen> {
  static const pageSize = 20;
  static const documentPageSize = 20;

  bool loading = true;
  int historyTab = 0;
  String documentKind = 'all';
  final TextEditingController documentSearchController = TextEditingController();
  final List<Map<String, dynamic>> documentSales = [];
  DateTimeRange? shiftPeriod;
  DateTimeRange? documentPeriod;
  bool loadingMore = false;
  bool hasMore = false;
  int page = 0;
  bool loadingMoreDocuments = false;
  bool documentsHasMore = false;
  int documentPage = 0;
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

  @override
  void dispose() {
    documentSearchController.dispose();
    super.dispose();
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
        ApiService.shiftHistory(
          page: 0,
          size: pageSize,
          dateFrom: _apiDate(shiftPeriod?.start),
          dateTo: _apiDate(shiftPeriod?.end),
        ).catchError((e) => <String, dynamic>{'_error': readableError(e)}),
        isOpen && number != null
            ? ApiService.getSalesHistory(
                shiftNumber: number,
                serialNumber: serial.isEmpty ? null : serial,
                page: 0,
                size: pageSize,
              ).catchError((_) => <dynamic>[])
            : Future<dynamic>.value(<dynamic>[]),
        ApiService.getSalesHistory(
          allHistory: true,
          page: 0,
          size: documentPageSize,
          queryText: documentSearchController.text,
          kind: documentKind,
          dateFrom: _apiDate(documentPeriod?.start),
          dateTo: _apiDate(documentPeriod?.end),
        ).catchError((_) => <dynamic>[]),
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
        documentPage = 0;
        hasMore = historyResponse['has_more'] == true ||
            (historyResponse['_error'] == null && loaded.length >= pageSize);
        documentsHasMore = docs.length >= documentPageSize;
        historyWarning = (historyResponse['_error'] ?? historyResponse['warning'])?.toString();
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

  Future<void> _reloadDocuments() async {
    if (mounted) setState(() => loadingMoreDocuments = true);
    try {
      final rows = await ApiService.getSalesHistory(
        allHistory: true,
        page: 0,
        size: documentPageSize,
        queryText: documentSearchController.text,
        kind: documentKind,
        dateFrom: _apiDate(documentPeriod?.start),
        dateTo: _apiDate(documentPeriod?.end),
      );
      final docs = rows.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
      if (!mounted) return;
      setState(() {
        documentSales
          ..clear()
          ..addAll(docs);
        documentPage = 0;
        documentsHasMore = docs.length >= documentPageSize;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => loadingMoreDocuments = false);
    }
  }

  Future<void> _reloadShifts() async {
    if (mounted) setState(() => loadingMore = true);
    try {
      final response = await ApiService.shiftHistory(
        page: 0,
        size: pageSize,
        dateFrom: _apiDate(shiftPeriod?.start),
        dateTo: _apiDate(shiftPeriod?.end),
      );
      final loaded = _extractHistory(response['history']);
      if (!mounted) return;
      setState(() {
        closedShifts
          ..clear()
          ..addAll(loaded);
        _sortAndDeduplicate();
        page = 0;
        hasMore = response['has_more'] == true || loaded.length >= pageSize;
        historyWarning = (response['warning'])?.toString();
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

  Future<void> loadMore() async {
    if (loadingMore || !hasMore) return;
    setState(() => loadingMore = true);
    try {
      final nextPage = page + 1;
      final response = await ApiService.shiftHistory(
        page: nextPage,
        size: pageSize,
        dateFrom: _apiDate(shiftPeriod?.start),
        dateTo: _apiDate(shiftPeriod?.end),
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

  Future<void> _loadMoreDocuments() async {
    if (loadingMoreDocuments || !documentsHasMore) return;
    setState(() => loadingMoreDocuments = true);
    try {
      final nextPage = documentPage + 1;
      final rows = await ApiService.getSalesHistory(
        allHistory: true,
        page: nextPage,
        size: documentPageSize,
        queryText: documentSearchController.text,
        kind: documentKind,
        dateFrom: _apiDate(documentPeriod?.start),
        dateTo: _apiDate(documentPeriod?.end),
      );
      final loaded = rows.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
      if (!mounted) return;
      setState(() {
        documentSales.addAll(loaded);
        documentPage = nextPage;
        documentsHasMore = loaded.length >= documentPageSize;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
      }
    } finally {
      if (mounted) setState(() => loadingMoreDocuments = false);
    }
  }

  String? _apiDate(DateTime? date) {
    if (date == null) return null;
    String two(int value) => value.toString().padLeft(2, '0');
    return '${date.year}-${two(date.month)}-${two(date.day)}';
  }

  String _shortDate(DateTime date) {
    String two(int value) => value.toString().padLeft(2, '0');
    return '${two(date.day)}.${two(date.month)}.${date.year}';
  }

  String _periodLabel(DateTimeRange? period) {
    if (period == null) return 'За всё время';
    if (_apiDate(period.start) == _apiDate(period.end)) return _shortDate(period.start);
    return '${_shortDate(period.start)} — ${_shortDate(period.end)}';
  }

  Future<DateTimeRange?> _pickRussianPeriod(DateTimeRange? current) async {
    final now = DateTime.now();
    return showDateRangePicker(
      context: context,
      locale: const Locale('ru', 'RU'),
      firstDate: DateTime(2020),
      lastDate: DateTime(now.year + 1, 12, 31),
      initialDateRange: current,
      helpText: 'Выберите период',
      cancelText: 'Отмена',
      confirmText: 'Применить',
      saveText: 'Применить',
      fieldStartHintText: 'Начало',
      fieldEndHintText: 'Конец',
      fieldStartLabelText: 'Дата начала',
      fieldEndLabelText: 'Дата окончания',
      errorFormatText: 'Введите дату в формате ДД.ММ.ГГГГ',
      errorInvalidText: 'Некорректная дата',
      errorInvalidRangeText: 'Дата окончания раньше даты начала',
    );
  }

  Future<void> _changeShiftPeriod() async {
    final selected = await _pickRussianPeriod(shiftPeriod);
    if (selected == null) return;
    setState(() => shiftPeriod = selected);
    await _reloadShifts();
  }

  Future<void> _changeDocumentPeriod() async {
    final selected = await _pickRussianPeriod(documentPeriod);
    if (selected == null) return;
    setState(() => documentPeriod = selected);
    await _reloadDocuments();
  }

  Future<void> _resetShiftPeriod() async {
    if (shiftPeriod == null) return;
    setState(() => shiftPeriod = null);
    await _reloadShifts();
  }

  Future<void> _resetDocumentFilters() async {
    documentSearchController.clear();
    setState(() {
      documentPeriod = null;
      documentKind = 'all';
    });
    await _reloadDocuments();
  }

  Future<void> _setDocumentKind(String kind) async {
    if (documentKind == kind) return;
    setState(() => documentKind = kind);
    await _reloadDocuments();
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
          SliverToBoxAdapter(child: _shiftFilterCard()),
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
    return [
      SliverToBoxAdapter(child: _documentFilterCard()),
      const SliverToBoxAdapter(child: SizedBox(height: 10)),
      if (documentSales.isEmpty)
        const SliverFillRemaining(
          hasScrollBody: false,
          child: ScreenStateView(
            icon: Icons.description_outlined,
            title: 'Ничего не найдено',
            message: 'Измените период, вид документа или поисковый запрос.',
          ),
        )
      else ...[
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
          sliver: SliverList.separated(
            itemCount: documentSales.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (_, i) => _documentSaleCard(documentSales[i]),
          ),
        ),
        if (documentsHasMore)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
              child: OutlinedButton.icon(
                onPressed: loadingMoreDocuments ? null : _loadMoreDocuments,
                icon: loadingMoreDocuments
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.expand_more_rounded),
                label: Text(loadingMoreDocuments ? 'Загрузка…' : 'Показать ещё'),
              ),
            ),
          ),
      ],
    ];
  }

  Widget _shiftFilterCard() => Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 2),
        child: _filterShell(
          title: 'Период смен',
          subtitle: 'Показываем по 20 смен, остальные — по кнопке «Показать ещё»',
          children: [
            Row(children: [
              Expanded(
                child: _periodButton(
                  label: _periodLabel(shiftPeriod),
                  onTap: _changeShiftPeriod,
                ),
              ),
              if (shiftPeriod != null) ...[
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: _resetShiftPeriod,
                  tooltip: 'Сбросить период',
                  icon: const Icon(Icons.close_rounded),
                ),
              ],
            ]),
          ],
        ),
      );

  Widget _documentFilterCard() => Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 2),
        child: _filterShell(
          title: 'Найти документы',
          subtitle: 'По номеру, клиенту или сумме · по 20 записей',
          children: [
            TextField(
              controller: documentSearchController,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _reloadDocuments(),
              decoration: InputDecoration(
                hintText: 'Номер, клиент или сумма',
                prefixIcon: const Icon(Icons.search_rounded),
                suffixIcon: documentSearchController.text.isEmpty
                    ? null
                    : IconButton(
                        onPressed: () {
                          documentSearchController.clear();
                          setState(() {});
                          _reloadDocuments();
                        },
                        icon: const Icon(Icons.close_rounded),
                      ),
                filled: true,
                fillColor: const Color(0xFFF7F7FC),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: _periodButton(label: _periodLabel(documentPeriod), onTap: _changeDocumentPeriod)),
              const SizedBox(width: 8),
              IconButton.filledTonal(
                onPressed: _resetDocumentFilters,
                tooltip: 'Сбросить фильтры',
                icon: const Icon(Icons.restart_alt_rounded),
              ),
            ]),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: _kindButton('all', 'Все', Icons.folder_copy_outlined)),
              const SizedBox(width: 8),
              Expanded(child: _kindButton('receipts', 'Чеки', Icons.receipt_long_outlined)),
              const SizedBox(width: 8),
              Expanded(child: _kindButton('invoices', 'Счета', Icons.request_quote_outlined)),
            ]),
          ],
        ),
      );

  Widget _filterShell({
    required String title,
    required String subtitle,
    required List<Widget> children,
  }) => Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(.96),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: AppColors.border),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(.035), blurRadius: 18, offset: const Offset(0, 7))],
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(12)),
              child: const Icon(Icons.tune_rounded, color: AppColors.primary, size: 20),
            ),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900)),
              const SizedBox(height: 2),
              Text(subtitle, style: const TextStyle(color: AppColors.muted, fontSize: 11)),
            ])),
          ]),
          const SizedBox(height: 13),
          ...children,
        ]),
      );

  Widget _periodButton({required String label, required VoidCallback onTap}) => OutlinedButton.icon(
        onPressed: onTap,
        icon: const Icon(Icons.calendar_month_rounded, size: 19),
        label: Align(alignment: Alignment.centerLeft, child: Text(label, overflow: TextOverflow.ellipsis)),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(48),
          alignment: Alignment.centerLeft,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
        ),
      );

  Widget _kindButton(String kind, String label, IconData icon) {
    final selected = documentKind == kind;
    return InkWell(
      onTap: () => _setDocumentKind(kind),
      borderRadius: BorderRadius.circular(14),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 11),
        decoration: BoxDecoration(
          color: selected ? AppColors.primary : const Color(0xFFF7F7FC),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: selected ? AppColors.primary : AppColors.border),
        ),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, size: 17, color: selected ? Colors.white : AppColors.muted),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: selected ? Colors.white : AppColors.navy),
            ),
          ),
        ]),
      ),
    );
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
    final serverTypes = sale['document_types'];
    if (serverTypes is List && serverTypes.isNotEmpty) {
      return serverTypes
          .map((raw) => _documentActionForType('$raw'))
          .whereType<_SaleDocumentAction>()
          .toList();
    }

    // Совместимость со старым API.
    final items = _saleItems(sale);
    final explicitHasServices = sale['has_services'] == true;
    final explicitHasProducts = sale['has_products'] == true;
    final hasServices = explicitHasServices || items.any(_isServiceItem);
    final hasProducts = explicitHasProducts || items.any((e) => !_isServiceItem(e));
    final invoice = '${sale['sale_type'] ?? sale['payment_method'] ?? ''}'.toLowerCase() == 'invoice' ||
        sale['invoice_number'] != null;
    final refunded = sale['sale_refunded'] == true || _isRefundSale(sale);
    final rawStatus = '${sale['status'] ?? sale['payment_status'] ?? ''}'.toLowerCase();
    final paid = rawStatus.contains('paid') || rawStatus.contains('оплачен') || rawStatus.contains('success');

    final types = <String>[];
    if (refunded) {
      types.add(invoice ? 'invoice' : 'refund-receipt');
    } else if (invoice) {
      types.add('invoice');
      if (paid) {
        if (hasProducts) types.add('nakladnaya');
        if (hasServices) types.add('act');
        if (hasProducts || hasServices) types.addAll(['schet-factura', 'esf']);
      }
    } else {
      types.add('receipt');
      if (hasProducts) types.add('nakladnaya');
      if (hasServices) types.add('act');
      if (hasProducts || hasServices) types.addAll(['schet-factura', 'esf']);
    }
    return types.map(_documentActionForType).whereType<_SaleDocumentAction>().toList();
  }

  _SaleDocumentAction? _documentActionForType(String type) {
    switch (type) {
      case 'receipt':
        return const _SaleDocumentAction('receipt', 'Чек', Icons.receipt_long_rounded, needsPaid: false);
      case 'refund-receipt':
        return const _SaleDocumentAction('refund-receipt', 'Чек возврата', Icons.assignment_return_rounded, needsPaid: false);
      case 'invoice':
        return const _SaleDocumentAction('invoice', 'Счёт на оплату', Icons.request_quote_rounded, needsPaid: false);
      case 'nakladnaya':
        return const _SaleDocumentAction('nakladnaya', 'Накладная', Icons.local_shipping_outlined);
      case 'act':
        return const _SaleDocumentAction('act', 'АВР', Icons.task_alt_rounded);
      case 'schet-factura':
        return const _SaleDocumentAction('schet-factura', 'Счёт-фактура', Icons.description_outlined);
      case 'esf':
        return const _SaleDocumentAction('esf', 'ЭСФ', Icons.cloud_done_outlined);
    }
    return null;
  }

  String _saleDateTime(Map<String, dynamic> sale) {
    final raw = sale['event_at'] ?? sale['created_at'] ?? sale['sale_date'] ?? sale['date'] ??
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
    const months = [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    ];
    String two(int v) => v.toString().padLeft(2, '0');
    return '${dt.day} ${months[dt.month - 1]} ${dt.year}, ${two(dt.hour)}:${two(dt.minute)}';
  }

  Future<Map<String, dynamic>> _detailFor(Map<String, dynamic> sale) async {
    final id = int.tryParse('${sale['id'] ?? sale['sale_id'] ?? ''}');
    if (id == null) return sale;
    try {
      final detail = await ApiService.getSale(id);
      return <String, dynamic>{...sale, ...detail};
    } catch (_) {
      return sale;
    }
  }

  Future<void> _confirmInvoicePayment(Map<String, dynamic> sale) async {
    final id = int.tryParse('${sale['id'] ?? sale['sale_id'] ?? ''}');
    if (id == null) return;
    final number = sale['invoice_number'] ?? sale['sale_number'] ?? id;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        icon: const Icon(Icons.payments_rounded, color: AppColors.success, size: 36),
        title: const Text('Подтвердить оплату?'),
        content: Text('Счёт №$number будет отмечен оплаченным. После этого появятся закрывающие документы.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Оплата получена')),
        ],
      ),
    );
    if (ok != true) return;

    try {
      final result = await ApiService.markInvoicePaid(id);
      if (!mounted) return;
      if (result['success'] != true) {
        throw ApiException('${result['error'] ?? 'Не удалось подтвердить оплату'}');
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Оплата подтверждена')),
      );
      await _reloadDocuments();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    }
  }

  Future<void> _openSaleDocuments(Map<String, dynamic> sale) async {
    final detail = await _detailFor(sale);
    if (!mounted) return;
    final docs = _documentsFor(detail);
    final changed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _SaleDocumentsSheet(
        sale: detail,
        documents: docs,
        formedAt: _saleDateTime(detail),
      ),
    );
    if (changed == true && mounted) await _reloadDocuments();
  }

  Widget _documentSaleCard(Map<String, dynamic> sale) {
    final id = sale['sale_number'] ?? sale['id'] ?? sale['sale_id'] ?? '—';
    final total = asDouble(sale['total'] ?? sale['total_amount'] ?? sale['amount']);
    final client = '${sale['client_name'] ?? sale['client_company_name'] ?? sale['client'] ?? 'Частное лицо'}';
    final raw = '${sale['status'] ?? sale['payment_status'] ?? ''}'.toLowerCase();
    final invoice = '${sale['sale_type'] ?? sale['payment_method'] ?? ''}'.toLowerCase() == 'invoice' ||
        sale['invoice_number'] != null || raw.contains('счёт выставлен') || raw.contains('pending');
    final paid = raw.contains('paid') || raw.contains('оплачен') || raw.contains('success');
    final refunded = sale['sale_refunded'] == true || _isRefundSale(sale);
    final statusText = refunded ? 'Возврат' : paid ? 'Оплачено' : (invoice ? 'Ожидает оплаты' : 'Проведено');
    final statusColor = refunded ? AppColors.danger : paid ? AppColors.success : (invoice ? AppColors.warning : AppColors.primary);
    final docs = _documentsFor(sale);
    final docLabel = docs.length == 1 ? '1 документ сформирован' : '${docs.length} документов сформировано';

    return Card(
      elevation: 0,
      color: Colors.white.withOpacity(.96),
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: const BorderSide(color: AppColors.border),
      ),
      child: InkWell(
        onTap: () => _openSaleDocuments(sale),
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
                child: Icon(
                  refunded ? Icons.assignment_return_rounded : invoice ? Icons.request_quote_rounded : Icons.receipt_long_rounded,
                  color: refunded ? AppColors.danger : AppColors.primary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(
                    invoice ? 'Счёт №${sale['invoice_number'] ?? id}' : 'Продажа №$id',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    client,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: AppColors.muted, fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ]),
              ),
              const SizedBox(width: 8),
              StatusPill(statusText, color: statusColor),
            ]),
            const SizedBox(height: 14),
            Text(money(total), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900)),
            const SizedBox(height: 12),
            _documentInfoRow(Icons.schedule_rounded, 'Сформировано', _saleDateTime(sale)),
            const SizedBox(height: 7),
            _documentInfoRow(Icons.folder_copy_outlined, 'Документы', docLabel),
            const SizedBox(height: 11),
            Row(children: [
              Text(
                'Нажмите, чтобы открыть документы',
                style: TextStyle(
                  color: AppColors.primary.withOpacity(.92),
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const Spacer(),
              const Icon(Icons.chevron_right_rounded, color: AppColors.primary),
            ]),
            if (invoice && !paid && !refunded) ...[
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: () => _confirmInvoicePayment(sale),
                  icon: const Icon(Icons.payments_rounded, size: 18),
                  label: const Text('Подтвердить оплату'),
                ),
              ),
            ],
          ]),
        ),
      ),
    );
  }

  Widget _documentInfoRow(IconData icon, String label, String value) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: AppColors.muted),
          const SizedBox(width: 7),
          Text('$label: ', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800),
            ),
          ),
        ],
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
                    _shiftPeriodLabel(opened, closed),
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

  String _shiftPeriodLabel(dynamic opened, dynamic closed) {
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


class _SaleDocumentsSheet extends StatefulWidget {
  final Map<String, dynamic> sale;
  final List<_SaleDocumentAction> documents;
  final String formedAt;

  const _SaleDocumentsSheet({
    required this.sale,
    required this.documents,
    required this.formedAt,
  });

  @override
  State<_SaleDocumentsSheet> createState() => _SaleDocumentsSheetState();
}

class _SaleDocumentsSheetState extends State<_SaleDocumentsSheet> {
  bool refunding = false;

  Map<String, dynamic> get sale => widget.sale;
  int get saleId => int.tryParse('${sale['id'] ?? sale['sale_id'] ?? ''}') ?? 0;
  bool get isInvoice => '${sale['sale_type'] ?? ''}'.toLowerCase() == 'invoice';
  bool get isRefunded =>
      sale['sale_refunded'] == true ||
      sale['is_refunded'] == true ||
      '${sale['status'] ?? ''}'.toLowerCase().contains('возврат');
  bool get isPaid {
    final raw = '${sale['status'] ?? ''}'.toLowerCase();
    return raw.contains('оплачен') || raw.contains('paid') || raw.contains('success');
  }

  String get statusText =>
      isRefunded ? 'Возврат' : isPaid ? 'Оплачено' : isInvoice ? 'Ожидает оплаты' : 'Проведено';

  Color get statusColor =>
      isRefunded ? AppColors.danger : isPaid ? AppColors.success : isInvoice ? AppColors.warning : AppColors.primary;

  Future<void> _openDocument(_SaleDocumentAction doc) async {
    if (saleId <= 0) return;

    if (doc.needsPaid && !isPaid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала подтвердите оплату счёта')),
      );
      return;
    }

    if (doc.type == 'esf') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ЭСФ готовится отдельно и будет подписываться через ЭЦП.')),
      );
      return;
    }

    if (doc.type == 'receipt') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => CheckScreen(saleId: saleId)),
      );
      return;
    }

    if (doc.type == 'refund-receipt') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => RefundCheckScreen(saleId: saleId)),
      );
      return;
    }

    final number = sale['sale_number'] ?? sale['invoice_number'] ?? saleId;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => SaleDocumentPreviewScreen(
          saleId: saleId,
          documentType: doc.type,
          title: '${doc.label} №$number',
          fileName: '${doc.type.replaceAll('-', '_')}_$number',
        ),
      ),
    );
  }

  Future<void> _refund() async {
    if (saleId <= 0 || refunding || isRefunded || isInvoice) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        icon: const Icon(Icons.undo_rounded, color: AppColors.danger, size: 36),
        title: const Text('Оформить возврат?'),
        content: const Text(
          'Товар вернётся на склад, сумма продажи и прибыль уменьшатся, а reKassa сформирует чек возврата.',
          textAlign: TextAlign.center,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            child: const Text('Подтвердить возврат'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    setState(() => refunding = true);
    try {
      final result = await ApiService.refundSale(saleId);
      if (!mounted) return;
      if (result['success'] != true) {
        throw ApiException('${result['error'] ?? 'Не удалось выполнить возврат'}');
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Возврат оформлен')),
      );
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => RefundCheckScreen(saleId: saleId)),
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e)), backgroundColor: AppColors.danger),
        );
      }
    } finally {
      if (mounted) setState(() => refunding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final total = asDouble(sale['total_amount'] ?? sale['total'] ?? sale['amount']);
    final number = sale['sale_number'] ?? sale['invoice_number'] ?? saleId;
    final client = '${sale['client_name'] ?? sale['client_company_name'] ?? sale['client'] ?? 'Частное лицо'}';

    return SafeArea(
      child: Container(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * .88),
        decoration: const BoxDecoration(
          color: Color(0xFFF8F8FD),
          borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
        ),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const SizedBox(height: 10),
          Center(
            child: Container(
              width: 44,
              height: 5,
              decoration: BoxDecoration(color: AppColors.border, borderRadius: BorderRadius.circular(8)),
            ),
          ),
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 26),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(
                    child: Text(
                      isInvoice ? 'Счёт №$number' : 'Продажа №$number',
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
                    ),
                  ),
                  const SizedBox(width: 10),
                  StatusPill(statusText, color: statusColor),
                ]),
                const SizedBox(height: 6),
                Text(client, style: const TextStyle(color: AppColors.muted, fontWeight: FontWeight.w600)),
                const SizedBox(height: 14),
                Text(money(total), style: const TextStyle(fontSize: 31, fontWeight: FontWeight.w900)),
                const SizedBox(height: 14),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Column(children: [
                    _sheetFact('Статус', statusText),
                    const SizedBox(height: 8),
                    _sheetFact('Сформировано', widget.formedAt),
                    const SizedBox(height: 8),
                    _sheetFact('Документов', '${widget.documents.length}'),
                  ]),
                ),
                const SizedBox(height: 20),
                const Text('Сформированные документы', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
                const SizedBox(height: 10),
                if (widget.documents.isEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16)),
                    child: const Text('Документы пока не сформированы', style: TextStyle(color: AppColors.muted)),
                  )
                else
                  ...widget.documents.map((doc) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Material(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      child: InkWell(
                        onTap: () => _openDocument(doc),
                        borderRadius: BorderRadius.circular(16),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: AppColors.border),
                          ),
                          child: Row(children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: AppColors.primarySoft,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Icon(doc.icon, color: AppColors.primary, size: 20),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(doc.label, style: const TextStyle(fontWeight: FontWeight.w800)),
                            ),
                            const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
                          ]),
                        ),
                      ),
                    ),
                  )),
                if (!isRefunded && !isInvoice) ...[
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: refunding ? null : _refund,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.danger,
                        foregroundColor: Colors.white,
                        minimumSize: const Size.fromHeight(48),
                      ),
                      icon: refunding
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.undo_rounded),
                      label: Text(refunding ? 'Оформляем возврат…' : 'Оформить возврат'),
                    ),
                  ),
                ],
              ]),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _sheetFact(String label, String value) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 105,
            child: Text(label, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
          ),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      );
}

