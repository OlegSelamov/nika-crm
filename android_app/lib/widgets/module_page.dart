import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'app_widgets.dart';

/// A native route shell for legacy body-only screens.
/// It guarantees that TextField, InkWell and dialogs always have Material.
class ModulePage extends StatelessWidget {
  final String title;
  final Widget child;

  const ModulePage({super.key, required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Material(
        color: AppColors.background,
        child: SafeArea(
          top: false,
          child: AdaptiveContent(child: child),
        ),
      ),
    );
  }
}
