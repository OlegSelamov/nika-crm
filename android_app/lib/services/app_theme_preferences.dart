import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppThemePreferences {
  static const String _key = 'app_dark_blue_theme';

  static final ValueNotifier<bool> darkMode = ValueNotifier<bool>(false);

  static bool get isDark => darkMode.value;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    darkMode.value = prefs.getBool(_key) ?? false;
  }

  static Future<void> setDarkMode(bool value) async {
    if (darkMode.value != value) {
      darkMode.value = value;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_key, value);
  }
}
