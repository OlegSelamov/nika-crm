import 'dart:async';

/// Result of a command handled by the live sales screen.
class SalesVoiceResult {
  final String reply;
  final bool openSales;
  final String? confirmationSummary;
  final bool clearConfirmation;

  const SalesVoiceResult({
    required this.reply,
    this.openSales = true,
    this.confirmationSummary,
    this.clearConfirmation = false,
  });

  bool get needsConfirmation => confirmationSummary != null;
}

typedef SalesVoiceHandler = Future<SalesVoiceResult?> Function(String command);

/// Connects the global Nika controller to the one real cart owned by
/// [SalesScreen]. It deliberately contains no cart state of its own.
class SalesVoiceBridge {
  SalesVoiceBridge._();

  static final SalesVoiceBridge instance = SalesVoiceBridge._();
  static const localPaymentConfirmationId = 'local_sales_payment';

  Object? _owner;
  SalesVoiceHandler? _handler;
  bool _salesVisible = false;

  bool get salesVisible => _salesVisible;

  void setSalesVisible(bool value) => _salesVisible = value;

  void attach(Object owner, SalesVoiceHandler handler) {
    _owner = owner;
    _handler = handler;
  }

  void detach(Object owner) {
    if (!identical(_owner, owner)) return;
    _owner = null;
    _handler = null;
  }

  Future<SalesVoiceResult?> handle(String command) async {
    final handler = _handler;
    if (handler == null) return null;
    return handler(command);
  }
}
