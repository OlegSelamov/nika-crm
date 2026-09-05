import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

import 'api_service.dart';
import 'sales_voice_bridge.dart';

enum NikaVoicePhase {
  dormant,
  wakeListening,
  commandListening,
  thinking,
  speaking,
  error,
}

/// One assistant instance for the whole application.
///
/// It lives above the Navigator, so the push-to-talk button stays available on
/// every page without keeping the microphone permanently active.
class NikaAssistantController extends ChangeNotifier
    with WidgetsBindingObserver {
  NikaAssistantController._() {
    _playerCompleteSubscription = _player.onPlayerComplete.listen((_) {
      if (_phase == NikaVoicePhase.speaking) {
        _returnToIdle();
      }
    });
  }

  static final NikaAssistantController instance = NikaAssistantController._();

  static const wakePhrases = <String>[
    'привет ника',
    'ника привет',
    'привет nika',
    'nika привет',
  ];

  final SpeechToText _speech = SpeechToText();
  final AudioPlayer _player = AudioPlayer();

  late final StreamSubscription<void> _playerCompleteSubscription;
  Timer? _restartTimer;
  Timer? _commandTimeoutTimer;
  NikaVoicePhase _phase = NikaVoicePhase.dormant;
  bool _enabled = false;
  bool _speechReady = false;
  bool _speechInitializing = false;
  bool _startingSpeech = false;
  bool _historyLoaded = false;
  bool _chatVisible = false;
  bool _observerAttached = false;
  bool _appInForeground = true;
  bool _pushToTalkActive = false;
  bool _finishingPushToTalk = false;
  bool _wakePrefixDetected = false;
  String? _localeId;
  String _liveText = '';
  String _lastReply = '';
  String? _error;
  dynamic _conversationId;
  Map<String, dynamic>? _confirmation;
  final List<Map<String, dynamic>> _messages = [];

  ValueChanged<String>? _navigationHandler;
  VoidCallback? _openChatHandler;

  NikaVoicePhase get phase => _phase;
  bool get enabled => _enabled;
  bool get speechReady => _speechReady;
  bool get chatVisible => _chatVisible;
  bool get pushToTalkActive => _pushToTalkActive;
  bool get isSending => _phase == NikaVoicePhase.thinking;
  bool get isListening =>
      _phase == NikaVoicePhase.wakeListening ||
      _phase == NikaVoicePhase.commandListening;
  bool get isCommandListening => _phase == NikaVoicePhase.commandListening;
  bool get showExpanded =>
      _phase == NikaVoicePhase.commandListening ||
      _phase == NikaVoicePhase.thinking ||
      _phase == NikaVoicePhase.speaking ||
      _phase == NikaVoicePhase.error;
  String get liveText => _liveText;
  String get lastReply => _lastReply;
  String? get error => _error;
  dynamic get conversationId => _conversationId;
  Map<String, dynamic>? get confirmation => _confirmation;
  List<Map<String, dynamic>> get messages => List.unmodifiable(_messages);

  String get statusTitle {
    switch (_phase) {
      case NikaVoicePhase.commandListening:
        return 'Слушаю вас…';
      case NikaVoicePhase.thinking:
        return 'Nika думает…';
      case NikaVoicePhase.speaking:
        return 'Nika отвечает';
      case NikaVoicePhase.error:
        return 'Нужна настройка';
      case NikaVoicePhase.wakeListening:
        return 'Nika готова';
      case NikaVoicePhase.dormant:
        return 'Удерживайте кнопку и говорите';
    }
  }

  String get statusDetail {
    if (_phase == NikaVoicePhase.error) {
      return _error ?? 'Не удалось включить микрофон';
    }
    if (_phase == NikaVoicePhase.speaking && _lastReply.isNotEmpty) {
      return _lastReply;
    }
    if (_liveText.isNotEmpty) return _liveText;
    if (_phase == NikaVoicePhase.commandListening) {
      return 'Говорите команду или задайте вопрос';
    }
    return '';
  }

  void setHandlers({
    ValueChanged<String>? onNavigate,
    VoidCallback? onOpenChat,
  }) {
    _navigationHandler = onNavigate;
    _openChatHandler = onOpenChat;
  }

  void clearHandlers() {
    _navigationHandler = null;
    _openChatHandler = null;
  }

  void openChat() => _openChatHandler?.call();

  void setChatVisible(bool value) {
    if (_chatVisible == value) return;
    _chatVisible = value;
    notifyListeners();
  }

  Future<void> activate() async {
    if (_enabled) return;
    _enabled = true;
    _error = null;
    if (!_observerAttached) {
      WidgetsBinding.instance.addObserver(this);
      _observerAttached = true;
    }
    notifyListeners();
    ensureHistoryLoaded();
    await _initializeSpeech();
  }

  Future<void> deactivate() async {
    _enabled = false;
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    await _speech.cancel();
    await _player.stop();
    _phase = NikaVoicePhase.dormant;
    _liveText = '';
    _lastReply = '';
    _conversationId = null;
    _confirmation = null;
    _messages.clear();
    _historyLoaded = false;
    notifyListeners();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _appInForeground = state == AppLifecycleState.resumed;
    if (!_appInForeground) {
      _restartTimer?.cancel();
      _commandTimeoutTimer?.cancel();
      _speech.cancel();
      _player.stop();
      if (_enabled) {
        _phase = NikaVoicePhase.dormant;
        notifyListeners();
      }
      return;
    }
    if (_enabled) _returnToIdle();
  }

  Future<void> ensureHistoryLoaded() async {
    if (_historyLoaded) return;
    _historyLoaded = true;
    try {
      final result = await ApiService.aiHistory();
      _conversationId = result['conversation_id'];
      _messages
        ..clear()
        ..addAll(
          List<dynamic>.from(result['items'] ?? const [])
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item)),
        );
      _confirmation = result['confirmation'] is Map
          ? Map<String, dynamic>.from(result['confirmation'] as Map)
          : null;
      notifyListeners();
    } catch (_) {
      // Voice commands remain usable even if old history cannot be loaded.
    }
  }

  Future<void> _initializeSpeech() async {
    if (!_enabled || _speechReady || _speechInitializing) {
      if (_speechReady) _returnToIdle();
      return;
    }
    _speechInitializing = true;
    try {
      _speechReady = await _speech.initialize(
        onStatus: _onSpeechStatus,
        onError: _onSpeechError,
        debugLogging: false,
        options: [SpeechToText.androidNoBluetooth],
      );
      if (!_speechReady) {
        _setError('Разрешите приложению доступ к микрофону и распознаванию речи');
        return;
      }
      final locales = await _speech.locales();
      for (final locale in locales) {
        if (locale.localeId.toLowerCase().startsWith('ru')) {
          _localeId = locale.localeId;
          break;
        }
      }
      await _returnToIdle();
    } catch (_) {
      _setError('Не удалось запустить распознавание речи на этом устройстве');
    } finally {
      _speechInitializing = false;
    }
  }

  void _onSpeechStatus(String status) {
    if (!_enabled || !_appInForeground || _startingSpeech) return;
    if (status != 'done' && status != 'notListening') return;

    if (_phase == NikaVoicePhase.commandListening) {
      if (_pushToTalkActive || _finishingPushToTalk) {
        if (_pushToTalkActive && !_finishingPushToTalk) {
          _scheduleRestart(commandMode: true);
        }
        return;
      }
      final command = _stripWakePhrase(_liveText).trim();
      if (command.isNotEmpty) {
        submitText(command);
      } else {
        _scheduleRestart(commandMode: true);
      }
      return;
    }
    if (_phase == NikaVoicePhase.wakeListening) {
      _scheduleRestart(commandMode: false);
    }
  }

  void _onSpeechError(SpeechRecognitionError speechError) {
    if (!_enabled) return;
    final message = speechError.errorMsg.toLowerCase();
    final recoverable = !speechError.permanent ||
        message.contains('no_match') ||
        message.contains('speech_timeout') ||
        message.contains('error_busy');

    if (!recoverable) {
      if (message.contains('permission')) {
        _setError('Нет доступа к микрофону. Разрешите его в настройках приложения');
      } else if (message.contains('recognizer_not_available')) {
        _setError('На телефоне недоступна служба распознавания речи');
      } else {
        _setError('Ошибка микрофона: ${speechError.errorMsg}');
      }
      return;
    }
    if (_pushToTalkActive || _finishingPushToTalk) {
      if (_pushToTalkActive && !_finishingPushToTalk) {
        _scheduleRestart(commandMode: true);
      }
      return;
    }
    if (_phase == NikaVoicePhase.commandListening &&
        _stripWakePhrase(_liveText).trim().isNotEmpty) {
      submitText(_stripWakePhrase(_liveText).trim());
    } else {
      _scheduleRestart(
        commandMode: _phase == NikaVoicePhase.commandListening,
      );
    }
  }

  void _onSpeechResult(SpeechRecognitionResult result) {
    if (!_enabled) return;
    final recognized = result.recognizedWords.trim();
    if (recognized.isEmpty) return;

    if (_phase == NikaVoicePhase.wakeListening) {
      final afterWake = _textAfterWakePhrase(recognized);
      if (afterWake == null) return;
      _wakePrefixDetected = true;
      _phase = NikaVoicePhase.commandListening;
      _liveText = afterWake;
      _error = null;
      _startCommandTimeout();
      notifyListeners();
      if (result.finalResult && afterWake.isNotEmpty) {
        submitText(afterWake);
      }
      return;
    }

    if (_phase != NikaVoicePhase.commandListening) return;
    _liveText = _wakePrefixDetected
        ? _stripWakePhrase(recognized)
        : recognized;
    notifyListeners();
    if (!_pushToTalkActive &&
        !_finishingPushToTalk &&
        result.finalResult &&
        _liveText.trim().isNotEmpty) {
      submitText(_liveText.trim());
    }
  }

  Future<void> _listenForWakePhrase() async {
    if (!_canListen) return;
    _wakePrefixDetected = false;
    _liveText = '';
    _error = null;
    _phase = NikaVoicePhase.wakeListening;
    notifyListeners();
    await _startSpeech(commandMode: false);
  }

  Future<void> startDirectCommand() async {
    if (!_enabled) await activate();
    if (!_speechReady) {
      await _initializeSpeech();
      if (!_speechReady) return;
    }
    _restartTimer?.cancel();
    await _player.stop();
    _wakePrefixDetected = false;
    _liveText = '';
    _error = null;
    _phase = NikaVoicePhase.commandListening;
    _startCommandTimeout();
    notifyListeners();
    await _startSpeech(commandMode: true);
  }

  Future<void> startPushToTalk() async {
    if (_pushToTalkActive || _finishingPushToTalk || isSending) return;
    _pushToTalkActive = true;
    _finishingPushToTalk = false;
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();

    if (!_enabled) await activate();
    if (!_speechReady) {
      await _initializeSpeech();
      if (!_speechReady) {
        _pushToTalkActive = false;
        return;
      }
    }

    _pushToTalkActive = true;
    _finishingPushToTalk = false;
    await _player.stop();
    _wakePrefixDetected = false;
    _liveText = '';
    _error = null;
    _phase = NikaVoicePhase.commandListening;
    notifyListeners();
    await _startSpeech(commandMode: true);
  }

  Future<void> finishPushToTalk() async {
    if (!_pushToTalkActive || _finishingPushToTalk) return;
    _finishingPushToTalk = true;
    _restartTimer?.cancel();
    await _speech.stop();
    await Future<void>.delayed(const Duration(milliseconds: 220));

    final command = _liveText.trim();
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    if (command.isEmpty) {
      await _returnToIdle();
      return;
    }
    await submitText(command);
  }

  Future<void> cancelPushToTalk() async {
    if (!_pushToTalkActive && !_finishingPushToTalk) return;
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    _restartTimer?.cancel();
    await _speech.cancel();
    await _returnToIdle();
  }

  Future<void> _startSpeech({required bool commandMode}) async {
    if (!_canListen || _startingSpeech) return;
    _startingSpeech = true;
    final expectedPhase = commandMode
        ? NikaVoicePhase.commandListening
        : NikaVoicePhase.wakeListening;
    try {
      await _speech.cancel();
      await Future<void>.delayed(const Duration(milliseconds: 180));
      if (!_canListen || _phase != expectedPhase) return;
      await _speech.listen(
        onResult: _onSpeechResult,
        localeId: _localeId,
        listenFor: Duration(seconds: commandMode ? 18 : 45),
        pauseFor: Duration(seconds: commandMode ? 3 : 5),
        listenOptions: SpeechListenOptions(
          partialResults: true,
          cancelOnError: false,
          listenMode: ListenMode.dictation,
        ),
      );
    } catch (_) {
      _scheduleRestart(commandMode: commandMode);
    } finally {
      _startingSpeech = false;
    }
  }

  bool get _canListen =>
      _enabled && _speechReady && _appInForeground &&
      _phase != NikaVoicePhase.thinking &&
      _phase != NikaVoicePhase.speaking;

  void _scheduleRestart({required bool commandMode}) {
    if (!_enabled || !_appInForeground) return;
    _restartTimer?.cancel();
    _restartTimer = Timer(const Duration(milliseconds: 420), () {
      if (!_enabled || !_appInForeground || _speech.isListening) return;
      if (commandMode && _phase == NikaVoicePhase.commandListening) {
        _startSpeech(commandMode: true);
      } else if (!commandMode && _phase == NikaVoicePhase.wakeListening) {
        _startSpeech(commandMode: false);
      }
    });
  }

  Future<void> submitText(String text) async {
    final message = _stripWakePhrase(text).trim();
    if (message.isEmpty || _phase == NikaVoicePhase.thinking) return;
    final localDecision = _localPaymentDecision(message);
    if (_confirmation?['id'] == SalesVoiceBridge.localPaymentConfirmationId &&
        localDecision != null) {
      _messages.add({'role': 'user', 'content': message});
      notifyListeners();
      await decide(localDecision);
      return;
    }
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    _phase = NikaVoicePhase.thinking;
    _liveText = message;
    _error = null;
    _messages.add({'role': 'user', 'content': message});
    notifyListeners();
    await _speech.stop();
    await _player.stop();

    try {
      final salesResult = await SalesVoiceBridge.instance.handle(message);
      if (salesResult != null) {
        await _applySalesResult(salesResult);
        return;
      }

      final result = await ApiService.aiChat(
        message,
        conversationId: _conversationId,
      );
      _conversationId = result['conversation_id'] ?? _conversationId;
      final reply = '${result['reply'] ?? result['message'] ?? 'Готово'}'.trim();
      _lastReply = reply;
      _messages.add({'role': 'assistant', 'content': reply});
      _confirmation = result['confirmation'] is Map
          ? Map<String, dynamic>.from(result['confirmation'] as Map)
          : null;
      if (result['action_status'] != null) _confirmation = null;
      notifyListeners();
      _handleNavigation(result);
      await _speak(reply);
    } catch (exception) {
      final message = exception is ApiException
          ? exception.message
          : 'Nika временно недоступна. Попробуйте ещё раз';
      _lastReply = message;
      _messages.add({'role': 'assistant', 'content': message, 'error': true});
      _error = message;
      _phase = NikaVoicePhase.error;
      notifyListeners();
    }
  }

  Future<void> decide(String decision) async {
    final id = _confirmation?['id']?.toString();
    if (id == null || _phase == NikaVoicePhase.thinking) return;
    _restartTimer?.cancel();
    _phase = NikaVoicePhase.thinking;
    _liveText = decision == 'confirm' ? 'Подтверждаю' : 'Отменяю';
    notifyListeners();
    await _speech.stop();
    await _player.stop();
    try {
      if (id == SalesVoiceBridge.localPaymentConfirmationId) {
        final result = await SalesVoiceBridge.instance.handle(
          decision == 'confirm' ? 'подтверждаю оплату' : 'отменить оплату',
        );
        if (result == null) {
          _confirmation = null;
          await _speak('Подтверждение уже не актуально. Повторите команду оплаты.');
          return;
        }
        await _applySalesResult(result);
        return;
      }

      final result = await ApiService.aiAction(id, decision);
      final reply = '${result['reply'] ?? result['message'] ?? 'Готово'}';
      _lastReply = reply;
      _messages.add({'role': 'assistant', 'content': reply});
      _confirmation = null;
      notifyListeners();
      await _speak(reply);
    } catch (exception) {
      _setError(exception is ApiException
          ? exception.message
          : 'Не удалось выполнить действие');
    }
  }

  Future<void> _applySalesResult(SalesVoiceResult result) async {
    final reply = result.reply.trim().isEmpty ? 'Готово' : result.reply.trim();
    _lastReply = reply;
    _messages.add({'role': 'assistant', 'content': reply});
    if (result.needsConfirmation) {
      _confirmation = {
        'id': SalesVoiceBridge.localPaymentConfirmationId,
        'summary': result.confirmationSummary,
      };
    } else if (result.clearConfirmation) {
      _confirmation = null;
    }
    if (result.openSales) _navigationHandler?.call('/sales');
    notifyListeners();
    await _speak(reply);
  }

  Future<void> _speak(String text) async {
    if (!_enabled || text.trim().isEmpty) {
      await _returnToIdle();
      return;
    }
    _phase = NikaVoicePhase.speaking;
    _liveText = '';
    notifyListeners();
    try {
      final bytes = await ApiService.aiVoice(text);
      if (!_enabled || _phase != NikaVoicePhase.speaking) return;
      await _player.play(BytesSource(bytes, mimeType: 'audio/mpeg'));
    } catch (_) {
      // The textual answer stays visible even when voice generation is down.
      await _returnToIdle();
    }
  }

  void _handleNavigation(Map<String, dynamic> result) {
    final action = '${result['action'] ?? ''}';
    if (action == 'redirect' && result['url'] != null) {
      _navigationHandler?.call('${result['url']}');
    } else if (action == 'open_drawer' && result['target'] != null) {
      _navigationHandler?.call('${result['target']}');
    }
  }

  Future<void> stopSpeakingAndListen() async {
    await _player.stop();
    await startDirectCommand();
  }

  Future<void> cancelInteraction() async {
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    await _speech.cancel();
    await _player.stop();
    await _returnToIdle();
  }

  Future<void> retry() async {
    _error = null;
    _speechReady = false;
    _phase = NikaVoicePhase.dormant;
    notifyListeners();
    await _initializeSpeech();
  }

  Future<void> _returnToIdle() async {
    if (!_enabled || !_appInForeground) return;
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    await _speech.cancel();
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    _liveText = '';
    _error = null;
    _phase = NikaVoicePhase.dormant;
    notifyListeners();
  }

  void _setError(String message) {
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    _pushToTalkActive = false;
    _finishingPushToTalk = false;
    _error = message;
    _phase = NikaVoicePhase.error;
    notifyListeners();
  }

  String _normalize(String text) => text
      .toLowerCase()
      .replaceAll('ё', 'е')
      .replaceAll(RegExp(r'[^a-zа-я0-9\s]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  String? _localPaymentDecision(String text) {
    final normalized = _normalize(text);
    if (normalized == 'нет' ||
        normalized.contains('отмена') ||
        normalized.contains('отмени') ||
        normalized.contains('не оплачивай') ||
        normalized.contains('не пробивай')) {
      return 'cancel';
    }
    if (normalized == 'да' ||
        normalized.contains('подтвержда') ||
        normalized.contains('оплачивай') ||
        normalized.contains('пробивай')) {
      return 'confirm';
    }
    return null;
  }

  String? _textAfterWakePhrase(String text) {
    final normalized = _normalize(text);
    for (final phrase in wakePhrases) {
      final index = normalized.indexOf(phrase);
      if (index >= 0) {
        return normalized.substring(index + phrase.length).trim();
      }
    }
    return null;
  }

  String _stripWakePhrase(String text) =>
      _textAfterWakePhrase(text) ?? text.trim();

  void _startCommandTimeout() {
    _commandTimeoutTimer?.cancel();
    _commandTimeoutTimer = Timer(const Duration(seconds: 28), () {
      if (_phase == NikaVoicePhase.commandListening) cancelInteraction();
    });
  }

  @override
  void dispose() {
    _restartTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    if (_observerAttached) WidgetsBinding.instance.removeObserver(this);
    _playerCompleteSubscription.cancel();
    _player.dispose();
    super.dispose();
  }
}
