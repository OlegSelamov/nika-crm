import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class WhatsappScreen extends StatefulWidget {
  const WhatsappScreen({super.key});

  @override
  State<WhatsappScreen> createState() => _WhatsappScreenState();
}

class _WhatsappScreenState extends State<WhatsappScreen> {
  final search = TextEditingController();
  bool loading = true;
  String? error;
  List<dynamic> chats = [];

  @override
  void initState() {
    super.initState();
    loadChats();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> loadChats() async {
    try {
      final result = await ApiService.whatsappChats(search: search.text.trim());
      if (!mounted) return;
      setState(() {
        chats = List<dynamic>.from(result['items'] ?? const []);
        loading = false;
        error = result['ok'] == false ? '${result['error'] ?? 'WhatsApp недоступен'}' : null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = readableError(e);
        loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('WhatsApp')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 10),
            child: TextField(
              controller: search,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => loadChats(),
              decoration: InputDecoration(
                hintText: 'Поиск по имени или телефону',
                prefixIcon: const Icon(Icons.search_rounded),
                suffixIcon: IconButton(onPressed: loadChats, icon: const Icon(Icons.arrow_forward_rounded)),
              ),
            ),
          ),
          Expanded(
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : error != null
                    ? ScreenStateView(
                        icon: Icons.chat_bubble_outline_rounded,
                        title: 'WhatsApp не подключён',
                        message: error!,
                        onAction: loadChats,
                      )
                    : chats.isEmpty
                        ? const ScreenStateView(
                            icon: Icons.forum_outlined,
                            title: 'Диалогов пока нет',
                            message: 'Новые обращения клиентов появятся здесь.',
                          )
                        : RefreshIndicator(
                            onRefresh: loadChats,
                            child: ListView.separated(
                              padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
                              itemCount: chats.length,
                              separatorBuilder: (_, __) => const SizedBox(height: 8),
                              itemBuilder: (_, index) => _chatTile(chats[index]),
                            ),
                          ),
          ),
        ],
      ),
    );
  }

  Widget _chatTile(dynamic raw) {
    final chat = Map<String, dynamic>.from(raw as Map);
    final unread = int.tryParse('${chat['unread_count'] ?? 0}') ?? 0;
    final name = '${chat['display_name'] ?? chat['contact_name'] ?? chat['phone'] ?? 'Клиент'}';
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFE6F8EF),
          foregroundColor: AppColors.success,
          child: Text(name.isEmpty ? '?' : name[0].toUpperCase(), style: const TextStyle(fontWeight: FontWeight.w900)),
        ),
        title: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text('${chat['last_message'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('${chat['last_message_at_short'] ?? ''}', style: const TextStyle(color: AppColors.muted, fontSize: 11)),
            if (unread > 0) ...[
              const SizedBox(height: 5),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(color: AppColors.success, borderRadius: BorderRadius.circular(99)),
                child: Text('$unread', style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800)),
              ),
            ],
          ],
        ),
        onTap: () async {
          await Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => WhatsappChatScreen(
                chatId: int.tryParse('${chat['id']}') ?? 0,
                title: name,
              ),
            ),
          );
          await loadChats();
        },
      ),
    );
  }
}

class WhatsappChatScreen extends StatefulWidget {
  final int chatId;
  final String title;

  const WhatsappChatScreen({super.key, required this.chatId, required this.title});

  @override
  State<WhatsappChatScreen> createState() => _WhatsappChatScreenState();
}

class _WhatsappChatScreenState extends State<WhatsappChatScreen> {
  final controller = TextEditingController();
  final scroll = ScrollController();
  bool loading = true;
  bool sending = false;
  List<dynamic> messages = [];

  @override
  void initState() {
    super.initState();
    loadMessages();
  }

  @override
  void dispose() {
    controller.dispose();
    scroll.dispose();
    super.dispose();
  }

  Future<void> loadMessages() async {
    try {
      final result = await ApiService.whatsappMessages(widget.chatId);
      if (!mounted) return;
      setState(() {
        messages = List<dynamic>.from(result['items'] ?? const []);
        loading = false;
      });
      _bottom();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        messages = [
          {'message': readableError(e), 'is_mine': false},
        ];
        loading = false;
      });
    }
  }

  Future<void> _send() async {
    final text = controller.text.trim();
    if (text.isEmpty || sending) return;
    setState(() => sending = true);
    try {
      await ApiService.sendWhatsappMessage(widget.chatId, text);
      controller.clear();
      await loadMessages();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    } finally {
      if (mounted) setState(() => sending = false);
    }
  }

  void _bottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!scroll.hasClients) return;
      scroll.jumpTo(scroll.position.maxScrollExtent);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.title, maxLines: 1, overflow: TextOverflow.ellipsis),
            const Text('WhatsApp', style: TextStyle(color: AppColors.success, fontSize: 12, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    controller: scroll,
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 20),
                    itemCount: messages.length,
                    itemBuilder: (_, index) {
                      final message = Map<String, dynamic>.from(messages[index] as Map);
                      final mine = message['is_mine'] == true;
                      return Align(
                        alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
                        child: Container(
                          constraints: const BoxConstraints(maxWidth: 320),
                          margin: const EdgeInsets.only(bottom: 8),
                          padding: const EdgeInsets.fromLTRB(13, 10, 13, 7),
                          decoration: BoxDecoration(
                            color: mine ? const Color(0xFFDDF8E8) : Colors.white,
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: AppColors.border),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Align(
                                alignment: Alignment.centerLeft,
                                child: Text('${message['message'] ?? ''}', style: const TextStyle(height: 1.35)),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${message['created_at_label'] ?? ''}${message['is_ai'] == true ? ' • AI' : ''}',
                                style: const TextStyle(color: AppColors.muted, fontSize: 10),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
          SafeArea(
            top: false,
            child: Container(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
              decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: AppColors.border))),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: controller,
                      minLines: 1,
                      maxLines: 4,
                      decoration: const InputDecoration(hintText: 'Сообщение клиенту…'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: sending ? null : _send,
                    style: IconButton.styleFrom(backgroundColor: AppColors.success),
                    icon: sending
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.send_rounded),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
