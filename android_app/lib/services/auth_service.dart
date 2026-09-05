import 'package:shared_preferences/shared_preferences.dart';

class AuthService {
  static Future<void> saveUser({
    required int userId,
    required String username,
    String? role,
  }) async {
    final prefs = await SharedPreferences.getInstance();

    await prefs.setBool("logged_in", true);
    await prefs.setInt("user_id", userId);
    await prefs.setString("username", username);
    await prefs.setString("role", role ?? "admin");
  }

  static Future<bool> isLoggedIn() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool("logged_in") ?? false;
  }

  static Future<String> getUsername() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString("username") ?? "Пользователь";
  }

  static Future<String> getRole() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString("role") ?? "Администратор";
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove("logged_in");
    await prefs.remove("user_id");
    await prefs.remove("username");
    await prefs.remove("role");
  }
}
