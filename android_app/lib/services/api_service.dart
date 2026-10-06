import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'offline_store.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;

  const ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

class ApiService {
  static const String baseUrl = 'https://www.nikabusiness.com';
  static const Duration _timeout = Duration(seconds: 30);

  static String? _cookie;

  static String? get sessionCookie => _cookie;

  static Map<String, String> get _headers => {
        'Accept': 'application/json',
        'Content-Type': 'application/json; charset=utf-8',
        if (_cookie != null && _cookie!.isNotEmpty) 'Cookie': _cookie!,
      };

  static Map<String, String> get headers => _headers;

  static Uri _uri(String path, [Map<String, String?>? query]) {
    final normalized = path.startsWith('/') ? path : '/$path';
    final values = <String, String>{};
    query?.forEach((key, value) {
      if (value != null && value.isNotEmpty) values[key] = value;
    });
    return Uri.parse('$baseUrl$normalized').replace(
      queryParameters: values.isEmpty ? null : values,
    );
  }

  static Future<void> saveCookie(String cookie) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('session_cookie', cookie);
    _cookie = cookie;
  }

  static Future<void> loadCookie() async {
    final prefs = await SharedPreferences.getInstance();
    _cookie = prefs.getString('session_cookie');
  }

  static Future<bool> isLoggedIn() async {
    await loadCookie();
    if (_cookie != null && _cookie!.isNotEmpty) return true;

    final prefs = await SharedPreferences.getInstance();
    return (prefs.getBool('logged_in') ?? false) &&
        prefs.getInt('offline_company_id') != null;
  }

  static Future<void> _clearServerSession() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('session_cookie');
    _cookie = null;
  }

  static Future<void> logout() async {
    await _clearServerSession();
    await OfflineStore.instance.clearActiveIdentity();
  }

  static Future<bool> _persistOfflineIdentity(
    Map<String, dynamic> result,
  ) async {
    final rawUser = result['user'];
    final user = rawUser is Map
        ? Map<String, dynamic>.from(rawUser)
        : <String, dynamic>{};

    final companyId = int.tryParse(
      '${result['company_id'] ?? user['company_id'] ?? ''}',
    );
    final userId = int.tryParse(
      '${result['user_id'] ?? user['id'] ?? ''}',
    );

    if (companyId == null ||
        companyId <= 0 ||
        userId == null ||
        userId <= 0) {
      return false;
    }

    await OfflineStore.instance.setIdentity(
      companyId: companyId,
      userId: userId,
    );
    return true;
  }

  static Future<bool> ensureOfflineIdentity() async {
    final companyId = await OfflineStore.instance.companyId;
    final userId = await OfflineStore.instance.userId;
    if (companyId != null &&
        companyId > 0 &&
        userId != null &&
        userId > 0) {
      return true;
    }

    if (_cookie == null || _cookie!.isEmpty) {
      await loadCookie();
    }
    if (_cookie == null || _cookie!.isEmpty) return false;

    try {
      final result = Map<String, dynamic>.from(
        await _request(
          'GET',
          '/api/mobile/profile',
          timeout: const Duration(seconds: 8),
        ),
      );
      final restored = await _persistOfflineIdentity(result);
      if (restored) {
        await OfflineStore.instance.cacheSnapshot('mobile_profile', result);
      }
      return restored;
    } on ApiException {
      return false;
    } catch (_) {
      return false;
    }
  }

  static String _errorMessage(dynamic decoded, int statusCode) {
    if (decoded is Map) {
      for (final key in const ['error', 'message', 'detail']) {
        final value = decoded[key];
        if (value != null && value.toString().trim().isNotEmpty) {
          return value is String ? value : jsonEncode(value);
        }
      }
    }
    if (statusCode == 401) return 'Сессия истекла. Войдите снова';
    if (statusCode == 403) return 'Недостаточно прав для этой операции';
    if (statusCode == 404) return 'Функция не найдена на сервере';
    return 'Ошибка сервера ($statusCode)';
  }

  static Future<dynamic> _request(
    String method,
    String path, {
    Map<String, String?>? query,
    Object? body,
    Duration timeout = _timeout,
  }) async {
    final uri = _uri(path, query);
    late http.Response response;

    try {
      switch (method) {
        case 'POST':
          response = await http
              .post(uri, headers: _headers, body: jsonEncode(body ?? {}))
              .timeout(timeout);
          break;
        case 'PATCH':
          response = await http
              .patch(uri, headers: _headers, body: jsonEncode(body ?? {}))
              .timeout(timeout);
          break;
        case 'PUT':
          response = await http
              .put(uri, headers: _headers, body: jsonEncode(body ?? {}))
              .timeout(timeout);
          break;
        case 'DELETE':
          response = await http
              .delete(uri, headers: _headers, body: jsonEncode(body ?? {}))
              .timeout(timeout);
          break;
        default:
          response = await http.get(uri, headers: _headers).timeout(timeout);
      }
    } catch (_) {
      throw const ApiException('Нет связи с сервером. Проверьте интернет');
    }

    dynamic decoded;
    if (response.body.trim().isNotEmpty) {
      try {
        decoded = jsonDecode(utf8.decode(response.bodyBytes));
      } catch (_) {
        decoded = null;
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      if (response.statusCode == 401) await _clearServerSession();
      throw ApiException(
        _errorMessage(decoded, response.statusCode),
        statusCode: response.statusCode,
      );
    }

    if (decoded == null) {
      throw const ApiException('Сервер вернул некорректный ответ');
    }
    return decoded;
  }

  static bool _retryableQueueError(ApiException error) {
    final status = error.statusCode;
    return status == null || status == 401 || status >= 500;
  }

  static Future<Map<String, dynamic>> _queuedPost({
    required String operationType,
    required String path,
    required Map<String, dynamic> body,
    required Map<String, dynamic> queuedResult,
    Future<void> Function()? onQueued,
    Duration timeout = const Duration(seconds: 30),
  }) async {
    await ensureOfflineIdentity();

    final operationId = await OfflineStore.instance.enqueue(
      operationType: operationType,
      method: 'POST',
      path: path,
      body: body,
    );
    final payload = <String, dynamic>{...body, 'operation_id': operationId};

    try {
      final result = Map<String, dynamic>.from(
        await _request('POST', path, body: payload, timeout: timeout),
      );
      if (result['pending'] == true) {
        await OfflineStore.instance.markOperationPending(operationId);
      } else {
        await OfflineStore.instance.markOperationSynced(operationId);
      }
      return result;
    } on ApiException catch (error) {
      if (_retryableQueueError(error)) {
        await OfflineStore.instance.markOperationPending(
          operationId,
          error: error.message,
        );
        if (onQueued != null) await onQueued();
        return {
          ...queuedResult,
          'success': true,
          'queued': true,
          'operation_id': operationId,
        };
      }
      await OfflineStore.instance.markOperationError(
        operationId,
        error.message,
      );
      rethrow;
    }
  }

  static Future<Map<String, dynamic>> replayQueuedOperation(
    Map<String, dynamic> operation,
  ) async {
    final method = '${operation['method'] ?? 'POST'}'.toUpperCase();
    final path = '${operation['path'] ?? ''}';
    final operationId = '${operation['operation_id'] ?? ''}';
    final rawBody = operation['body'];
    final body = rawBody is Map
        ? Map<String, dynamic>.from(rawBody)
        : <String, dynamic>{};
    body['operation_id'] = operationId;

    final result = await _request(
      method,
      path,
      body: body,
      timeout: const Duration(seconds: 60),
    );
    return result is Map
        ? Map<String, dynamic>.from(result)
        : <String, dynamic>{'success': true};
  }

  static Future<Map<String, dynamic>> login(
    String username,
    String password,
  ) async {
    final uri = _uri('/api/login');
    try {
      final response = await http
          .post(
            uri,
            headers: const {
              'Accept': 'application/json',
              'Content-Type': 'application/json; charset=utf-8',
            },
            body: jsonEncode({'username': username, 'password': password}),
          )
          .timeout(_timeout);
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! Map) {
        throw const ApiException('Некорректный ответ сервера');
      }
      final result = Map<String, dynamic>.from(decoded);
      final rawCookie = response.headers['set-cookie'];
      if (response.statusCode >= 200 &&
          response.statusCode < 300 &&
          result['success'] == true) {
        if (rawCookie != null && rawCookie.trim().isNotEmpty) {
          await saveCookie(rawCookie.split(';').first);
        }
        await _persistOfflineIdentity(result);
      }
      return result;
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ApiException('Не удалось подключиться к серверу');
    }
  }

  static Future<Map<String, dynamic>> mobileProfile({bool forceRemote = false}) async {
    final cached = await OfflineStore.instance.snapshot('mobile_profile');
    if (!forceRemote && cached is Map) return Map<String, dynamic>.from(cached);
    try {
      final result = Map<String, dynamic>.from(await _request(
        'GET', '/api/mobile/profile', timeout: const Duration(seconds: 8),
      ));
      await _persistOfflineIdentity(result);
      await OfflineStore.instance.cacheSnapshot('mobile_profile', result);
      return result;
    } on ApiException {
      if (cached is Map) return Map<String, dynamic>.from(cached);
      rethrow;
    }
  }

  static Future<Map<String, dynamic>> interfaceSettings({bool forceRemote = false}) async {
    final cached = await OfflineStore.instance.snapshot('interface_settings');
    if (!forceRemote && cached is Map) return Map<String, dynamic>.from(cached);
    try {
      final result = Map<String, dynamic>.from(await _request(
        'GET', '/api/mobile/interface-settings', timeout: const Duration(seconds: 8),
      ));
      await OfflineStore.instance.cacheSnapshot('interface_settings', result);
      return result;
    } on ApiException {
      if (cached is Map) return Map<String, dynamic>.from(cached);
      rethrow;
    }
  }

  static Future<Map<String, dynamic>> saveInterfaceSettings({
    required bool showCatalogImages,
  }) async =>
      Map<String, dynamic>.from(
        await _request(
          'POST',
          '/api/mobile/interface-settings',
          body: {'show_catalog_images': showCatalogImages},
        ),
      );

  static Future<Map<String, dynamic>> schoolLeaders() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/school/leaders'));

  static Future<Map<String, dynamic>> saveSchoolLeader(Map<String, dynamic> data, {int? id}) async =>
      Map<String, dynamic>.from(await _request(id == null ? 'POST' : 'PATCH',
          id == null ? '/api/mobile/school/leaders' : '/api/mobile/school/leaders/$id',
          body: data));

  static Future<void> deleteSchoolLeader(int id) async {
    await _request('DELETE', '/api/mobile/school/leaders/$id');
  }

  static Future<Map<String, dynamic>> schoolMeals(String date) async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/school/meals?date=$date'));

  static Future<Map<String, dynamic>> saveSchoolMeals(Map<String, dynamic> data) async =>
      Map<String, dynamic>.from(await _request('POST', '/api/mobile/school/meals', body: data));

  static Future<Map<String, dynamic>> saveSchoolPrices(Map<String, dynamic> data) async =>
      Map<String, dynamic>.from(await _request('POST', '/api/mobile/school/prices', body: data));

  static Future<Map<String, dynamic>> syncHealth() async =>
      Map<String, dynamic>.from(
        await _request(
          'GET',
          '/api/mobile/health',
          timeout: const Duration(seconds: 4),
        ),
      );

  static Future<Set<String>> getModules({bool forceRemote = false}) async {
    final cached = await OfflineStore.instance.snapshot('modules');
    if (!forceRemote && cached is List) {
      return cached.map((item) => item.toString()).toSet();
    }
    try {
      final result = Map<String, dynamic>.from(await _request(
        'GET', '/api/mobile/modules', timeout: const Duration(seconds: 8),
      ));
      final modules = List<dynamic>.from(result['modules'] ?? const [])
          .map((item) => item.toString()).toSet();
      await OfflineStore.instance.cacheSnapshot('modules', modules.toList());
      return modules;
    } on ApiException {
      if (cached is List) return cached.map((item) => item.toString()).toSet();
      rethrow;
    }
  }

  static Future<Map<String, dynamic>> dashboard({bool forceRemote = false}) async {
    final cached = await OfflineStore.instance.snapshot('dashboard');
    if (!forceRemote && cached is Map) return Map<String, dynamic>.from(cached);
    try {
      final result = Map<String, dynamic>.from(await _request(
        'GET', '/api/dashboard', timeout: const Duration(seconds: 8),
      ));
      await OfflineStore.instance.cacheSnapshot('dashboard', result);
      return result;
    } on ApiException {
      if (cached is Map) return Map<String, dynamic>.from(cached);
      rethrow;
    }
  }

  static Future<List<dynamic>> getItems({
    String type = 'all',
    String category = 'all',
    bool forceRemote = false,
  }) async {
    final cached = await OfflineStore.instance.items(type: type, category: category);
    if (!forceRemote && cached.isNotEmpty) return cached;
    try {
      final result = List<dynamic>.from(await _request(
        'GET', '/api/items', timeout: const Duration(seconds: 8),
        query: {
          if (type != 'all') 'type': type,
          if (category != 'all') 'category': category,
        },
      ));
      await OfflineStore.instance.cacheItems(
        result, replaceAll: type == 'all' && category == 'all',
      );
      return result;
    } on ApiException {
      if (cached.isNotEmpty) return cached;
      rethrow;
    }
  }

  static Future<List<dynamic>> searchItems(String query) async {
    try {
      final result = await _request(
        'GET',
        '/api/items/search',
        query: {'q': query},
      );
      final items = result is Map
          ? List<dynamic>.from(result['items'] ?? const [])
          : List<dynamic>.from(result as List);
      await OfflineStore.instance.cacheItems(items);
      return items;
    } on ApiException catch (error) {
      if (error.statusCode != null) rethrow;
      final cached = await OfflineStore.instance.items(query: query);
      if (cached.isNotEmpty) return cached;
      rethrow;
    }
  }

  static Future<Map<String, dynamic>> barcode(String barcode) async {
    final cached = await OfflineStore.instance.findItem(barcode);
    if (cached != null) {
      return OfflineStore.instance.barcodeResult(cached, barcode);
    }

    try {
      final result = Map<String, dynamic>.from(await _request(
        'POST',
        '/api/barcode',
        body: {'barcode': barcode},
      ));
      if (result['found'] == true) {
        await OfflineStore.instance.cacheItems([result]);
      }
      return result;
    } on ApiException catch (error) {
      if (error.statusCode != null) rethrow;
      return {'found': false, 'offline': true};
    }
  }

  static Future<Map<String, dynamic>> paySale({
    required List cart,
    int? clientId,
    String? paymentMethod,
    String? kaspiTransactionId,
    String? kaspiMethod,
  }) async {
    final cartSnapshot = cart
        .map((item) => item is Map ? Map<String, dynamic>.from(item) : item)
        .toList();
    return _queuedPost(
      operationType: 'sale',
      path: '/sales/pay',
      timeout: const Duration(seconds: 60),
      body: {
        'client_id': clientId,
        'payment_method': paymentMethod ?? 'cash',
        'kaspi_transaction_id': kaspiTransactionId,
        'kaspi_method': kaspiMethod,
        'cart': cartSnapshot,
      },
      queuedResult: {
        'sale_id': null,
        'fiscalized': false,
        'rekassa_required': true,
        'rekassa': {
          'status': 'PENDING',
          'message': 'Ожидает синхронизации и фискализации',
        },
      },
      onQueued: () => OfflineStore.instance.applySaleStockDelta(cartSnapshot),
    );
  }

  static Future<Map<String, dynamic>> createInvoiceSale({
    required List cart,
    int? clientId,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/sales/create-invoice',
        timeout: const Duration(seconds: 60),
        body: {
          'client_id': clientId,
          'cart': cart,
        },
      ));

  static Future<Map<String, dynamic>> markInvoicePaid(int saleId) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/sales/mark-paid',
        body: {'sale_id': saleId},
      ));

  static String saleDocumentPdfPath(String type, int saleId) =>
      '/docs/pdf/$type/$saleId';


  static Future<List<dynamic>> getSalesHistory({
    int? shiftNumber,
    String? serialNumber,
    bool allHistory = false,
    int page = 0,
    int size = 50,
    String? queryText,
    String kind = 'all',
    String? dateFrom,
    String? dateTo,
  }) async =>
      List<dynamic>.from(await _request(
        'GET',
        '/api/sales/history',
        query: {
          'shift_number': shiftNumber?.toString(),
          'serial_number': serialNumber,
          if (allHistory) 'scope': 'all',
          if (queryText != null && queryText.trim().isNotEmpty) 'q': queryText.trim(),
          if (kind != 'all') 'kind': kind,
          if (dateFrom != null && dateFrom.isNotEmpty) 'date_from': dateFrom,
          if (dateTo != null && dateTo.isNotEmpty) 'date_to': dateTo,
          'page': '$page',
          'size': '$size',
        },
      ));

  static Future<List<dynamic>> getClients({
    bool deleted = false,
    bool forceRemote = false,
  }) async {
    final cached = await OfflineStore.instance.clients(deleted: deleted);
    if (!forceRemote && cached.isNotEmpty) return cached;
    try {
      final result = List<dynamic>.from(await _request(
        'GET', '/api/clients', timeout: const Duration(seconds: 8),
        query: {if (deleted) 'deleted': 'true'},
      ));
      await OfflineStore.instance.cacheClients(
        result, deleted: deleted, replaceAll: true,
      );
      return result;
    } on ApiException {
      if (cached.isNotEmpty) return cached;
      rethrow;
    }
  }

  static Future<Map<String, dynamic>> getClient(int id) async =>
      Map<String, dynamic>.from(await _request('GET', '/api/client/$id'));

  static Future<Map<String, dynamic>> getSale(int saleId) async =>
      Map<String, dynamic>.from(await _request('GET', '/api/sale/$saleId'));

  static Future<List<dynamic>> getStock({bool forceRemote = false}) async {
    final cached = await OfflineStore.instance.stock();
    if (!forceRemote && cached.isNotEmpty) return cached;
    try {
      final result = List<dynamic>.from(await _request(
        'GET', '/api/stock', timeout: const Duration(seconds: 8),
      ));
      await OfflineStore.instance.cacheStock(result, replaceAll: true);
      return result;
    } on ApiException {
      if (cached.isNotEmpty) return cached;
      rethrow;
    }
  }

  static Future<List<dynamic>> getStockMovements({bool forceRemote = false}) async {
    final cached = await OfflineStore.instance.snapshot('stock_movements');
    if (!forceRemote && cached is List) return List<dynamic>.from(cached);
    try {
      final result = List<dynamic>.from(await _request(
        'GET', '/api/stock/movements', timeout: const Duration(seconds: 8),
      ));
      await OfflineStore.instance.cacheSnapshot('stock_movements', result);
      return result;
    } on ApiException {
      if (cached is List) return List<dynamic>.from(cached);
      return const [];
    }
  }

  static Future<Map<String, dynamic>> stockIncome({
    required int itemId,
    required double quantity,
    required double price,
    String comment = '',
    bool updateRetail = false,
  }) async =>
      _queuedPost(
        operationType: 'stock_income',
        path: '/api/stock/income',
        body: {
          'item_id': itemId,
          'quantity': quantity,
          'price': price,
          'comment': comment,
          'update_retail': updateRetail,
        },
        queuedResult: {
          'movement_id': null,
          'pricing': <String, dynamic>{},
        },
        onQueued: () => OfflineStore.instance.applyStockDelta(itemId, quantity),
      );

  static Future<Map<String, dynamic>> stockIncomeWithSupplier({
    required int itemId,
    required int supplierId,
    required double quantity,
    required double price,
    String comment = '',
    bool updateRetail = false,
  }) async =>
      _queuedPost(
        operationType: 'stock_income_supplier',
        path: '/api/mobile/stock/income/supplier',
        body: {
          'item_id': itemId,
          'supplier_id': supplierId,
          'quantity': quantity,
          'price': price,
          'comment': comment,
          'update_retail': updateRetail,
        },
        queuedResult: {
          'movement_id': null,
          'supplier_id': supplierId,
          'pricing': <String, dynamic>{},
        },
        onQueued: () => OfflineStore.instance.applyStockDelta(itemId, quantity),
      );

  static Future<Map<String, dynamic>> stockWriteoff({
    required int itemId,
    required double quantity,
    String comment = '',
  }) async =>
      _queuedPost(
        operationType: 'stock_writeoff',
        path: '/api/stock/writeoff',
        body: {
          'item_id': itemId,
          'quantity': quantity,
          'comment': comment,
        },
        queuedResult: {'movement_id': null},
        onQueued: () => OfflineStore.instance.applyStockDelta(itemId, -quantity),
      );

  static Future<Map<String, dynamic>> getBarcodeInfo(
    String barcode, {
    String itemType = 'product',
  }) async {
    final cached = await OfflineStore.instance.findItem(barcode);
    if (cached != null &&
        (itemType == 'product'
            ? '${cached['item_type'] ?? 'product'}' != 'service'
            : '${cached['item_type'] ?? ''}' == itemType)) {
      final result = OfflineStore.instance.barcodeResult(cached, barcode);
      result['found'] = true;
      return result;
    }

    try {
      final result = Map<String, dynamic>.from(
        await _request(
          'GET',
          '/api/barcode-info/$barcode',
          query: {'item_type': itemType},
        ),
      );
      return result;
    } on ApiException catch (error) {
      if (error.statusCode != null) rethrow;
      return {'found': false, 'offline': true};
    }
  }

  static Future<Map<String, dynamic>> createItem({
    required String name,
    required String barcode,
    required double purchasePrice,
    required double retailPrice,
    required double quantity,
    String category = '',
    String unit = 'шт',
    String description = '',
    String gtin = '',
    String ntin = '',
    bool isMarked = false,
    String itemType = 'product',
    String serviceSaleMode = 'order',
    double wholesalePrice = 0,
    int discountPercent = 0,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/items/create',
        body: {
          'name': name,
          'barcode': barcode,
          'purchase_price': purchasePrice,
          'retail_price': retailPrice,
          'quantity': quantity,
          'category': category,
          'unit': unit,
          'description': description,
          'gtin': gtin,
          'ntin': ntin,
          'is_marked': isMarked,
          'item_type': itemType,
          'service_sale_mode': serviceSaleMode,
          'wholesale_price': wholesalePrice,
          'discount_percent': discountPercent,
        },
      ));

  static Future<Map<String, dynamic>> updateItem(
    int id,
    Map<String, dynamic> data,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'PATCH',
        '/api/items/$id',
        body: data,
      ));

  static Future<void> deleteItem(int id) async {
    await _request('DELETE', '/api/items/$id');
  }

  static Future<List<dynamic>> getCategories({
    String type = 'all',
    bool forceRemote = false,
  }) async {
    final cacheKey = 'categories:$type';
    final cached = await OfflineStore.instance.snapshot(cacheKey);
    if (!forceRemote && cached is List) return List<dynamic>.from(cached);
    try {
      final result = List<dynamic>.from(await _request(
        'GET', '/api/categories', timeout: const Duration(seconds: 8),
        query: {if (type != 'all') 'type': type},
      ));
      await OfflineStore.instance.cacheSnapshot(cacheKey, result);
      if (type == 'all') {
        await OfflineStore.instance.cacheSnapshot('categories:all', result);
      }
      return result;
    } on ApiException {
      if (cached is List) return List<dynamic>.from(cached);
      return const [];
    }
  }

  static Future<Map<String, dynamic>> createCategory({
    required String name,
    required String type,
    double markup = 0,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/add_category',
        body: {'name': name, 'category_type': type, 'markup': markup},
      ));

  static Future<Map<String, dynamic>> updateCategory(
    int id, {
    required String name,
    required String type,
    double markup = 0,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/edit_category/$id',
        body: {'name': name, 'category_type': type, 'markup': markup},
      ));

  static Future<void> deleteCategory(int id) async {
    await _request('POST', '/delete_category/$id');
  }

  static Future<Map<String, dynamic>> createClient({
    required String fullName,
    required String phone,
    String iin = '',
    String companyName = '',
    String address = '',
    String comment = '',
    String status = 'Новый',
    String category = 'Клиент',
    String payment = 'Не оплачено',
    String contractNumber = '',
    String contractDate = '',
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/clients/create',
        body: {
          'full_name': fullName,
          'phone': phone,
          'iin': iin,
          'company_name': companyName,
          'address': address,
          'comment': comment,
          'status': status,
          'category': category,
          'payment': payment,
          'contract_number': contractNumber,
          'contract_date': contractDate,
        },
      ));

  static Future<Map<String, dynamic>> lookupClient(String identifier) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/clients/lookup',
        body: {'identifier': identifier},
      ));

  static Future<Map<String, dynamic>> updateClient(
    int id,
    Map<String, dynamic> data,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'PATCH',
        '/api/client/$id/update',
        body: data,
      ));

  static Future<void> deleteClient(int id) async {
    await _request('POST', '/api/client/$id/delete');
  }

  static Future<void> restoreClient(int id) async {
    await _request('POST', '/api/client/$id/restore');
  }

  static Future<void> deleteClientPermanently(int id) async {
    await _request('DELETE', '/api/client/$id/permanent');
  }

  static Future<Map<String, dynamic>> startKaspiPayment(int amount) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/kaspi/start-payment',
        body: {'amount': amount},
      ));

  static Future<Map<String, dynamic>> getKaspiStatus(String processId) async =>
      Map<String, dynamic>.from(
        await _request('GET', '/kaspi/status/$processId'),
      );

  static Future<Map<String, dynamic>> refundSale(int saleId) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/sales/refund/$saleId',
        timeout: const Duration(seconds: 90),
      ));

  static Future<Map<String, dynamic>> refundReceipt(int saleId) async {
    final result = Map<String, dynamic>.from(await _request(
      'GET',
      '/api/mobile/sales/$saleId/refund-receipt',
    ));
    return Map<String, dynamic>.from(result['document'] as Map);
  }

  static Future<Map<String, dynamic>> findByGtin(String gtin) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/gtin',
        body: {'gtin': gtin},
      ));

  static Future<Map<String, dynamic>> analytics({
    String? dateFrom,
    String? dateTo,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/analytics',
        query: {'date_from': dateFrom, 'date_to': dateTo},
      ));

  static Future<Map<String, dynamic>> getClientByIin(String iin) async {
    final cached = await OfflineStore.instance.findClientByIin(iin);
    if (cached != null) {
      return {'found': true, 'client': cached, 'offline': true};
    }
    try {
      final result = Map<String, dynamic>.from(
        await _request('GET', '/api/clients/by-iin/$iin'),
      );
      final client = result['client'];
      if (result['found'] == true && client is Map) {
        await OfflineStore.instance.cacheClients(
          [client],
          deleted: false,
        );
      }
      return result;
    } on ApiException catch (error) {
      if (error.statusCode != null) rethrow;
      return {'found': false, 'offline': true};
    }
  }

  static Future<Map<String, dynamic>> quickAddItem({
    required String name,
    required int price,
    required String barcode,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/quick-add-item',
        body: {
          'name': name,
          'retail_price': price,
          'barcode': barcode,
          'unit': 'шт',
          'purchase_price': 0,
          'category': '',
        },
      ));

  static Future<Map<String, dynamic>> shiftStatus() async =>
      Map<String, dynamic>.from(
        await _request('GET', '/api/rekassa/shift/status'),
      );

  static Future<Map<String, dynamic>> xReport() async =>
      Map<String, dynamic>.from(
        await _request('POST', '/api/rekassa/reports/x'),
      );

  static Future<Map<String, dynamic>> closeShift({
    required String pin,
    bool withdrawMoney = false,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/rekassa/shifts/close',
        timeout: const Duration(seconds: 60),
        body: {'pin': pin, 'withdraw_money': withdrawMoney},
      ));

  static Future<Map<String, dynamic>> shiftHistory({
    int page = 0,
    int size = 20,
    String? dateFrom,
    String? dateTo,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/rekassa/shifts',
        query: {
          'page': '$page',
          'size': '$size',
          if (dateFrom != null && dateFrom.isNotEmpty) 'date_from': dateFrom,
          if (dateTo != null && dateTo.isNotEmpty) 'date_to': dateTo,
        },
      ));

  static Future<Map<String, dynamic>> zReport(int shiftNumber) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/rekassa/shifts/$shiftNumber/report',
      ));

  static Future<Map<String, dynamic>> reportData({
    required String type,
    required String dateFrom,
    required String dateTo,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/reports/data',
        query: {
          'type': type,
          'date_from': dateFrom,
          'date_to': dateTo,
        },
      ));

  static Future<Uint8List> downloadReportExcel({
    required String type,
    required String dateFrom,
    required String dateTo,
  }) async {
    late http.Response response;
    try {
      response = await http.get(
        _uri('/reports/export.xlsx', {
          'type': type,
          'date_from': dateFrom,
          'date_to': dateTo,
        }),
        headers: {
          ..._headers,
          'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        },
      ).timeout(const Duration(seconds: 60));
    } catch (_) {
      throw const ApiException('Не удалось скачать отчёт. Проверьте интернет');
    }

    dynamic decoded;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      try {
        decoded = jsonDecode(utf8.decode(response.bodyBytes));
      } catch (_) {
        decoded = null;
      }
      if (response.statusCode == 401) await _clearServerSession();
      throw ApiException(
        _errorMessage(decoded, response.statusCode),
        statusCode: response.statusCode,
      );
    }

    final bytes = response.bodyBytes;
    final isExcel = bytes.length >= 4 && bytes[0] == 0x50 && bytes[1] == 0x4B;
    if (!isExcel) {
      throw const ApiException('Сервер не смог сформировать Excel-отчёт');
    }
    return bytes;
  }

  static Future<Map<String, dynamic>> bankAccounts() async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/integrations/alatau/accounts',
        query: {'environment': 'production'},
      ));

  static Future<Map<String, dynamic>> bankPayments({bool refresh = false}) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/integrations/alatau/payments/history',
        query: {
          'environment': 'production',
          if (refresh) 'refresh': '1',
        },
      ));

  static Future<Map<String, dynamic>> bankStatement({
    required String iban,
    required String dateFrom,
    required String dateTo,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/integrations/alatau/statements',
        timeout: const Duration(seconds: 60),
        query: {
          'environment': 'production',
          'iban': iban,
          'date_from': dateFrom,
          'date_to': dateTo,
          'page': '1',
          'page_size': '200',
          'smart': '1',
        },
      ));

  static Future<Map<String, dynamic>?> linkBankStatementOperation({
    required Map<String, dynamic> operation,
    String? linkType,
    int? linkId,
    bool clear = false,
  }) async {
    final result = Map<String, dynamic>.from(await _request(
      'POST',
      '/api/integrations/alatau/statement-links',
      body: {
        'environment': 'production',
        'operationKey': operation['operationKey'],
        'accountIban': operation['accountIban'],
        'date': operation['date'],
        'direction': operation['direction'],
        'amount': operation['amount'],
        'currency': operation['currency'],
        'counterpartyName': operation['counterpartyName'],
        'counterpartyIinBin': operation['counterpartyIinBin'],
        'purpose': operation['purpose'],
        if (clear) 'clear': true,
        if (!clear) 'linkType': linkType,
        if (!clear) 'linkId': linkId,
      },
    ));
    final link = result['link'];
    return link is Map ? Map<String, dynamic>.from(link) : null;
  }

  static Future<List<Map<String, dynamic>>> bankPaymentTemplates() async {
    final result = Map<String, dynamic>.from(
      await _request('GET', '/api/integrations/alatau/payment-templates'),
    );
    return List<dynamic>.from(result['templates'] ?? const [])
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
  }

  static Future<Map<String, dynamic>> bankDictionary(String code) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/integrations/alatau/dictionaries',
        timeout: const Duration(seconds: 60),
        query: {
          'environment': 'production',
          'code': code.toUpperCase(),
        },
      ));

  static Future<Map<String, dynamic>> prepareBankTaxPayment(
    Map<String, dynamic> payment,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/integrations/alatau/payments/tax/draft',
        timeout: const Duration(seconds: 60),
        body: {
          ...payment,
          'environment': 'production',
        },
      ));

  static Future<Map<String, dynamic>> prepareBankPayment(
    Map<String, dynamic> payment,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/integrations/alatau/payments/draft',
        timeout: const Duration(seconds: 60),
        body: {
          ...payment,
          'environment': 'production',
          'prepareOnly': true,
        },
      ));

  static Future<Map<String, dynamic>> sendSignedBankPayment({
    required String content,
    required Map<String, dynamic> payment,
    required String requestId,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/integrations/alatau/payments/signed',
        timeout: const Duration(seconds: 90),
        body: {
          'environment': 'production',
          'content': content,
          'payment': payment,
          'requestId': requestId,
        },
      ));

  static Future<Map<String, dynamic>> getSaleEsf(int saleId) async =>
      Map<String, dynamic>.from(
        await _request('GET', '/api/sales/$saleId/esf'),
      );

  static Future<Map<String, dynamic>> saveSaleEsfDraft(
    int saleId,
    Map<String, dynamic> payload,
  ) async =>
      Map<String, dynamic>.from(
        await _request(
          'POST',
          '/api/sales/$saleId/esf/draft',
          timeout: const Duration(seconds: 60),
          body: {'payload': payload},
        ),
      );

  static Future<Map<String, dynamic>> saveSaleEsfSignature(
    int saleId, {
    required String signature,
    required String certificate,
    required String payloadHash,
    String certificateSubject = '',
  }) async =>
      Map<String, dynamic>.from(
        await _request(
          'POST',
          '/api/sales/$saleId/esf/signature',
          timeout: const Duration(seconds: 60),
          body: {
            'signature': signature,
            'certificate': certificate,
            'certificate_subject': certificateSubject,
            'payload_hash': payloadHash,
          },
        ),
      );

  static Future<Map<String, dynamic>> getSaleEsfAuthTicket(
    int saleId, {
    required String iin,
  }) async =>
      Map<String, dynamic>.from(
        await _request(
          'POST',
          '/api/sales/$saleId/esf/auth-ticket',
          timeout: const Duration(seconds: 60),
          body: {'iin': iin},
        ),
      );

  static Future<Map<String, dynamic>> openSaleEsfSession(
    int saleId, {
    required String iin,
    required String password,
    required String signedAuthTicket,
    required String profileType,
  }) async =>
      Map<String, dynamic>.from(
        await _request(
          'POST',
          '/api/sales/$saleId/esf/session',
          timeout: const Duration(seconds: 75),
          body: {
            'iin': iin,
            'password': password,
            'signed_auth_ticket': signedAuthTicket,
            'profile_type': profileType,
          },
        ),
      );

  static Future<Map<String, dynamic>> sendSaleEsf(
    int saleId, {
    required String iin,
    required String password,
    required String signedAuthTicket,
    required String profileType,
    String sessionId = '',
  }) async =>
      Map<String, dynamic>.from(
        await _request(
          'POST',
          '/api/sales/$saleId/esf/send',
          timeout: const Duration(seconds: 75),
          body: {
            'iin': iin,
            'password': password,
            'signed_auth_ticket': signedAuthTicket,
            'profile_type': profileType,
            if (sessionId.isNotEmpty) 'session_id': sessionId,
          },
        ),
      );

  static Future<Map<String, dynamic>> notifications() async =>
      Map<String, dynamic>.from(
        await _request('GET', '/api/notifications'),
      );

  static Future<void> readNotification(int id) async {
    await _request('POST', '/api/notifications/$id/read');
  }

  static Future<void> readAllNotifications() async {
    await _request('POST', '/api/notifications/read-all');
  }

  static Future<Map<String, dynamic>> aiHistory() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/ai/history'));

  static Future<Map<String, dynamic>> aiChat(
    String message, {
    dynamic conversationId,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/ai/chat',
        timeout: const Duration(seconds: 90),
        body: {'message': message, 'conversation_id': conversationId},
      ));

  static Future<Map<String, dynamic>> aiAction(
    String actionId,
    String decision,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/ai/action/$actionId',
        body: {'decision': decision},
      ));

  static Future<Uint8List> aiVoice(String text) async {
    final uri = _uri('/api/ai/voice');
    late http.Response response;

    try {
      response = await http
          .post(
            uri,
            headers: {
              ..._headers,
              'Accept': 'audio/mpeg',
            },
            body: jsonEncode({'text': text}),
          )
          .timeout(const Duration(seconds: 60));
    } catch (_) {
      throw const ApiException('Не удалось загрузить голос Nika');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      dynamic decoded;
      try {
        decoded = jsonDecode(utf8.decode(response.bodyBytes));
      } catch (_) {
        decoded = null;
      }
      if (response.statusCode == 401) await _clearServerSession();
      throw ApiException(
        _errorMessage(decoded, response.statusCode),
        statusCode: response.statusCode,
      );
    }

    if (response.bodyBytes.isEmpty) {
      throw const ApiException('Сервер вернул пустой голосовой ответ');
    }
    return response.bodyBytes;
  }

  static Future<Map<String, dynamic>> whatsappChats({
    String search = '',
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/whatsapp/api/chats',
        query: {'search': search},
      ));

  static Future<Map<String, dynamic>> whatsappMessages(int chatId) async =>
      Map<String, dynamic>.from(
        await _request('GET', '/whatsapp/api/chats/$chatId/messages'),
      );

  static Future<Map<String, dynamic>> sendWhatsappMessage(
    int chatId,
    String message,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/whatsapp/api/chats/$chatId/messages',
        body: {'message': message},
      ));

  static Future<Map<String, dynamic>> mobileTasks() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/tasks'));

  static Future<void> createMobileTask(Map<String, dynamic> data) async {
    await _request('POST', '/api/mobile/tasks', body: data);
  }

  static Future<void> updateMobileTask(int id, Map<String, dynamic> data) async {
    await _request('PATCH', '/api/mobile/tasks/$id', body: data);
  }

  static Future<void> deleteMobileTask(int id) async {
    await _request('DELETE', '/api/mobile/tasks/$id');
  }

  static Future<Map<String, dynamic>> mobileExpenses() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/expenses'));

  static Future<void> createMobileExpense(Map<String, dynamic> data) async {
    await _request('POST', '/api/mobile/expenses', body: data);
  }

  static Future<void> updateMobileExpense(int id, Map<String, dynamic> data) async {
    await _request('PATCH', '/api/mobile/expenses/$id', body: data);
  }

  static Future<void> deleteMobileExpense(int id) async {
    await _request('DELETE', '/api/mobile/expenses/$id');
  }

  static Future<Map<String, dynamic>> mobileAccounting() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/accounting'));

  static Future<Map<String, dynamic>> mobileTaxCalculation(String period) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/accounting/tax-calculation',
        query: {'period': period},
      ));

  static Future<void> saveMobileTaxEmployee(
    int userId,
    Map<String, dynamic> data,
  ) async {
    await _request(
      'POST',
      '/api/mobile/accounting/tax-employee/$userId',
      body: data,
    );
  }

  static Future<void> createMobileTaxDebts(String period) async {
    await _request(
      'POST',
      '/api/mobile/accounting/tax-debts',
      body: {'period': period},
    );
  }

  static Future<Map<String, dynamic>> mobileTaxSettings() async =>
      Map<String, dynamic>.from(
        await _request('GET', '/api/mobile/profile/tax-settings'),
      );

  static Future<Map<String, dynamic>> saveMobileTaxSettings(
    Map<String, dynamic> data,
  ) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/mobile/profile/tax-settings',
        body: data,
      ));

  static Future<void> syncMobileAccounting() async {
    await _request('POST', '/api/mobile/accounting/sync');
  }

  static Future<void> markMobileAccountingPaid(String kind, int id) async {
    await _request('POST', '/api/mobile/accounting/$kind/$id/paid');
  }

  static Future<Map<String, dynamic>> accountingOperationDocuments(int id) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/accounting/operations/$id/documents',
      ));

  static Future<Map<String, dynamic>> accountingDocumentPreview(int id) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/accounting/documents/$id/preview',
      ));

  static Future<Uint8List> downloadPdf(String path) async {
    late http.Response response;
    try {
      response = await http.get(
        _uri(path),
        headers: {..._headers, 'Accept': 'application/pdf'},
      ).timeout(const Duration(seconds: 60));
    } catch (_) {
      throw const ApiException('Не удалось загрузить документ. Проверьте интернет');
    }

    dynamic decoded;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      try {
        decoded = jsonDecode(utf8.decode(response.bodyBytes));
      } catch (_) {
        decoded = null;
      }
      if (response.statusCode == 401) await _clearServerSession();
      throw ApiException(
        _errorMessage(decoded, response.statusCode),
        statusCode: response.statusCode,
      );
    }

    final bytes = response.bodyBytes;
    final isPdf = bytes.length >= 5 &&
        bytes[0] == 0x25 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x44 &&
        bytes[3] == 0x46 &&
        bytes[4] == 0x2D;
    if (!isPdf) {
      throw const ApiException('Сервер не смог сформировать PDF документа');
    }
    return bytes;
  }

  static Future<Map<String, dynamic>> mobileEmployees() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/employees'));

  static Future<void> createMobileEmployee(Map<String, dynamic> data) async {
    await _request('POST', '/api/mobile/employees', body: data);
  }

  static Future<void> updateMobileEmployee(int id, Map<String, dynamic> data) async {
    await _request('PATCH', '/api/mobile/employees/$id', body: data);
  }

  static Future<void> deleteMobileEmployee(int id) async {
    await _request('DELETE', '/api/mobile/employees/$id');
  }

  static Future<Map<String, dynamic>> mobileStorefront() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/storefront'));

  static Future<void> updateMobileStorefront(Map<String, dynamic> data) async {
    await _request('PATCH', '/api/mobile/storefront', body: data);
  }

  static Future<void> updateMobileStorefrontStatus(
    String kind,
    int id,
    String status,
  ) async {
    await _request(
      'POST',
      '/api/mobile/storefront/$kind/$id/status',
      body: {'status': status},
    );
  }

  static Future<Map<String, dynamic>> mobileCto() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/mobile/cto'));

  static Future<Map<String, dynamic>> saleClients({
    String query = '',
    int page = 1,
    int limit = 30,
  }) async {
    try {
      final result = Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/sale/clients',
        query: {'q': query, 'page': '$page', 'limit': '$limit'},
      ));
      final items = List<dynamic>.from(result['items'] ?? const []);
      await OfflineStore.instance.cacheClients(items, deleted: false);
      final defaultClient = result['default_client'];
      if (defaultClient is Map) {
        await OfflineStore.instance.cacheClients(
          [defaultClient],
          deleted: false,
        );
      }
      return result;
    } on ApiException catch (error) {
      if (error.statusCode != null) rethrow;
      final offset = (page - 1) * limit;
      final items = await OfflineStore.instance.clients(
        query: query,
        limit: limit,
        offset: offset,
      );
      final all = await OfflineStore.instance.clients(deleted: false);
      Map<String, dynamic>? defaultClient;
      for (final raw in all) {
        if (raw is! Map) continue;
        final client = Map<String, dynamic>.from(raw);
        final label = '${client['company_name'] ?? client['full_name'] ?? ''}'
            .trim()
            .toLowerCase();
        if (label == 'частное лицо') {
          defaultClient = client;
          break;
        }
      }
      return {
        'success': true,
        'offline': true,
        'items': items,
        'page': page,
        'has_more': items.length == limit,
        'default_client': defaultClient,
      };
    }
  }

  static Future<Map<String, dynamic>> saleItems({
    String query = '',
    int page = 1,
    int limit = 30,
  }) async {
    try {
      final result = Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/sale/items',
        query: {'q': query, 'page': '$page', 'limit': '$limit'},
      ));
      final items = List<dynamic>.from(result['items'] ?? const []);
      await OfflineStore.instance.cacheItems(items);
      return result;
    } on ApiException catch (error) {
      if (error.statusCode != null) rethrow;
      final offset = (page - 1) * limit;
      final items = await OfflineStore.instance.items(
        query: query,
        limit: limit,
        offset: offset,
      );
      return {
        'success': true,
        'offline': true,
        'items': items,
        'page': page,
        'has_more': items.length == limit,
      };
    }
  }
}
