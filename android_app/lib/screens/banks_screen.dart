import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/mobile_p12_signer.dart';
import '../services/supplier_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class BanksScreen extends StatefulWidget {
  const BanksScreen({super.key});

  @override
  State<BanksScreen> createState() => _BanksScreenState();
}

class _BanksScreenState extends State<BanksScreen> {
  bool loading = true;
  bool refreshingPayments = false;
  String? error;
  List<Map<String, dynamic>> accounts = [];
  List<Map<String, dynamic>> payments = [];
  Map<String, dynamic>? selectedAccount;
  Map<String, dynamic> bank = const {};
  Map<String, dynamic> company = const {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  String _text(dynamic value) => value == null ? '' : '$value';

  dynamic _first(Map<String, dynamic> source, List<String> keys) {
    for (final key in keys) {
      final value = source[key];
      if (value != null && '$value'.trim().isNotEmpty) return value;
    }
    return null;
  }

  double _amount(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse('$value'.replaceAll(' ', '').replaceAll(',', '.')) ?? 0;
  }

  String _money(dynamic value) {
    final number = _amount(value);
    final raw = number.toStringAsFixed(2);
    final parts = raw.split('.');
    final chars = parts.first.split('').reversed.toList();
    final out = <String>[];
    for (var i = 0; i < chars.length; i++) {
      if (i > 0 && i % 3 == 0) out.add(' ');
      out.add(chars[i]);
    }
    return '${out.reversed.join()}.${parts.last}';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) return Map<String, dynamic>.from(value);
    return <String, dynamic>{};
  }

