import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class StorefrontScreen extends StatefulWidget {
  const StorefrontScreen({super.key});

  @override
  State<StorefrontScreen> createState() => _StorefrontScreenState();
}

class _StorefrontScreenState extends State<StorefrontScreen> {
  bool loading = true;
  String? error;
  Map<String, dynamic> data = {};

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await ApiService.mobileStorefront();
      if (mounted) setState(() => data = result);
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> editSettings() async {
    final settings = Map<String, dynamic>.from(data['settings'] ?? const {});
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _StorefrontSettingsDialog(settings: settings),
    );
    if (result == null) return;
    try {
      await ApiService.updateMobileStorefront(result);
      await load();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Настройки витрины сохранены')));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Future<void> setStatus(String kind, Map<String, dynamic> item, String value) async {
    try {
      await ApiService.updateMobileStorefrontStatus(kind, item['id'] as int, value);
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return ScreenStateView(icon: Icons.storefront_outlined, title: 'Витрина недоступна', message: error!, onAction: load);
    final settings = Map<String, dynamic>.from(data['settings'] ?? const {});
    final summary = Map<String, dynamic>.from(data['summary'] ?? const {});
    final enabled = settings['enabled'] == true;
    return DefaultTabController(
      length: 2,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 10),
          child: Column(children: [
            Row(children: [
              Expanded(child: SectionTitle(settings['title']?.toString().trim().isNotEmpty == true ? '${settings['title']}' : 'Онлайн‑витрина', subtitle: enabled ? 'Опубликована' : 'Выключена')),
              OutlinedButton.icon(onPressed: editSettings, icon: const Icon(Icons.tune_rounded), label: const Text('Настроить')),
            ]),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(children: [
                  Container(width: 46, height: 46, decoration: BoxDecoration(color: (enabled ? AppColors.success : AppColors.muted).withOpacity(.1), borderRadius: BorderRadius.circular(14)), child: Icon(enabled ? Icons.public_rounded : Icons.public_off_outlined, color: enabled ? AppColors.success : AppColors.muted)),
                  const SizedBox(width: 12),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(settings['slug']?.toString().isNotEmpty == true ? '${ApiService.baseUrl}/s/${settings['slug']}' : 'Адрес ещё не настроен', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text('${summary['new_orders'] ?? 0} новых заказов · ${summary['new_bookings'] ?? 0} новых записей', style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                  ])),
                  StatusPill(enabled ? 'Активна' : 'Скрыта', color: enabled ? AppColors.success : AppColors.muted),
                ]),
              ),
            ),
          ]),
        ),
        const TabBar(tabs: [Tab(text: 'Заказы'), Tab(text: 'Бронирования')]),
        Expanded(child: TabBarView(children: [
          _StorefrontList(kind: 'orders', items: List<dynamic>.from(data['orders'] ?? const []), onRefresh: load, onStatus: setStatus),
          _StorefrontList(kind: 'bookings', items: List<dynamic>.from(data['bookings'] ?? const []), onRefresh: load, onStatus: setStatus),
        ])),
      ]),
    );
  }
}

class _StorefrontList extends StatelessWidget {
  final String kind;
  final List<dynamic> items;
  final Future<void> Function() onRefresh;
  final Future<void> Function(String kind, Map<String, dynamic> item, String value) onStatus;
  const _StorefrontList({required this.kind, required this.items, required this.onRefresh, required this.onStatus});

