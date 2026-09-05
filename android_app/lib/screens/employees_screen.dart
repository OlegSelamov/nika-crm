import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class EmployeesScreen extends StatefulWidget {
  const EmployeesScreen({super.key});

  @override
  State<EmployeesScreen> createState() => _EmployeesScreenState();
}

class _EmployeesScreenState extends State<EmployeesScreen> {
  bool loading = true;
  String? error;
  List<dynamic> items = [];

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.mobileEmployees();
      if (mounted) setState(() => items = List<dynamic>.from(data['items'] ?? const []));
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> save([Map<String, dynamic>? item]) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _EmployeeDialog(item: item),
    );
    if (result == null) return;
    try {
      if (item == null) {
        await ApiService.createMobileEmployee(result);
      } else {
        await ApiService.updateMobileEmployee(item['id'] as int, result);
      }
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Future<void> remove(Map<String, dynamic> item) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Удалить сотрудника?'),
        content: Text('${item['full_name']}'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Удалить')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.deleteMobileEmployee(item['id'] as int);
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) return ScreenStateView(icon: Icons.badge_outlined, title: 'Сотрудники недоступны', message: error!, onAction: load);
    final online = items.where((e) => e['is_online'] == true).length;
    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 30),
        children: [
          Row(children: [
            Expanded(child: SectionTitle('Команда', subtitle: '${items.length} сотрудников · $online онлайн')),
            FilledButton.icon(onPressed: () => save(), icon: const Icon(Icons.person_add_alt_1_rounded), label: const Text('Добавить')),
          ]),
          const SizedBox(height: 14),
          if (items.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(30), child: Center(child: Text('Сотрудников пока нет', style: TextStyle(color: AppColors.muted)))))
          else
            ...items.map((raw) {
              final item = Map<String, dynamic>.from(raw as Map);
              final isOnline = item['is_online'] == true;
              final owner = item['role'] == 'owner';
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  child: InkWell(
                    onTap: () => save(item),
                    borderRadius: BorderRadius.circular(20),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(children: [
                        Stack(children: [
                          CircleAvatar(
                            radius: 25,
                            backgroundColor: AppColors.primarySoft,
                            child: Text(_initials('${item['full_name']}'), style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w900)),
                          ),
                          Positioned(right: 0, bottom: 1, child: Container(width: 13, height: 13, decoration: BoxDecoration(color: isOnline ? AppColors.success : AppColors.muted, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 2)))),
                        ]),
                        const SizedBox(width: 13),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${item['full_name']}'.trim().isEmpty ? item['username'] : item['full_name'], style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                          const SizedBox(height: 4),
                          Text('${item['position']}'.trim().isEmpty ? '@${item['username']}' : '${item['position']} · @${item['username']}', style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                          const SizedBox(height: 8),
                          Wrap(spacing: 7, children: [
                            StatusPill(owner ? 'Владелец' : item['role'] == 'admin' ? 'Администратор' : 'Сотрудник', color: owner ? AppColors.warning : AppColors.primary),
                            StatusPill(isOnline ? 'Онлайн' : 'Не в сети', color: isOnline ? AppColors.success : AppColors.muted),
                            if (asDouble(item['percent_rate']) > 0) StatusPill('${item['percent_rate']}%', color: AppColors.cyan),
                          ]),
                        ])),
                        PopupMenuButton<String>(
                          onSelected: (value) => value == 'edit' ? save(item) : remove(item),
                          itemBuilder: (_) => [
                            const PopupMenuItem(value: 'edit', child: Text('Изменить')),
                            if (!owner) const PopupMenuItem(value: 'delete', child: Text('Удалить')),
                          ],
                        ),
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

  String _initials(String value) {
    final words = value.trim().split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
    if (words.isEmpty) return '?';
    return words.take(2).map((e) => e[0].toUpperCase()).join();
  }
}

class _EmployeeDialog extends StatefulWidget {
  final Map<String, dynamic>? item;
  const _EmployeeDialog({required this.item});

  @override
  State<_EmployeeDialog> createState() => _EmployeeDialogState();
}

class _EmployeeDialogState extends State<_EmployeeDialog> {
  late final TextEditingController fullName;
  late final TextEditingController username;
  late final TextEditingController password;
  late final TextEditingController phone;
  late final TextEditingController position;
  late final TextEditingController rate;
  late String role;
  bool hidePassword = true;

  @override
  void initState() {
    super.initState();
    fullName = TextEditingController(text: '${widget.item?['full_name'] ?? ''}');
    username = TextEditingController(text: '${widget.item?['username'] ?? ''}');
    password = TextEditingController();
    phone = TextEditingController(text: '${widget.item?['phone'] ?? ''}');
    position = TextEditingController(text: '${widget.item?['position'] ?? ''}');
    rate = TextEditingController(text: '${widget.item?['percent_rate'] ?? 0}');
    role = '${widget.item?['role'] ?? 'employee'}';
  }

  @override
  void dispose() {
    fullName.dispose(); username.dispose(); password.dispose(); phone.dispose(); position.dispose(); rate.dispose(); super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final editing = widget.item != null;
    final owner = role == 'owner';
    return AlertDialog(
      title: Text(editing ? 'Изменить сотрудника' : 'Новый сотрудник'),
      content: SingleChildScrollView(child: SizedBox(width: 420, child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: fullName, decoration: const InputDecoration(labelText: 'ФИО *')),
        const SizedBox(height: 10),
        TextField(controller: username, enabled: !editing, decoration: const InputDecoration(labelText: 'Логин *')),
        const SizedBox(height: 10),
        TextField(
          controller: password,
          obscureText: hidePassword,
          decoration: InputDecoration(
            labelText: editing ? 'Новый пароль' : 'Пароль *',
            suffixIcon: IconButton(onPressed: () => setState(() => hidePassword = !hidePassword), icon: Icon(hidePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined)),
          ),
        ),
        const SizedBox(height: 10),
        TextField(controller: phone, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Телефон')),
        const SizedBox(height: 10),
        TextField(controller: position, decoration: const InputDecoration(labelText: 'Должность')),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          value: owner ? 'owner' : role,
          decoration: const InputDecoration(labelText: 'Роль'),
          items: [
            if (owner) const DropdownMenuItem(value: 'owner', child: Text('Владелец')),
            const DropdownMenuItem(value: 'admin', child: Text('Администратор')),
            const DropdownMenuItem(value: 'employee', child: Text('Сотрудник')),
          ],
          onChanged: owner ? null : (v) => setState(() => role = v ?? 'employee'),
        ),
        const SizedBox(height: 10),
        TextField(controller: rate, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Процент от продаж', suffixText: '%')),
      ]))),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
        FilledButton(
          onPressed: () {
            if (fullName.text.trim().isEmpty || (!editing && (username.text.trim().isEmpty || password.text.isEmpty))) return;
            Navigator.pop(context, {
              'full_name': fullName.text.trim(),
              if (!editing) 'username': username.text.trim(),
              'password': password.text,
              'phone': phone.text.trim(),
              'position': position.text.trim(),
              'role': role,
              'percent_rate': rate.text.replaceAll(',', '.'),
            });
          },
          child: const Text('Сохранить'),
        ),
      ],
    );
  }
}
