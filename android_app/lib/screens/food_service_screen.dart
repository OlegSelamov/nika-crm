import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:printing/printing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import '../services/food_order_logic.dart';
import '../services/kaspi_pos_service.dart';
import '../services/printer_service.dart';
import '../widgets/app_widgets.dart';
import 'sale_detail_screen.dart';
import 'check_screen.dart';

/// Native restaurant checkout. All food writes are online and use the same
/// food_orders, sales, stock and fiscal endpoints as the website.
class FoodServiceScreen extends StatefulWidget {
  const FoodServiceScreen({super.key});

  @override
  State<FoodServiceScreen> createState() => _FoodServiceScreenState();
}

class _FoodServiceScreenState extends State<FoodServiceScreen> {
  final table = TextEditingController();
  final guest = TextEditingController();
  final note = TextEditingController();
  final search = TextEditingController();
  final cart = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> menu = [];
  List<Map<String, dynamic>> orders = [];
  Timer? debounce;
  String mode = 'orders';
  String view = 'menu';
  String payment = 'cash';
  String filter = 'all';
  String company = '';
  int? orderId;
  int? clientId;
  String clientName = 'Частное лицо';
  bool loading = true;
  bool busy = false;
  bool uncertain = false;
  bool printedPair = false;
  bool menuMore = false;
  bool ordersMore = false;
  int menuPage = 1;
  int ordersPage = 1;
  String? error;
  double get total => FoodOrderLogic.total(cart);

  @override
  void initState() { super.initState(); initialize(); }

  @override
  void dispose() {
    for (final c in [table, guest, note, search]) { c.dispose(); }
    debounce?.cancel();
    super.dispose();
  }

