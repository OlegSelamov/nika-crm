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
    for (final key in const ['value', 'total', 'sum', 'amount', 'revenue', 'net']) {
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

// reKassa supplies both ISO timestamps and structured local clock objects,
// e.g. {"date":{"day":7,"month":10,"year":2026},
//       "time":{"hour":10,"minute":50,"second":21}}.
String shiftDateLabel(dynamic value, {String fallback = '—'}) {
  if (value == null || '$value'.trim().isEmpty) return fallback;

  String two(int number) => number.toString().padLeft(2, '0');
  int? part(dynamic raw) => int.tryParse('${raw ?? ''}');

  if (value is Map) {
    final datePart = value['date'];
    final timePart = value['time'];
    if (datePart is Map && timePart is Map) {
      final year = part(datePart['year']);
      final month = part(datePart['month']);
      final day = part(datePart['day']);
      final hour = part(timePart['hour']);
      final minute = part(timePart['minute']);
      if (year != null && month != null && day != null &&
          hour != null && minute != null) {
        return '${two(day)}.${two(month)}.$year ${two(hour)}:${two(minute)}';
      }
    }
    for (final key in const ['value', 'dateTime', 'datetime', 'timestamp']) {
      if (value[key] != null) {
        return shiftDateLabel(value[key], fallback: fallback);
      }
    }
    return fallback; // Never display a raw Dart Map to the cashier.
  }

  if (value is num) {
    final raw = value.toInt();
    final milliseconds = raw.abs() < 100000000000 ? raw * 1000 : raw;
    final kazakhstanTime = DateTime.fromMillisecondsSinceEpoch(
      milliseconds,
      isUtc: true,
    ).add(const Duration(hours: 5));
    return DateFormat('dd.MM.yyyy HH:mm').format(kazakhstanTime);
  }

  final raw = '$value'.trim();
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return raw;
  // Timestamps with an explicit offset represent instants. Display them in
  // Kazakhstan (UTC+5), regardless of the phone's timezone. Naive strings
  // already contain the local wall-clock time and must not be shifted.
  final hasOffset = RegExp(r'(Z|[+-]\d{2}:?\d{2})$', caseSensitive: false)
      .hasMatch(raw);
  final date = hasOffset
      ? parsed.toUtc().add(const Duration(hours: 5))
      : parsed;
  return DateFormat('dd.MM.yyyy HH:mm').format(date);
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

  // Mirror the fiscal Z-report rendered on the Nika Business website.
  // reKassa keeps its detailed figures inside report.data, not the flattened
  // "sales" / "payments" objects previously assumed by the mobile screen.
  Widget _content() {
    final core = shiftPayloadCore(report);
    dynamic field(String key) => core[key] ?? report[key];

    final businessName = _meta('business_name', fallback: 'Nika Business');
    final businessId = _meta('business_id');
    final address = _meta('address');
    final registration = _meta('registration_number');
    final serial = _meta('serial_number');
    final model = _meta('model', fallback: 'reKassa 3.0');
    final fdoTitle = _meta('fdo_title', fallback: 'ОФД ТОО «COMRUN»');
    final fdoUrl = _meta('fdo_url', fallback: 'https://ofd.rekassa.kz');

    final rawOperator = field('operator');
    final operator = rawOperator is Map ? rawOperator : const {};
    final cashier = _firstText([operator['name'], operator['code']]);
    final opened = shiftDateLabel(
      report['openTime'] ?? core['openShiftTime'] ?? core['openTime'],
    );
    final closed = shiftDateLabel(
      report['closeTime'] ?? core['closeShiftTime'] ?? core['closeTime'],
    );
    final number = shiftNumberFrom(report) ?? widget.shiftNumber;
    final documentNumber =
        _firstText([report['shiftDocumentNumber'], core['shiftDocumentNumber']]);

    final startSums = _mapList(field('startShiftNonNullableSums'));
    final endSums = _mapList(field('nonNullableSums'));
    final ticketOperations = _mapList(field('ticketOperations'))
        .where((item) => _integer(item['ticketsCount']) > 0)
        .toList()
      ..sort((a, b) => _operationOrderIndex(a['operation'])
          .compareTo(_operationOrderIndex(b['operation'])));
    final placements = _mapList(field('moneyPlacements'))
        .where((item) => _integer(item['operationsCount']) > 0)
        .toList();

    final ticketsCount = ticketOperations.fold<int>(
          0, (total, item) => total + _integer(item['ticketsCount']),
        ) +
        placements.fold<int>(
          0, (total, item) => total + _integer(item['operationsCount']),
        );

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
                    businessName,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
                  ),
                  _centerText('БИН (ИИН): $businessId'),
                  _centerText(address),
                  const SizedBox(height: 10),
                  _receiptRow('РНМ:', registration),
                  _receiptRow('ЗНМ:', serial),
                  _receiptRow('ККМ:', model),
                  const SizedBox(height: 12),
                  const Text(
                    'Z‑отчёт',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 21, fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 8),
                  _receiptRow('Смена:', '№$number'),
                  _receiptRow('Кассир:', cashier),
                  _receiptRow('Начало:', _fiscalDate(opened)),
                  _receiptRow('Время:', _fiscalTime(opened)),
                  _receiptRow('Конец:', _fiscalDate(closed)),
                  _receiptRow('Время:', _fiscalTime(closed)),
                  if (documentNumber.isNotEmpty)
                    _receiptRow('Документ:', documentNumber),
                  _receiptDivider(),
                  _sectionTitle('Необнуляемая сумма на начало смены'),
                  ..._cumulativeRows(startSums),
                  _receiptDivider(),
                  if (ticketOperations.isEmpty && placements.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Text('Фискальных операций в смене нет'),
                    ),
                  for (final item in ticketOperations) ...[
                    _sectionTitle(_operationLabel(item['operation'])),
                    _receiptRow('Количество чеков', '${_integer(item['ticketsCount'])}'),
                    for (final payment in _mapList(item['payments']))
                      _receiptRow(
                        _paymentLabel(payment['payment']),
                        _fiscalMoney(payment['sum']),
                      ),
                    _receiptRow('Сумма', _fiscalMoney(item['ticketsSum'])),
                    const SizedBox(height: 12),
                  ],
                  for (final item in placements) ...[
                    _sectionTitle(_placementLabel(item['operation'])),
                    _receiptRow('Количество чеков', '${_integer(item['operationsCount'])}'),
                    _receiptRow('Сумма', _fiscalMoney(item['operationsSum'])),
                    const SizedBox(height: 12),
                  ],
                  _receiptRow('Количество чеков за смену', '$ticketsCount', bold: true),
                  _receiptDivider(),
                  _sectionTitle('Необнуляемая сумма на конец смены'),
                  ..._cumulativeRows(endSums),
                  const SizedBox(height: 16),
                  _sectionTitle('Наличных в кассе'),
                  _receiptRow('Сумма', _fiscalMoney(field('cashSum'))),
                  _receiptDivider(),
                  _centerText(fdoTitle),
                  _centerText(fdoUrl),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _centerText(String value) => Text(value,
      textAlign: TextAlign.center, softWrap: true);

  Widget _sectionTitle(String title) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Text(title, style: const TextStyle(fontWeight: FontWeight.w900)),
      );

  String _meta(String key, {String fallback = '—'}) {
    final value = cashRegister[key];
    if (value == null || '$value'.trim().isEmpty) return fallback;
    return '$value';
  }

  static String _firstText(List<dynamic> values) {
    for (final value in values) {
      if (value != null && '$value'.trim().isNotEmpty) return '$value';
    }
    return '—';
  }

  static List<Map<String, dynamic>> _mapList(dynamic raw) {
    if (raw is! List) return [];
    return raw.whereType<Map>()
        .map((value) => Map<String, dynamic>.from(value)).toList();
  }

  static int _integer(dynamic value) =>
      int.tryParse('${value ?? ''}') ?? 0;

  static const operationOrder = [
    'OPERATION_SELL',
    'OPERATION_SELL_RETURN',
    'OPERATION_BUY',
    'OPERATION_BUY_RETURN',
  ];

  static String _operationCode(dynamic raw) {
    const codes = [
      'OPERATION_BUY',
      'OPERATION_BUY_RETURN',
      'OPERATION_SELL',
      'OPERATION_SELL_RETURN',
    ];
    if (raw is String && raw.startsWith('OPERATION_')) return raw;
    final index = int.tryParse('${raw ?? ''}');
    return index != null && index >= 0 && index < codes.length
        ? codes[index] : '${raw ?? ''}';
  }

  static String _operationLabel(dynamic value) {
    switch (_operationCode(value)) {
      case 'OPERATION_SELL': return 'Продажа';
      case 'OPERATION_SELL_RETURN': return 'Возврат';
      case 'OPERATION_BUY': return 'Покупка';
      case 'OPERATION_BUY_RETURN': return 'Возврат покупки';
      default: return '${value ?? 'Операция'}';
    }
  }

  static int _operationOrderIndex(dynamic raw) {
    final index = operationOrder.indexOf(_operationCode(raw));
    return index < 0 ? operationOrder.length : index;
  }

  static String _paymentLabel(dynamic raw) {
    const labels = [
      'Наличные',
      'Карта',
      'Кредит',
      'Тара',
      'Мобильная оплата',
    ];
    const codes = [
      'PAYMENT_CASH',
      'PAYMENT_CARD',
      'PAYMENT_CREDIT',
      'PAYMENT_TARE',
      'PAYMENT_MOBILE',
    ];
    final index = raw is String && raw.startsWith('PAYMENT_')
        ? codes.indexOf(raw)
        : (int.tryParse('${raw ?? ''}') ?? -1);
    return index >= 0 && index < labels.length
        ? labels[index] : '${raw ?? 'Оплата'}';
  }

  static String _placementLabel(dynamic raw) {
    return raw == 1 || '$raw' == '1' ||
            '$raw' == 'MONEY_PLACEMENT_WITHDRAWAL'
        ? 'Изъятие' : 'Внесение';
  }

  static String _fiscalDate(String label) =>
      label.contains(' ') ? label.split(' ').first : label;
  static String _fiscalTime(String label) =>
      label.contains(' ') ? label.split(' ').last : '—';

  static String _fiscalMoney(dynamic value) {
    final amount = _moneyValue(value) ?? 0;
    return '${NumberFormat('#,##0.00', 'ru_RU').format(amount)} ₸';
  }

  static dynamic _sumByOperation(List<Map<String, dynamic>> sums, String code) {
    for (final row in sums) {
      if (_operationCode(row['operation']) == code) return row['sum'];
    }
    return 0;
  }

  List<Widget> _cumulativeRows(List<Map<String, dynamic>> sums) {
    return [
      for (final code in operationOrder)
        _receiptRow(_operationLabel(code), _fiscalMoney(_sumByOperation(sums, code))),
    ];
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

}
