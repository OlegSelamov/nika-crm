import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/mobile_p12_signer.dart';
import '../theme/app_theme.dart';

class EsfScreen extends StatefulWidget {
  final int saleId;
  const EsfScreen({super.key, required this.saleId});

  @override
  State<EsfScreen> createState() => _EsfScreenState();
}

class _EsfScreenState extends State<EsfScreen> {
  bool loading = true;
  bool busy = false;
  String? error;
  String? message;
  Map<String, dynamic> doc = {};
  Map<String, dynamic> payload = {};
  final fields = <String, TextEditingController>{};

  Map<String, dynamic> _map(dynamic v) =>
      v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};

  String _read(String path) {
    dynamic v = payload;
    for (final key in path.split('.')) {
      if (v is! Map) return '';
      v = v[key];
    }
    return v == null ? '' : '$v';
  }

  TextEditingController _c(String path) => fields.putIfAbsent(
        path,
        () => TextEditingController(text: _read(path)),
      );

  void _write(Map<String, dynamic> root, String path, dynamic value) {
    final keys = path.split('.');
    Map<String, dynamic> current = root;
    for (var i = 0; i < keys.length - 1; i++) {
      final old = current[keys[i]];
      current[keys[i]] =
          old is Map ? Map<String, dynamic>.from(old) : <String, dynamic>{};
      current = current[keys[i]] as Map<String, dynamic>;
    }
    current[keys.last] = value;
  }

  Map<String, dynamic> _collect() {
    final next = Map<String, dynamic>.from(payload);
    for (final section in const ['invoice', 'seller', 'customer', 'delivery']) {
      next[section] = _map(payload[section]);
    }
    for (final e in fields.entries) {
      _write(next, e.key, e.value.text.trim());
    }
    next['products'] = List<dynamic>.from(payload['products'] ?? const []);
    return next;
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final c in fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final data = await ApiService.getSaleEsf(widget.saleId);
      _apply(_map(data['document']));
    } catch (e) {
      error = e.toString();
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  void _apply(Map<String, dynamic> value) {
    doc = value;
    payload = _map(value['payload']);
    for (final e in fields.entries) {
      e.value.text = _read(e.key);
    }
  }

  Future<Map<String, dynamic>?> _save({bool quiet = false}) async {
    if (busy) return null;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final data = await ApiService.saveSaleEsfDraft(widget.saleId, _collect());
      _apply(_map(data['document']));
      if (!quiet) message = '${data['message'] ?? 'Черновик сохранён'}';
      return data;
    } catch (e) {
      error = e.toString();
      return null;
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _sign() async {
    final saved = await _save(quiet: true);
    if (saved == null || !mounted) return;
    final savedDoc = _map(saved['document']);
    final errors = List<dynamic>.from(savedDoc['validation_errors'] ?? const []);
    if (errors.isNotEmpty) {
      setState(() => error = errors.join('\n'));
      return;
    }
    final xml = '${saved['invoice_xml'] ?? ''}';
    final signed = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _EsfSignDialog(
        title: 'Подписание ЭСФ',
        payload: xml,
        xmlMode: false,
      ),
    );
    if (signed == null || !mounted) return;

    setState(() => busy = true);
    try {
      final result = await ApiService.saveSaleEsfSignature(
        widget.saleId,
        signature: '${signed['signature'] ?? ''}',
        certificate: '${signed['certificate'] ?? ''}',
        certificateSubject: '${signed['certificateSubject'] ?? ''}',
        payloadHash: '${savedDoc['payload_hash'] ?? ''}',
      );
      _apply(_map(result['document']));
      message = '${result['message'] ?? 'ЭСФ подписана'}';
    } catch (e) {
      error = e.toString();
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _send() async {
    final auth = await showDialog<Map<String, String>>(
      context: context,
      builder: (_) => const _EsfAuthDialog(),
    );
    if (auth == null || !mounted) return;

    setState(() {
      busy = true;
      error = null;
      message = 'Получаем тикет авторизации…';
    });
    try {
      final ticket = await ApiService.getSaleEsfAuthTicket(
        widget.saleId,
        iin: auth['iin']!,
      );
      final xml = '${ticket['auth_ticket_xml'] ?? ''}';
      if (!mounted) return;
      setState(() => busy = false);

      final signed = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _EsfSignDialog(
          title: 'Авторизация ИС ЭСФ',
          payload: xml,
          xmlMode: true,
        ),
      );
      if (signed == null || !mounted) return;

      setState(() {
        busy = true;
        message = 'Отправляем ЭСФ…';
      });
      final result = await ApiService.sendSaleEsf(
        widget.saleId,
        iin: auth['iin']!,
        password: auth['password']!,
        signedAuthTicket: '${signed['signedXml'] ?? ''}',
        profileType: auth['profile_type']!,
      );
      _apply(_map(result['document']));
      message = '${result['message'] ?? 'ЭСФ отправлена'}';
    } catch (e) {
      error = e.toString();
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Widget _field(String path, String label, {TextInputType? keyboard}) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TextField(
          controller: _c(path),
          keyboardType: keyboard,
          decoration: InputDecoration(labelText: label),
        ),
      );

  Widget _card(String title, List<Widget> children) => Card(
        elevation: 0,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style: const TextStyle(
                      fontSize: 17, fontWeight: FontWeight.w900)),
              const SizedBox(height: 12),
              ...children,
            ],
          ),
        ),
      );

  String _status() {
    switch ('${doc['status'] ?? ''}') {
      case 'prepared': return 'Готова к подписи';
      case 'signed': return 'Подписана';
      case 'sent': return 'Отправлена';
      case 'accepted': return 'Принята';
      case 'failed': return 'Ошибка';
      default: return 'Черновик';
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final products = List<dynamic>.from(payload['products'] ?? const []);

    return Scaffold(
      appBar: AppBar(
        title: Text('ЭСФ №${_read('invoice.num')}'),
        actions: [
          IconButton(onPressed: busy ? null : _load, icon: const Icon(Icons.refresh))
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 110),
        children: [
          Row(children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Электронный счёт-фактура',
                      style: TextStyle(fontSize: 21, fontWeight: FontWeight.w900)),
                  Text(
                    '${doc['api_environment']}' == 'production'
                        ? 'Боевая ИС ЭСФ'
                        : 'Тестовая ИС ЭСФ',
                    style: const TextStyle(color: AppColors.muted),
                  ),
                ],
              ),
            ),
            Chip(label: Text(_status())),
          ]),
          if (message != null) _notice(message!, AppColors.success),
          if (error != null) _notice(error!, AppColors.danger),
          _card('Документ', [
            _field('invoice.num', 'Номер', keyboard: TextInputType.number),
            Row(children: [
              Expanded(child: _field('invoice.date', 'Дата выписки')),
              const SizedBox(width: 8),
              Expanded(child: _field('invoice.turnover_date', 'Дата оборота')),
            ]),
            _field('invoice.operator_fullname', 'Руководитель / оператор'),
          ]),
          _card('Поставщик', [
            _field('seller.name', 'Наименование'),
            _field('seller.tin', 'БИН / ИИН', keyboard: TextInputType.number),
            _field('seller.address', 'Адрес'),
          ]),
          _card('Получатель', [
            _field('customer.name', 'Наименование'),
            _field('customer.tin', 'БИН / ИИН', keyboard: TextInputType.number),
            _field('customer.address', 'Адрес'),
          ]),
          _card('Расчёт', [
            _field('delivery.document_num', '№ документа'),
            _field('delivery.contract_num', '№ договора'),
            _field('delivery.contract_date', 'Дата договора'),
            DropdownButtonFormField<String>(
              value: {'CASH', 'NON_CASH'}.contains(_read('delivery.payment_form'))
                  ? _read('delivery.payment_form')
                  : 'NON_CASH',
              decoration: const InputDecoration(labelText: 'Способ расчёта'),
              items: const [
                DropdownMenuItem(value: 'CASH', child: Text('Наличный')),
                DropdownMenuItem(value: 'NON_CASH', child: Text('Безналичный')),
              ],
              onChanged: (v) {
                if (v != null) _c('delivery.payment_form').text = v;
              },
            ),
          ]),
          const SizedBox(height: 6),
          Text('Позиции: ${products.length}',
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900)),
          const SizedBox(height: 8),
          ...products.asMap().entries.map((e) {
            final item = _map(e.value);
            return Card(
              elevation: 0,
              child: ListTile(
                leading: CircleAvatar(child: Text('${e.key + 1}')),
                title: Text('${item['description'] ?? 'Товар'}'),
                subtitle: Text(
                  '${item['quantity'] ?? ''} × ${item['price_with_tax'] ?? ''} · '
                  'NTIN ${item['gtin_code'] ?? '—'}',
                ),
              ),
            );
          }),
          if (busy) const Padding(
            padding: EdgeInsets.only(top: 12),
            child: LinearProgressIndicator(),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(children: [
            Expanded(
              child: OutlinedButton(
                onPressed: busy ? null : () => _save(),
                child: const Text('Сохранить'),
              ),
            ),
            const SizedBox(width: 7),
            Expanded(
              child: FilledButton(
                onPressed: busy || doc['can_sign'] != true ? null : _sign,
                child: const Text('Подписать'),
              ),
            ),
            const SizedBox(width: 7),
            Expanded(
              child: FilledButton(
                onPressed: busy || doc['can_send'] != true ? null : _send,
                child: const Text('Отправить'),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _notice(String value, Color color) => Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: color.withOpacity(.10),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(value,
              style: TextStyle(color: color, fontWeight: FontWeight.w700)),
        ),
      );
}

class _EsfSignDialog extends StatefulWidget {
  final String title;
  final String payload;
  final bool xmlMode;
  const _EsfSignDialog({
    required this.title,
    required this.payload,
    required this.xmlMode,
  });

  @override
  State<_EsfSignDialog> createState() => _EsfSignDialogState();
}

class _EsfSignDialogState extends State<_EsfSignDialog> {
  final password = TextEditingController();
  bool loading = true;
  bool signing = false;
  bool savedReady = false;
  bool rememberPassword = false;
  String? error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final info = await MobileP12Signer.savedKeyInfo();
      final saved = await MobileP12Signer.loadSavedPassword();
      savedReady = info['hasKey'] == true && info['hasPassword'] == true;
      if (saved != null && saved.isNotEmpty) {
        password.text = saved;
        rememberPassword = true;
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _saved() async {
    setState(() {
      signing = true;
      error = null;
    });
    try {
      final result = widget.xmlMode
          ? await MobileP12Signer.signEsfXmlWithSavedKey(payload: widget.payload)
          : await MobileP12Signer.signEsfRawWithSavedKey(payload: widget.payload);
      if (mounted) Navigator.pop(context, result);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => signing = false);
    }
  }

  Future<void> _manual() async {
    if (password.text.isEmpty) {
      setState(() => error = 'Введите пароль ЭЦП');
      return;
    }
    setState(() {
      signing = true;
      error = null;
    });
    try {
      final result = widget.xmlMode
          ? await MobileP12Signer.signEsfXml(
              payload: widget.payload, password: password.text)
          : await MobileP12Signer.signEsfRaw(
              payload: widget.payload, password: password.text);
      if (rememberPassword) {
        await MobileP12Signer.savePassword(password.text);
      }
      if (mounted) Navigator.pop(context, result);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => signing = false);
    }
  }

  @override
  void dispose() {
    password.clear();
    password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            if (savedReady)
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: signing ? null : _saved,
                  icon: const Icon(Icons.fingerprint),
                  label: const Text('Подписать по биометрии'),
                ),
              ),
            const SizedBox(height: 12),
            TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Пароль ЭЦП'),
            ),
            CheckboxListTile(
              value: rememberPassword,
              contentPadding: EdgeInsets.zero,
              title: const Text('Сохранить пароль'),
              onChanged: signing
                  ? null
                  : (v) => setState(() => rememberPassword = v ?? false),
            ),
            if (error != null)
              Text(error!,
                  style: const TextStyle(
                      color: AppColors.danger, fontWeight: FontWeight.w700)),
            if (widget.xmlMode)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'Авторизационный XML подписывается локально через Kalkan XMLDSig.',
                  style: TextStyle(color: AppColors.muted, fontSize: 12),
                ),
              ),
          ]),
        ),
        actions: [
          TextButton(
              onPressed: signing ? null : () => Navigator.pop(context),
              child: const Text('Отмена')),
          FilledButton(
            onPressed: loading || signing ? null : _manual,
            child: Text(signing ? 'Подписываем…' : 'Выбрать .p12'),
          ),
        ],
      );
}

