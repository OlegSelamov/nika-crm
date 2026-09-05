import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'sale_detail_screen.dart';

Map<String, dynamic> shiftPayloadCore(dynamic raw) {
  if (raw is! Map) return <String, dynamic>{};
  final item = Map<String, dynamic>.from(raw);
  return item['data'] is Map
      ? Map<String, dynamic>.from(item['data'] as Map)
      : item;
}

dynamic _shiftPath(Map<String, dynamic> source, List<String> path) {
  dynamic value = source;
  for (final key in path) {
    if (value is! Map) return null;
    value = value[key];
  }
  return value;
}

int? shiftNumberFrom(dynamic raw) {
  final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
  final core = shiftPayloadCore(raw);
  final value = core['shiftNumber'] ??
      core['shift_number'] ??
      core['number'] ??
      item['shiftNumber'] ??
      item['shift_number'] ??
      item['number'];
  return int.tryParse('${value ?? ''}');
}

String shiftSerialFrom(dynamic raw) {
  final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
  final core = shiftPayloadCore(raw);
  final value = core['serialNumber'] ??
      core['serial_number'] ??
      core['znm'] ??
      item['serialNumber'] ??
      item['serial_number'] ??
      item['znm'];
  return '${value ?? ''}'.trim();
}

dynamic shiftOpenTimeFrom(dynamic raw) {
  final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
  final core = shiftPayloadCore(raw);
  return core['openShiftTime'] ??
      core['open_shift_time'] ??
      core['openTime'] ??
      core['open_time'] ??
      core['startTime'] ??
      item['openShiftTime'] ??
      item['open_shift_time'] ??
      item['openTime'] ??
      item['open_time'] ??
      item['startTime'];
}

dynamic shiftCloseTimeFrom(dynamic raw) {
  final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
  final core = shiftPayloadCore(raw);
  return core['closeShiftTime'] ??
      core['close_shift_time'] ??
      core['closeTime'] ??
      core['close_time'] ??
      core['endTime'] ??
      item['closeShiftTime'] ??
      item['close_shift_time'] ??
      item['closeTime'] ??
      item['close_time'] ??
      item['endTime'];
}

int? shiftTicketCountFrom(dynamic raw) {
  final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
  final core = shiftPayloadCore(raw);
  for (final source in [core, item]) {
    for (final path in const [
      ['ticketCount'],
      ['ticket_count'],
      ['ticketsCount'],
      ['checkCount'],
      ['totals', 'ticketCount'],
    ]) {
      final value = int.tryParse('${_shiftPath(source, path) ?? ''}');
      if (value != null) return value;
    }
  }
  return null;
}

double? _moneyValue(dynamic value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is Map) {
    final map = Map<String, dynamic>.from(value);
    if (map['bills'] != null || map['coins'] != null) {
      final bills = double.tryParse('${map['bills'] ?? 0}') ?? 0;
      final coins = double.tryParse('${map['coins'] ?? 0}') ?? 0;
      return bills + coins / 100;
    }
    for (final key in const ['total', 'sum', 'amount', 'revenue', 'net']) {
      final nested = _moneyValue(map[key]);
      if (nested != null) return nested;
    }
    return null;
  }
  final normalized = '$value'
      .replaceAll(RegExp(r'[^0-9,.-]'), '')
      .replaceAll(',', '.');
  return double.tryParse(normalized);
}

double? shiftRevenueFrom(dynamic raw) {
  final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
  final core = shiftPayloadCore(raw);
  for (final source in [core, item]) {
    for (final path in const [
      ['netRevenue'],
      ['net_revenue'],
      ['totalRevenue'],
      ['total_revenue'],
      ['revenue'],
      ['amount'],
      ['totals', 'netRevenue'],
      ['totals', 'revenue'],
      ['amounts', 'total'],
      ['sell', 'total'],
      ['total'],
    ]) {
      final value = _moneyValue(_shiftPath(source, path));
      if (value != null) return value;
    }
  }
  return null;
}

