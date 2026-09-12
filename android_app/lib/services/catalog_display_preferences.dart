import 'package:flutter/foundation.dart';

import 'api_service.dart';

class CatalogDisplayPreferences {
  CatalogDisplayPreferences._();

  static final ValueNotifier<bool> showImages = ValueNotifier<bool>(true);

  static Future<void> load() async {
    final result = await ApiService.interfaceSettings();
    showImages.value = result['show_catalog_images'] != false;
  }

  static Future<void> setShowImages(bool value) async {
    final previous = showImages.value;
    showImages.value = value;
    try {
      final result = await ApiService.saveInterfaceSettings(
        showCatalogImages: value,
      );
      showImages.value = result['show_catalog_images'] != false;
    } catch (_) {
      showImages.value = previous;
      rethrow;
    }
  }
}