  List<Map<String, dynamic>> _normalizeAccounts(dynamic value) {
    if (value is List) {
      return value.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    }
    if (value is Map) {
      final map = Map<String, dynamic>.from(value);
      final nested = map['accounts'] ?? map['items'] ?? map['data'];
      if (nested is List) {
        return nested.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
      }
      if (map['iban'] != null) return [map];
    }
    return [];
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        loading = true;
        error = null;
      });
    }
    try {
      final results = await Future.wait([
        ApiService.bankAccounts(),
        ApiService.bankPayments(),
      ]);
      final accountResult = results[0];
      final paymentResult = results[1];
      final nextAccounts = _normalizeAccounts(accountResult['accounts']);
      final nextPayments = List<dynamic>.from(paymentResult['payments'] ?? const [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      if (!mounted) return;
      setState(() {
        accounts = nextAccounts;
        payments = nextPayments;
        selectedAccount = nextAccounts.isNotEmpty ? nextAccounts.first : null;
        bank = _asMap(accountResult['bank']);
        company = _asMap(accountResult['company']);
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        loading = false;
        error = e.toString();
      });
    }
  }

  String get _selectedIban =>
      _text(_first(selectedAccount ?? const {}, const ['iban', 'account', 'accountNumber', 'number']))
          .replaceAll(' ', '')
          .toUpperCase();

  String _accountBalance(Map<String, dynamic> account) {
    final raw = _first(account, const ['balance', 'availableBalance', 'currentBalance', 'amount']);
    if (raw is Map) {
      final map = Map<String, dynamic>.from(raw);
      final amount = _first(map, const ['amount', 'value', 'balance']);
      final currency = _text(_first(map, const ['currency', 'currencyCode']));
      return '${_money(amount)} ${currency.isEmpty ? 'KZT' : currency}';
    }
    final currency = _text(_first(account, const ['currency', 'currencyCode']));
    return '${_money(raw)} ${currency.isEmpty ? 'KZT' : currency}';
  }

  Future<void> _refreshPayments() async {
    if (refreshingPayments) return;
    setState(() => refreshingPayments = true);
    try {
      final result = await ApiService.bankPayments(refresh: true);
      final next = List<dynamic>.from(result['payments'] ?? const [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      if (!mounted) return;
      setState(() => payments = next);
      final warning = _text(result['refresh_warning']);
      if (warning.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Статусы загружены частично: $warning')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
      }
    } finally {
      if (mounted) setState(() => refreshingPayments = false);
    }
  }

  void _showRequisites() {
    if (_selectedIban.isEmpty) return;
    final name = _text(company['name']);
    final bin = _text(company['bin']);
    final kbe = _text(company['kbe']);
    final address = _text(company['address']);
    final bankName = _text(bank['name']).isEmpty ? 'Alatau City Bank' : _text(bank['name']);
    final bic = _text(bank['bic']).isEmpty ? 'TSESKZKA' : _text(bank['bic']);

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 26),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Реквизиты счёта', style: TextStyle(fontSize: 21, fontWeight: FontWeight.w900)),
              const SizedBox(height: 16),
              _req('Компания', name),
              _req('БИН', bin),
              _req('Адрес', address),
              _req('Банк', bankName),
              _req('БИК', bic),
              _req('КБЕ', kbe),
              _req('IBAN', _selectedIban),
            ],
          ),
        ),
      ),
    );
  }

  Widget _req(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 95, child: Text(label, style: const TextStyle(color: AppColors.muted))),
            Expanded(child: Text(value.isEmpty ? '—' : value, style: const TextStyle(fontWeight: FontWeight.w800))),
          ],
        ),
      );

  Future<void> _newPayment() async {
    if (_selectedIban.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала выберите банковский счёт')),
      );
      return;
    }

    final changed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _BankPaymentSheet(
        payerIban: _selectedIban,
      ),
    );
    if (changed == true) await _refreshPayments();
  }

  String _paymentStatus(Map<String, dynamic> item) {
    final raw = _text(item['statusCode']).toUpperCase();
    const ok = {'EXECUTED', 'COMPLETED', 'SUCCESS', 'ACCEPTED'};
    const bad = {'REJECTED', 'FAILED', 'ERROR', 'CANCELLED', 'CANCELED'};
    if (ok.contains(raw)) return 'Исполнен';
    if (bad.contains(raw)) return 'Ошибка';
    if (raw == 'SENT') return 'Отправлен';
    if (raw == 'READY_TO_SEND' || raw == 'CREATED') return 'Подготовлен';
    if (raw.isEmpty) return '—';
    return 'В обработке';
  }

  Color _paymentStatusColor(Map<String, dynamic> item) {
    final label = _paymentStatus(item);
    if (label == 'Исполнен') return AppColors.success;
    if (label == 'Ошибка') return AppColors.danger;
    if (label == 'Отправлен') return AppColors.primary;
    return AppColors.warning;
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.account_balance_outlined, size: 52, color: AppColors.muted),
            const SizedBox(height: 12),
            Text(error!, textAlign: TextAlign.center),
            const SizedBox(height: 14),
            FilledButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text('Повторить')),
          ]),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 30),
        children: [
          Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Alatau City Bank', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
                const SizedBox(height: 3),
                Text(
                  _text(company['name']).isEmpty ? 'Мои банковские счета' : _text(company['name']),
                  style: const TextStyle(color: AppColors.muted),
                ),
              ]),
            ),
            IconButton(onPressed: _load, icon: const Icon(Icons.refresh_rounded)),
          ]),
          const SizedBox(height: 14),
          if (accounts.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(18),
                child: Text('Alatau не вернул доступных счетов.'),
              ),
            )
          else
            ...accounts.map((account) {
              final iban = _text(_first(account, const ['iban', 'account', 'accountNumber', 'number']));
              final selected = identical(account, selectedAccount);
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20),
                    side: BorderSide(
                      color: selected ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.outlineVariant,
                      width: selected ? 1.5 : 1,
                    ),
                  ),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20),
                    onTap: () => setState(() => selectedAccount = account),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(children: [
                        CircleAvatar(
                          backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                          child: const Icon(Icons.account_balance_wallet_outlined),
                        ),
                        const SizedBox(width: 12),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(iban, style: const TextStyle(fontWeight: FontWeight.w900)),
                          const SizedBox(height: 4),
                          Text(
                            _text(_first(account, const ['accountType', 'type', 'account_type'])).isEmpty
                                ? 'Расчётный счёт'
                                : _text(_first(account, const ['accountType', 'type', 'account_type'])),
                            style: const TextStyle(color: AppColors.muted, fontSize: 12),
                          ),
                        ])),
                        const SizedBox(width: 10),
                        Text(_accountBalance(account), style: const TextStyle(fontWeight: FontWeight.w900)),
                      ]),
                    ),
                  ),
                ),
              );
            }),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _selectedIban.isEmpty ? null : _showRequisites,
                icon: const Icon(Icons.description_outlined),
                label: const Text('Реквизиты'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: FilledButton.icon(
                onPressed: _selectedIban.isEmpty ? null : _newPayment,
                icon: const Icon(Icons.add_card_rounded),
                label: const Text('Новый платёж'),
              ),
            ),
          ]),
          const SizedBox(height: 24),
          Row(children: [
            const Expanded(child: Text('Платежи', style: TextStyle(fontSize: 19, fontWeight: FontWeight.w900))),
            IconButton(
              tooltip: 'Обновить статусы',
              onPressed: refreshingPayments ? null : _refreshPayments,
              icon: refreshingPayments
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.sync_rounded),
            ),
          ]),
          if (payments.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(18),
                child: Text('Платежей из Nika пока нет.', style: TextStyle(color: AppColors.muted)),
              ),
            )
          else
            ...payments.map((p) {
              final created = DateTime.tryParse(_text(p['createdAt']))?.toLocal();
              final date = created == null
                  ? ''
                  : '${created.day.toString().padLeft(2, '0')}.${created.month.toString().padLeft(2, '0')}.${created.year}';
              return Card(
                elevation: 0,
                child: Padding(
                  padding: const EdgeInsets.all(15),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(
                        _text(p['receiverName']).isEmpty ? 'Получатель не указан' : _text(p['receiverName']),
                        style: const TextStyle(fontWeight: FontWeight.w900),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '№ ${_text(p['documentNumber']).isEmpty ? '—' : _text(p['documentNumber'])}${date.isEmpty ? '' : ' · $date'}',
                        style: const TextStyle(color: AppColors.muted, fontSize: 12),
                      ),
                      if (_text(p['purpose']).isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(_text(p['purpose']), maxLines: 2, overflow: TextOverflow.ellipsis),
                      ],
                    ])),
                    const SizedBox(width: 12),
                    Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Text('${_money(p['amount'])} ${_text(p['currency']).isEmpty ? 'KZT' : _text(p['currency'])}', style: const TextStyle(fontWeight: FontWeight.w900)),
                      const SizedBox(height: 7),
                      StatusPill(_paymentStatus(p), color: _paymentStatusColor(p)),
                    ]),
                  ]),
                ),
              );
            }),
        ],
      ),
    );
  }
}