String shiftDateLabel(dynamic value, {String fallback = '—'}) {
  if (value == null || '$value'.trim().isEmpty) return fallback;
  DateTime? date;
  if (value is num) {
    final raw = value.toInt();
    date = DateTime.fromMillisecondsSinceEpoch(
      raw < 100000000000 ? raw * 1000 : raw,
    );
  } else {
    date = DateTime.tryParse('$value');
  }
  if (date == null) return '$value';
  return DateFormat('dd.MM.yyyy HH:mm').format(date.toLocal());
}

class ShiftDetailScreen extends StatefulWidget {
  final Map<String, dynamic> shift;
  final Map<String, dynamic> cashRegister;
  final bool isOpen;

  const ShiftDetailScreen({
    super.key,
    required this.shift,
    this.cashRegister = const {},
    this.isOpen = false,
  });

  @override
  State<ShiftDetailScreen> createState() => _ShiftDetailScreenState();
}

class _ShiftDetailScreenState extends State<ShiftDetailScreen> {
  static const pageSize = 50;

  bool loading = true;
  bool loadingMore = false;
  bool hasMore = false;
  int page = 0;
  String? error;
  List<Map<String, dynamic>> tickets = [];
  Map<String, dynamic> reportResponse = {};

  int get shiftNumber => shiftNumberFrom(widget.shift) ?? 0;

  @override
  void initState() {
    super.initState();
    load();
    if (!widget.isOpen) loadReportSummary();
  }

  Future<void> loadReportSummary() async {
    if (widget.isOpen || shiftNumber <= 0) return;
    try {
      final result = await ApiService.zReport(shiftNumber);
      if (mounted) setState(() => reportResponse = result);
    } catch (_) {
      // Детальную страницу всё равно показываем по локальным операциям.
      // Кнопка Z-отчёта повторит запрос и покажет понятную ошибку.
    }
  }

  Future<void> refresh() async {
    if (widget.isOpen) {
      await load();
    } else {
      await Future.wait([load(), loadReportSummary()]);
    }
  }

  Future<void> load({bool reset = true}) async {
    if (!reset && (loadingMore || !hasMore)) return;
    if (reset) {
      if (mounted) setState(() => loading = true);
    } else {
      setState(() => loadingMore = true);
    }
    try {
      final serial = shiftSerialFrom(widget.shift);
      final requestedPage = reset ? 0 : page + 1;
      final result = await ApiService.getSalesHistory(
        shiftNumber: shiftNumber,
        serialNumber: serial.isEmpty ? null : serial,
        page: requestedPage,
        size: pageSize,
      );
      if (!mounted) return;
      setState(() {
        final loaded = result
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList();
        if (reset) {
          tickets = loaded;
        } else {
          tickets.addAll(loaded);
          _deduplicateTickets();
        }
        page = requestedPage;
        hasMore = loaded.length >= pageSize;
        loading = false;
        error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        loading = false;
        error = readableError(e);
      });
    } finally {
      if (mounted) setState(() => loadingMore = false);
    }
  }

  void _deduplicateTickets() {
    final unique = <String, Map<String, dynamic>>{};
    for (final ticket in tickets) {
      final id = '${ticket['id'] ?? ''}';
      final fallback = '${ticket['sale_number']}|${ticket['created_at']}';
      unique[id.isEmpty ? fallback : id] = ticket;
    }
    tickets = unique.values.toList();
  }

  double get localRevenue {
    var total = 0.0;
    for (final ticket in tickets) {
      final value = asDouble(ticket['total']);
      total += ticket['is_refunded'] == true ? -value : value;
    }
    return total;
  }

