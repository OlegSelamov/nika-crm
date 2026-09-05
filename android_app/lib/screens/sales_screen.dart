import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/kaspi_pos_service.dart';
import '../services/sales_voice_bridge.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'check_screen.dart';
import 'scanner_screen.dart';

class SalesScreen extends StatefulWidget {
  const SalesScreen({super.key});

  @override
  State<SalesScreen> createState() => _SalesScreenState();
}

class _SalesScreenState extends State<SalesScreen> {
  static const Map<String, dynamic> anonymousClient = {
    'id': null,
    'full_name': 'Частное лицо',
    'company_name': '',
    'phone': '',
  };

  final List<Map<String, dynamic>> cart = [];
  Map<String, dynamic> selectedClient = Map<String, dynamic>.from(anonymousClient);
  Map<String, dynamic> defaultClient = Map<String, dynamic>.from(anonymousClient);
  String paymentMethod = 'cash';
  bool paying = false;
  bool clientTouched = false;
  String? pendingVoicePaymentMethod;
  double? pendingVoicePaymentTotal;
  String? lastPaymentError;
  List<Map<String, dynamic>> voiceCatalogCache = [];
  DateTime? voiceCatalogLoadedAt;

  double get total => cart.fold<double>(
        0,
        (sum, item) => sum + asDouble(item['price']) * asDouble(item['qty']),
      );

  @override
  void initState() {
    super.initState();
    SalesVoiceBridge.instance.attach(this, handleVoiceCommand);
    loadDefaultClient();
    _warmVoiceCatalog();
  }

  @override
  void dispose() {
    SalesVoiceBridge.instance.detach(this);
    super.dispose();
  }

  Future<void> loadDefaultClient() async {
    try {
      final result = await ApiService.saleClients(limit: 10);
      final raw = result['default_client'];
      if (!mounted || raw is! Map) return;
      final client = Map<String, dynamic>.from(raw);
      setState(() {
        defaultClient = client;
        if (!clientTouched) selectedClient = client;
      });
    } catch (_) {
      // Продажа частному лицу продолжает работать без привязки client_id.
    }
  }

  String clientName(Map<String, dynamic> client) {
    final company = '${client['company_name'] ?? ''}'.trim();
    final name = '${client['full_name'] ?? ''}'.trim();
    return company.isNotEmpty ? company : name.isNotEmpty ? name : 'Частное лицо';
  }

