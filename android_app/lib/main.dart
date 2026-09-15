import 'package:flutter/material.dart';

import 'app_root.dart';
import 'services/api_service.dart';
import 'services/app_navigation.dart';
import 'services/app_theme_preferences.dart';
import 'services/app_update_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await ApiService.loadCookie();
  await AppThemePreferences.load();

  runApp(const NikaBusinessApp());

  WidgetsBinding.instance.addPostFrameCallback((_) async {
    await Future<void>.delayed(const Duration(seconds: 3));
    final context = appNavigatorKey.currentContext;
    if (context != null && context.mounted) {
      await AppUpdateService.checkAndPrompt(context);
    }
  });
}