  void toast(String value) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(value), duration: const Duration(seconds: 5)));
  }

  Future<void> initialize() async {
    try {
      final config = await ApiService.foodConfiguration();
      if (config['success'] != true) throw const ApiException('Общепит недоступен');
      if (!mounted) return;
      setState(() {
        mode = (config['food_checkout_mode'] ?? 'orders').toString();
        company = (config['company_name'] ?? '').toString();
        loading = false;
      });
      await Future.wait([loadMenu(), loadOrders()]);
    } catch (e) {
      if (mounted) setState(() { loading = false; error = readableError(e); });
    }
  }

  Future<void> loadMenu({bool more = false}) async {
    try {
      final page = more ? menuPage + 1 : 1;
      final data = await ApiService.foodMenu(
        query: search.text, page: page,
        type: search.text.trim().isEmpty ? 'dish' : 'food_menu',
      );
      if (!mounted) return;
      setState(() {
        if (!more) menu.clear();
        menu.addAll((data['items'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map)));
        menuPage = page;
        menuMore = data['has_more'] == true;
      });
    } catch (e) { toast(readableError(e)); }
  }

  Future<void> loadOrders({bool more = false}) async {
    try {
      final page = more ? ordersPage + 1 : 1;
      final data = await ApiService.foodOrders(status: filter, page: page);
      if (!mounted) return;
      setState(() {
        if (!more) orders.clear();
        orders.addAll((data['orders'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map)));
        ordersPage = page;
        ordersMore = data['has_more'] == true;
      });
    } catch (e) { toast(readableError(e)); }
  }

  void changed() { printedPair = false; }

  void resetOrder() {
    table.clear(); guest.clear(); note.clear();
    setState(() {
      cart.clear(); orderId = null; payment = 'cash';
      clientId = null; clientName = 'Частное лицо';
      printedPair = false; uncertain = false; view = 'menu';
    });
  }

  Future<void> runBusy(Future<void> Function() task) async {
    if (busy || uncertain) return;
    setState(() => busy = true);
    try { await task(); }
    catch (e) { toast(readableError(e)); }
    finally { if (mounted) setState(() => busy = false); }
  }

  Future<void> chooseClient() async {
    try {
      final clients = await ApiService.getClients(forceRemote: true);
      if (!mounted) return;
      final selected = await showModalBottomSheet<Map<String, dynamic>>(
        context: context, showDragHandle: true, isScrollControlled: true,
        builder: (c) => SafeArea(child: ListView(shrinkWrap: true, children: [
          ListTile(title: const Text('Частное лицо'), onTap: () =>
            Navigator.pop(c, <String, dynamic>{})),
          for (final raw in clients.take(70).whereType<Map>())
            ListTile(
              title: Text((raw['full_name'] ?? raw['company_name'] ?? 'Клиент').toString()),
              onTap: () => Navigator.pop(c, Map<String, dynamic>.from(raw)),
            ),
        ])),
      );
      if (!mounted || selected == null) return;
      setState(() {
        clientId = int.tryParse((selected['id'] ?? '').toString());
        clientName = (selected['full_name'] ?? selected['company_name'] ?? 'Частное лицо').toString();
        changed();
      });
    } catch (e) { toast(readableError(e)); }
  }

  Future<void> addItem(Map<String, dynamic> item) async {
    if (busy || uncertain) return;
    if (item['item_type'] != 'dish') {
      setState(() {
        cart.add(FoodOrderLogic.line(item)); changed(); view = 'order';
      });
      return;
    }
    try {
      final id = int.parse(item['id'].toString());
      final result = await Future.wait([
        ApiService.foodModifiers(id), ApiService.foodRecipe(id),
      ]);
      final groups = (result[0]['groups'] as List? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map)).toList();
      final ingredients = (result[1]['ingredients'] as List? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map)).toList();
      if (ingredients.isEmpty) throw const ApiException('Для блюда не заполнена техкарта');
      if (!mounted) return;
      final line = await modifierDialog(item, groups, ingredients);
      if (!mounted || line == null) return;
      setState(() { cart.add(line); changed(); view = 'order'; });
    } catch (e) { toast(readableError(e)); }
  }

  Future<Map<String, dynamic>?> modifierDialog(
    Map<String, dynamic> item, List<Map<String, dynamic>> groups,
    List<Map<String, dynamic>> ingredients,
  ) async {
    final additions = <int>{};
    final removals = <int>{};
    var active = 0;
    return showModalBottomSheet<Map<String, dynamic>>(
      context: context, useSafeArea: true, isScrollControlled: true,
      showDragHandle: true,
      builder: (sheet) => StatefulBuilder(builder: (ctx, update) {
        final selected = <Map<String, dynamic>>[];
        for (final group in groups) {
          for (final raw in group['options'] as List? ?? []) {
            final o = Map<String, dynamic>.from(raw as Map);
            if (additions.contains(int.tryParse(o['id'].toString()))) selected.add(o);
          }
        }
        final extras = selected.fold<double>(0,
          (sum, o) => sum + FoodOrderLogic.number(o['price_delta']));
        return FractionallySizedBox(heightFactor: .88, child: Column(children: [
          Padding(padding: const EdgeInsets.all(12), child: Column(children: [
            Text((item['name'] ?? 'Блюдо').toString(),
              style: Theme.of(ctx).textTheme.titleLarge),
            Row(children: [
              Expanded(child: ChoiceChip(
                label: Text('＋ Добавить (' + additions.length.toString() + ')'),
                selected: active == 0, onSelected: (_) => update(() => active = 0))),
              const SizedBox(width: 8),
              Expanded(child: ChoiceChip(
                label: Text('− Убрать (' + removals.length.toString() + ')'),
                selected: active == 1, onSelected: (_) => update(() => active = 1))),
            ]),
          ])),
          Expanded(child: ListView(children: active == 0 ? [
            const ListTile(subtitle: Text('Дополнения могут увеличить стоимость блюда')),
            if (groups.isEmpty) const ListTile(title: Text('Дополнений нет')),
            for (final group in groups) ...[
              ListTile(title: Text((group['name'] ?? 'Дополнения').toString(),
                style: const TextStyle(fontWeight: FontWeight.bold)),
                subtitle: Text(FoodOrderLogic.number(group['min_select']) > 0
                  ? 'Обязательный выбор' : 'По желанию')),
              for (final raw in group['options'] as List? ?? [])
                Builder(builder: (ctx) {
                  final o = Map<String, dynamic>.from(raw as Map);
                  final id = int.tryParse(o['id'].toString()) ?? -1;
                  return CheckboxListTile(
                    title: Text((o['name'] ?? '').toString()),
                    subtitle: FoodOrderLogic.number(o['price_delta']) == 0 ? null
                      : Text('+' + money(o['price_delta'])),
                    value: additions.contains(id),
                    onChanged: (yes) => update(() {
                      if (yes == true) {
                        final max = FoodOrderLogic.number(group['max_select']).toInt();
                        final count = (group['options'] as List? ?? []).where((o) =>
                          additions.contains(int.tryParse((o as Map)['id'].toString()))).length;
                        if (max > 0 && count >= max) { toast('Достигнут лимит группы'); return; }
                        additions.add(id);
                      } else { additions.remove(id); }
                    }),
                  );
                }),
            ],
          ] : [
            const ListTile(subtitle: Text('Убранные ингредиенты не списываются по техкарте; цена не меняется')),
            for (final i in ingredients) CheckboxListTile(
              title: Text('Без ' + (i['name'] ?? '').toString()),
              value: removals.contains(int.tryParse(i['item_id'].toString())),
              onChanged: (yes) => update(() {
                final id = int.tryParse(i['item_id'].toString()) ?? -1;
                if (yes == true) { removals.add(id); } else { removals.remove(id); }
              }),
            ),
          ])),
          SafeArea(top: false, child: Padding(
            padding: const EdgeInsets.all(12),
            child: SizedBox(width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  for (final group in groups) {
                    if (!FoodOrderLogic.groupValid(group, additions)) {
                      update(() => active = 0);
                      toast('Проверьте выбор: ' + (group['name'] ?? '').toString());
                      return;
                    }
                  }
                  Navigator.pop(sheet, FoodOrderLogic.line(item,
                    modifiers: selected,
                    exclusions: ingredients.where((i) =>
                      removals.contains(int.tryParse(i['item_id'].toString()))).toList(),
                  ));
                },
                child: Text('Добавить в заказ · ' + money(
                  FoodOrderLogic.number(item['retail_price']) + extras)),
              ),
            ),
          )),
        ]));
      }),
    );
  }

  Future<Map<String, dynamic>> saveOrder() async {
    if (cart.isEmpty) throw const ApiException('Корзина пуста');
    final result = await ApiService.saveFoodOrder({
      if (orderId != null) 'id': orderId,
      'cart': cart, 'client_id': clientId,
      'table_name': table.text.trim(), 'guest_name': guest.text.trim(),
      'note': note.text.trim(), 'planned_payment_method': payment,
    });
    if (result['success'] != true || result['order'] is! Map) {
      throw ApiException((result['message'] ?? 'Заказ не сохранён').toString());
    }
    final order = Map<String, dynamic>.from(result['order'] as Map);
    if (mounted) setState(() {
      orderId = int.parse(order['id'].toString());
      cart.clear();
      cart.addAll((order['cart'] as List? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map)));
    });
    return order;
  }

  String ticketText(Map<String, dynamic> order, String kind) {
    final out = StringBuffer();
    out.writeln(company);
    out.writeln(kind == 'kitchen' ? 'ЗАКАЗ НА КУХНЮ' : 'ЧЕК ГОСТЮ');
    out.writeln('Заказ №' + order['id'].toString());
    out.writeln('Стол: ' + table.text);
    for (final raw in order['cart'] as List? ?? []) {
      final item = Map<String, dynamic>.from(raw as Map);
      out.writeln((item['name'] ?? 'Позиция').toString() + ' x' +
        (item['qty'] ?? 1).toString());
      for (final raw in item['modifiers'] as List? ?? []) {
        out.writeln(' + ' + ((raw as Map)['name'] ?? '').toString());
      }
      for (final raw in item['excluded_ingredients'] as List? ?? []) {
        out.writeln(' БЕЗ ' + ((raw as Map)['name'] ?? '').toString());
      }
      if (kind == 'precheck') out.writeln(money(item['line_total'] ??
        FoodOrderLogic.number(item['price']) * FoodOrderLogic.number(item['qty'])));
    }
    out.writeln('Комментарий: ' + note.text);
    if (kind == 'precheck') {
      out.writeln('Итого: ' + money(order['total_amount']));
      out.writeln('Оплата: ' + payment);
    }
    return out.toString();
  }

  Future<bool> printPair(Map<String, dynamic> order) async {
    final prefs = await SharedPreferences.getInstance();
    if ((prefs.getString('printer_mac') ?? '').isEmpty) {
      toast('Заказ сохранён. Чеки доступны в истории; Bluetooth-принтер не настроен.');
      return true;
    }
    final kitchenMac = prefs.getString('kitchen_printer_mac');
    if (!await PrinterService.printReceipt(
      text: ticketText(order, 'kitchen'),
      printerMac: kitchenMac == null || kitchenMac.isEmpty
          ? null : kitchenMac,
    )) return false;
    return PrinterService.printReceipt(text: ticketText(order, 'precheck'));
  }

  Future<void> stage() async => runBusy(() async {
    final order = await saveOrder();
    final printed = await printPair(order);
    if (mounted) setState(() => printedPair = printed);
    toast(printed ? 'Заказ сохранён. Кухня и пречек готовы.'
      : 'Заказ сохранён, но печать не завершена. Оплата не проведена.');
    await loadOrders();
  });

  Future<void> document(int id, String kind, {bool share = false}) async =>
    runBusy(() async {
      final bytes = await ApiService.downloadPdf(ApiService.foodTicketPdfPath(id, kind));
      if (share) {
        await Printing.sharePdf(bytes: bytes,
          filename: 'nika-order-' + id.toString() + '-' + kind + '.pdf');
      } else {
        await Printing.layoutPdf(onLayout: (_) async => bytes,
          name: 'Заказ №' + id.toString());
      }
    });

  Future<void> openOrder(int id) async => runBusy(() async {
    final data = await ApiService.foodOrder(id);
    final order = Map<String, dynamic>.from(data['order'] as Map);
    if (order['status'] != 'open') throw const ApiException('Заказ уже закрыт');
    if (!mounted) return;
    setState(() {
      orderId = id; cart.clear();
      cart.addAll((order['cart'] as List? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map)));
      table.text = (order['table_name'] ?? '').toString();
      guest.text = (order['guest_name'] ?? '').toString();
      note.text = (order['note'] ?? '').toString();
      payment = (order['planned_payment_method'] ?? 'cash').toString();
      clientId = int.tryParse((order['client_id'] ?? '').toString());
      clientName = clientId == null ? 'Частное лицо' : 'Клиент №' + clientId.toString();
      printedPair = false; view = 'order';
    });
  });

  Future<void> cancelOrder(Map<String, dynamic> order) async {
    final ok = await showDialog<bool>(context: context, builder: (c) => AlertDialog(
      title: const Text('Отменить неоплаченный заказ?'),
      content: const Text('Если кухня уже получила чек, предупредите сотрудников.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Назад')),
        FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Отменить')),
      ],
    ));
    if (ok != true) return;
    await runBusy(() async {
      final id = int.parse(order['id'].toString());
      final result = await ApiService.cancelFoodOrder(id);
      if (result['success'] != true) throw ApiException(
        (result['message'] ?? 'Заказ не отменён').toString());
      if (orderId == id) resetOrder();
      await loadOrders();
      toast('Заказ отменён без оплаты и списания склада.');
    });
  }

  Future<void> externalPayment() async {
    final order = await saveOrder();
    if (!mounted) return;
    final controller = TextEditingController();
    final receipt = await showDialog<String>(context: context,
      builder: (c) => AlertDialog(
        title: const Text('Чек внешней ККМ'),
        content: TextField(controller: controller,
          decoration: const InputDecoration(labelText: 'Номер фискального чека')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(c, controller.text.trim()),
            child: const Text('Подтвердить')),
        ],
      ),
    );
    controller.dispose();
    if (receipt == null || receipt.isEmpty) return;
    final result = await ApiService.confirmExternalFoodPayment(
      int.parse(order['id'].toString()), receipt);
    if (result['success'] != true) throw ApiException(
      (result['message'] ?? 'Ошибка ККМ').toString());
    resetOrder();
    await loadOrders();
    toast('Внешний чек записан. Продажа и склад Nika не изменены.');
  }

  Future<void> checkout() async {
    if (cart.isEmpty || busy || uncertain) return;
    final amount = total;
    final input = TextEditingController(text: amount.toStringAsFixed(0));
    final received = payment == 'cash'
      ? await showDialog<double>(context: context, builder: (c) => AlertDialog(
          title: const Text('Получено наличными'),
          content: TextField(controller: input,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(helperText: 'К оплате: ' + money(amount))),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c), child: const Text('Назад')),
            FilledButton(onPressed: () => Navigator.pop(c,
              FoodOrderLogic.number(input.text)), child: const Text('Далее')),
          ],
        ))
      : null;
    input.dispose();
    if (!mounted || (payment == 'cash' && received == null)) return;
    if (payment == 'cash' && (received ?? 0) < amount) {
      toast('Недостаточно наличных'); return;
    }
    final ok = await showDialog<bool>(context: context, builder: (c) => AlertDialog(
      title: const Text('Подтвердить оплату?'),
      content: Text(payment == 'kaspi'
        ? 'Сумма будет отправлена на Kaspi POS. При тайм-ауте не запускайте оплату повторно.'
        : payment == 'card'
          ? 'Подтвердите, что деньги уже получены банковским терминалом.'
          : 'Сдача: ' + money((received ?? amount) - amount)),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Назад')),
        FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Подтвердить')),
      ],
    ));
    if (ok != true) return;

    await runBusy(() async {
      final order = await saveOrder();
      final id = int.parse(order['id'].toString());
      final prefs = await SharedPreferences.getInstance();
      if ((prefs.getString('printer_mac') ?? '').isNotEmpty && !printedPair) {
        if (!await printPair(order)) {
          throw const ApiException('Не удалось распечатать оба чека. Оплата не проведена.');
        }
        printedPair = true;
      }
      String? txId;
      String? posMethod;
      if (payment == 'kaspi') {
        final start = await KaspiPosService.startPayment(amount.round());
        if (start['statusCode'] != 0) throw ApiException(
          (start['message'] ?? 'Kaspi POS не принял оплату').toString());
        final pid = (start['data']?['processId'] ?? '').toString();
        if (pid.isEmpty) throw const ApiException('Kaspi POS не вернул processId');
        if (mounted) setState(() => uncertain = true);
        for (var n = 0; n < 60; n++) {
          await Future<void>.delayed(const Duration(seconds: 2));
          final status = await KaspiPosService.getStatus(pid);
          final data = status['data'] is Map
              ? Map<String, dynamic>.from(status['data'] as Map)
              : <String, dynamic>{};
          if (data['status'] == 'fail') {
            if (mounted) setState(() => uncertain = false);
            throw const ApiException('Kaspi POS отменил платёж');
          }
          if (data['status'] == 'success') {
            txId = (data['transactionId'] ?? '').toString();
            posMethod = (data['chequeInfo'] is Map
              ? (data['chequeInfo']['method'] ?? 'qr') : 'qr').toString();
            break;
          }
        }
        if (txId == null || txId.isEmpty) {
          throw const ApiException('Нет подтверждения Kaspi POS. Проверьте терминал до повтора.');
        }
      }
      Map<String, dynamic> result;
      try {
        result = await ApiService.payFoodOrder(
          foodOrderId: id, cart: cart, method: payment,
          operationId: 'food-' + DateTime.now().microsecondsSinceEpoch.toString() +
            '-' + Random.secure().nextInt(0x7fffffff).toString(),
          clientId: clientId, transactionId: txId, kaspiMethod: posMethod,
          cashReceived: received,
        );
      } catch (_) {
        if (mounted) setState(() => uncertain = true);
        rethrow;
      }
      if (result['success'] != true) {
        if (mounted) setState(() => uncertain = true);
        throw ApiException((result['error'] ?? 'Продажа не подтверждена').toString());
      }
      final saleId = int.tryParse((result['sale_id'] ?? '').toString());
      final fiscalized = result['fiscalized'] == true;
      if (!mounted) return;
      resetOrder();
      await loadOrders();
      toast(fiscalized ? 'Заказ оплачен, чек reKassa сформирован'
        : 'Продажа сохранена, но чек не фискализирован. Не оплачивайте повторно!');
      if (saleId != null && mounted) {
        await Navigator.push(context, MaterialPageRoute(
          builder: (_) => CheckScreen(saleId: saleId, autoPrint: fiscalized)));
      }
    });
  }

  Future<void> checkUncertain() async {
    if (orderId == null) return;
    try {
      final data = await ApiService.foodOrder(orderId!);
      if (!mounted) return;
      if (data['order']?['status'] != 'open') {
        resetOrder(); await loadOrders();
        toast('Заказ уже закрыт. Проверьте историю.');
      } else {
        toast('Заказ открыт. Проверьте результаты оплаты в Kaspi POS вручную.');
      }
    } catch (e) { toast(readableError(e)); }
  }

  Widget menuView() => Column(children: [
    Padding(padding: const EdgeInsets.all(10), child: TextField(
      controller: search,
      decoration: const InputDecoration(prefixIcon: Icon(Icons.search),
        hintText: 'Поиск по меню'),
      onChanged: (_) {
        debounce?.cancel();
        debounce = Timer(const Duration(milliseconds: 300), loadMenu);
      },
    )),
    Expanded(child: RefreshIndicator(
      onRefresh: loadMenu,
      child: ListView(
        children: [
          for (final item in menu) Card(child: ListTile(
            leading: Icon(item['item_type'] == 'dish'
              ? Icons.restaurant : Icons.local_drink),
            title: Text((item['name'] ?? '').toString()),
            subtitle: Text(item['item_type'] == 'dish' ? 'Блюдо' : 'Товар'),
            trailing: Text(money(item['retail_price'])),
            onTap: busy ? null : () => addItem(item),
          )),
          if (menuMore) TextButton(
            onPressed: () => loadMenu(more: true),
            child: const Text('Показать ещё')),
        ],
      ),
    )),
  ]);

  Widget orderView() => Column(children: [
    if (uncertain) Card(child: ListTile(
      title: const Text('Оплата требует проверки'),
      subtitle: const Text('Не проводите оплату повторно до проверки терминала.'),
      trailing: TextButton(onPressed: checkUncertain, child: const Text('Проверить')),
    )),
    Padding(padding: const EdgeInsets.all(10), child: Column(children: [
      Text(orderId == null ? 'Новый заказ' : 'Заказ №' + orderId.toString(),
        style: Theme.of(context).textTheme.titleLarge),
      Row(children: [
        Expanded(child: TextField(controller: table,
          decoration: const InputDecoration(labelText: 'Стол / номер'),
          onChanged: (_) => setState(changed))),
        const SizedBox(width: 8),
        Expanded(child: TextField(controller: guest,
          decoration: const InputDecoration(labelText: 'Гость'),
          onChanged: (_) => setState(changed))),
      ]),
      TextField(controller: note,
        decoration: const InputDecoration(labelText: 'Комментарий кухне'),
        onChanged: (_) => setState(changed)),
      ListTile(
        title: Text(clientName), leading: const Icon(Icons.person_outline),
        trailing: const Icon(Icons.chevron_right),
        onTap: busy ? null : chooseClient,
      ),
    ])),
    Expanded(child: ListView.builder(
      itemCount: cart.length,
      itemBuilder: (c, index) {
        final item = cart[index];
        return Card(child: ListTile(
          title: Text((item['name'] ?? '').toString()),
          subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final e in item['modifiers'] as List? ?? [])
              Text('＋ ' + ((e as Map)['name'] ?? '').toString()),
            for (final e in item['excluded_ingredients'] as List? ?? [])
              Text('− ' + ((e as Map)['name'] ?? '').toString()),
            Row(children: [
              IconButton(icon: const Icon(Icons.remove_circle_outline),
                onPressed: busy ? null : () => setState(() {
                  final qty = FoodOrderLogic.number(item['qty']);
                  if (qty <= 1) { cart.removeAt(index); }
                  else { item['qty'] = qty - 1; item.remove('line_total'); }
                  changed();
                })),
              Text((item['qty'] ?? 1).toString()),
              IconButton(icon: const Icon(Icons.add_circle_outline),
                onPressed: busy ? null : () => setState(() {
                  item['qty'] = FoodOrderLogic.number(item['qty']) + 1;
                  item.remove('line_total'); changed();
                })),
            ]),
          ]),
          trailing: Text(money(FoodOrderLogic.number(item['price']) *
              FoodOrderLogic.number(item['qty']))),
        ));
      },
    )),
    const Divider(height: 1),
    SafeArea(top: false, child: Padding(
      padding: const EdgeInsets.all(10), child: Column(children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          const Text('Итого', style: TextStyle(fontWeight: FontWeight.bold)),
          Text(money(total), style: Theme.of(context).textTheme.titleLarge),
        ]),
        Wrap(spacing: 8, children: [
          for (final (kind, name) in [
            ('cash', 'Наличные'), ('card', 'Карта'), ('kaspi', 'Kaspi POS')])
            ChoiceChip(label: Text(name), selected: payment == kind,
              onSelected: busy ? null : (_) => setState(() {
                payment = kind; changed();
              })),
        ]),
        const SizedBox(height: 6),
        Row(children: [
          Expanded(child: OutlinedButton(
            onPressed: busy || uncertain || cart.isEmpty ? null : stage,
            child: const Text('Оформить заказ'),
          )),
          const SizedBox(width: 6),
          Expanded(child: FilledButton(
            onPressed: busy || uncertain || cart.isEmpty ? null :
              mode == 'external' ? () => runBusy(externalPayment) : checkout,
            child: Text(mode == 'external' ? 'Внешняя ККМ' : 'Подтвердить оплату'),
          )),
        ]),
        if (orderId != null) TextButton.icon(
          onPressed: busy ? null : () async {
            final yes = await showDialog<bool>(context: context, builder: (c) =>
              AlertDialog(title: const Text('Начать новый заказ?'),
                content: const Text('Текущий останется в истории.'),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(c, false),
                    child: const Text('Назад')),
                  FilledButton(onPressed: () => Navigator.pop(c, true),
                    child: const Text('Новый заказ')),
                ]));
            if (yes == true) resetOrder();
          },
          icon: const Icon(Icons.add),
          label: const Text('Новый заказ')),
      ]),
    )),
  ]);

  Widget historyView() => Column(children: [
    SingleChildScrollView(scrollDirection: Axis.horizontal,
      child: Row(children: [
        for (final (key, label) in [
          ('all', 'Все'), ('open', 'Ожидают'), ('paid', 'Оплачены'),
          ('refunded', 'Возвраты'), ('cancelled', 'Отменены'),
          ('external_paid', 'Внешняя ККМ'),
        ]) Padding(padding: const EdgeInsets.all(3),
          child: ChoiceChip(label: Text(label), selected: filter == key,
            onSelected: (_) {
              setState(() => filter = key);
              loadOrders();
            })),
      ])),
    Expanded(child: RefreshIndicator(
      onRefresh: loadOrders,
      child: ListView(children: [
        if (orders.isEmpty) const ListTile(title: Text('История пуста')),
        for (final order in orders) Card(child: Padding(
          padding: const EdgeInsets.all(10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text('Заказ №' + (order['id'] ?? '').toString(),
                style: const TextStyle(fontWeight: FontWeight.bold))),
              Text(money(order['total_amount'])),
            ]),
            Text((order['table_name'] ?? 'Без стола').toString() + ' · ' +
              (order['created_at_display'] ?? '').toString()),
            Text(switch ((order['status'] ?? '').toString()) {
              'open' => 'Ожидает оплаты',
              'paid' => 'Оплачен',
              'refunded' => 'Возврат',
              'cancelled' => 'Отменён',
              'external_paid' => 'Внешняя ККМ',
              _ => (order['status'] ?? '').toString(),
            }),
            Wrap(spacing: 2, children: [
              if (order['status'] == 'open') ...[
                TextButton(onPressed: busy ? null : () =>
                  openOrder(int.parse(order['id'].toString())),
                  child: const Text('Открыть')),
                TextButton(onPressed: busy ? null : () => cancelOrder(order),
                  child: const Text('Отменить')),
              ],
              if (order['status'] == 'paid' && order['sale_id'] != null)
                TextButton(onPressed: busy ? null : () async {
                  await Navigator.push(context, MaterialPageRoute(
                    builder: (_) => SaleDetailScreen(
                      saleId: int.parse(order['sale_id'].toString()))));
                  await loadOrders();
                }, child: const Text('Возврат')),
              TextButton(onPressed: busy ? null : () =>
                document(int.parse(order['id'].toString()), 'kitchen'),
                child: const Text('Кухня')),
              TextButton(onPressed: busy ? null : () =>
                document(int.parse(order['id'].toString()), 'precheck'),
                child: const Text('Пречек')),
              IconButton(onPressed: busy ? null : () =>
                document(int.parse(order['id'].toString()), 'precheck', share: true),
                icon: const Icon(Icons.share_outlined)),
            ]),
          ]),
        )),
        if (ordersMore) TextButton(onPressed: () => loadOrders(more: true),
          child: const Text('Показать ещё')),
      ]),
    )),
  ]);

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Общепит'),
      actions: [IconButton(onPressed: busy ? null : () { loadMenu(); loadOrders(); },
        icon: const Icon(Icons.refresh))]),
    body: loading
      ? const Center(child: CircularProgressIndicator())
      : error != null
        ? Center(child: Text(error!))
        : Column(children: [
            Row(children: [
              for (final (key, label, icon) in [
                ('menu', 'Меню', Icons.restaurant_menu),
                ('order', 'Заказ', Icons.shopping_cart),
                ('history', 'История', Icons.history),
              ]) Expanded(child: Padding(padding: const EdgeInsets.all(3),
                child: FilledButton.tonalIcon(
                  onPressed: () => setState(() => view = key),
                  icon: Icon(icon, size: 16),
                  label: Text(label),
                ))),
            ]),
            if (busy) const LinearProgressIndicator(),
            Expanded(child: switch (view) {
              'menu' => menuView(),
              'order' => orderView(),
              _ => historyView(),
            }),
          ]),
  );
}
