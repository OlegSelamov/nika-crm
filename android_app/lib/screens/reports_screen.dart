import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  static const String reportBuild = '2026.08.17.2';

  static const types = <String, String>{
    'sales': 'Продажи',
    'products': 'Товары',
    'services': 'Услуги',
    'profit': 'Прибыль',
    'stock': 'Склад',
    'clients': 'Клиенты',
  };

  String type = 'sales';
  late DateTimeRange period;
  bool loading = true;
  bool downloading = false;
  String? error;
  String title = 'Отчёт';
  List<dynamic> columns = [];
  List<dynamic> rows = [];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    period = DateTimeRange(start: DateTime(now.year, now.month, 1), end: now);
    loadReport();
  }

  String _date(DateTime value) =>
      '${value.year}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';

  Future<void> loadReport() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = await ApiService.reportData(
        type: type,
        dateFrom: _date(period.start),
        dateTo: _date(period.end),
      );
      if (!mounted) return;
      setState(() {
        title = '${result['title'] ?? types[type]}';
        columns = List<dynamic>.from(result['columns'] ?? const []);
        rows = List<dynamic>.from(result['rows'] ?? const []);
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

  Future<void> _pickPeriod() async {
    final result = await showDateRangePicker(
      context: context,
      initialDateRange: period,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      helpText: 'Период отчёта',
      saveText: 'Применить',
    );
    if (result == null) return;
    period = result;
    await loadReport();
  }

  Future<void> _downloadReport() async {
    if (downloading) return;
    setState(() => downloading = true);
    try {
      final from = _date(period.start);
      final to = _date(period.end);
      final bytes = await ApiService.downloadReportExcel(
        type: type,
        dateFrom: from,
        dateTo: to,
      );
      final savedPath = await FileSaver.instance.saveAs(
        name: '${type}_${from}_$to',
        bytes: bytes,
        fileExtension: 'xlsx',
        mimeType: MimeType.microsoftExcel,
      );
      if (mounted && savedPath != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Отчёт «${types[type]}» сохранён')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => downloading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          height: 52,
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            scrollDirection: Axis.horizontal,
            itemCount: types.length,
            separatorBuilder: (_, __) => const SizedBox(width: 8),
            itemBuilder: (_, index) {
              final entry = types.entries.elementAt(index);
              return ChoiceChip(
                label: Text(entry.value),
                selected: type == entry.key,
                onSelected: (_) {
                  type = entry.key;
                  loadReport();
                },
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _pickPeriod,
                  icon: const Icon(Icons.calendar_month_rounded),
                  label: Text(
                    '${period.start.day.toString().padLeft(2, '0')}.${period.start.month.toString().padLeft(2, '0')} — '
                    '${period.end.day.toString().padLeft(2, '0')}.${period.end.month.toString().padLeft(2, '0')}.${period.end.year}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton.icon(
                onPressed: loading || downloading ? null : _downloadReport,
                icon: downloading
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                    : const Icon(Icons.download_rounded),
                label: const Text('Excel'),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Версия отчётов $reportBuild',
              style: const TextStyle(fontSize: 11, color: AppColors.muted),
            ),
          ),
        ),
        if (type == 'products' || type == 'services')
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(14)),
              child: Row(
                children: [
                  Icon(type == 'services' ? Icons.design_services_outlined : Icons.inventory_2_outlined, color: AppColors.primary),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      type == 'services'
                          ? 'В отчёт включены только проданные услуги.'
                          : 'В отчёт включены только проданные товары.',
                      style: const TextStyle(fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          ),
        Expanded(
          child: loading
              ? const Center(child: CircularProgressIndicator())
              : error != null
                  ? ScreenStateView(
                      icon: Icons.summarize_outlined,
                      title: 'Отчёт не загрузился',
                      message: error!,
                      onAction: loadReport,
                    )
                  : _content(),
        ),
      ],
    );
  }

  Widget _content() {
    if (rows.isEmpty) {
      return const ScreenStateView(
        icon: Icons.insert_chart_outlined_rounded,
        title: 'За период данных нет',
        message: 'Измените период или выберите другой вид отчёта.',
      );
    }

    return RefreshIndicator(
      onRefresh: loadReport,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
        itemCount: rows.length + 1,
        separatorBuilder: (_, __) => const SizedBox(height: 9),
        itemBuilder: (_, index) {
          if (index == 0) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: SectionTitle(title, subtitle: '${rows.length} строк'),
            );
          }
          final row = Map<String, dynamic>.from(rows[index - 1] as Map);
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(15),
              child: Column(
                children: columns.map((rawColumn) {
                  final column = Map<String, dynamic>.from(rawColumn as Map);
                  final key = '${column['key'] ?? ''}';
                  final label = '${column['label'] ?? key}';
                  final value = row[key];
                  final isMoney = const {
                    'amount',
                    'revenue',
                    'profit',
                    'gross_profit',
                    'net_profit',
                    'cash',
                    'card',
                    'kaspi',
                    'balance',
                    'purchase_price',
                    'retail_price',
                    'stock_cost',
                    'total',
                  }.contains(key);
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 5),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: Text(label, style: const TextStyle(color: AppColors.muted))),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            isMoney
                                ? money(value)
                                : key == 'margin'
                                    ? '${value ?? 0}%'
                                    : '${value ?? '—'}',
                            textAlign: TextAlign.right,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          );
        },
      ),
    );
  }
}
