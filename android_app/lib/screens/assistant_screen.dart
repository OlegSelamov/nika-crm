import 'package:flutter/material.dart';

import '../services/nika_assistant_controller.dart';
import '../theme/app_theme.dart';

class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key});

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  final textController = TextEditingController();
  final scrollController = ScrollController();
  final nika = NikaAssistantController.instance;

  @override
  void initState() {
    super.initState();
    nika
      ..setChatVisible(true)
      ..addListener(_assistantChanged)
      ..ensureHistoryLoaded();
  }

  @override
  void dispose() {
    nika
      ..removeListener(_assistantChanged)
      ..setChatVisible(false);
    textController.dispose();
    scrollController.dispose();
    super.dispose();
  }

  void _assistantChanged() {
    if (!mounted) return;
    setState(() {});
    _scrollToEnd();
  }

  Future<void> _send() async {
    final text = textController.text.trim();
    if (text.isEmpty || nika.isSending) return;
    textController.clear();
    await nika.submitText(text);
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!scrollController.hasClients) return;
      scrollController.animateTo(
        scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final messages = nika.messages;
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            CircleAvatar(
              radius: 17,
              backgroundColor: AppColors.primarySoft,
              child: Icon(
                Icons.auto_awesome_rounded,
                color: AppColors.primary,
                size: 19,
              ),
            ),
            SizedBox(width: 10),
            Text('Nika AI'),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Голосовая команда',
            onPressed: nika.isCommandListening
                ? nika.cancelInteraction
                : nika.startDirectCommand,
            icon: Icon(
              nika.isCommandListening
                  ? Icons.stop_circle_outlined
                  : Icons.mic_none_rounded,
              color: nika.isCommandListening
                  ? AppColors.danger
                  : AppColors.primary,
            ),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Column(
        children: [
          _voiceStatus(),
          Expanded(
            child: messages.isEmpty
                ? _welcome()
                : ListView.builder(
                    controller: scrollController,
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
                    itemCount: messages.length,
                    itemBuilder: (_, index) => _bubble(messages[index]),
                  ),
          ),
          if (nika.confirmation != null) _confirmationCard(),
          _composer(),
        ],
      ),
    );
  }

  Widget _voiceStatus() {
    final listening = nika.isCommandListening;
    final thinking = nika.phase == NikaVoicePhase.thinking;
    final speaking = nika.phase == NikaVoicePhase.speaking;
    final failed = nika.phase == NikaVoicePhase.error;
    final active = listening || thinking || speaking || failed;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      width: double.infinity,
      color: active ? AppColors.navy : AppColors.primarySoft,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: active
                  ? Colors.white.withOpacity(.12)
                  : Colors.white.withOpacity(.8),
            ),
            child: Icon(
              listening
                  ? Icons.mic_rounded
                  : thinking
                      ? Icons.auto_awesome_rounded
                      : speaking
                          ? Icons.graphic_eq_rounded
                          : failed
                              ? Icons.mic_off_rounded
                              : Icons.hearing_rounded,
              color: active ? Colors.white : AppColors.primary,
            ),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  active ? nika.statusTitle : 'Голосовой режим активен',
                  style: TextStyle(
                    color: active ? Colors.white : AppColors.text,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  active && nika.statusDetail.isNotEmpty
                      ? nika.statusDetail
                      : 'В этом окне нажмите микрофон или удерживайте плавающую кнопку на любой странице',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: active ? Colors.white70 : AppColors.muted,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          if (failed)
            IconButton(
              tooltip: 'Повторить',
              onPressed: nika.retry,
              color: Colors.white,
              icon: const Icon(Icons.refresh_rounded),
            ),
        ],
      ),
    );
  }

  Widget _welcome() {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 28),
        const Icon(
          Icons.auto_awesome_rounded,
          size: 54,
          color: AppColors.primary,
        ),
        const SizedBox(height: 16),
        const Text(
          'Чем помочь бизнесу?',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 8),
        const Text(
          'Можно написать или нажать на микрофон. Nika ответит голосом и сможет открыть нужный раздел.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.muted, height: 1.45),
        ),
        const SizedBox(height: 24),
        for (final prompt in const [
          'Какая выручка сегодня?',
          'Какие товары заканчиваются?',
          'Открой движение товара',
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 9),
            child: OutlinedButton(
              onPressed: nika.isSending ? null : () => nika.submitText(prompt),
              child: Text(prompt),
            ),
          ),
      ],
    );
  }

  Widget _bubble(Map<String, dynamic> item) {
    final mine = item['role'] == 'user';
    final isError = item['error'] == true;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 360),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
        decoration: BoxDecoration(
          color: mine
              ? AppColors.primary
              : isError
                  ? const Color(0xFFFFE8E9)
                  : Colors.white,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(18),
            topRight: const Radius.circular(18),
            bottomLeft: Radius.circular(mine ? 18 : 5),
            bottomRight: Radius.circular(mine ? 5 : 18),
          ),
          border: mine ? null : Border.all(color: AppColors.border),
        ),
        child: Text(
          '${item['content'] ?? ''}',
          style: TextStyle(
            color: mine ? Colors.white : AppColors.text,
            height: 1.4,
          ),
        ),
      ),
    );
  }

  Widget _confirmationCard() {
    final confirmation = nika.confirmation;
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF7E2),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFF9D97B)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Нужно подтверждение',
            style: TextStyle(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 5),
          Text('${confirmation?['summary'] ?? 'Выполнить действие?'}'),
          const SizedBox(height: 5),
          const Text(
            'Можно также сказать «подтверждаю» или «отмена».',
            style: TextStyle(color: AppColors.muted, fontSize: 12),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: nika.isSending ? null : () => nika.decide('cancel'),
                  child: const Text('Отмена'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: nika.isSending ? null : () => nika.decide('confirm'),
                  child: const Text('Подтвердить'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _composer() {
    final listening = nika.isCommandListening;
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 9, 12, 10),
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            IconButton.filledTonal(
              tooltip: listening ? 'Остановить' : 'Говорить',
              onPressed: listening
                  ? nika.cancelInteraction
                  : nika.phase == NikaVoicePhase.speaking
                      ? nika.stopSpeakingAndListen
                      : nika.startDirectCommand,
              style: IconButton.styleFrom(
                foregroundColor:
                    listening ? AppColors.danger : AppColors.primary,
              ),
              icon: Icon(
                listening ? Icons.stop_rounded : Icons.mic_rounded,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: textController,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(
                  hintText: listening
                      ? (nika.liveText.isEmpty
                          ? 'Nika слушает…'
                          : nika.liveText)
                      : 'Напишите Nika AI…',
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: nika.isSending ? null : _send,
              icon: nika.isSending
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.arrow_upward_rounded),
            ),
          ],
        ),
      ),
    );
  }
}