  Future<void> openZReport() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (_) => ZReportSheet(
        shiftNumber: shiftNumber,
        initialResponse: reportResponse,
        cashRegister: widget.cashRegister,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.isOpen ? 'Текущая смена №$shiftNumber' : 'Смена №$shiftNumber',
        ),
        actions: [
          if (!widget.isOpen)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: TextButton.icon(
                onPressed: shiftNumber > 0 ? openZReport : null,
                icon: const Icon(Icons.summarize_outlined, size: 19),
                label: const Text('Z‑отчёт'),
              ),
            ),
        ],
      ),
      body: AdaptiveContent(
        maxWidth: 760,
        child: RefreshIndicator(
          onRefresh: refresh,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(child: _summary()),
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.fromLTRB(16, 8, 16, 10),
                  child: SectionTitle(
                    'Операции смены',
                    subtitle: 'Продажи и возвраты этой смены',
                  ),
                ),
              ),
              if (loading)
                const SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (error != null)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: ScreenStateView(
                    icon: Icons.receipt_long_outlined,
                    title: 'Чеки смены не загрузились',
                    message: error!,
                    onAction: load,
                  ),
                )
              else if (tickets.isEmpty)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: ScreenStateView(
                    icon: Icons.receipt_long_outlined,
                    title: 'Чеков в смене пока нет',
                    message: widget.isOpen
                        ? 'Продажи и возвраты появятся здесь автоматически.'
                        : 'Фискальный Z‑отчёт смены доступен по кнопке сверху.',
                  ),
                )
              else
                ...[
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    sliver: SliverList.separated(
                      itemCount: tickets.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 9),
                      itemBuilder: (_, index) => _ticketCard(tickets[index]),
                    ),
                  ),
                  if (hasMore)
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                        child: OutlinedButton.icon(
                          onPressed: loadingMore ? null : () => load(reset: false),
                          icon: loadingMore
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.expand_more_rounded),
                          label: Text(
                            loadingMore ? 'Загрузка…' : 'Показать ещё чеки',
                          ),
                        ),
                      ),
                    )
                  else
                    const SliverToBoxAdapter(child: SizedBox(height: 16)),
                ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _summary() {
    final rawReport = reportResponse['report'];
    final summarySource = rawReport is Map ? rawReport : widget.shift;
    final openTime = shiftDateLabel(shiftOpenTimeFrom(summarySource));
    final closeTime = widget.isOpen
        ? 'по настоящее время'
        : shiftDateLabel(shiftCloseTimeFrom(summarySource));
    final remoteRevenue = shiftRevenueFrom(summarySource);
    final ticketCount = shiftTicketCountFrom(summarySource) ?? tickets.length;
    final revenue = remoteRevenue ?? localRevenue;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [AppColors.navy, AppColors.navySoft],
          ),
          borderRadius: BorderRadius.circular(24),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            StatusPill(
              widget.isOpen ? 'Смена открыта' : 'Смена закрыта',
              color: const Color(0xFF73E2B8),
            ),
            const SizedBox(height: 16),
            Text(
              widget.isOpen ? 'Выручка текущей смены' : 'Выручка за смену',
              style: TextStyle(color: Colors.white70, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 5),
            Text(
              money(revenue),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 34,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 14),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _summaryFact(Icons.schedule_rounded, '$openTime — $closeTime'),
                const SizedBox(height: 7),
                _summaryFact(Icons.receipt_long_rounded, 'Чеков: $ticketCount'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _summaryFact(IconData icon, String text) => Row(
        children: [
          Icon(icon, size: 17, color: Colors.white70),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        ],
      );

  Widget _ticketCard(Map<String, dynamic> ticket) {
    final refunded = ticket['is_refunded'] == true ||
        '${ticket['status']}' == 'Возврат';
    final color = refunded ? AppColors.danger : AppColors.success;
    final id = int.tryParse('${ticket['id'] ?? ''}');

    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: id == null
            ? null
            : () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => SaleDetailScreen(saleId: id)),
                ),
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: color.withOpacity(.11),
                borderRadius: BorderRadius.circular(13),
              ),
              child: Icon(
                refunded ? Icons.undo_rounded : Icons.receipt_long_rounded,
                color: color,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                      child: Text(
                        '${refunded ? 'Возврат' : 'Продажа'} №${ticket['sale_number'] ?? ticket['id']}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ),
                    Text(
                      '${refunded ? '−' : ''}${money(ticket['total'])}',
                      style: TextStyle(color: color, fontWeight: FontWeight.w900),
                    ),
                  ]),
                  const SizedBox(height: 5),
                  Text(
                    '${ticket['payment_type'] ?? '—'} • ${ticket['client_name'] ?? 'Частное лицо'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: AppColors.muted, fontSize: 12),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '${ticket['created_at_display'] ?? '—'}',
                    style: const TextStyle(color: AppColors.muted, fontSize: 12),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
          ]),
        ),
      ),
    );
  }
}

