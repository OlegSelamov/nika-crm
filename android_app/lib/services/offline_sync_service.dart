import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_service.dart';

enum OfflineSyncStatus {
  idle,
  syncing,
  synced,
  offline,
  error,
}

class OfflineSyncService {
  OfflineSyncService._();

  static final OfflineSyncService instance = OfflineSyncService._();

  final ValueNotifier<OfflineSyncStatus> status =
      ValueNotifier<OfflineSyncStatus>(OfflineSyncStatus.idle);

  bool _running = false;
  DateTime? _lastAttempt;

  Future<void> syncNow({bool force = false}) async {
    if (_running) return;

    final now = DateTime.now();
    if (!force &&
        _lastAttempt != null &&
        now.difference(_lastAttempt!) < const Duration(seconds: 20)) {
      return;
    }

    _running = true;
    _lastAttempt = now;
    status.value = OfflineSyncStatus.syncing;

    try {
      // This request is deliberately not cached. It tells us whether the
      // server is actually reachable before a background refresh starts.
      await ApiService.syncHealth();

      // Small company-level snapshots first, so the shell becomes useful fast.
      await Future.wait<dynamic>([
        ApiService.getModules(),
        ApiService.dashboard(),
        ApiService.mobileProfile(),
        ApiService.interfaceSettings(),
        ApiService.getCategories(),
      ]);

      // Then refresh the complete operational cache. These API methods write
      // the successful response to SQLite themselves.
      await ApiService.getItems();
      await Future.wait<dynamic>([
        ApiService.getClients(),
        ApiService.getClients(deleted: true),
        ApiService.getStock(),
      ]);

      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(
        'offline_last_sync_at',
        DateTime.now().millisecondsSinceEpoch,
      );
      status.value = OfflineSyncStatus.synced;
    } on ApiException catch (error) {
      status.value = error.statusCode == null
          ? OfflineSyncStatus.offline
          : OfflineSyncStatus.error;
    } catch (_) {
      status.value = OfflineSyncStatus.error;
    } finally {
      _running = false;
    }
  }

  Future<DateTime?> lastSuccessfulSync() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getInt('offline_last_sync_at');
    return value == null ? null : DateTime.fromMillisecondsSinceEpoch(value);
  }
}
