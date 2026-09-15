import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/splash_screen.dart';
import 'services/app_navigation.dart';
import 'services/app_theme_preferences.dart';
import 'services/nika_assistant_controller.dart';
import 'theme/app_theme.dart';
import 'widgets/nika_voice_overlay.dart';

class NikaBusinessApp extends StatelessWidget {
  const NikaBusinessApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: AppThemePreferences.darkMode,
      builder: (context, darkBlue, _) => MaterialApp(
        navigatorKey: appNavigatorKey,
        title: 'Nika Business',
        debugShowCheckedModeBanner: false,
        locale: const Locale('ru', 'RU'),
        supportedLocales: const [
          Locale('ru', 'RU'),
          Locale('kk', 'KZ'),
          Locale('en', 'US'),
        ],
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        theme: AppTheme.light(),
        darkTheme: AppTheme.darkBlue(),
        themeMode: darkBlue ? ThemeMode.dark : ThemeMode.light,
        builder: (context, child) => NikaVoiceOverlay(
          controller: NikaAssistantController.instance,
          child: child ?? const SizedBox.shrink(),
        ),
        home: const SplashScreen(),
      ),
    );
  }
}