class ZReportSheet extends StatefulWidget {
  final int shiftNumber;
  final Map<String, dynamic> initialResponse;
  final Map<String, dynamic> cashRegister;

  const ZReportSheet({
    super.key,
    required this.shiftNumber,
    this.initialResponse = const {},
    this.cashRegister = const {},
  });

  @override
  State<ZReportSheet> createState() => _ZReportSheetState();
}

class _ZReportSheetState extends State<ZReportSheet> {
  bool loading = true;
  String? error;
  Map<String, dynamic> report = {};
  Map<String, dynamic> cashRegister = {};

  @override
  void initState() {
    super.initState();
    cashRegister = Map<String, dynamic>.from(widget.cashRegister);
    final responseRegister = widget.initialResponse['cash_register'];
    if (responseRegister is Map) {
      cashRegister.addAll(Map<String, dynamic>.from(responseRegister));
    }
    final raw = widget.initialResponse['report'];
    if (raw is Map) {
      report = Map<String, dynamic>.from(raw);
      loading = false;
    } else {
      load();
    }
  }

  Future<void> load() async {
    try {
      final response = await ApiService.zReport(widget.shiftNumber);
      if (!mounted) return;
      final raw = response['report'];
      final responseRegister = response['cash_register'];
      setState(() {
        report = raw is Map ? Map<String, dynamic>.from(raw) : response;
        if (responseRegister is Map) {
          cashRegister.addAll(Map<String, dynamic>.from(responseRegister));
        }
        error = null;
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
    return FractionallySizedBox(
      heightFactor: .9,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 4, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(Icons.summarize_outlined, color: AppColors.primary),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Z‑отчёт №${widget.shiftNumber}',
                      style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900),
                    ),
                    const Text(
                      'Фискальный отчёт закрытой смены',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ]),
            const SizedBox(height: 14),
            Expanded(
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : error != null
                      ? ScreenStateView(
                          icon: Icons.description_outlined,
                          title: 'Z‑отчёт не загрузился',
                          message: error!,
                          onAction: load,
                        )
                      : _content(),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Готово'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content() {
    final businessName = _textFrom(
      cashRegister['business_name'] ??
          _find(report, const {'businessname', 'organizationname'}),
    );
    final businessId = _textFrom(
      cashRegister['business_id'] ??
          _find(report, const {'businessid', 'bin', 'iin'}),
    );
    final address = _textFrom(
      cashRegister['address'] ?? _find(report, const {'address'}),
    );
    final serial = _textFrom(
      cashRegister['serial_number'] ??
          _find(report, const {'serialnumber', 'znm'}),
    );
    final registration = _textFrom(
      cashRegister['registration_number'] ??
          _find(report, const {'registrationnumber', 'fnskkmid', 'rnm'}),
    );
    final cashier = _textFrom(
      _find(report, const {'cashiername', 'operatorname', 'username'}),
    );

    final sales = _findMap(
      report,
      const {'sell', 'sales', 'sale', 'salesoperations'},
    );
    final refunds = _findMap(
      report,
      const {
        'returnsale',
        'salesreturn',
        'sellreturn',
        'refunds',
        'returns',
      },
    );
    final payments = _findMap(
      report,
      const {'payments', 'payment', 'paymenttotals'},
    );

    final salesCount = _countFrom(
      sales,
      const {'count', 'ticketcount', 'ticketscount', 'quantity'},
      fallbackKeys: const {'sellcount', 'salescount', 'salecount'},
    );
    final salesAmount = _amountFrom(
      sales,
      const {'amount', 'sum', 'total', 'revenue'},
      fallbackKeys: const {'sellamount', 'sellsum', 'salesamount'},
    );
    final refundCount = _countFrom(
      refunds,
      const {'count', 'ticketcount', 'ticketscount', 'quantity'},
      fallbackKeys: const {'refundcount', 'returncount', 'returnsalecount'},
    );
    final refundAmount = _amountFrom(
      refunds,
      const {'amount', 'sum', 'total'},
      fallbackKeys: const {'refundamount', 'returnamount', 'returnsaleamount'},
    );
    final ticketCount = shiftTicketCountFrom(report) ??
        _countFrom(
          report,
          const {'ticketcount', 'ticketscount', 'checkcount'},
        );
    final cash = _amountFrom(
      payments,
      const {'cash', 'cashamount'},
      fallbackKeys: const {'cashamount', 'cashtotal'},
    );
    final card = _amountFrom(
      payments,
      const {'card', 'cashless', 'noncash', 'cardamount'},
      fallbackKeys: const {'cardamount', 'cashlessamount', 'noncashamount'},
    );
    final kaspi = _amountFrom(
      payments,
      const {'kaspi', 'mobile', 'qr', 'kaspiamount'},
      fallbackKeys: const {'kaspiamount', 'mobileamount', 'qramount'},
    );
    final startBalance = _amountFrom(
      report,
      const {'startbalance', 'cashstartbalance', 'openingbalance'},
    );
    final deposits = _amountFrom(
      report,
      const {'deposit', 'deposits', 'cashdeposit', 'cashin'},
    );
    final withdrawals = _amountFrom(
      report,
      const {'withdraw', 'withdrawals', 'cashwithdrawal', 'cashout'},
    );
    final endBalance = _amountFrom(
      report,
      const {'endbalance', 'cashendbalance', 'closingbalance'},
    );
    final taxes = _amountFrom(
      report,
      const {'tax', 'taxes', 'taxamount', 'vat'},
    );
    final revenue = shiftRevenueFrom(report) ??
        (salesAmount == null
            ? null
            : salesAmount - (refundAmount ?? 0));
    final opened = shiftDateLabel(
      _find(
            report,
            const {'openshifttime', 'opentime', 'open_time', 'starttime'},
          ) ??
          shiftOpenTimeFrom(report),
      fallback: '—',
    );
    final closed = shiftDateLabel(
      _find(
            report,
            const {'closeshifttime', 'closetime', 'close_time', 'endtime'},
          ) ??
          shiftCloseTimeFrom(report),
      fallback: '—',
    );
    final reportShiftNumber = int.tryParse(
          '${_find(report, const {'shiftnumber', 'shift_number'}) ?? ''}',
        ) ??
        shiftNumberFrom(report) ??
        widget.shiftNumber;
    final fiscalRows = _fallbackRows(report);

    return SingleChildScrollView(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 390),
          child: Container(
            padding: const EdgeInsets.fromLTRB(20, 22, 20, 24),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: const Color(0xFFE2E2E2)),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x14000000),
                  blurRadius: 18,
                  offset: Offset(0, 8),
                ),
              ],
            ),
            child: DefaultTextStyle(
              style: const TextStyle(
                color: Colors.black87,
                fontSize: 13,
                height: 1.35,
                fontFamily: 'monospace',
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    businessName.isEmpty ? 'reKassa' : businessName,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  if (businessId.isNotEmpty)
                    Text(
                      'БИН/ИИН: $businessId',
                      textAlign: TextAlign.center,
                    ),
                  if (address.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Text(address, textAlign: TextAlign.center),
                    ),
                  _receiptDivider(strong: true),
                  const Text(
                    'ФИСКАЛЬНЫЙ Z‑ОТЧЁТ',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    'СМЕНА №$reportShiftNumber',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  _receiptDivider(),
                  _receiptRow('Открытие', opened),
                  _receiptRow('Закрытие', closed),
                  if (cashier.isNotEmpty) _receiptRow('Кассир', cashier),
                  if (ticketCount != null)
                    _receiptRow('Всего чеков', '$ticketCount'),
                  _receiptDivider(),
                  if (salesCount != null || salesAmount != null)
                    _operationRow(
                      'ПРОДАЖИ',
                      salesCount,
                      salesAmount,
                    ),
                  if (refundCount != null || refundAmount != null)
                    _operationRow(
                      'ВОЗВРАТЫ',
                      refundCount,
                      refundAmount,
                      negative: true,
                    ),
                  if (revenue != null) ...[
                    _receiptDivider(strong: true),
                    _receiptRow(
                      'ИТОГО ЗА СМЕНУ',
                      money(revenue),
                      bold: true,
                      large: true,
                    ),
                  ],
                  if ([cash, card, kaspi].any((value) => value != null)) ...[
                    _receiptDivider(),
                    const Text(
                      'ОПЛАТА',
                      style: TextStyle(fontWeight: FontWeight.w900),
                    ),
                    const SizedBox(height: 5),
                    if (cash != null) _receiptRow('Наличные', money(cash)),
                    if (card != null) _receiptRow('Банковская карта', money(card)),
                    if (kaspi != null) _receiptRow('Kaspi / QR', money(kaspi)),
                  ],
                  if ([startBalance, deposits, withdrawals, endBalance]
                      .any((value) => value != null)) ...[
                    _receiptDivider(),
                    const Text(
                      'НАЛИЧНЫЕ В КАССЕ',
                      style: TextStyle(fontWeight: FontWeight.w900),
                    ),
                    const SizedBox(height: 5),
                    if (startBalance != null)
                      _receiptRow('На начало', money(startBalance)),
                    if (deposits != null)
                      _receiptRow('Внесение', money(deposits)),
                    if (withdrawals != null)
                      _receiptRow('Изъятие', money(withdrawals)),
                    if (endBalance != null)
                      _receiptRow('На конец', money(endBalance), bold: true),
                  ],
                  if (taxes != null) ...[
                    _receiptDivider(),
                    _receiptRow('Налоги', money(taxes)),
                  ],
                  if (fiscalRows.isNotEmpty) ...[
                    _receiptDivider(),
                    const Text(
                      'ДАННЫЕ ОТЧЁТА',
                      style: TextStyle(fontWeight: FontWeight.w900),
                    ),
                    const SizedBox(height: 5),
                    ...fiscalRows.map(
                      (row) => _receiptRow(row.key, row.value),
                    ),
                  ],
                  _receiptDivider(strong: true),
                  if (registration.isNotEmpty)
                    _receiptRow('РНМ', registration),
                  if (serial.isNotEmpty) _receiptRow('ЗНМ', serial),
                  const SizedBox(height: 12),
                  const Text(
                    'СМЕНА ЗАКРЫТА',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontWeight: FontWeight.w900),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _receiptDivider({bool strong = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Divider(
          height: 1,
          thickness: strong ? 2 : 1,
          color: strong ? Colors.black87 : Colors.black38,
        ),
      );

  Widget _receiptRow(
    String label,
    String value, {
    bool bold = false,
    bool large = false,
  }) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontWeight: bold ? FontWeight.w900 : FontWeight.w500,
                  fontSize: large ? 15 : 13,
                ),
              ),
            ),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                value,
                textAlign: TextAlign.right,
                style: TextStyle(
                  fontWeight: bold ? FontWeight.w900 : FontWeight.w700,
                  fontSize: large ? 15 : 13,
                ),
              ),
            ),
          ],
        ),
      );

  Widget _operationRow(
    String label,
    int? count,
    double? amount, {
    bool negative = false,
  }) {
    final countText = count == null ? '' : '$count чек.';
    final amountText = amount == null
        ? ''
        : '${negative && amount > 0 ? '−' : ''}${money(amount.abs())}';
    return _receiptRow(
      countText.isEmpty ? label : '$label ($countText)',
      amountText,
      bold: true,
    );
  }

  static String _normalizeKey(dynamic value) => '$value'
      .replaceAll(RegExp(r'[^A-Za-zА-Яа-я0-9]'), '')
      .toLowerCase();

  static dynamic _find(dynamic source, Set<String> keys) {
    final normalized = keys.map(_normalizeKey).toSet();
    dynamic walk(dynamic value) {
      if (value is Map) {
        for (final entry in value.entries) {
          if (normalized.contains(_normalizeKey(entry.key))) {
            return entry.value;
          }
        }
        for (final nested in value.values) {
          final found = walk(nested);
          if (found != null) return found;
        }
      } else if (value is List) {
        for (final nested in value) {
          final found = walk(nested);
          if (found != null) return found;
        }
      }
      return null;
    }

    return walk(source);
  }

  static Map<String, dynamic> _findMap(dynamic source, Set<String> keys) {
    final value = _find(source, keys);
    return value is Map
        ? Map<String, dynamic>.from(value)
        : <String, dynamic>{};
  }

  static String _textFrom(dynamic value) {
    if (value == null || value is Map || value is List) return '';
    return '$value'.trim();
  }

  int? _countFrom(
    dynamic source,
    Set<String> keys, {
    Set<String> fallbackKeys = const {},
  }) {
    dynamic value = _find(source, keys);
    value ??= fallbackKeys.isEmpty ? null : _find(report, fallbackKeys);
    return int.tryParse('${value ?? ''}');
  }

  double? _amountFrom(
    dynamic source,
    Set<String> keys, {
    Set<String> fallbackKeys = const {},
  }) {
    dynamic value = _find(source, keys);
    value ??= fallbackKeys.isEmpty ? null : _find(report, fallbackKeys);
    return _moneyValue(value);
  }

  static List<MapEntry<String, String>> _fallbackRows(
    Map<String, dynamic> source,
  ) {
    const labels = <String, String>{
      'documentnumber': 'Номер документа',
      'reportnumber': 'Номер отчёта',
      'fiscaldocumentnumber': 'Фискальный документ',
      'ofdstatus': 'Статус ОФД',
      'offlinecount': 'Офлайн-документы',
      'correctioncount': 'Коррекции',
      'buycount': 'Покупки',
      'buyamount': 'Сумма покупок',
      'returnbuycount': 'Возвраты покупок',
      'returnbuyamount': 'Сумма возвратов покупок',
      'discountamount': 'Скидки',
      'markupamount': 'Наценки',
      'taxamount': 'Сумма налогов',
    };
    final result = <MapEntry<String, String>>[];
    final used = <String>{};

    void walk(dynamic value) {
      if (result.length >= 20) return;
      if (value is Map) {
        for (final entry in value.entries) {
          final key = _normalizeKey(entry.key);
          final label = labels[key];
          final raw = entry.value;
          if (label != null && raw is! Map && raw is! List && raw != null) {
            if (used.add(label)) result.add(MapEntry(label, '$raw'));
          } else {
            walk(raw);
          }
        }
      } else if (value is List) {
        for (final item in value) {
          walk(item);
        }
      }
    }

    walk(source);
    return result;
  }
}