  Future<void> selectClient() async {
    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _ClientPickerSheet(),
    );
    if (result != null && mounted) {
      setState(() {
        clientTouched = true;
        selectedClient = result;
      });
    }
  }

  Future<void> showManualAddDialog() async {
    final item = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _ItemPickerSheet(),
    );
    if (item != null) await addToCart(item);
  }

  Future<void> scanBarcode() async {
    final barcode = await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ScannerScreen()),
    );
    if (barcode == null) return;
    final code = barcode.toString().trim();
    try {
      if (code.startsWith('01') && code.length > 16) {
        final result = await ApiService.findByGtin(code.substring(2, 16));
        if (result['found'] == true) {
          result['excise_stamp'] = code;
          await addToCart(result);
          return;
        }
      }
      final result = await ApiService.barcode(code);
      if (result['found'] == true) {
        await addToCart(result);
      } else if (mounted) {
        await showAddNewItemDialog(barcode: code);
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  Future<void> addToCart(
    Map<String, dynamic> source, {
    bool requestMeasuredQuantity = true,
  }) async {
    final item = Map<String, dynamic>.from(source);
    item['price'] = asDouble(item['price'] ?? item['retail_price']);
    item['qty'] = asDouble(item['qty'] ?? 1);
    final unit = '${item['unit'] ?? ''}'.toLowerCase();
    if (requestMeasuredQuantity &&
        (unit == 'кг' ||
            unit == 'л' ||
            item['type'] == 'weight' ||
            item['type'] == 'liter')) {
      final quantity = await _quantityDialog(item, unit == 'л' ? 'Количество (л)' : 'Вес (кг)');
      if (quantity == null) return;
      item['qty'] = quantity;
    }

    final index = cart.indexWhere((value) => value['id'] == item['id']);
    setState(() {
      _clearPendingVoicePayment();
      if (index >= 0 && item['excise_stamp'] == null) {
        cart[index]['qty'] = asDouble(cart[index]['qty']) + asDouble(item['qty']);
      } else {
        cart.add({
          'id': item['id'],
          'name': item['name'] ?? 'Без названия',
          'price': asDouble(item['price']),
          'qty': asDouble(item['qty']),
          'unit': item['unit'] ?? 'шт',
          'item_type': item['item_type'] ?? 'product',
          'gtin': item['gtin'],
          'ntin': item['ntin'],
          'excise_stamp': item['excise_stamp'],
        });
      }
    });
  }

  Future<double?> _quantityDialog(Map<String, dynamic> item, String label) async {
    final controller = TextEditingController(text: '1');
    final result = await showDialog<double>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('${item['name']}'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: label),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
          FilledButton(
            onPressed: () {
              final value = double.tryParse(controller.text.replaceAll(',', '.'));
              if (value != null && value > 0) Navigator.pop(context, value);
            },
            child: const Text('Добавить'),
          ),
        ],
      ),
    );
    controller.dispose();
    return result;
  }

  Future<void> showAddNewItemDialog({required String barcode}) async {
    Map<String, dynamic> info = {};
    try {
      info = await ApiService.getBarcodeInfo(barcode);
    } catch (_) {}
    if (!mounted) return;

    final name = TextEditingController(text: '${info['name'] ?? ''}');
    final purchase = TextEditingController();
    final retail = TextEditingController();
    final quantity = TextEditingController(text: '1');
    String unit = '${info['measure'] ?? ''}'.toLowerCase().contains('кил') ? 'кг' : 'шт';
    bool saving = false;

    await showDialog<void>(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('Новый товар'),
          content: SingleChildScrollView(
            child: SizedBox(
              width: 420,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(controller: name, decoration: const InputDecoration(labelText: 'Наименование *')),
                const SizedBox(height: 10),
                TextField(controller: purchase, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Закупочная цена')),
                const SizedBox(height: 10),
                TextField(controller: retail, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Цена продажи *')),
                const SizedBox(height: 10),
                TextField(controller: quantity, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Начальный остаток')),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  value: unit,
                  decoration: const InputDecoration(labelText: 'Единица измерения'),
                  items: const [
                    DropdownMenuItem(value: 'шт', child: Text('шт')),
                    DropdownMenuItem(value: 'кг', child: Text('кг')),
                    DropdownMenuItem(value: 'л', child: Text('л')),
                  ],
                  onChanged: (value) => setDialogState(() => unit = value ?? 'шт'),
                ),
                const SizedBox(height: 12),
                Align(alignment: Alignment.centerLeft, child: Text('Штрихкод: $barcode', style: const TextStyle(color: AppColors.muted))),
              ]),
            ),
          ),
          actions: [
            TextButton(onPressed: saving ? null : () => Navigator.pop(dialogContext), child: const Text('Отмена')),
            FilledButton(
              onPressed: saving ? null : () async {
                if (name.text.trim().isEmpty || asDouble(retail.text.replaceAll(',', '.')) <= 0) return;
                setDialogState(() => saving = true);
                try {
                  final result = await ApiService.createItem(
                    name: name.text.trim(),
                    barcode: barcode,
                    unit: unit,
                    purchasePrice: asDouble(purchase.text.replaceAll(',', '.')),
                    retailPrice: asDouble(retail.text.replaceAll(',', '.')),
                    quantity: asDouble(quantity.text.replaceAll(',', '.')),
                    gtin: '${info['gtin'] ?? ''}',
                    ntin: '${info['ntin'] ?? ''}',
                    isMarked: info['is_marked'] == true,
                  );
                  if (!dialogContext.mounted) return;
                  Navigator.pop(dialogContext);
                  await addToCart({
                    'id': result['id'],
                    'name': name.text.trim(),
                    'price': asDouble(retail.text.replaceAll(',', '.')),
                    'unit': unit,
                    'qty': 1,
                    'gtin': info['gtin'],
                    'ntin': info['ntin'],
                  });
                } catch (e) {
                  if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(SnackBar(content: Text(readableError(e))));
                  setDialogState(() => saving = false);
                }
              },
              child: saving
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Сохранить'),
            ),
          ],
        ),
      ),
    );
    name.dispose(); purchase.dispose(); retail.dispose(); quantity.dispose();
  }

  Future<SalesVoiceResult?> handleVoiceCommand(String rawCommand) async {
    final command = _normalizeVoice(rawCommand);
    if (command.isEmpty) return null;

    if (pendingVoicePaymentMethod != null) {
      if (_isVoiceConfirmation(command)) {
        final expectedTotal = pendingVoicePaymentTotal;
        final method = pendingVoicePaymentMethod!;
        _clearPendingVoicePayment();
        if (expectedTotal == null || (total - expectedTotal).abs() > .009) {
          return const SalesVoiceResult(
            reply: 'Корзина изменилась. Назовите способ оплаты ещё раз.',
            clearConfirmation: true,
          );
        }
        if (paying) {
          return const SalesVoiceResult(
            reply: 'Оплата уже выполняется. Дождитесь результата.',
            clearConfirmation: true,
          );
        }
        setState(() => paymentMethod = method);
        final paidTotal = total;
        final success = await paySale();
        if (success) {
          return SalesVoiceResult(
            reply: 'Оплата на сумму ${money(paidTotal)} проведена. Чек сформирован.',
            openSales: false,
            clearConfirmation: true,
          );
        }
        final detail = lastPaymentError ?? 'операция не завершена';
        return SalesVoiceResult(
          reply: 'Не удалось завершить оплату: $detail. Проверьте статус операции перед повтором.',
          openSales: false,
          clearConfirmation: true,
        );
      }
      if (_isVoiceCancellation(command)) {
        _clearPendingVoicePayment();
        return const SalesVoiceResult(
          reply: 'Оплату отменила. Корзина сохранена.',
          clearConfirmation: true,
        );
      }
    }

    final requestedPayment = _voicePaymentMethod(command);
    if (requestedPayment != null) {
      if (cart.isEmpty) {
        return const SalesVoiceResult(reply: 'Корзина пустая. Сначала добавьте товары.');
      }
      if (paying) {
        return const SalesVoiceResult(reply: 'Оплата уже выполняется. Дождитесь результата.');
      }
      final methodName = requestedPayment == 'kaspi' ? 'Kaspi POS' : 'наличными';
      setState(() {
        paymentMethod = requestedPayment;
        pendingVoicePaymentMethod = requestedPayment;
        pendingVoicePaymentTotal = total;
      });
      final summary = 'Оплатить ${money(total)} способом $methodName?';
      return SalesVoiceResult(
        reply: '$summary Скажите «подтверждаю» или «отмена».',
        confirmationSummary: summary,
      );
    }

    final explicitlySales = SalesVoiceBridge.instance.salesVisible ||
        command.contains('корзин') ||
        command.contains('чек');
    if (!explicitlySales) return null;

    if ((command.contains('очист') && command.contains('корзин')) ||
        command.contains('убери все из корзин')) {
      if (cart.isEmpty) {
        return const SalesVoiceResult(reply: 'Корзина уже пустая.');
      }
      setState(() {
        cart.clear();
        _clearPendingVoicePayment();
      });
      return const SalesVoiceResult(
        reply: 'Корзину очистила.',
        clearConfirmation: true,
      );
    }

    if (_isCartSummaryCommand(command)) {
      if (cart.isEmpty) {
        return const SalesVoiceResult(reply: 'Корзина пустая.');
      }
      final preview = cart.take(5).map((item) {
        final qty = asDouble(item['qty']);
        return '${item['name']}, ${_voiceNumber(qty)} ${item['unit'] ?? 'шт'}';
      }).join('; ');
      final tail = cart.length > 5 ? '; и ещё ${cart.length - 5}' : '';
      return SalesVoiceResult(
        reply: 'В корзине: $preview$tail. Итого ${money(total)}.',
      );
    }

    if (_startsWithAny(command, const ['увеличь ', 'уменьши ', 'убавь '])) {
      final decreasing = command.startsWith('уменьши ') || command.startsWith('убавь ');
      final absolute = command.contains(' до ');
      final tokens = _voiceTokens(command);
      var amount = 1.0;
      for (final token in tokens) {
        final parsed = _spokenQuantity(token);
        if (parsed != null) {
          amount = parsed;
          break;
        }
      }
      final ignored = <String>{
        'увеличь', 'уменьши', 'убавь', 'количество', 'товара', 'товары',
        'позиции', 'позицию', 'на', 'до', 'штук', 'штуки', 'шт',
      };
      final query = tokens
          .where((token) => !ignored.contains(token) && _spokenQuantity(token) == null)
          .join(' ')
          .trim();
      if (query.isEmpty) {
        return const SalesVoiceResult(reply: 'Назовите товар, количество которого нужно изменить.');
      }
      final indexes = _matchingCartIndexes(query);
      if (indexes.isEmpty) {
        return SalesVoiceResult(reply: 'В корзине нет позиции «$query».');
      }
      if (indexes.length > 1) {
        final names = indexes.take(3).map((index) => '${cart[index]['name']}').join(', ');
        return SalesVoiceResult(reply: 'Нашла несколько позиций: $names. Назовите точнее.');
      }
      final index = indexes.single;
      final name = '${cart[index]['name']}';
      final current = asDouble(cart[index]['qty']);
      final next = absolute ? amount : current + (decreasing ? -amount : amount);
      setState(() {
        _clearPendingVoicePayment();
        if (next <= 0) {
          cart.removeAt(index);
        } else {
          cart[index]['qty'] = next;
        }
      });
      return SalesVoiceResult(
        reply: next <= 0
            ? '$name удалила из корзины. Итого ${money(total)}.'
            : 'Количество $name: ${_voiceNumber(next)}. Итого ${money(total)}.',
        clearConfirmation: true,
      );
    }

    if (_startsWithAny(command, const ['удали ', 'убери ', 'исключи '])) {
      final query = command
          .replaceFirst(RegExp(r'^(удали|убери|исключи)\s+'), '')
          .replaceAll(RegExp(r'\s+из\s+корзины?$'), '')
          .trim();
      if (query.isEmpty) return null;
      final indexes = _matchingCartIndexes(query);
      if (indexes.isEmpty) {
        return SalesVoiceResult(reply: 'В корзине нет позиции «$query».');
      }
      if (indexes.length > 1) {
        final names = indexes.take(3).map((index) => '${cart[index]['name']}').join(', ');
        return SalesVoiceResult(reply: 'Нашла несколько позиций: $names. Назовите точнее.');
      }
      final name = '${cart[indexes.single]['name']}';
      setState(() {
        cart.removeAt(indexes.single);
        _clearPendingVoicePayment();
      });
      return SalesVoiceResult(
        reply: '$name удалила. Итого ${money(total)}.',
        clearConfirmation: true,
      );
    }

    if (_startsWithAny(command, const ['добавь ', 'положи ']) ||
        command.contains('добавь в корзин')) {
      return _addItemsByVoice(command);
    }

    return null;
  }

  Future<SalesVoiceResult> _addItemsByVoice(String command) async {
    var payload = command
        .replaceFirst(RegExp(r'^(добавь|положи)\s+'), '')
        .replaceFirst(RegExp(r'^(в\s+)?корзину?\s+'), '')
        .replaceAll(RegExp(r'\s+в\s+корзину?$'), '')
        .trim();
    if (payload.isEmpty) {
      return const SalesVoiceResult(reply: 'Назовите товар, который нужно добавить.');
    }

    try {
      final catalog = await _loadVoiceCatalog();
      var matches = _catalogMatches(payload, catalog);

      if (matches.isEmpty) {
        final search = await ApiService.saleItems(query: payload, limit: 8);
        final found = List<dynamic>.from(search['items'] ?? const [])
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList();
        if (found.length == 1) {
          matches = [_VoiceCatalogMatch(found.single, 1)];
        } else if (found.length > 1) {
          final names = found.take(3).map((item) => '${item['name']}').join(', ');
          return SalesVoiceResult(
            reply: 'Нашла несколько вариантов: $names. Назовите товар точнее.',
          );
        }
      }

      if (matches.isEmpty) {
        return SalesVoiceResult(reply: 'Не нашла «$payload» в каталоге. Назовите точное наименование.');
      }

      final added = <String>[];
      for (final match in matches) {
        final item = Map<String, dynamic>.from(match.item);
        item['qty'] = match.quantity;
        await addToCart(item, requestMeasuredQuantity: false);
        final quantity = match.quantity == 1 ? '' : ' — ${_voiceNumber(match.quantity)}';
        added.add('${item['name']}$quantity');
      }
      return SalesVoiceResult(
        reply: 'Добавила: ${added.join(', ')}. Итого ${money(total)}.',
        clearConfirmation: true,
      );
    } catch (error) {
      return SalesVoiceResult(reply: 'Не удалось открыть каталог: ${readableError(error)}');
    }
  }

  Future<void> _warmVoiceCatalog() async {
    try {
      await _loadVoiceCatalog();
    } catch (_) {
      // Первая голосовая команда повторит загрузку и покажет понятную ошибку.
    }
  }

  Future<List<Map<String, dynamic>>> _loadVoiceCatalog() async {
    final loadedAt = voiceCatalogLoadedAt;
    if (voiceCatalogCache.isNotEmpty &&
        loadedAt != null &&
        DateTime.now().difference(loadedAt) < const Duration(minutes: 3)) {
      return voiceCatalogCache;
    }
    final response = await ApiService.saleItems(limit: 100);
    final loaded = List<dynamic>.from(response['items'] ?? const [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    voiceCatalogCache = loaded;
    voiceCatalogLoadedAt = DateTime.now();
    return voiceCatalogCache;
  }

  List<_VoiceCatalogMatch> _catalogMatches(
    String payload,
    List<Map<String, dynamic>> catalog,
  ) {
    final commandTokens = _voiceTokens(payload);
    final candidates = <_PositionedVoiceMatch>[];
    for (final item in catalog) {
      final itemTokens = _voiceTokens('${item['name'] ?? ''}');
      if (itemTokens.isEmpty || itemTokens.length > commandTokens.length) continue;
      for (var start = 0; start <= commandTokens.length - itemTokens.length; start++) {
        var matches = true;
        for (var offset = 0; offset < itemTokens.length; offset++) {
          if (!_voiceTokenEquals(itemTokens[offset], commandTokens[start + offset])) {
            matches = false;
            break;
          }
        }
        if (!matches) continue;
        var quantity = 1.0;
        if (start > 0) quantity = _spokenQuantity(commandTokens[start - 1]) ?? quantity;
        final after = start + itemTokens.length;
        if (after < commandTokens.length) {
          quantity = _spokenQuantity(commandTokens[after]) ?? quantity;
        }
        candidates.add(_PositionedVoiceMatch(
          item: item,
          quantity: quantity,
          start: start,
          length: itemTokens.length,
        ));
      }
    }

    candidates.sort((a, b) {
      final byStart = a.start.compareTo(b.start);
      return byStart != 0 ? byStart : b.length.compareTo(a.length);
    });
    final selected = <_PositionedVoiceMatch>[];
    final occupied = <int>{};
    final ids = <dynamic>{};
    for (final candidate in candidates) {
      final range = List<int>.generate(candidate.length, (index) => candidate.start + index);
      if (range.any(occupied.contains) || ids.contains(candidate.item['id'])) continue;
      selected.add(candidate);
      occupied.addAll(range);
      ids.add(candidate.item['id']);
    }
    return selected
        .map((match) => _VoiceCatalogMatch(match.item, match.quantity))
        .toList();
  }

  List<int> _matchingCartIndexes(String query) {
    final queryTokens = _voiceTokens(query);
    final result = <int>[];
    for (var index = 0; index < cart.length; index++) {
      final nameTokens = _voiceTokens('${cart[index]['name'] ?? ''}');
      if (queryTokens.isEmpty || nameTokens.isEmpty) continue;
      final allFound = queryTokens.every(
        (queryToken) => nameTokens.any((nameToken) => _voiceTokenEquals(queryToken, nameToken)),
      );
      if (allFound) result.add(index);
    }
    return result;
  }

  void _clearPendingVoicePayment() {
    pendingVoicePaymentMethod = null;
    pendingVoicePaymentTotal = null;
  }

  Future<bool> paySale() async {
    if (cart.isEmpty || paying) return false;
    lastPaymentError = null;
    setState(() => paying = true);
    try {
      String? kaspiTransactionId;
      String? kaspiMethod;
      if (paymentMethod == 'kaspi') {
        final kaspiResult = await KaspiPosService.startPayment(total.toInt());
        if (kaspiResult['statusCode'] != 0) {
          throw ApiException('${kaspiResult['error'] ?? kaspiResult['message'] ?? 'Kaspi POS не принял оплату'}');
        }
        final processId = kaspiResult['data']?['processId'];
        var success = false;
        for (var attempt = 0; attempt < 60; attempt++) {
          await Future<void>.delayed(const Duration(seconds: 2));
          final status = await KaspiPosService.getStatus('$processId');
          final value = '${status['data']?['status'] ?? ''}';
          if (value == 'success') {
            kaspiTransactionId = '${status['data']?['transactionId'] ?? ''}';
            kaspiMethod = '${status['data']?['chequeInfo']?['method'] ?? ''}';
            success = true;
            break;
          }
          if (value == 'fail') break;
        }
        if (!success) throw const ApiException('Оплата Kaspi не выполнена');
      }

      final result = await ApiService.paySale(
        cart: cart,
        clientId: selectedClient['id'] as int?,
        paymentMethod: paymentMethod,
        kaspiTransactionId: kaspiTransactionId,
        kaspiMethod: kaspiMethod,
      );
      if (!mounted || result['success'] != true) {
        throw ApiException('${result['error'] ?? 'Сервер не подтвердил продажу'}');
      }
      final saleId = int.tryParse('${result['sale_id']}');
      setState(() {
        cart.clear();
        clientTouched = false;
        selectedClient = Map<String, dynamic>.from(defaultClient);
      });
      if (saleId != null) {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => CheckScreen(saleId: saleId, autoPrint: true)),
        );
      }
      return true;
    } catch (e) {
      lastPaymentError = readableError(e);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
      return false;
    } finally {
      if (mounted) setState(() => paying = false);
    }
  }

  void changeQuantity(int index, double delta) {
    setState(() {
      _clearPendingVoicePayment();
      final next = asDouble(cart[index]['qty']) + delta;
      if (next <= 0) {
        cart.removeAt(index);
      } else {
        cart[index]['qty'] = next;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final actions = Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
        child: Row(children: [
          Expanded(
            child: ElevatedButton.icon(
              onPressed: scanBarcode,
              icon: const Icon(Icons.qr_code_scanner_rounded),
              label: const Text('Сканер'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.navy,
                padding: const EdgeInsets.symmetric(horizontal: 10),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: ElevatedButton.icon(
              onPressed: showManualAddDialog,
              icon: const Icon(Icons.add_box_rounded),
              label: const Text('Добавить'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 10),
              ),
            ),
          ),
        ]),
      );
    final client = Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Card(
          child: InkWell(
            onTap: selectClient,
            borderRadius: BorderRadius.circular(20),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(children: [
                const CircleAvatar(backgroundColor: AppColors.primarySoft, child: Icon(Icons.person_outline_rounded, color: AppColors.primary)),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Клиент', style: TextStyle(color: AppColors.muted, fontSize: 12)),
                  const SizedBox(height: 3),
                  Text(clientName(selectedClient), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
                  if ('${selectedClient['phone'] ?? ''}'.isNotEmpty)
                    Text('${selectedClient['phone']}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                ])),
                const Icon(Icons.unfold_more_rounded, color: AppColors.muted),
              ]),
            ),
          ),
        ),
      );
    final cartContent = cart.isEmpty
        ? const ScreenStateView(icon: Icons.shopping_cart_outlined, title: 'Корзина пустая', message: 'Отсканируйте товар или добавьте товар либо услугу вручную.')
        : ListView.builder(
                keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                padding: const EdgeInsets.fromLTRB(14, 4, 14, 12),
                itemCount: cart.length,
                itemBuilder: (_, index) {
                  final item = cart[index];
                  final quantity = asDouble(item['qty']);
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 9),
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Row(children: [
                          Container(width: 46, height: 46, decoration: BoxDecoration(color: AppColors.primarySoft, borderRadius: BorderRadius.circular(14)), child: Icon(item['item_type'] == 'service' ? Icons.design_services_outlined : Icons.inventory_2_outlined, color: AppColors.primary)),
                          const SizedBox(width: 12),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('${item['name']}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
                            const SizedBox(height: 7),
                            Row(children: [
                              _QtyButton(icon: Icons.remove_rounded, onTap: () => changeQuantity(index, -1)),
                              SizedBox(width: 54, child: Text(quantity % 1 == 0 ? '${quantity.toInt()}' : quantity.toStringAsFixed(3), textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w800))),
                              _QtyButton(icon: Icons.add_rounded, onTap: () => changeQuantity(index, 1), primary: true),
                            ]),
                          ])),
                          const SizedBox(width: 8),
                          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                            Text(money(asDouble(item['price']) * quantity), style: const TextStyle(fontWeight: FontWeight.w900)),
                            IconButton(onPressed: () => setState(() { cart.removeAt(index); _clearPendingVoicePayment(); }), icon: const Icon(Icons.delete_outline_rounded, color: AppColors.danger), tooltip: 'Удалить'),
                          ]),
                        ]),
                      ),
                    ),
                  );
                },
              );
    final checkout = Material(
        color: AppColors.surface,
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Row(children: [
                const Text('Итого', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const Spacer(),
                Text(money(total), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
              ]),
              const SizedBox(height: 10),
              Row(children: [
                Expanded(child: ChoiceChip(label: const Text('Наличные'), selected: paymentMethod == 'cash', onSelected: (_) => setState(() => paymentMethod = 'cash'))),
                const SizedBox(width: 7),
                Expanded(child: ChoiceChip(label: const Text('Карта'), selected: paymentMethod == 'card', onSelected: (_) => setState(() => paymentMethod = 'card'))),
                const SizedBox(width: 7),
                Expanded(child: ChoiceChip(label: const Text('Kaspi POS'), selected: paymentMethod == 'kaspi', onSelected: (_) => setState(() => paymentMethod = 'kaspi'))),
              ]),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: cart.isEmpty || paying ? null : paySale,
                  child: paying
                      ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Оплатить'),
                ),
              ),
            ]),
          ),
        ),
      );

    return LayoutBuilder(
      builder: (_, constraints) {
        final tablet = constraints.maxWidth >= AppBreakpoints.tablet;
        if (!tablet) {
          return Column(children: [
            actions,
            client,
            const SizedBox(height: 8),
            Expanded(child: cartContent),
            checkout,
          ]);
        }

        return Padding(
          padding: const EdgeInsets.only(right: 16),
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(
              child: Column(children: [
                actions,
                const SizedBox(height: 2),
                Expanded(child: cartContent),
              ]),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: constraints.maxWidth >= 1120 ? 390 : 350,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 14),
                child: Column(children: [
                  client,
                  const Spacer(),
                  Card(
                    clipBehavior: Clip.antiAlias,
                    child: checkout,
                  ),
                ]),
              ),
            ),
          ]),
        );
      },
    );
  }
}