class _BankPaymentSheet extends StatefulWidget {
  final String payerIban;

  const _BankPaymentSheet({required this.payerIban});

  @override
  State<_BankPaymentSheet> createState() => _BankPaymentSheetState();
}

class _BankPaymentSheetState extends State<_BankPaymentSheet> {
  final receiverName = TextEditingController();
  final receiverIin = TextEditingController();
  final receiverIban = TextEditingController();
  final receiverBic = TextEditingController();
  final kbe = TextEditingController();
  final knp = TextEditingController();
  final amount = TextEditingController();
  final documentNumber = TextEditingController();
  final purpose = TextEditingController();
  bool loadingChoices = true;
  bool sending = false;
  String? formError;
  List<Map<String, dynamic>> suppliers = [];
  List<Map<String, dynamic>> templates = [];
  String selectedChoice = '';

  @override
  void initState() {
    super.initState();
    _loadChoices();
  }

  @override
  void dispose() {
    for (final controller in [
      receiverName,
      receiverIin,
      receiverIban,
      receiverBic,
      kbe,
      knp,
      amount,
      documentNumber,
      purpose,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadChoices() async {
    try {
      final results = await Future.wait([
        SupplierService.getSuppliers(),
        ApiService.bankPaymentTemplates(),
      ]);
      if (!mounted) return;
      setState(() {
        suppliers = results[0] as List<Map<String, dynamic>>;
        templates = results[1] as List<Map<String, dynamic>>;
        loadingChoices = false;
      });
    } catch (_) {
      if (mounted) setState(() => loadingChoices = false);
    }
  }

  void _applyChoice(String value) {
    setState(() => selectedChoice = value);
    if (value.startsWith('s:')) {
      final id = int.tryParse(value.substring(2));
      final item = suppliers.where((e) => int.tryParse('${e['id']}') == id).firstOrNull;
      if (item != null) {
        receiverName.text = '${item['name'] ?? ''}';
        receiverIin.text = '${item['bin_iin'] ?? ''}';
        receiverIban.text = '${item['iban'] ?? ''}';
        receiverBic.text = '${item['bic'] ?? ''}';
        kbe.text = '${item['kbe'] ?? ''}';
        knp.text = '${item['knp'] ?? ''}';
        purpose.text = '${item['payment_purpose'] ?? ''}';
      }
      return;
    }
    if (value.startsWith('t:')) {
      final id = int.tryParse(value.substring(2));
      final item = templates.where((e) => int.tryParse('${e['id']}') == id).firstOrNull;
      if (item != null) {
        receiverName.text = '${item['name'] ?? ''}';
        receiverIin.text = '${item['iinBin'] ?? ''}';
        receiverIban.text = '${item['iban'] ?? ''}';
        receiverBic.text = '${item['bic'] ?? ''}';
        kbe.text = '${item['kbe'] ?? ''}';
        knp.text = '${item['knp'] ?? ''}';
        purpose.text = '${item['purpose'] ?? ''}';
      }
    }
  }

  Map<String, dynamic> _paymentData() => {
        'accountIban': widget.payerIban,
        'receiverName': receiverName.text.trim(),
        'receiverIinBin': receiverIin.text.replaceAll(RegExp(r'\D'), ''),
        'receiverIban': receiverIban.text.replaceAll(' ', '').toUpperCase(),
        'receiverBic': receiverBic.text.replaceAll(' ', '').toUpperCase(),
        'kbe': kbe.text.replaceAll(RegExp(r'\D'), ''),
        'knp': knp.text.replaceAll(RegExp(r'\D'), ''),
        'amount': double.tryParse(amount.text.replaceAll(' ', '').replaceAll(',', '.')) ?? 0,
        'documentNumber': documentNumber.text.trim(),
        'purpose': purpose.text.trim(),
      };

  Future<void> _send() async {
    if (sending) return;

    setState(() {
      sending = true;
      formError = null;
    });

    try {
      final capabilities = await MobileP12Signer.capabilities();
      if (capabilities['readyForAlatau'] != true) {
        throw const ApiException(
          'В этой сборке Nika Business нет KalkanCrypt НУЦ РК. '
          'Установите сборку с официальным Kalkan SDK.',
        );
      }

      final payment = _paymentData();
      final prepared = await ApiService.prepareBankPayment(payment);
      final payload = prepared['payload'];
      if (payload is! Map) {
        throw const ApiException('Сервер не вернул данные платежа для подписи');
      }

      if (!mounted) return;
      final signed = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _P12SigningDialog(
          payload: jsonEncode(payload),
          receiverName: receiverName.text.trim(),
          amount: amount.text.trim(),
        ),
      );
      if (signed == null) return;

      final content = '${signed['content'] ?? ''}';
      if (content.isEmpty) {
        throw const ApiException('Не удалось получить JWS-подпись');
      }

      final result = await ApiService.sendSignedBankPayment(
        content: content,
        payment: payment,
      );
      if (!mounted) return;
      Navigator.pop(context, true);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '${result['message'] ?? 'Платёж передан в Alatau City Bank'}',
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => formError = e.toString());
      }
    } finally {
      if (mounted) setState(() => sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * .94),
      decoration: BoxDecoration(
        color: Theme.of(context).scaffoldBackgroundColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
      ),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(18, 12, 18, 20 + bottom),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Center(child: Container(width: 42, height: 5, decoration: BoxDecoration(color: AppColors.border, borderRadius: BorderRadius.circular(8)))),
            const SizedBox(height: 16),
            const Text('Новый платёж', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
            const SizedBox(height: 4),
            Text('Счёт списания: ${widget.payerIban}', style: const TextStyle(color: AppColors.muted)),
            const SizedBox(height: 16),
            if (loadingChoices)
              const LinearProgressIndicator()
            else if (suppliers.isNotEmpty || templates.isNotEmpty)
              DropdownButtonFormField<String>(
                value: selectedChoice.isEmpty ? null : selectedChoice,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Поставщик / шаблон'),
                items: [
                  ...suppliers.map((s) => DropdownMenuItem(value: 's:${s['id']}', child: Text('Поставщик · ${s['name']}'))),
                  ...templates.map((t) => DropdownMenuItem(value: 't:${t['id']}', child: Text('Шаблон · ${t['name']}'))),
                ],
                onChanged: (value) {
                  if (value != null) _applyChoice(value);
                },
              ),
            const SizedBox(height: 10),
            TextField(controller: receiverName, decoration: const InputDecoration(labelText: 'Получатель')),
            const SizedBox(height: 10),
            TextField(controller: receiverIin, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'БИН / ИИН')),
            const SizedBox(height: 10),
            TextField(controller: receiverIban, textCapitalization: TextCapitalization.characters, decoration: const InputDecoration(labelText: 'IBAN получателя')),
            const SizedBox(height: 10),
            TextField(controller: receiverBic, textCapitalization: TextCapitalization.characters, decoration: const InputDecoration(labelText: 'БИК')),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: TextField(controller: kbe, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'КБЕ'))),
              const SizedBox(width: 10),
              Expanded(child: TextField(controller: knp, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'КНП'))),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: TextField(controller: amount, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Сумма'))),
              const SizedBox(width: 10),
              Expanded(child: TextField(controller: documentNumber, decoration: const InputDecoration(labelText: '№ документа'))),
            ]),
            const SizedBox(height: 10),
            TextField(controller: purpose, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Назначение платежа')),
            const SizedBox(height: 16),
            if (formError != null) ...[
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.danger.withOpacity(.10),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: AppColors.danger.withOpacity(.30)),
                ),
                child: Text(
                  formError!,
                  style: const TextStyle(
                    color: AppColors.danger,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(height: 12),
            ],
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: sending ? null : _send,
                icon: sending
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.verified_user_outlined),
                label: Text(sending ? 'Подготавливаем…' : 'Подписать'),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _P12SigningDialog extends StatefulWidget {
  final String payload;
  final String receiverName;
  final String amount;

  const _P12SigningDialog({
    required this.payload,
    required this.receiverName,
    required this.amount,
  });

  @override
  State<_P12SigningDialog> createState() => _P12SigningDialogState();
}

