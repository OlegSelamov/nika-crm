import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class CtoScreen extends StatefulWidget {
  const CtoScreen({super.key});

  @override
  State<CtoScreen> createState() => _CtoScreenState();
}

class _CtoScreenState extends State<CtoScreen> {
  bool loading = true;
  String? error;
  List<dynamic> items = [];

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.mobileCto();
      if (mounted) setState(() => items = List<dynamic>.from(data['items'] ?? const []));
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  IconData icon(String code) {
    switch (code) {
      case 'register': return Icons.app_registration_rounded;
      case 'reregister': return Icons.sync_rounded;
      case 'deregister': return Icons.remove_circle_outline_rounded;
      case 'ofd': return Icons.cloud_done_outlined;
      case 'repair': return Icons.build_outlined;
      default: return Icons.directions_car_outlined;
    }
  }

  String description(String code) {
    switch (code) {
      case 'register': return 'Подготовка и постановка кассы на учёт';
      case 'reregister': return 'Изменение владельца, адреса или параметров';
      case 'deregister': return 'Корректное закрытие и снятие кассы с учёта';
      case 'ofd': return 'Подключение оператора фискальных данных';
      case 'repair': return 'Диагностика и восстановление оборудования';
      default: return 'Помощь специалиста на вашей торговой точке';
    }
  }

  void openRequest(Map<String, dynamic> item) {
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('${item['title']}'),
        content: const Text('Заявка будет передана техническому специалисту. Для подтверждения он свяжется с вами по телефону компании.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
          FilledButton(onPressed: () { Navigator.pop(context); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Заявка подготовлена. Свяжитесь с поддержкой для подтверждения'))); }, child: const Text('Понятно')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return ScreenStateView(icon: Icons.developer_board_outlined, title: 'CTO недоступен', message: error!, onAction: load);
    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 30),
        children: [
          const SectionTitle('Технический сервис', subtitle: 'Кассы, ОФД и выезд специалиста'),
          const SizedBox(height: 14),
          ...items.map((raw) {
            final item = Map<String, dynamic>.from(raw as Map);
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Card(
                child: InkWell(
                  onTap: () => openRequest(item),
                  borderRadius: BorderRadius.circular(20),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(children: [
                      Container(width: 48, height: 48, decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(15)), child: Icon(icon('${item['code']}'), color: AppColors.primary)),
                      const SizedBox(width: 13),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${item['title']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 5),
                        Text(description('${item['code']}'), style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                      ])),
                      const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
                    ]),
                  ),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}
