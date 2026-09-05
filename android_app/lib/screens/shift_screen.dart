import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'shift_detail_screen.dart';

class ShiftScreen extends StatefulWidget {
  const ShiftScreen({super.key});

  @override
  State<ShiftScreen> createState() => _ShiftScreenState();
}

class _ShiftScreenState extends State<ShiftScreen> {
  bool loading = true;
  bool actionLoading = false;
  String? error;
  Map<String, dynamic> status = {};
  List<dynamic> history = [];
  int historyPage = 0;
  bool historyHasMore = false;
  bool historyLoadingMore = false;

  @override
  void initState() {
    super.initState();
    loadData();
  }

  Future<void> loadData() async {
    try {
      final results = await Future.wait<dynamic>([
        ApiService.shiftStatus(),
        ApiService.shiftHistory(page: 0, size: 50)
            .catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      final historyResponse = Map<String, dynamic>.from(results[1]);
      final loadedHistory = _extractHistory(historyResponse['history']);
      setState(() {
        status = Map<String, dynamic>.from(results[0]);
        history = loadedHistory;
        historyPage = 0;
        historyHasMore = historyResponse['has_more'] == true ||
            loadedHistory.length >= 50;
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

  List<dynamic> _extractHistory(dynamic raw) {
    if (raw is List) return raw;
    if (raw is Map) {
      for (final key in const ['content', 'items', 'shifts', 'data']) {
        if (raw[key] is List) return List<dynamic>.from(raw[key] as List);
      }
    }
    return [];
  }

  Future<void> _xReport() async {
    await _runAction(() => ApiService.xReport(), 'X-отчёт');
  }

  Future<void> _loadMoreHistory() async {
    if (historyLoadingMore || !historyHasMore) return;
    setState(() => historyLoadingMore = true);
    try {
      final nextPage = historyPage + 1;
      final response = await ApiService.shiftHistory(page: nextPage, size: 50);
      final loaded = _extractHistory(response['history']);
      if (!mounted) return;
      setState(() {
        history.addAll(loaded);
        historyPage = nextPage;
        historyHasMore = response['has_more'] == true || loaded.length >= 50;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => historyLoadingMore = false);
    }
  }

  Future<void> _closeShift() async {
    final pin = TextEditingController();
    var withdraw = false;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) => AlertDialog(
          title: const Text('Закрыть смену'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Будет сформирован Z‑отчёт. Введите PIN ККМ reKassa.'),
              const SizedBox(height: 16),
              TextField(
                controller: pin,
                obscureText: true,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'PIN ККМ',
                  prefixIcon: Icon(Icons.password_rounded),
                ),
              ),
              const SizedBox(height: 8),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Изъять наличные'),
                value: withdraw,
                onChanged: (value) => setModalState(() => withdraw = value ?? false),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
            ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text('Закрыть')),
          ],
        ),
      ),
    );
    if (confirmed != true) return;
    setState(() => actionLoading = true);
    try {
      final result = await ApiService.closeShift(
        pin: pin.text.trim(),
        withdrawMoney: withdraw,
      );
      if (!mounted) return;
      final number = int.tryParse(
            '${result['shift_number'] ?? status['shift_number'] ?? ''}',
          ) ??
          0;
      final responseRegister = result['cash_register'];
      final register = responseRegister is Map
          ? Map<String, dynamic>.from(responseRegister)
          : cashRegister;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        showDragHandle: true,
        builder: (_) => ZReportSheet(
          shiftNumber: number,
          initialResponse: result,
          cashRegister: register,
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(readableError(e)),
            backgroundColor: AppColors.danger,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => actionLoading = false);
        await loadData();
      }
    }
  }

  Map<String, dynamic> get cashRegister {
    final raw = status['cash_register'];
    return raw is Map
        ? Map<String, dynamic>.from(raw)
        : <String, dynamic>{};
  }

  Future<void> _runAction(
    Future<Map<String, dynamic>> Function() request,
    String title,
  ) async {
    setState(() => actionLoading = true);
    try {
      final result = await request();
      if (!mounted) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (_) => _ReportSheet(title: title, response: result),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(readableError(e)), backgroundColor: AppColors.danger),
      );
    } finally {
      if (mounted) setState(() => actionLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.point_of_sale_outlined,
        title: 'reKassa не подключена',
        message: error!,
        onAction: loadData,
      );
    }

    final open = status['shift_open'] == true;
    final shiftData = status['shift'] is Map
        ? Map<String, dynamic>.from(status['shift'] as Map)
        : <String, dynamic>{};
    final register = status['cash_register'] is Map
        ? Map<String, dynamic>.from(status['cash_register'] as Map)
        : <String, dynamic>{};