class _EsfAuthDialog extends StatefulWidget {
  const _EsfAuthDialog();
  @override
  State<_EsfAuthDialog> createState() => _EsfAuthDialogState();
}

class _EsfAuthDialogState extends State<_EsfAuthDialog> {
  final iin = TextEditingController();
  final password = TextEditingController();
  String profile = 'ADMIN_ENTERPRISE';

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Вход в ИС ЭСФ'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: iin,
            maxLength: 12,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'ИИН пользователя'),
          ),
          TextField(
            controller: password,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Пароль ИС ЭСФ'),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: profile,
            decoration: const InputDecoration(labelText: 'Профиль'),
            items: const [
              DropdownMenuItem(
                  value: 'ADMIN_ENTERPRISE',
                  child: Text('Администратор предприятия')),
              DropdownMenuItem(
                  value: 'ENTREPRENEUR', child: Text('Предприниматель')),
              DropdownMenuItem(value: 'USER', child: Text('Пользователь')),
            ],
            onChanged: (v) {
              if (v != null) setState(() => profile = v);
            },
          ),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена')),
          FilledButton(
            onPressed: () {
              final clean = iin.text.replaceAll(RegExp(r'\D'), '');
              if (clean.length != 12 || password.text.isEmpty) return;
              Navigator.pop(context, <String, String>{
                'iin': clean,
                'password': password.text,
                'profile_type': profile,
              });
            },
            child: const Text('Продолжить'),
          ),
        ],
      );

  @override
  void dispose() {
    iin.dispose();
    password.clear();
    password.dispose();
    super.dispose();
  }
}
