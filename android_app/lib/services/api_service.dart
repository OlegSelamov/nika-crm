import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

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
    return _cookie != null && _cookie!.isNotEmpty;
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('session_cookie');
    _cookie = null;
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
      if (response.statusCode == 401) await logout();
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
          result['success'] == true &&
          rawCookie != null) {
        await saveCookie(rawCookie.split(';').first);
      }
      return result;
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ApiException('Не удалось подключиться к серверу');
    }
  }

  static Future<Set<String>> getModules() async {
    final result = Map<String, dynamic>.from(
      await _request('GET', '/api/mobile/modules'),
    );
    return List<dynamic>.from(result['modules'] ?? const [])
        .map((item) => item.toString())
        .toSet();
  }

  static Future<Map<String, dynamic>> dashboard() async =>
      Map<String, dynamic>.from(await _request('GET', '/api/dashboard'));

  static Future<List<dynamic>> getItems({String type = 'all', String category = 'all'}) async =>
      List<dynamic>.from(await _request(
        'GET',
        '/api/items',
        query: {
          if (type != 'all') 'type': type,
          if (category != 'all') 'category': category,
        },
      ));

  static Future<List<dynamic>> searchItems(String query) async {
    final result = await _request(
      'GET',
      '/api/items/search',
      query: {'q': query},
    );
    if (result is Map) return List<dynamic>.from(result['items'] ?? const []);
    return List<dynamic>.from(result as List);
  }

  static Future<Map<String, dynamic>> barcode(String barcode) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/api/barcode',
        body: {'barcode': barcode},
      ));

  static Future<Map<String, dynamic>> paySale({
    required List cart,
    int? clientId,
    String? paymentMethod,
    String? kaspiTransactionId,
    String? kaspiMethod,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'POST',
        '/sales/pay',
        timeout: const Duration(seconds: 60),
        body: {
          'client_id': clientId,
          'payment_method': paymentMethod ?? 'cash',
          'kaspi_transaction_id': kaspiTransactionId,
          'kaspi_method': kaspiMethod,
          'cart': cart,
        },
      ));

  static Future<List<dynamic>> getSalesHistory({
    int? shiftNumber,
    String? serialNumber,
    bool allHistory = false,
    int page = 0,
    int size = 50,
  }) async =>
      List<dynamic>.from(await _request(
        'GET',
        '/api/sales/history',
        query: {
          'shift_number': shiftNumber?.toString(),
          'serial_number': serialNumber,
          if (allHistory) 'scope': 'all',
          'page': '$page',
          'size': '$size',
        },
      ));

  static Future<List<dynamic>> getClients({bool deleted = false}) async =>
      List<dynamic>.from(await _request(
        'GET',
        '/api/clients',
        query: {if (deleted) 'deleted': 'true'},
      ));

  static Future<Map<String, dynamic>> getClient(int id) async =>
      Map<String, dynamic>.from(await _request('GET', '/api/client/$id'));

  static Future<Map<String, dynamic>> getSale(int saleId) async =>
      Map<String, dynamic>.from(await _request('GET', '/api/sale/$saleId'));

  static Future<List<dynamic>> getStock() async =>
      List<dynamic>.from(await _request('GET', '/api/stock'));

  static Future<List<dynamic>> getStockMovements() async =>
      List<dynamic>.from(await _request('GET', '/api/stock/movements'));

  static Future<void> stockIncome({
    required int itemId,
    required double quantity,
    required double price,
    String comment = '',
  }) async {
    await _request('POST', '/api/stock/income', body: {
      'item_id': itemId,
      'quantity': quantity,
      'price': price,
      'comment': comment,
    });
  }

  static Future<void> stockWriteoff({
    required int itemId,
    required double quantity,
    String comment = '',
  }) async {
    await _request('POST', '/api/stock/writeoff', body: {
      'item_id': itemId,
      'quantity': quantity,
      'comment': comment,
    });
  }

  static Future<Map<String, dynamic>> getBarcodeInfo(
    String barcode, {
    String itemType = 'product',
  }) async =>
      Map<String, dynamic>.from(
        await _request(
          'GET',
          '/api/barcode-info/$barcode',
          query: {'item_type': itemType},
        ),
      );

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

  static Future<List<dynamic>> getCategories({String type = 'all'}) async =>
      List<dynamic>.from(await _request(
        'GET',
        '/api/categories',
        query: {if (type != 'all') 'type': type},
      ));

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

  static Future<Map<String, dynamic>> getClientByIin(String iin) async =>
      Map<String, dynamic>.from(
        await _request('GET', '/api/clients/by-iin/$iin'),
      );

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
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/rekassa/shifts',
        query: {'page': '$page', 'size': '$size'},
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
      if (response.statusCode == 401) await logout();
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
      if (response.statusCode == 401) await logout();
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
      if (response.statusCode == 401) await logout();
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
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/sale/clients',
        query: {'q': query, 'page': '$page', 'limit': '$limit'},
      ));

  static Future<Map<String, dynamic>> saleItems({
    String query = '',
    int page = 1,
    int limit = 30,
  }) async =>
      Map<String, dynamic>.from(await _request(
        'GET',
        '/api/mobile/sale/items',
        query: {'q': query, 'page': '$page', 'limit': '$limit'},
      ));
}