class _P12SigningDialogState extends State<_P12SigningDialog> {
  final password = TextEditingController();
  bool loading = true;
  bool signing = false;
  bool rememberPassword = false;
  bool rememberKey = false;
  bool hidePassword = true;
  bool hasSavedKey = false;
  bool hasSavedPassword = false;
  String savedKeyName = '';
  String? error;

  @override
  void initState() {
    super.initState();
    _loadSigningState();
  }

  Future<void> _loadSigningState() async {
    try {
      final info = await MobileP12Signer.savedKeyInfo();
      final savedPassword = await MobileP12Signer.loadSavedPassword();
      if (!mounted) return;
      setState(() {
        hasSavedKey = info['hasKey'] == true;
        hasSavedPassword = info['hasPassword'] == true;
        savedKeyName = '${info['name'] ?? ''}';
        if (savedPassword != null && savedPassword.isNotEmpty) {
          password.text = savedPassword;
          rememberPassword = true;
        }
        rememberKey = hasSavedKey;
      });
    } catch (_) {
      // Ручной режим подписи остаётся доступен.
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  void dispose() {
    password.clear();
    password.dispose();
    super.dispose();
  }

  Future<void> _signWithSavedKey() async {
    if (signing) return;
    setState(() {
      signing = true;
      error = null;
    });

    try {
      final signed = await MobileP12Signer.signAlatauWithSavedKey(
        payload: widget.payload,
      );
      if (!mounted) return;
      Navigator.pop(context, signed);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => signing = false);
    }
  }

  Future<void> _signWithSelectedKey() async {
    if (signing) return;
    if (password.text.isEmpty) {
      setState(() => error = 'Введите пароль ЭЦП');
      return;
    }

    setState(() {
      signing = true;
      error = null;
    });

    try {
      final signed = await MobileP12Signer.signAlatauJws(
        payload: widget.payload,
        password: password.text,
        saveKey: rememberKey,
      );

      if (rememberPassword) {
        await MobileP12Signer.savePassword(password.text);
      } else {
        await MobileP12Signer.clearSavedPassword();
      }

      if (!mounted) return;
      Navigator.pop(context, signed);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => signing = false);
    }
  }

