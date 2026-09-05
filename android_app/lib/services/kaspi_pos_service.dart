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