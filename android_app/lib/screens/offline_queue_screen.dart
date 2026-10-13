
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/offline_store.dart';
import '../theme/app_theme.dart';

/// Works entirely from the on-device SQLite store, including airplane mode.
/// The screen intentionally provides no destructive actions or blind retries.
class OfflineQueueScreen extends StatefulWidget {
  const OfflineQueueScreen({super.key});

  @override
  State<OfflineQueueScreen> createState() => _OfflineQueueScreenState();
}

class _OfflineQueueScreenState extends State<OfflineQueueScreen> {
  OfflineSaleQueueSnapshot? snapshot;
  String filter = 'all';
  String? loadError;
  bool loading = true;
  final money = NumberFormat('#,##0.##', 'ru_RU');
  final date = DateFormat('dd.MM.yyyy HH:mm', 'ru_RU');

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    setState(() { loading = true; loadError = null; });
    try {
      final result = await OfflineStore.instance.localSaleQueueSnapshot();
      if (!mounted) return;
      setState(() { snapshot = result; loading = false; });
    } catch (error) {
      if (!mounted) return;
      setState(() { loadError = 'Не удалось прочитать локальную очередь: $error'; loading = false; });
    }
  }

  double number(dynamic value) =>
      double.tryParse('${value ?? 0}'.replaceAll(',', '.')) ?? 0;

  String amount(dynamic value) => '${money.format(number(value))} ₸';

  String stamp(dynamic value) {
    final ms = value is int ? value : int.tryParse('${value ?? ''}');
    if (ms == null) return 'Неизвестно';
    return date.format(DateTime.fromMillisecondsSinceEpoch(ms));
  }

  String label(String state) {
    switch (state) {
      case 'pending': return 'Ожидает отправки';
      case 'syncing': return 'Отправляется';
      case 'error': return 'Ошибка отправки';
      case 'synced': return 'Отправлена';
      default: return 'Неизвестный статус';
    }
  }

  String explanation(Map<String, dynamic> operation) {
    final error = '${operation['last_error'] ?? ''}'.trim();
    final state = '${operation['state'] ?? ''}';
    if (state == 'error') {
      return error.isEmpty
          ? 'Автоматические попытки приостановлены. Нужна проверка ошибки и наличия продажи на сервере.'
          : 'Причина: $error. Автоматическая отправка этой операции приостановлена.';
    }
    if (state == 'pending') {
      return error.isEmpty
          ? 'Продажа сохранена на этом устройстве. Ожидает связи и следующей попытки отправки.'
          : 'Последняя ошибка: $error. Приложение попробует отправить снова после восстановления связи.';
    }
    if (state == 'syncing') {
      return 'Отправка была начата, но подтверждение пока не записано локально. После сбоя возможна повторная проверка.';
    }
    if (state == 'synced') {
      return 'Приложение получило подтверждение операции от сервера. Это не подтверждает отдельно фискализацию чека reKassa.';
    }
    return 'Статус операции не распознан. Запись сохранена локально.';
  }

  Color statusColor(String state) {
    switch (state) {
      case 'synced': return AppColors.success;
      case 'error': return AppColors.danger;
      case 'syncing': return AppColors.primary;
      default: return AppColors.warning;
    }
  }

  Widget counter(String title, int count, String value) {
    final active = filter == value;
    return OutlinedButton(
      onPressed: () => setState(() => filter = value),
      style: OutlinedButton.styleFrom(
        backgroundColor: active
            ? Theme.of(context).colorScheme.primaryContainer
            : null,
      ),
      child: Text('$title · $count'),
    );
  }

  Widget operationCard(Map<String, dynamic> operation) {
    final body = operation['body'] is Map
        ? Map<String, dynamic>.from(operation['body'] as Map)
        : <String, dynamic>{};
    final cart = body['cart'] is List ? List<dynamic>.from(body['cart'] as List) : <dynamic>[];
    final total = cart.fold<double>(0, (sum, raw) {
      if (raw is! Map) return sum;
      final item = Map<String, dynamic>.from(raw);
      final qty = number(item['qty'] ?? item['quantity'] ?? 1);
      return sum + (item['line_total'] == null
          ? number(item['price']) * qty
          : number(item['line_total']));
    });
    final state = '${operation['state'] ?? 'pending'}';
    final color = statusColor(state);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        leading: CircleAvatar(
          backgroundColor: color.withOpacity(.13),
          child: Icon(state == 'synced' ? Icons.check_rounded
              : state == 'error' ? Icons.error_outline
              : state == 'syncing' ? Icons.sync
              : Icons.schedule, color: color),
        ),
        title: Text(amount(total), style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(stamp(operation['created_at'])),
            Text(label(state), style: TextStyle(color: color, fontWeight: FontWeight.w700)),
          ],
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(explanation(operation)),
          const SizedBox(height: 10),
          Text('Позиций: ${cart.length} · Попыток: ${operation['attempts'] ?? 0}'),
          Text('Последнее изменение: ${stamp(operation['updated_at'])}'),
          Text('Способ оплаты: ${body['payment_method'] ?? 'не указан'}'),
          const SizedBox(height: 8),
          for (final raw in cart)
            if (raw is Map)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Text(
                  '${raw['name'] ?? 'Товар'} · ${raw['qty'] ?? raw['quantity'] ?? 1} × ${amount(raw['price'])}',
                ),
              ),
          const SizedBox(height: 8),
          SelectableText(
            'ID: ${operation['operation_id'] ?? ''}',
            style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant),
          ),
          if (state == 'error' || state == 'syncing')
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                'Перед повторной продажей проверьте историю на сервере, оплату и чек reKassa — возможно дублирование.',
                style: TextStyle(color: AppColors.warning, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final counts = snapshot?.counts ?? const <String, int>{};
    int n(String state) => counts[state] ?? 0;
    final all = counts.values.fold<int>(0, (sum, value) => sum + value);
    final operations = (snapshot?.operations ?? const <Map<String, dynamic>>[])
        .where((item) => filter == 'all' || item['state'] == filter)
        .toList();

    return RefreshIndicator(
      onRefresh: refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Очередь синхронизации', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          const Text(
            'Все данные на этом экране читаются только из памяти телефона. '
            'Экран доступен без интернета и без подключения к серверу. '
            'Отображаются все неотправленные и последние 100 отправленных продаж.',
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 6, runSpacing: 6,
            children: [
              counter('Все', all, 'all'),
              counter('Ожидают', n('pending'), 'pending'),
              counter('Отправляются', n('syncing'), 'syncing'),
              counter('Ошибки', n('error'), 'error'),
              counter('Отправлены', n('synced'), 'synced'),
            ],
          ),
          const SizedBox(height: 12),
          if (loading)
            const Center(child: Padding(
              padding: EdgeInsets.all(24),
              child: CircularProgressIndicator(),
            ))
          else if (loadError != null)
            Text(loadError!, style: const TextStyle(color: AppColors.danger))
          else if (operations.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 30),
              child: Center(child: Text('Локальных продаж с таким статусом нет')),
            )
          else
            ...operations.map(operationCard),
          if (!loading)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: OutlinedButton.icon(
                onPressed: refresh,
                icon: const Icon(Icons.refresh),
                label: const Text('Обновить из памяти телефона'),
              ),
            ),
        ],
      ),
    );
  }
}
