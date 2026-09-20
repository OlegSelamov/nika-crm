import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/splash_screen.dart';
import 'services/app_navigation.dart';
import 'services/app_theme_preferences.dart';
import 'services/nika_assistant_controller.dart';
import 'theme/app_theme.dart';
import 'widgets/nika_voice_overlay.dart';

final _nikaModalRouteObserver = _NikaModalRouteObserver(
  NikaAssistantController.instance,
);

class _NikaModalRouteObserver extends NavigatorObserver {
  final NikaAssistantController controller;
  int _modalDepth = 0;

  _NikaModalRouteObserver(this.controller);

  bool _isModal(Route<dynamic>? route) => route is PopupRoute;

  void _sync() {
    controller.setOverlaySuppressed(_modalDepth > 0);
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    if (_isModal(route)) {
      _modalDepth++;
      _sync();
    }
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPop(route, previousRoute);
    if (_isModal(route)) {
      _modalDepth = (_modalDepth - 1).clamp(0, 999);
      _sync();
    }
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didRemove(route, previousRoute);
    if (_isModal(route)) {
      _modalDepth = (_modalDepth - 1).clamp(0, 999);
      _sync();
    }
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    if (_isModal(oldRoute)) {
      _modalDepth = (_modalDepth - 1).clamp(0, 999);
    }
    if (_isModal(newRoute)) {
      _modalDepth++;
    }
    _sync();
  }
}

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
        navigatorObservers: [_nikaModalRouteObserver],
        builder: (context, child) => NikaVoiceOverlay(
          controller: NikaAssistantController.instance,
          child: child ?? const SizedBox.shrink(),
        ),
        home: const SplashScreen(),
      ),
    );
  }
}