class _QtyButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final bool primary;
  const _QtyButton({required this.icon, required this.onTap, this.primary = false});

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(9),
        child: Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(color: primary ? AppColors.primarySoft : AppColors.danger.withOpacity(.08), borderRadius: BorderRadius.circular(9)),
          child: Icon(icon, size: 18, color: primary ? AppColors.primary : AppColors.danger),
        ),
      );
}

class _ClientPickerSheet extends StatefulWidget {
  const _ClientPickerSheet();

  @override
  State<_ClientPickerSheet> createState() => _ClientPickerSheetState();
}

class _ClientPickerSheetState extends State<_ClientPickerSheet> {
  final search = TextEditingController();
  final scroll = ScrollController();
  Timer? debounce;
  List<Map<String, dynamic>> items = [];
  bool loading = true;
  bool loadingMore = false;
  bool hasMore = false;
  int page = 1;
  int requestId = 0;
  String? error;

  @override
  void initState() {
    super.initState();
    scroll.addListener(_onScroll);
    load(reset: true);
  }

  @override
  void dispose() {
    debounce?.cancel(); search.dispose(); scroll.dispose(); super.dispose();
  }

  void _onScroll() {
    if (scroll.position.pixels > scroll.position.maxScrollExtent - 180 && hasMore && !loadingMore) load();
  }

