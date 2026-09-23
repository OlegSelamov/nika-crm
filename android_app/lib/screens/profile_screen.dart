import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/catalog_display_preferences.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? data;
  String? error;
  bool loading = true;
  bool savingCatalogDisplay = false;

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    try {
      final result = await ApiService.mobileProfile();
      try {
        await CatalogDisplayPreferences.load();
      } catch (_) {}
      if (mounted) setState(() { data = result; error = null; loading = false; });
    } catch (e) {
      if (mounted) setState(() { error = e.toString(); loading = false; });
    }
  }

  String money(dynamic v) => '${(num.tryParse('${v ?? 0}') ?? 0).toStringAsFixed(0)} ₸';

  Future<void> setCatalogImages(bool value) async {
    setState(() => savingCatalogDisplay = true);
    try {
      await CatalogDisplayPreferences.setShowImages(value);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            value
                ? 'Фотографии товаров включены во всей системе'
                : 'Включён компактный список без фотографий',
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => savingCatalogDisplay = false);
    }
  }


  Future<void> openTaxSettings() async {
    final current = Map<String, dynamic>.from(data?['tax_settings'] ?? const {});
    final fields = <String, TextEditingController>{
      'turnover_rate': TextEditingController(text: '${current['turnover_rate'] ?? 4}'),
      'mzp': TextEditingController(text: '${current['mzp'] ?? 85000}'),
      'mrp': TextEditingController(text: '${current['mrp'] ?? 4325}'),
      'owner_base': TextEditingController(text: '${current['owner_base'] ?? 85000}'),
      'owner_opv_rate': TextEditingController(text: '${current['owner_opv_rate'] ?? 10}'),
      'owner_so_rate': TextEditingController(text: '${current['owner_so_rate'] ?? 5}'),
      'owner_vosms_rate': TextEditingController(text: '${current['owner_vosms_rate'] ?? 5}'),
      'employee_opv_rate': TextEditingController(text: '${current['employee_opv_rate'] ?? 10}'),
      'employee_vosms_rate': TextEditingController(text: '${current['employee_vosms_rate'] ?? 2}'),
      'employee_ipn_rate': TextEditingController(text: '${current['employee_ipn_rate'] ?? 10}'),
      'employer_so_rate': TextEditingController(text: '${current['employer_so_rate'] ?? 5}'),
      'employer_osms_rate': TextEditingController(text: '${current['employer_osms_rate'] ?? 3}'),
      'employer_opvr_rate': TextEditingController(text: '${current['employer_opvr_rate'] ?? 3.5}'),
      'standard_deduction': TextEditingController(text: '${current['standard_deduction'] ?? 0}'),
    };
    bool includeOwnerOpvr = current['include_owner_opvr'] == true;
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialog) => AlertDialog(
          title: const Text('Настройки налогов'),
          content: SingleChildScrollView(
            child: SizedBox(
              width: 460,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                _taxField(fields['turnover_rate']!, 'Налог с оборота', '%'),
                const SizedBox(height: 10),
                Row(children: [
                  Expanded(child: _taxField(fields['mzp']!, 'МЗП', '₸')),
                  const SizedBox(width: 10),
                  Expanded(child: _taxField(fields['mrp']!, 'МРП', '₸')),
                ]),
                const SizedBox(height: 10),
                _taxField(fields['owner_base']!, 'База ИП за себя', '₸'),
                const SizedBox(height: 14),
                const Align(alignment: Alignment.centerLeft, child: Text('ИП за себя', style: TextStyle(fontWeight: FontWeight.w900))),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(child: _taxField(fields['owner_opv_rate']!, 'ОПВ', '%')),
                  const SizedBox(width: 8),
                  Expanded(child: _taxField(fields['owner_so_rate']!, 'СО', '%')),
                  const SizedBox(width: 8),
                  Expanded(child: _taxField(fields['owner_vosms_rate']!, 'ВОСМС', '%')),
                ]),
                const SizedBox(height: 14),
                const Align(alignment: Alignment.centerLeft, child: Text('Работники', style: TextStyle(fontWeight: FontWeight.w900))),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(child: _taxField(fields['employee_opv_rate']!, 'ОПВ', '%')),
                  const SizedBox(width: 8),
                  Expanded(child: _taxField(fields['employee_vosms_rate']!, 'ВОСМС', '%')),
                  const SizedBox(width: 8),
                  Expanded(child: _taxField(fields['employee_ipn_rate']!, 'ИПН', '%')),
                ]),
                const SizedBox(height: 10),
                Row(children: [
                  Expanded(child: _taxField(fields['employer_so_rate']!, 'СО раб.', '%')),
                  const SizedBox(width: 8),
                  Expanded(child: _taxField(fields['employer_osms_rate']!, 'ОСМС', '%')),
                  const SizedBox(width: 8),
                  Expanded(child: _taxField(fields['employer_opvr_rate']!, 'ОПВР', '%')),
                ]),
                const SizedBox(height: 10),
                _taxField(fields['standard_deduction']!, 'Стандартный вычет', '₸'),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  value: includeOwnerOpvr,
                  onChanged: (v) => setDialog(() => includeOwnerOpvr = v),
                  title: const Text('Считать ОПВР за ИП'),
                ),
              ]),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Отмена')),
            FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Сохранить')),
          ],
        ),
      ),
    );
    if (saved == true) {
      try {
        final payload = <String, dynamic>{
          for (final entry in fields.entries)
            entry.key: entry.value.text.replaceAll(' ', '').replaceAll(',', '.'),
          'include_owner_opvr': includeOwnerOpvr,
          'regime': current['regime'] ?? 'simplified',
        };
        await ApiService.saveMobileTaxSettings(payload);
        await load();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Налоговые ставки сохранены')),
          );
        }
      } catch (e) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
      }
    }
    for (final controller in fields.values) {
      controller.dispose();
    }
  }

  Widget _taxField(TextEditingController controller, String label, String suffix) =>
      TextField(
        controller: controller,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(labelText: label, suffixText: suffix),
      );

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
          Card(
            child: ValueListenableBuilder<bool>(
              valueListenable: CatalogDisplayPreferences.showImages,
              builder: (context, showImages, _) => SwitchListTile.adaptive(
                value: showImages,
                onChanged: savingCatalogDisplay ? null : setCatalogImages,
                secondary: Icon(
                  showImages
                      ? Icons.photo_library_outlined
                      : Icons.view_list_rounded,
                  color: AppColors.primary,
                ),
                title: const Text(
                  'Фотографии товаров',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(
                  showImages
                      ? 'Каталог, продажи и склад отображаются с фотографиями'
                      : 'Во всей системе используется компактный список',
                ),
              ),
            ),
          ),
          if (data?['can_manage_taxes'] == true) ...[
            const SizedBox(height: 12),
            Card(
              child: ListTile(
                leading: const CircleAvatar(
                  backgroundColor: AppColors.primarySoft,
                  child: Icon(Icons.calculate_outlined, color: AppColors.primary),
                ),
                title: const Text('Налоговые ставки и базы', style: TextStyle(fontWeight: FontWeight.w800)),
                subtitle: const Text('МЗП, МРП, ОПВ, СО, ОСМС, ВОСМС, ИПН и ОПВР'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: openTaxSettings,
              ),
            ),
          ],
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