  Future<void> _forgetSavedKey() async {
    try {
      await MobileP12Signer.clearSavedKey();
      if (!mounted) return;
      setState(() {
        hasSavedKey = false;
        hasSavedPassword = false;
        savedKeyName = '';
        rememberKey = false;
        rememberPassword = false;
        password.clear();
      });
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final receiver = widget.receiverName.isEmpty
        ? 'Получатель не указан'
        : widget.receiverName;
    final canUseBiometric = hasSavedKey && hasSavedPassword;

    return AlertDialog(
      title: const Row(
        children: [
          Icon(Icons.verified_user_outlined),
          SizedBox(width: 10),
          Expanded(child: Text('Подписание платежа')),
        ],
      ),
      content: SizedBox(
        width: 430,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(receiver, style: const TextStyle(fontWeight: FontWeight.w900)),
              if (widget.amount.isNotEmpty) ...[
                const SizedBox(height: 3),
                Text(
                  '${widget.amount} KZT',
                  style: const TextStyle(color: AppColors.muted),
                ),
              ],
              if (canUseBiometric) ...[
                const SizedBox(height: 16),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primaryContainer.withOpacity(.45),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.fingerprint_rounded, size: 28),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              savedKeyName.isEmpty ? 'Сохранённая ЭЦП' : savedKeyName,
                              style: const TextStyle(fontWeight: FontWeight.w900),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: signing ? null : _signWithSavedKey,
                          icon: const Icon(Icons.fingerprint_rounded),
                          label: const Text('Подписать по биометрии'),
                        ),
                      ),
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton(
                          onPressed: signing ? null : _forgetSavedKey,
                          child: const Text('Удалить сохранённый ключ'),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                const Row(
                  children: [
                    Expanded(child: Divider()),
                    Padding(
                      padding: EdgeInsets.symmetric(horizontal: 10),
                      child: Text('или другой ключ', style: TextStyle(color: AppColors.muted)),
                    ),
                    Expanded(child: Divider()),
                  ],
                ),
              ],
              const SizedBox(height: 14),
              TextField(
                controller: password,
                enabled: !loading && !signing,
                obscureText: hidePassword,
                enableSuggestions: false,
                autocorrect: false,
                decoration: InputDecoration(
                  labelText: 'Пароль ЭЦП',
                  prefixIcon: const Icon(Icons.key_rounded),
                  suffixIcon: IconButton(
                    onPressed: () => setState(() => hidePassword = !hidePassword),
                    icon: Icon(
                      hidePassword
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                    ),
                  ),
                ),
              ),
              CheckboxListTile(
                value: rememberPassword,
                onChanged: signing
                    ? null
                    : (value) => setState(() => rememberPassword = value ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(
                  'Сохранить пароль на этом телефоне',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              CheckboxListTile(
                value: rememberKey,
                onChanged: signing
                    ? null
                    : (value) => setState(() => rememberKey = value ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(
                  'Сохранить файл ключа на этом телефоне',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: const Text(
                  'Ключ хранится только внутри Nika Business и не отправляется на сервер.',
                ),
              ),
              if (rememberKey && !rememberPassword)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text(
                    'Для подписи по отпечатку или биометрии сохраните также пароль.',
                    style: TextStyle(color: AppColors.warning, fontSize: 12),
                  ),
                ),
              if (error != null) ...[
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.danger.withOpacity(.10),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    error!,
                    style: const TextStyle(
                      color: AppColors.danger,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 10),
              const Text(
                'При ручной подписи откроется выбор файла .p12.',
                style: TextStyle(color: AppColors.muted, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: signing ? null : () => Navigator.pop(context),
          child: const Text('Отмена'),
        ),
        FilledButton.icon(
          onPressed: loading || signing ? null : _signWithSelectedKey,
          icon: signing
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.folder_open_outlined),
          label: Text(signing ? 'Подписываем…' : 'Выбрать ключ и подписать'),
        ),
      ],
    );
  }
}

extension _FirstOrNullExtension<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