  @override
  Widget build(BuildContext context) {
    final order = kind == 'orders';
    final statuses = order
        ? const {'new': 'Новый', 'accepted': 'Принят', 'assembling': 'Собирается', 'ready': 'Готов', 'completed': 'Выполнен', 'cancelled': 'Отменён'}
        : const {'new': 'Новая', 'confirmed': 'Подтверждена', 'completed': 'Выполнена', 'cancelled': 'Отменена', 'rejected': 'Отклонена'};
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: items.isEmpty
          ? ListView(children: [const SizedBox(height: 90), Center(child: Text(order ? 'Заказов пока нет' : 'Бронирований пока нет', style: const TextStyle(color: AppColors.muted)))])
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
              itemCount: items.length,
              itemBuilder: (_, index) {
                final item = Map<String, dynamic>.from(items[index] as Map);
                final status = '${item['status'] ?? 'new'}';
                final color = status == 'completed' ? AppColors.success : status == 'cancelled' || status == 'rejected' ? AppColors.muted : status == 'new' ? AppColors.warning : AppColors.primary;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Container(width: 42, height: 42, decoration: BoxDecoration(color: color.withOpacity(.1), borderRadius: BorderRadius.circular(13)), child: Icon(order ? Icons.shopping_bag_outlined : Icons.event_available_outlined, color: color)),
                          const SizedBox(width: 12),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('${item['customer_name']}'.trim().isEmpty ? 'Клиент' : '${item['customer_name']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                            const SizedBox(height: 4),
                            Text(order ? '${item['positions_count']} поз. · ${item['created_at']}' : '${item['service_name']} · ${item['date']} ${item['time']}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                          ])),
                          if (order) Text(money(item['total_amount']), style: const TextStyle(fontWeight: FontWeight.w900)),
                        ]),
                        const SizedBox(height: 12),
                        Row(children: [
                          Expanded(child: Text('${item['phone']}', style: const TextStyle(color: AppColors.muted))),
                          DropdownButtonHideUnderline(child: DropdownButton<String>(
                            value: statuses.containsKey(status) ? status : 'new',
                            borderRadius: BorderRadius.circular(14),
                            items: statuses.entries.map((entry) => DropdownMenuItem(value: entry.key, child: Text(entry.value))).toList(),
                            onChanged: (value) { if (value != null && value != status) onStatus(kind, item, value); },
                          )),
                        ]),
                      ]),
                    ),
                  ),
                );
              },
            ),
    );
  }
}

class _StorefrontSettingsDialog extends StatefulWidget {
  final Map<String, dynamic> settings;
  const _StorefrontSettingsDialog({required this.settings});

  @override
  State<_StorefrontSettingsDialog> createState() => _StorefrontSettingsDialogState();
}

class _StorefrontSettingsDialogState extends State<_StorefrontSettingsDialog> {
  late final TextEditingController slug;
  late final TextEditingController title;
  late final TextEditingController description;
  late bool enabled;
  late bool showProducts;
  late bool showServices;
  late bool allowOrders;
  late bool allowBooking;

  @override
  void initState() {
    super.initState();
    slug = TextEditingController(text: '${widget.settings['slug'] ?? ''}');
    title = TextEditingController(text: '${widget.settings['title'] ?? ''}');
    description = TextEditingController(text: '${widget.settings['description'] ?? ''}');
    enabled = widget.settings['enabled'] == true;
    showProducts = widget.settings['show_products'] != false;
    showServices = widget.settings['show_services'] != false;
    allowOrders = widget.settings['allow_orders'] != false;
    allowBooking = widget.settings['allow_booking'] != false;
  }

  @override
  void dispose() { slug.dispose(); title.dispose(); description.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Настройки витрины'),
    content: SingleChildScrollView(child: SizedBox(width: 440, child: Column(mainAxisSize: MainAxisSize.min, children: [
      TextField(controller: slug, decoration: const InputDecoration(labelText: 'Адрес витрины *', prefixText: '/s/')),
      const SizedBox(height: 10),
      TextField(controller: title, decoration: const InputDecoration(labelText: 'Название')),
      const SizedBox(height: 10),
      TextField(controller: description, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Описание')),
      const SizedBox(height: 8),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Опубликовать витрину'), value: enabled, onChanged: (v) => setState(() => enabled = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Показывать товары'), value: showProducts, onChanged: (v) => setState(() => showProducts = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Показывать услуги'), value: showServices, onChanged: (v) => setState(() => showServices = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Принимать заказы'), value: allowOrders, onChanged: (v) => setState(() => allowOrders = v)),
      SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Разрешить бронирование'), value: allowBooking, onChanged: (v) => setState(() => allowBooking = v)),
    ]))),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
      FilledButton(
        onPressed: () {
          final cleanSlug = slug.text.trim().toLowerCase().replaceAll(RegExp(r'[^a-z0-9_-]'), '-');
          if (cleanSlug.isEmpty) return;
          Navigator.pop(context, {
            'slug': cleanSlug,
            'title': title.text.trim(),
            'description': description.text.trim(),
            'enabled': enabled,
            'show_products': showProducts,
            'show_services': showServices,
            'allow_orders': allowOrders,
            'allow_booking': allowBooking,
          });
        },
        child: const Text('Сохранить'),
      ),
    ],
  );
}
