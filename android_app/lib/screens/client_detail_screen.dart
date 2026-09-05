import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'add_client_screen.dart';

class ClientDetailScreen extends StatefulWidget {
  final int clientId;

  const ClientDetailScreen({super.key, required this.clientId});

  @override
  State<ClientDetailScreen> createState() => _ClientDetailScreenState();
}

class _ClientDetailScreenState extends State<ClientDetailScreen> {
  bool loading = true;
  String? error;
  Map<String, dynamic> client = {};
  List<dynamic> deals = [];

  bool get isDeleted => client['is_deleted'] == true;

  @override
  void initState() {
    super.initState();
    loadClient();
  }

  Future<void> loadClient() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final data = await ApiService.getClient(widget.clientId);
      if (!mounted) return;
      setState(() {
        client = Map<String, dynamic>.from(data['client'] as Map? ?? {});
        deals = List<dynamic>.from(data['deals'] ?? const []);
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  Future<bool> _confirm(String title, String message, String action) async =>
      await showDialog<bool>(
        context: context,
        builder: (_) => AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(action)),
          ],
        ),
      ) ?? false;

  Future<void> _edit() async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => AddClientScreen(client: client)),
    );
    if (changed == true) await loadClient();
  }

  Future<void> _delete() async {
    final confirmed = await _confirm(
      'Удалить клиента?',
      'Карточка будет перемещена в раздел «Удалённые».',
      'Удалить',
    );
    if (!confirmed) return;
    try {
      await ApiService.deleteClient(widget.clientId);
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Future<void> _restore() async {
    try {
      await ApiService.restoreClient(widget.clientId);
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Future<void> _deletePermanently() async {
    final confirmed = await _confirm(
      'Удалить навсегда?',
      'Клиента и его карточку нельзя будет восстановить.',
      'Удалить навсегда',
    );
    if (!confirmed) return;
    try {
      await ApiService.deleteClientPermanently(widget.clientId);
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  String _value(String key) {
    final value = '${client[key] ?? ''}'.trim();
    return value.isEmpty ? '—' : value;
  }

  Widget _info(String label, String value, IconData icon) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 20, color: AppColors.muted),
            const SizedBox(width: 11),
            SizedBox(width: 112, child: Text(label, style: const TextStyle(color: AppColors.muted))),
            Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Клиент')),
        body: ScreenStateView(
          icon: Icons.person_off_outlined,
          title: 'Клиент недоступен',
          message: error!,
          onAction: loadClient,
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(_value('full_name')),
        actions: [
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'edit') _edit();
              if (value == 'delete') _delete();
              if (value == 'restore') _restore();
              if (value == 'permanent') _deletePermanently();
            },
            itemBuilder: (_) => isDeleted
                ? const [
                    PopupMenuItem(value: 'restore', child: Text('Восстановить')),
                    PopupMenuItem(value: 'permanent', child: Text('Удалить навсегда')),
                  ]
                : const [
                    PopupMenuItem(value: 'edit', child: Text('Изменить')),
                    PopupMenuItem(value: 'delete', child: Text('Удалить')),
                  ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: loadClient,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      CircleAvatar(
                        radius: 28,
                        backgroundColor: AppColors.primarySoft,
                        foregroundColor: AppColors.primary,
                        child: Text(_value('full_name').substring(0, 1).toUpperCase(), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                      ),
                      const SizedBox(width: 13),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(_value('full_name'), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                          if (_value('company_name') != '—') Text(_value('company_name'), style: const TextStyle(color: AppColors.muted)),
                        ]),
                      ),
                    ]),
                    const Divider(height: 30),
                    _info('ИИН / БИН', _value('iin'), Icons.badge_outlined),
                    _info('Телефон', _value('phone'), Icons.phone_outlined),
                    _info('Адрес', _value('address'), Icons.location_on_outlined),
                    _info('Статус', _value('status'), Icons.flag_outlined),
                    _info('Категория', _value('category'), Icons.category_outlined),
                    _info('Оплата', _value('payment'), Icons.payments_outlined),
                    _info('Договор', _value('contract_number'), Icons.description_outlined),
                    _info('Дата договора', _value('contract_date'), Icons.calendar_month_outlined),
                    _info('Комментарий', _value('comment'), Icons.notes_outlined),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),
            const SectionTitle('История продаж', subtitle: 'Все операции, связанные с клиентом'),
            const SizedBox(height: 10),
            if (deals.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(22),
                  child: Center(child: Text('Продаж пока нет', style: TextStyle(color: AppColors.muted))),
                ),
              )
            else
              ...deals.map((sale) => Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: CircleAvatar(child: Text('#${sale['id']}')),
                      title: Text(money(sale['total_amount']), style: const TextStyle(fontWeight: FontWeight.w800)),
                      subtitle: Text('${sale['status'] ?? ''}'),
                    ),
                  )),
          ],
        ),
      ),
      floatingActionButton: isDeleted
          ? null
          : FloatingActionButton.extended(onPressed: _edit, icon: const Icon(Icons.edit_outlined), label: const Text('Изменить')),
    );
  }
}