  void onSearch(String value) {
    debounce?.cancel();
    if (value.trim().length == 1) {
      load(reset: true);
      return;
    }
    debounce = Timer(const Duration(milliseconds: 350), () => load(reset: true));
  }

  Future<void> load({bool reset = false}) async {
    final currentRequest = ++requestId;
    final query = search.text.trim();
    if (query.length == 1) {
      setState(() { items = []; loading = false; hasMore = false; error = null; });
      return;
    }
    if (reset) {
      page = 1;
      setState(() { loading = true; error = null; });
    } else {
      setState(() => loadingMore = true);
    }
    try {
      final result = await ApiService.saleClients(query: query, page: page, limit: 30);
      final loaded = List<dynamic>.from(result['items'] ?? const []).map((raw) => Map<String, dynamic>.from(raw as Map)).toList();
      final defaultRaw = result['default_client'];
      final privateClient = defaultRaw is Map
          ? Map<String, dynamic>.from(defaultRaw)
          : Map<String, dynamic>.from(_SalesScreenState.anonymousClient);
      if (!mounted || currentRequest != requestId) return;
      setState(() {
        if (reset) {
          items = query.isEmpty ? [privateClient] : [];
        }
        for (final client in loaded) {
          if (!items.any((current) => current['id'] == client['id'])) items.add(client);
        }
        hasMore = result['has_more'] == true;
        if (hasMore) page += 1;
        loading = false;
        loadingMore = false;
      });
    } catch (e) {
      if (!mounted || currentRequest != requestId) return;
      setState(() { error = readableError(e); loading = false; loadingMore = false; });
    }
  }

