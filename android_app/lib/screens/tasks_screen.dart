import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  bool loading = true;
  String? error;
  Map<String, dynamic> data = {};

  List<dynamic> get items => List<dynamic>.from(data['items'] ?? const []);
  List<dynamic> get users => List<dynamic>.from(data['users'] ?? const []);
  Map<String, dynamic> get summary => Map<String, dynamic>.from(data['summary'] ?? const {});

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await ApiService.mobileTasks();
      if (mounted) setState(() => data = result);
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> save([Map<String, dynamic>? task]) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _TaskDialog(task: task, users: users),
    );
    if (result == null) return;
    try {
      if (task == null) {
        await ApiService.createMobileTask(result);
      } else {
        await ApiService.updateMobileTask(task['id'] as int, result);
      }
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Future<void> setStatus(Map<String, dynamic> task, String value) async {
    try {
      await ApiService.updateMobileTask(task['id'] as int, {'status': value});
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Future<void> remove(Map<String, dynamic> task) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Удалить задачу?'),
        content: Text('${task['title']}'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Удалить')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.deleteMobileTask(task['id'] as int);
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Color statusColor(String status) {
    switch (status) {
      case 'done': return AppColors.success;
      case 'in_progress': return AppColors.primary;
      case 'cancelled': return AppColors.muted;
      default: return AppColors.warning;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(icon: Icons.task_alt_rounded, title: 'Задачи недоступны', message: error!, onAction: load);
    }
    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 30),
        children: [
          Row(
            children: [
              Expanded(child: SectionTitle('Работа команды', subtitle: '${summary['total'] ?? 0} задач')),
              FilledButton.icon(onPressed: () => save(), icon: const Icon(Icons.add_rounded), label: const Text('Создать')),
            ],
          ),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(child: _MiniMetric('Новые', '${summary['new'] ?? 0}', AppColors.warning)),
            const SizedBox(width: 8),
            Expanded(child: _MiniMetric('В работе', '${summary['in_progress'] ?? 0}', AppColors.primary)),
            const SizedBox(width: 8),
            Expanded(child: _MiniMetric('Просрочено', '${summary['overdue'] ?? 0}', AppColors.danger)),
          ]),
          const SizedBox(height: 14),
          if (items.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(28), child: Center(child: Text('Задач пока нет', style: TextStyle(color: AppColors.muted)))))
          else
            ...items.map((raw) {
              final task = Map<String, dynamic>.from(raw as Map);
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20),
                    onTap: () => save(task),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Expanded(child: Text('${task['title']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800))),
                          PopupMenuButton<String>(
                            tooltip: 'Действия',
                            onSelected: (value) => value == 'delete' ? remove(task) : setStatus(task, value),
                            itemBuilder: (_) => const [
                              PopupMenuItem(value: 'new', child: Text('Новая')),
                              PopupMenuItem(value: 'in_progress', child: Text('В работе')),
                              PopupMenuItem(value: 'done', child: Text('Выполнена')),
                              PopupMenuDivider(),
                              PopupMenuItem(value: 'delete', child: Text('Удалить')),
                            ],
                          ),
                        ]),
                        if ('${task['description'] ?? ''}'.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text('${task['description']}', maxLines: 3, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted)),
                        ],
                        const SizedBox(height: 12),
                        Wrap(spacing: 7, runSpacing: 7, children: [
                          StatusPill('${task['status_label']}', color: statusColor('${task['status']}')),
                          StatusPill('${task['priority_label']}', color: task['priority'] == 'urgent' ? AppColors.danger : AppColors.warning),
                          StatusPill('${task['due_date_label']}', color: task['overdue'] == true ? AppColors.danger : AppColors.muted),
                        ]),
                        const SizedBox(height: 10),
                        Row(children: [
                          const Icon(Icons.person_outline_rounded, size: 18, color: AppColors.muted),
                          const SizedBox(width: 6),
                          Expanded(child: Text('${task['assignee_name']}', style: const TextStyle(color: AppColors.muted))),
                        ]),
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

class _MiniMetric extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _MiniMetric(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 14),
      child: Column(children: [
        Text(value, style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w900)),
        const SizedBox(height: 3),
        Text(label, maxLines: 1, style: const TextStyle(color: AppColors.muted, fontSize: 11)),
      ]),
    ),
  );
}

class _TaskDialog extends StatefulWidget {
  final Map<String, dynamic>? task;
  final List<dynamic> users;
  const _TaskDialog({required this.task, required this.users});

  @override
  State<_TaskDialog> createState() => _TaskDialogState();
}

class _TaskDialogState extends State<_TaskDialog> {
  late final TextEditingController title;
  late final TextEditingController description;
  late final TextEditingController dueDate;
  String priority = 'medium';
  int? assignee;

  @override
  void initState() {
    super.initState();
    title = TextEditingController(text: '${widget.task?['title'] ?? ''}');
    description = TextEditingController(text: '${widget.task?['description'] ?? ''}');
    dueDate = TextEditingController(text: '${widget.task?['due_date'] ?? ''}');
    priority = '${widget.task?['priority'] ?? 'medium'}';
    assignee = widget.task?['assignee_id'] as int?;
  }

  @override
  void dispose() {
    title.dispose(); description.dispose(); dueDate.dispose(); super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.task == null ? 'Новая задача' : 'Редактировать задачу'),
    content: SingleChildScrollView(child: SizedBox(
      width: 420,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: title, decoration: const InputDecoration(labelText: 'Название *')),
        const SizedBox(height: 10),
        TextField(controller: description, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Описание')),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          value: priority,
          decoration: const InputDecoration(labelText: 'Приоритет'),
          items: const [
            DropdownMenuItem(value: 'low', child: Text('Низкий')),
            DropdownMenuItem(value: 'medium', child: Text('Средний')),
            DropdownMenuItem(value: 'high', child: Text('Высокий')),
            DropdownMenuItem(value: 'urgent', child: Text('Срочный')),
          ],
          onChanged: (v) => setState(() => priority = v ?? 'medium'),
        ),
        const SizedBox(height: 10),
        DropdownButtonFormField<int?>(
          value: assignee,
          decoration: const InputDecoration(labelText: 'Исполнитель'),
          items: [
            const DropdownMenuItem<int?>(value: null, child: Text('Не назначен')),
            ...widget.users.map((raw) {
              final user = Map<String, dynamic>.from(raw as Map);
              return DropdownMenuItem<int?>(value: user['id'] as int, child: Text('${user['name']}'));
            }),
          ],
          onChanged: (v) => setState(() => assignee = v),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: dueDate,
          readOnly: true,
          decoration: const InputDecoration(labelText: 'Срок', hintText: 'ГГГГ-ММ-ДД', suffixIcon: Icon(Icons.calendar_month_outlined)),
          onTap: () async {
            final selected = await showDatePicker(context: context, firstDate: DateTime(2020), lastDate: DateTime(2100), initialDate: DateTime.tryParse(dueDate.text) ?? DateTime.now());
            if (selected != null) dueDate.text = selected.toIso8601String().substring(0, 10);
          },
        ),
      ]),
    )),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
      FilledButton(
        onPressed: () {
          if (title.text.trim().isEmpty) return;
          Navigator.pop(context, {
            'title': title.text.trim(),
            'description': description.text.trim(),
            'priority': priority,
            'assigned_user_id': assignee,
            'due_date': dueDate.text,
          });
        },
        child: const Text('Сохранить'),
      ),
    ],
  );
}
