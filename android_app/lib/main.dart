import 'package:flutter/material.dart';
import 'services/api_service.dart';
import 'services/nika_assistant_controller.dart';
import 'services/app_update_service.dart';
import 'theme/app_theme.dart';
import 'screens/splash_screen.dart';
import 'widgets/nika_voice_overlay.dart';

final appNavigatorKey = GlobalKey<NavigatorState>();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  await ApiService.loadCookie();

  runApp(const NikaBusinessApp());

  WidgetsBinding.instance.addPostFrameCallback((_) async {
    await Future<void>.delayed(const Duration(seconds: 3));
    final context = appNavigatorKey.currentContext;
    if (context != null && context.mounted) {
      await AppUpdateService.checkAndPrompt(context);
    }
  });
}

class NikaBusinessApp extends StatelessWidget {
  const NikaBusinessApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: appNavigatorKey,
      title: 'Nika Business',
      debugShowCheckedModeBanner: false,
	  theme: AppTheme.light(),
      themeMode: ThemeMode.light,
      builder: (context, child) => NikaVoiceOverlay(
        controller: NikaAssistantController.instance,
        child: child ?? const SizedBox.shrink(),
      ),
      home: const SplashScreen(),
    );
  }
}