  @override
  Widget build(BuildContext context) => _SheetFrame(
    title: 'Выберите клиента',
    child: Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        child: TextField(controller: search, onChanged: onSearch, autofocus: true, decoration: const InputDecoration(hintText: 'Имя, компания, телефон или ИИН', prefixIcon: Icon(Icons.search_rounded))),
      ),
      Expanded(
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : error != null
                ? ScreenStateView(icon: Icons.people_alt_outlined, title: 'Клиенты не загрузились', message: error!, onAction: () => load(reset: true))
                : search.text.trim().length == 1
                    ? const Center(child: Text('Введите ещё один символ', style: TextStyle(color: AppColors.muted)))
                    : items.isEmpty
                        ? const Center(child: Text('Клиенты не найдены', style: TextStyle(color: AppColors.muted)))
                        : ListView.builder(
                            controller: scroll,
                            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                            padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                            itemCount: items.length + (loadingMore ? 1 : 0),
                            itemBuilder: (_, index) {
                              if (index == items.length) return const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()));
                              final client = items[index];
                              final name = '${client['company_name'] ?? ''}'.trim().isNotEmpty ? '${client['company_name']}' : '${client['full_name'] ?? 'Частное лицо'}';
                              final detail = ['${client['full_name'] ?? ''}', '${client['phone'] ?? ''}'].where((value) => value.trim().isNotEmpty && value != name).join(' · ');
                              return ListTile(
                                leading: CircleAvatar(backgroundColor: AppColors.primarySoft, child: Icon(client['id'] == null ? Icons.person_outline_rounded : Icons.person_rounded, color: AppColors.primary)),
                                title: Text(name, style: const TextStyle(fontWeight: FontWeight.w800)),
                                subtitle: detail.isEmpty ? null : Text(detail),
                                trailing: const Icon(Icons.chevron_right_rounded),
                                onTap: () => Navigator.pop(context, client),
                              );
                            },
                          ),
      ),
    ]),
  );
}

