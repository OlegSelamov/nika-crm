import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'add_client_screen.dart';
import 'client_detail_screen.dart';
import 'scanner_screen.dart';

class ClientsScreen extends StatefulWidget {
  const ClientsScreen({super.key});

  @override
  State<ClientsScreen> createState() => _ClientsScreenState();
}

class _ClientsScreenState extends State<ClientsScreen> {
  bool loading = true;
  String? error;
  bool showDeleted = false;
  List<Map<String, dynamic>> activeClients = [];
  List<Map<String, dynamic>> deletedClients = [];
  final searchController = TextEditingController();

  List<Map<String, dynamic>> get _source =>
      showDeleted ? deletedClients : activeClients;

  List<Map<String, dynamic>> get _filtered {
    final query = searchController.text.trim().toLowerCase();
    if (query.isEmpty) return _source;
    return _source.where((client) {
      final search = [
        client['full_name'],
        client['company_name'],
        client['iin'],
        client['phone'],
        client['address'],
        client['category'],
        client['status'],
      ].map((value) => '${value ?? ''}'.toLowerCase()).join(' ');
      return search.contains(query);
    }).toList();
  }

  @override
  void initState() {
    super.initState();
    loadClients();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  Future<void> loadClients() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final results = await Future.wait([
        ApiService.getClients(),
        ApiService.getClients(deleted: true),
      ]);
      if (!mounted) return;
      setState(() {
        activeClients = results[0]
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
        deletedClients = results[1]
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { error = readableError(e); loading = false; });
    }
  }

  Future<void> _openAdd() async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const AddClientScreen()),
    );
    if (changed == true) loadClients();
  }

  Future<void> _openClient(Map<String, dynamic> client) async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => ClientDetailScreen(clientId: client['id'] as int),
      ),
    );
    if (changed == true) loadClients();
  }

  Future<void> _scanClient() async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ScannerScreen()),
    );
    if (result == null) return;
    final iin = result.toString().replaceAll(RegExp(r'\D'), '');
    try {
      final response = await ApiService.getClientByIin(iin);
      if (!mounted) return;
      if (response['found'] == true && response['client'] is Map) {
        await _openClient(Map<String, dynamic>.from(response['client'] as Map));
      } else {
        final changed = await Navigator.push<bool>(
          context,
          MaterialPageRoute(builder: (_) => AddClientScreen(initialIdentifier: iin)),
        );
        if (changed == true) loadClients();
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(error))),
        );
      }
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

  Future<void> _delete(Map<String, dynamic> client) async {
    final confirmed = await _confirm(
      'Удалить клиента?',
      '${client['full_name'] ?? 'Клиент'} будет перемещён в удалённые.',
      'Удалить',
    );
    if (!confirmed) return;
    try {
      await ApiService.deleteClient(client['id'] as int);
      await loadClients();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Future<void> _restore(Map<String, dynamic> client) async {
    try {
      await ApiService.restoreClient(client['id'] as int);
      await loadClients();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Future<void> _deletePermanently(Map<String, dynamic> client) async {
    final confirmed = await _confirm(
      'Удалить навсегда?',
      'Карточку ${client['full_name'] ?? 'клиента'} нельзя будет восстановить.',
      'Удалить навсегда',
    );
    if (!confirmed) return;
    try {
      await ApiService.deleteClientPermanently(client['id'] as int);
      await loadClients();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(error))));
    }
  }

  Widget _pill(String text, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        decoration: BoxDecoration(
          color: color.withOpacity(.1),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(text, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
      );

  Widget _clientCard(Map<String, dynamic> client) {
    final name = '${client['full_name'] ?? ''}'.trim();
    final company = '${client['company_name'] ?? ''}'.trim();
    final status = '${client['status'] ?? 'Новый'}';
    final category = '${client['category'] ?? 'Клиент'}';
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () => _openClient(client),
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                backgroundColor: showDeleted ? AppColors.border : AppColors.primarySoft,
                foregroundColor: showDeleted ? AppColors.muted : AppColors.primary,
                child: Text(name.isEmpty ? 'К' : name.substring(0, 1).toUpperCase()),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name.isEmpty ? 'Без имени' : name, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                    if (company.isNotEmpty && company != name) ...[
                      const SizedBox(height: 2),
                      Text(company, style: const TextStyle(color: AppColors.muted)),
                    ],
                    const SizedBox(height: 9),
                    Wrap(spacing: 6, runSpacing: 6, children: [
                      _pill(category, AppColors.cyan),
                      _pill(status, status == 'Завершен' ? AppColors.success : AppColors.primary),
                    ]),
                    const SizedBox(height: 9),
                    if ('${client['iin'] ?? ''}'.isNotEmpty)
                      Text('ИИН/БИН: ${client['iin']}', style: const TextStyle(fontSize: 13)),
                    if ('${client['phone'] ?? ''}'.isNotEmpty)
                      Text('Телефон: ${client['phone']}', style: const TextStyle(fontSize: 13)),
                    if ('${client['address'] ?? ''}'.isNotEmpty)
                      Text('${client['address']}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                  ],
                ),
              ),
              PopupMenuButton<String>(
                onSelected: (value) {
                  if (value == 'open') _openClient(client);
                  if (value == 'delete') _delete(client);
                  if (value == 'restore') _restore(client);
                  if (value == 'permanent') _deletePermanently(client);
                },
                itemBuilder: (_) => showDeleted
                    ? const [
                        PopupMenuItem(value: 'open', child: Text('Просмотреть')),
                        PopupMenuItem(value: 'restore', child: Text('Восстановить')),
                        PopupMenuItem(value: 'permanent', child: Text('Удалить навсегда')),
                      ]
                    : const [
                        PopupMenuItem(value: 'open', child: Text('Просмотреть')),
                        PopupMenuItem(value: 'delete', child: Text('Удалить')),
                      ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.people_alt_outlined,
        title: 'Клиенты недоступны',
        message: error!,
        onAction: loadClients,
      );
    }
    final clients = _filtered;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Row(children: [
            Expanded(
              child: SegmentedButton<bool>(
                segments: [
                  ButtonSegment(value: false, label: Text('Активные ${activeClients.length}'), icon: const Icon(Icons.people_alt_outlined)),
                  ButtonSegment(value: true, label: Text('Удалённые ${deletedClients.length}'), icon: const Icon(Icons.delete_outline)),
                ],
                selected: {showDeleted},
                onSelectionChanged: (value) => setState(() => showDeleted = value.first),
              ),
            ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: TextField(
            controller: searchController,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              hintText: 'Имя, компания, ИИН, телефон или адрес',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: IconButton(icon: const Icon(Icons.qr_code_scanner), onPressed: _scanClient),
            ),
          ),
        ),
        if (!showDeleted)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(onPressed: _openAdd, icon: const Icon(Icons.person_add_alt_1), label: const Text('Добавить клиента')),
            ),
          ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: loadClients,
            child: clients.isEmpty
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(36),
                        child: Center(child: Text(showDeleted ? 'Удалённых клиентов нет' : 'Клиенты не найдены')),
                      ),
                    ],
                  )
                : ListView.builder(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
                    itemCount: clients.length,
                    itemBuilder: (_, index) => _clientCard(clients[index]),
                  ),
          ),
        ),
      ],
    );
  }
}
