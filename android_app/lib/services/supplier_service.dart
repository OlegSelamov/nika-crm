import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_service.dart';

class SupplierService {
  static const Duration _timeout = Duration(seconds: 30);

  static Uri _uri(String path) => Uri.parse('${ApiService.baseUrl}$path');

  static String _messageFromResponse(http.Response response) {
    final body = utf8.decode(response.bodyBytes).trim();
    if (body.isEmpty) return 'Ошибка сервера (${response.statusCode})';
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        for (final key in const ['error', 'message', 'detail']) {
          final value = decoded[key];
          if (value != null && value.toString().trim().isNotEmpty) {
            return value.toString();
          }
        }
      }
    } catch (_) {}
    return body.length > 220 ? body.substring(0, 220) : body;
  }

  static Future<http.Response> _jsonRequest(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = _uri(path);
    late http.Response response;
    try {
      switch (method) {
        case 'POST':
          response = await http
              .post(uri, headers: ApiService.headers, body: jsonEncode(body ?? const {}))
              .timeout(_timeout);
          break;
        case 'PUT':
          response = await http
              .put(uri, headers: ApiService.headers, body: jsonEncode(body ?? const {}))
              .timeout(_timeout);
          break;
        case 'DELETE':
          response = await http
              .delete(uri, headers: ApiService.headers)
              .timeout(_timeout);
          break;
        default:
          response = await http.get(uri, headers: ApiService.headers).timeout(_timeout);
      }
    } catch (_) {
      throw const ApiException('Нет связи с сервером. Проверьте интернет');
    }

    if (response.statusCode == 401) await ApiService.logout();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        _messageFromResponse(response),
        statusCode: response.statusCode,
      );
    }
    return response;
  }

  static Future<Map<String, dynamic>> _jsonMap(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final response = await _jsonRequest(method, path, body: body);
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map) {
      throw const ApiException('Сервер вернул некорректный ответ');
    }
    return Map<String, dynamic>.from(decoded);
  }

  static Future<List<Map<String, dynamic>>> getSuppliers() async {
    final response = await _jsonRequest('GET', '/api/suppliers');
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! List) {
      throw const ApiException('Сервер вернул некорректный список поставщиков');
    }
    return decoded
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
  }

  static Future<int> createSupplier(Map<String, dynamic> data) async {
    final decoded = await _jsonMap('POST', '/api/suppliers', body: data);
    return int.tryParse('${decoded['id'] ?? ''}') ?? 0;
  }

  static Future<void> updateSupplier(int id, Map<String, dynamic> data) async {
    await _jsonRequest('PUT', '/api/suppliers/$id', body: data);
  }

  static Future<void> deleteSupplier(int id) async {
    await _jsonRequest('DELETE', '/api/suppliers/$id');
  }

  static Future<Map<String, dynamic>> stockIncomeWithSupplier({
    required int itemId,
    required int supplierId,
    required double quantity,
    required double price,
    String comment = '',
    bool updateRetail = false,
  }) async =>
      _jsonMap(
        'POST',
        '/api/mobile/stock/income/supplier',
        body: {
          'item_id': itemId,
          'supplier_id': supplierId,
          'quantity': quantity,
          'price': price,
          'comment': comment,
          'update_retail': updateRetail,
        },
      );
}
