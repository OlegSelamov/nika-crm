import 'package:flutter/material.dart';

import '../services/nika_assistant_controller.dart';
import '../theme/app_theme.dart';

class NikaVoiceOverlay extends StatelessWidget {
  final Widget child;
  final NikaAssistantController controller;

  const NikaVoiceOverlay({
    super.key,
    required this.child,
    required this.controller,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        child,
        AnimatedBuilder(
          animation: controller,
          builder: (context, _) {
            if (!controller.enabled || controller.chatVisible) {
              return const SizedBox.shrink();
            }
            final bottom = MediaQuery.paddingOf(context).bottom + 82;
            return Positioned(
              right: 14,
              bottom: bottom,
              child: Listener(
                behavior: HitTestBehavior.opaque,
                onPointerDown: (_) {
                  if (!controller.showExpanded) controller.startPushToTalk();
                },
                onPointerUp: (_) {
                  if (controller.pushToTalkActive) {
                    controller.finishPushToTalk();
                  }
                },
                onPointerCancel: (_) => controller.cancelPushToTalk(),
                child: controller.showExpanded
                    ? _ExpandedVoicePanel(controller: controller)
                    : _CollapsedVoiceButton(controller: controller),
              ),
            );
          },
        ),
      ],
    );
  }
}

class _CollapsedVoiceButton extends StatelessWidget {
  final NikaAssistantController controller;

  const _CollapsedVoiceButton({required this.controller});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Удерживайте кнопку, говорите и отпустите для выполнения',
      child: Container(
        width: 58,
        height: 58,
        decoration: BoxDecoration(
          color: AppColors.navy,
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: 2),
          boxShadow: const [
            BoxShadow(
              color: Color(0x33071A30),
              blurRadius: 18,
              offset: Offset(0, 7),
            ),
          ],
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            const Icon(
              Icons.mic_rounded,
              color: Colors.white,
              size: 26,
            ),
            Positioned(
              right: 5,
              bottom: 5,
              child: Container(
                width: 11,
                height: 11,
                decoration: BoxDecoration(
                  color: controller.speechReady
                      ? AppColors.success
                      : AppColors.warning,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.navy, width: 2),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ExpandedVoicePanel extends StatelessWidget {
  final NikaAssistantController controller;

  const _ExpandedVoicePanel({required this.controller});

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.sizeOf(context).width;
    final width = screenWidth < 360 ? screenWidth - 28 : 332.0;
    final listening = controller.phase == NikaVoicePhase.commandListening;
    final thinking = controller.phase == NikaVoicePhase.thinking;
    final speaking = controller.phase == NikaVoicePhase.speaking;
    final failed = controller.phase == NikaVoicePhase.error;
    final title = controller.statusTitle;
    final detail = controller.statusDetail;
    final icon = failed
        ? Icons.mic_off_rounded
        : speaking
            ? Icons.graphic_eq_rounded
            : thinking
                ? Icons.auto_awesome_rounded
                : Icons.mic_rounded;

    return Material(
      color: Colors.transparent,
      child: Container(
        width: width,
        height: 82,
        padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
        decoration: BoxDecoration(
          color: AppColors.navy,
          borderRadius: BorderRadius.circular(20),
          boxShadow: const [
            BoxShadow(
              color: Color(0x40071A30),
              blurRadius: 20,
              offset: Offset(0, 7),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: (failed ? AppColors.warning : AppColors.primary)
                    .withOpacity(.24),
                border: Border.all(
                  color: failed ? AppColors.warning : AppColors.primary,
                  width: 1.5,
                ),
              ),
              child: Icon(icon, color: Colors.white, size: 22),
            ),
            const SizedBox(width: 10),
            Flexible(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      fontSize: 14,
                    ),
                  ),
                  if (detail.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      detail,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                        height: 1.25,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 2),
            if (failed)
              IconButton(
                onPressed: controller.retry,
                color: Colors.white,
                icon: const Icon(Icons.refresh_rounded),
              )
            else
              IconButton(
                onPressed: controller.openChat,
                color: Colors.white,
                icon: const Icon(Icons.chat_bubble_outline_rounded),
              ),
            IconButton(
              onPressed: listening
                  ? controller.cancelInteraction
                  : controller.stopSpeakingAndListen,
              color: Colors.white70,
              icon: Icon(listening ? Icons.close_rounded : Icons.mic_rounded),
            ),
          ],
        ),
      ),
    );
  }
}