class _ItemPickerSheet extends StatefulWidget {
  const _ItemPickerSheet();

  @override
  State<_ItemPickerSheet> createState() => _ItemPickerSheetState();
}

class _ItemPickerSheetState extends State<_ItemPickerSheet> {
  final search = TextEditingController();
  final scroll = ScrollController();
  Timer? debounce;
  List<Map<String, dynamic>> items = [];
  bool loading = true;
  bool loadingMore = false;
  bool hasMore = false;
  int page = 1;
  int requestId = 0;
  String? error;

  @override
  void initState() {
    super.initState();
    scroll.addListener(_onScroll);
    load(reset: true);
  }

  @override
  void dispose() {
    debounce?.cancel(); search.dispose(); scroll.dispose(); super.dispose();
  }

  void _onScroll() {
    if (scroll.position.pixels > scroll.position.maxScrollExtent - 180 && hasMore && !loadingMore) load();
  }

  void onSearch(String value) {
    debounce?.cancel();
    if (value.trim().length == 1) {
      load(reset: true);
      return;
    }
    debounce = Timer(const Duration(milliseconds: 350), () => load(reset: true));
  }

  Future<void> load({bool reset = false}) async {
    final currentRequest = ++requestId;
    final query = search.text.trim();
    if (query.length == 1) {
      setState(() { items = []; loading = false; hasMore = false; error = null; });
      return;
    }
    if (reset) {
      page = 1;
      setState(() { loading = true; error = null; });
    } else {
      setState(() => loadingMore = true);
    }
    try {
      final result = await ApiService.saleItems(query: query, page: page, limit: 30);
      final loaded = List<dynamic>.from(result['items'] ?? const []).map((raw) => Map<String, dynamic>.from(raw as Map)).toList();
      if (!mounted || currentRequest != requestId) return;
      setState(() {
        if (reset) items = [];
        for (final item in loaded) {
          if (!items.any((current) => current['id'] == item['id'])) items.add(item);
        }
        hasMore = result['has_more'] == true;
        if (hasMore) page += 1;
        loading = false;
        loadingMore = false;
      });
    } catch (e) {
      if (!mounted || currentRequest != requestId) return;
      setState(() { error = readableError(e); loading = false; loadingMore = false; });
    }
  }

