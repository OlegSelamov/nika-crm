import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class KaspiPosService {

  static Future<String> getIp() async {
    final prefs =
        await SharedPreferences.getInstance();

    return prefs.getString(
          "kaspi_ip",
        ) ??
        "";
  }

  static Future<bool> testConnection() async {
    try {
      final ip = await getIp();

      if (ip.isEmpty) {
        return false;
      }

      final response = await http.get(
        Uri.parse(
          "http://$ip:8080/v2/deviceinfo",
        ),
      );

      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  static Future<Map<String, dynamic>>
  startPayment(int amount) async {
  
	final ip = await getIp();

	if (ip.isEmpty) {
	  return {
		"success": false,
		"message":
			"IP терминала не указан",
	  };
	}

    final response = await http.get(
      Uri.parse(
        "http://$ip:8080/v2/payment?amount=$amount",
      ),
    );

    return jsonDecode(response.body);
  }

  /// Refunds a genuine Kaspi POS payment on the phone's local network.
  /// Never re-issues the bank request if the first response was ambiguous:
  /// the process ID and successful bank refund are retained for resumption.
  static Future<String> refundPayment({
    required int saleId,
    required String transactionId,
    required int amount,
    required String method,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final key = 'nika_kaspi_refund_' + saleId.toString() + '_' + transactionId;
    final successful = prefs.getString(key + '_confirmed');
    if (successful != null && successful.isNotEmpty) return successful;
    var processId = prefs.getString(key + '_process') ?? '';
    if (processId.isEmpty) {
      final ip = await getIp();
      if (ip.isEmpty) throw StateError('Не настроен локальный IP Kaspi POS');
      final response = await http.get(
        Uri.parse('http://' + ip + ':8080/v2/refund').replace(queryParameters: {
          'transactionId': transactionId,
          'amount': amount.toString(),
          'method': method,
        }),
      ).timeout(const Duration(seconds: 18));
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (data['statusCode'] != 0) {
        throw StateError((data['message'] ?? 'Kaspi POS отклонил возврат').toString());
      }
      processId = (data['data']?['processId'] ?? '').toString();
      if (processId.isEmpty) throw StateError('Kaspi POS не вернул processId. Проверьте терминал.');
      await prefs.setString(key + '_process', processId);
    }
    for (var attempt = 0; attempt < 30; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 2));
      final status = await getStatus(processId);
      final detail = status['data'] is Map
          ? Map<String, dynamic>.from(status['data'] as Map)
          : <String, dynamic>{};
      if (detail['status'] == 'fail') {
        await prefs.remove(key + '_process');
        throw StateError('Kaspi POS отклонил банковский возврат');
      }
      if (detail['status'] == 'success') {
        final bankRefundTransactionId = (detail['transactionId'] ?? '').toString();
        if (bankRefundTransactionId.isEmpty) {
          throw StateError('Kaspi POS не вернул transactionId возврата. Проверьте терминал.');
        }
        await prefs.setString(key + '_confirmed', bankRefundTransactionId);
        await prefs.remove(key + '_process');
        return bankRefundTransactionId;
      }
    }
    throw StateError('Возврат не подтверждён. Проверьте Kaspi POS; повторная банковская операция не запускается.');
  }

  static Future<Map<String, dynamic>>
  getStatus(String processId) async {
  
	final ip = await getIp();

	if (ip.isEmpty) {
	  return {
		"status": "fail",
	  };
	}

    final response = await http.get(
      Uri.parse(
        "http://$ip:8080/v2/status?processId=$processId",
      ),
    );

    return jsonDecode(response.body);
  }
}