    return RefreshIndicator(
      onRefresh: loadData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: open
                    ? const [AppColors.navy, AppColors.navySoft]
                    : const [Color(0xFF667085), Color(0xFF344054)],
              ),
              borderRadius: BorderRadius.circular(24),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                StatusPill(open ? 'Смена открыта' : 'Смена закрыта', color: open ? const Color(0xFF73E2B8) : Colors.white70),
                const SizedBox(height: 18),
                Text(
                  open ? 'Смена №${status['shift_number'] ?? '—'}' : 'Касса готова к работе',
                  style: const TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 6),
                Text(
                  '${register['business_name'] ?? status['name'] ?? 'reKassa'}',
                  style: const TextStyle(color: Colors.white70),
                ),
                if (shiftData['ticket_count'] != null) ...[
                  const SizedBox(height: 14),
                  Text('Чеков: ${shiftData['ticket_count']}', style: const TextStyle(color: Colors.white70)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: open && !actionLoading ? _xReport : null,
                  icon: const Icon(Icons.summarize_outlined),
                  label: const Text('X‑отчёт'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: open && !actionLoading ? _closeShift : null,
                  icon: const Icon(Icons.lock_clock_rounded),
                  label: const Text('Закрыть'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          const SectionTitle('Архив Z‑отчётов', subtitle: 'Закрытые смены reKassa'),
          const SizedBox(height: 12),
          if (history.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Text('Закрытых смен пока нет', style: TextStyle(color: AppColors.muted)),
              ),
            )
          else
            ...history.map(_historyTile),
          if (historyHasMore) ...[
            const SizedBox(height: 4),
            OutlinedButton.icon(
              onPressed: historyLoadingMore ? null : _loadMoreHistory,
              icon: historyLoadingMore
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.expand_more_rounded),
              label: Text(historyLoadingMore ? 'Загружаем…' : 'Показать ещё'),
            ),
          ],
        ],
      ),
    );
  }

  Widget _historyTile(dynamic raw) {
    final item = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
    final number = shiftNumberFrom(item);
    final amount = shiftRevenueFrom(item);
    final tickets = shiftTicketCountFrom(item);
    final closeTime = shiftDateLabel(
      shiftCloseTimeFrom(item),
      fallback: 'Закрыта',
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: Card(
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 15, vertical: 9),
          leading: const CircleAvatar(
            backgroundColor: AppColors.primarySoft,
            foregroundColor: AppColors.primary,
            child: Icon(Icons.lock_clock_rounded),
          ),
          title: Text(
            amount == null ? 'Смена №${number ?? '—'}' : money(amount),
            style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17),
          ),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              '№${number ?? '—'}${tickets == null ? '' : ' • Чеков: $tickets'}\n$closeTime',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          trailing: const Icon(Icons.chevron_right_rounded),
          onTap: number == null
              ? null
              : () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => ShiftDetailScreen(
                        shift: item,
                        cashRegister: cashRegister,
                      ),
                    ),
                  ),
        ),
      ),
    );
  }
}

class _ReportSheet extends StatelessWidget {
  final String title;
  final Map<String, dynamic> response;

  const _ReportSheet({required this.title, required this.response});

  @override
  Widget build(BuildContext context) {
    final raw = response['report'];
    final report = raw is Map ? Map<String, dynamic>.from(raw) : response;
    final values = _flatten(report);

    return SafeArea(
      child: FractionallySizedBox(
        heightFactor: .82,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
              const SizedBox(height: 4),
              const Text('Фискальные данные reKassa', style: TextStyle(color: AppColors.muted)),
              const SizedBox(height: 14),
              Expanded(
                child: Card(
                  child: ListView.separated(
                    padding: const EdgeInsets.all(15),
                    itemCount: values.length,
                    separatorBuilder: (_, __) => const Divider(height: 18),
                    itemBuilder: (_, index) {
                      final item = values[index];
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: Text(item.key, style: const TextStyle(color: AppColors.muted))),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              item.value,
                              textAlign: TextAlign.right,
                              style: const TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ),
              const SizedBox(height: 12),
              ElevatedButton(onPressed: () => Navigator.pop(context), child: const Text('Готово')),
            ],
          ),
        ),
      ),
    );
  }

  static List<MapEntry<String, String>> _flatten(Map<String, dynamic> source) {
    final result = <MapEntry<String, String>>[];
    void walk(Map<String, dynamic> map, [String prefix = '']) {
      for (final entry in map.entries) {
        final key = prefix.isEmpty ? entry.key : '$prefix · ${entry.key}';
        if (entry.value is Map && result.length < 60) {
          walk(Map<String, dynamic>.from(entry.value as Map), key);
        } else if (entry.value is! List && entry.value != null && result.length < 60) {
          result.add(MapEntry(key, '${entry.value}'));
        }
      }
    }

    walk(source);
    if (result.isEmpty) result.add(const MapEntry('Статус', 'Отчёт сформирован'));
    return result;
  }
}
