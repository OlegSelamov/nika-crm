import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  bool loading = true;
  String? error;
  List<dynamic> items = [];
  int unread = 0;

  @override
  void initState() {
    super.initState();
    loadData();
  }

  Future<void> loadData() async {
    try {
      final result = await ApiService.notifications();
      if (!mounted) return;
      setState(() {
        items = List<dynamic>.from(result['items'] ?? const []);
        unread = int.tryParse('${result['unread_count'] ?? 0}') ?? 0;
        loading = false;
        error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = readableError(e);
        loading = false;
      });
    }
  }

  Future<void> _read(Map<String, dynamic> item) async {
    if (item['is_read'] == true) return;
    try {
      await ApiService.readNotification(int.tryParse('${item['id']}') ?? 0);
      await loadData();
    } catch (_) {}
  }

  Future<void> _readAll() async {
    try {
      await ApiService.readAllNotifications();
      await loadData();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Уведомления'),
        actions: [
          if (unread > 0)
            TextButton(onPressed: _readAll, child: const Text('Прочитать все')),
          const SizedBox(width: 6),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? ScreenStateView(
                  icon: Icons.notifications_off_outlined,
                  title: 'Не удалось загрузить уведомления',
                  message: error!,
                  onAction: loadData,
                )
              : items.isEmpty
                  ? const ScreenStateView(
                      icon: Icons.notifications_none_rounded,
                      title: 'Уведомлений нет',
                      message: 'Здесь появятся важные события компании.',
                    )
                  : RefreshIndicator(
                      onRefresh: loadData,
                      child: ListView.separated(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                        itemCount: items.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 9),
                        itemBuilder: (_, index) {
                          final item = Map<String, dynamic>.from(items[index] as Map);
                          final read = item['is_read'] == true;
                          return Card(
                            color: read ? Colors.white : AppColors.primarySoft,
                            child: InkWell(
                              onTap: () => _read(item),
                              borderRadius: BorderRadius.circular(20),
                              child: Padding(
                                padding: const EdgeInsets.all(15),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                      width: 42,
                                      height: 42,
                                      decoration: BoxDecoration(
                                        color: (read ? AppColors.muted : AppColors.primary).withOpacity(.12),
                                        borderRadius: BorderRadius.circular(13),
                                      ),
                                      child: Icon(
                                        _icon('${item['type']}'),
                                        color: read ? AppColors.muted : AppColors.primary,
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text('${item['title'] ?? 'Уведомление'}', style: const TextStyle(fontWeight: FontWeight.w800)),
                                          const SizedBox(height: 5),
                                          Text('${item['message'] ?? ''}', style: const TextStyle(color: AppColors.muted, height: 1.35)),
                                          const SizedBox(height: 7),
                                          Text('${item['created_at_label'] ?? ''}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                                        ],
                                      ),
                                    ),
                                    if (!read)
                                      Container(
                                        width: 8,
                                        height: 8,
                                        decoration: const BoxDecoration(color: AppColors.primary, shape: BoxShape.circle),
                                      ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }

  IconData _icon(String type) {
    if (type.contains('task')) return Icons.task_alt_rounded;
    if (type.contains('stock')) return Icons.inventory_2_outlined;
    if (type.contains('sale')) return Icons.receipt_long_outlined;
    return Icons.notifications_none_rounded;
  }
}
