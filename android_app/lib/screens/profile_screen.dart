import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? data;
  String? error;
  bool loading = true;

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    try {
      final result = await ApiService.mobileProfile();
      if (mounted) setState(() { data = result; error = null; loading = false; });
    } catch (e) {
      if (mounted) setState(() { error = e.toString(); loading = false; });
    }
  }

  String money(dynamic v) => '${(num.tryParse('${v ?? 0}') ?? 0).toStringAsFixed(0)} ₸';

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return Center(child: Text(error!));
    final user = Map<String,dynamic>.from(data?['user'] ?? {});
    final today = Map<String,dynamic>.from(data?['today'] ?? {});
    final month = Map<String,dynamic>.from(data?['month'] ?? {});
    final salary = Map<String,dynamic>.from(data?['salary'] ?? {});
    final sales = List<dynamic>.from(data?['recent_sales'] ?? const []);
    final tasks = List<dynamic>.from(data?['tasks'] ?? const []);
    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(child: Padding(padding: const EdgeInsets.all(18), child: Row(children: [
            CircleAvatar(radius: 30, child: Text(((user['full_name'] ?? user['username'] ?? 'N').toString())[0].toUpperCase())),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(user['full_name'] ?? user['username'] ?? '', style: Theme.of(context).textTheme.titleLarge),
              Text(user['position'] ?? user['role'] ?? ''),
              Text(user['company_name'] ?? '', style: const TextStyle(color: AppColors.muted)),
            ]))
          ]))),
          const SizedBox(height: 12),
          Text('Сегодня', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _stats(today),
          const SizedBox(height: 16),
          Text('За месяц', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _stats(month),
          const SizedBox(height: 16),
          Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Зарплата', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            Text('Оклад: ${money(salary['base'])}'),
            Text('Процент: ${salary['percent_rate'] ?? 0}%'),
            Text('Вознаграждение: ${money(salary['reward'])}'),
            const Divider(),
            Text('К выплате: ${money(salary['payable'])}', style: const TextStyle(fontWeight: FontWeight.w700)),
          ]))),
          if (tasks.isNotEmpty) ...[
            const SizedBox(height: 16), Text('Мои задачи', style: Theme.of(context).textTheme.titleMedium),
            ...tasks.map((x) { final t=Map<String,dynamic>.from(x); return Card(child: ListTile(
              leading: const Icon(Icons.task_alt_outlined), title: Text(t['title'] ?? ''),
              subtitle: Text('${t['status'] ?? ''} • ${t['priority'] ?? ''}'),
            )); }),
          ],
          if (sales.isNotEmpty) ...[
            const SizedBox(height: 16), Text('Последние продажи', style: Theme.of(context).textTheme.titleMedium),
            ...sales.map((x) { final s=Map<String,dynamic>.from(x); return Card(child: ListTile(
              leading: const Icon(Icons.receipt_long_outlined), title: Text('Чек №${s['sale_number'] ?? s['id']}'),
              subtitle: Text(s['status'] ?? ''), trailing: Text(money(s['total_amount'])),
            )); }),
          ],
        ],
      ),
    );
  }

  Widget _stats(Map<String,dynamic> s) => Row(children: [
    Expanded(child: _stat('Продажи', '${s['sales_count'] ?? 0}', Icons.shopping_cart_outlined)),
    const SizedBox(width: 8),
    Expanded(child: _stat('Выручка', money(s['revenue']), Icons.payments_outlined)),
  ]);
  Widget _stat(String title,String value,IconData icon)=>Card(child: Padding(padding: const EdgeInsets.all(14),child:Column(children:[
    Icon(icon,color:AppColors.primary),const SizedBox(height:8),Text(value,style:const TextStyle(fontWeight:FontWeight.w700)),Text(title,style:const TextStyle(color:AppColors.muted))
  ])));
}