  @override
  Widget build(BuildContext context) => _SheetFrame(
    title: 'Товары и услуги',
    child: Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        child: TextField(controller: search, onChanged: onSearch, autofocus: true, decoration: const InputDecoration(hintText: 'Название или штрихкод', prefixIcon: Icon(Icons.search_rounded))),
      ),
      Expanded(
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : error != null
                ? ScreenStateView(icon: Icons.inventory_2_outlined, title: 'Каталог не загрузился', message: error!, onAction: () => load(reset: true))
                : search.text.trim().length == 1
                    ? const Center(child: Text('Введите ещё один символ', style: TextStyle(color: AppColors.muted)))
                    : items.isEmpty
                        ? const Center(child: Text('Ничего не найдено', style: TextStyle(color: AppColors.muted)))
                        : ListView.builder(
                            controller: scroll,
                            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                            padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                            itemCount: items.length + (loadingMore ? 1 : 0),
                            itemBuilder: (_, index) {
                              if (index == items.length) return const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()));
                              final item = items[index];
                              final service = item['item_type'] == 'service';
                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                child: ListTile(
                                  leading: Container(width: 44, height: 44, decoration: BoxDecoration(color: (service ? AppColors.cyan : AppColors.primary).withOpacity(.1), borderRadius: BorderRadius.circular(13)), child: Icon(service ? Icons.design_services_outlined : Icons.inventory_2_outlined, color: service ? AppColors.cyan : AppColors.primary)),
                                  title: Text('${item['name'] ?? 'Без названия'}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
                                  subtitle: Text(service ? 'Услуга' : 'Остаток: ${item['quantity'] ?? 0} ${item['unit'] ?? 'шт'}'),
                                  trailing: Text(money(item['retail_price']), style: const TextStyle(fontWeight: FontWeight.w900)),
                                  onTap: () => Navigator.pop(context, item),
                                ),
                              );
                            },
                          ),
      ),
    ]),
  );
}

class _SheetFrame extends StatelessWidget {
  final String title;
  final Widget child;
  const _SheetFrame({required this.title, required this.child});

  @override
  Widget build(BuildContext context) => Container(
    height: MediaQuery.sizeOf(context).height * .88,
    decoration: const BoxDecoration(color: AppColors.background, borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    child: Column(children: [
      const SizedBox(height: 10),
      Container(width: 42, height: 4, decoration: BoxDecoration(color: AppColors.border, borderRadius: BorderRadius.circular(99))),
      Padding(
        padding: const EdgeInsets.fromLTRB(18, 12, 8, 10),
        child: Row(children: [
          Expanded(child: Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900))),
          IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close_rounded)),
        ]),
      ),
      Expanded(child: child),
    ]),
  );
}

class _VoiceCatalogMatch {
  final Map<String, dynamic> item;
  final double quantity;

  const _VoiceCatalogMatch(this.item, this.quantity);
}

class _PositionedVoiceMatch {
  final Map<String, dynamic> item;
  final double quantity;
  final int start;
  final int length;

  const _PositionedVoiceMatch({
    required this.item,
    required this.quantity,
    required this.start,
    required this.length,
  });
}

String _normalizeVoice(String text) => text
    .toLowerCase()
    .replaceAll('ё', 'е')
    .replaceAll(RegExp(r'[^a-zа-я0-9\s.,-]'), ' ')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

List<String> _voiceTokens(String text) => _normalizeVoice(text)
    .replaceAll(RegExp(r'[.,-]'), ' ')
    .split(RegExp(r'\s+'))
    .where((token) => token.isNotEmpty)
    .toList();

bool _voiceTokenEquals(String first, String second) {
  if (first == second) return true;
  if (first.length < 4 || second.length < 4) return false;
  if ((first.length - second.length).abs() > 1) return false;
  return _editDistance(first, second) <= 1;
}

int _editDistance(String first, String second) {
  var previous = List<int>.generate(second.length + 1, (index) => index);
  for (var row = 1; row <= first.length; row++) {
    final current = List<int>.filled(second.length + 1, 0)..[0] = row;
    for (var column = 1; column <= second.length; column++) {
      final substitution = previous[column - 1] +
          (first.codeUnitAt(row - 1) == second.codeUnitAt(column - 1) ? 0 : 1);
      final insertion = current[column - 1] + 1;
      final deletion = previous[column] + 1;
      current[column] = substitution < insertion
          ? (substitution < deletion ? substitution : deletion)
          : (insertion < deletion ? insertion : deletion);
    }
    previous = current;
  }
  return previous.last;
}

double? _spokenQuantity(String token) {
  final numeric = double.tryParse(token.replaceAll(',', '.'));
  if (numeric != null && numeric > 0) return numeric;
  return const <String, double>{
    'один': 1,
    'одну': 1,
    'два': 2,
    'две': 2,
    'три': 3,
    'четыре': 4,
    'пять': 5,
    'шесть': 6,
    'семь': 7,
    'восемь': 8,
    'девять': 9,
    'десять': 10,
  }[token];
}

String _voiceNumber(double value) => value % 1 == 0
    ? '${value.toInt()}'
    : value.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '');

bool _startsWithAny(String value, List<String> prefixes) =>
    prefixes.any(value.startsWith);

bool _isVoiceConfirmation(String command) =>
    command == 'да' ||
    command.contains('подтвержда') ||
    command.contains('оплачивай') ||
    command.contains('пробивай');

bool _isVoiceCancellation(String command) =>
    command == 'нет' ||
    command.contains('отмена') ||
    command.contains('отмени') ||
    command.contains('не оплачивай') ||
    command.contains('не пробивай');

String? _voicePaymentMethod(String command) {
  final paymentVerb = command.contains('оплат') ||
      command.contains('пробей') ||
      command.contains('проведи') ||
      command.contains('рассчитай');
  if (!paymentVerb) return null;
  if (command.contains('kaspi') || command.contains('каспи')) return 'kaspi';
  if (command.contains('налич')) return 'cash';
  return null;
}

bool _isCartSummaryCommand(String command) =>
    command.contains('что в корзин') ||
    command.contains('покажи корзин') ||
    command.contains('назови корзин') ||
    command.contains('итого') ||
    command.contains('сумма корзин');
