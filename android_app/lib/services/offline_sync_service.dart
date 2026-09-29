import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_service.dart';
import 'offline_store.dart';

enum OfflineSyncStatus { idle, syncing, synced, offline, error }

class OfflineSyncService {
  OfflineSyncService._();
  static final OfflineSyncService instance = OfflineSyncService._();

  final ValueNotifier<OfflineSyncStatus> status =
      ValueNotifier<OfflineSyncStatus>(OfflineSyncStatus.idle);

  bool _checking = false;
  bool _bulkRunning = false;
  DateTime? _lastAttempt;

  Future<void> syncNow({bool force = false}) async {
    if (_checking) return;
    final now = DateTime.now();
    if (!force &&
        _lastAttempt != null &&
        now.difference(_lastAttempt!) < const Duration(seconds: 30)) return;

    _checking = true;
    _lastAttempt = now;
    status.value = OfflineSyncStatus.syncing;
    try {
      await ApiService.syncHealth();
      status.value = OfflineSyncStatus.synced;
      unawaited(_refreshInBackground());
    } on ApiException catch (error) {
      status.value = error.statusCode == null
          ? OfflineSyncStatus.offline
          : OfflineSyncStatus.error;
    } catch (_) {
      status.value = OfflineSyncStatus.error;
    } finally {
      _checking = false;
    }
  }

  Future<void> _refreshInBackground() async {
    if (_bulkRunning) return;
    _bulkRunning = true;
    try {
      await _flushQueue();
      await Future<void>.delayed(const Duration(seconds: 2));
      await Future.wait<dynamic>([
        ApiService.getModules(forceRemote: true),
        ApiService.dashboard(forceRemote: true),
        ApiService.mobileProfile(forceRemote: true),
        ApiService.interfaceSettings(forceRemote: true),
        ApiService.getCategories(forceRemote: true),
      ]);
      await ApiService.getItems(forceRemote: true);
      await Future.wait<dynamic>([
        ApiService.getClients(forceRemote: true),
        ApiService.getClients(deleted: true, forceRemote: true),
        ApiService.getStock(forceRemote: true),
        ApiService.getStockMovements(forceRemote: true),
      ]);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(
        'offline_last_sync_at',
        DateTime.now().millisecondsSinceEpoch,
      );
    } catch (_) {
      // Keep the last good cache and retry later.
    } finally {
      _bulkRunning = false;
    }
  }

  Future<void> _flushQueue() async {
    final operations = await OfflineStore.instance.pendingOperations(limit: 25);
    for (final operation in operations) {
      final operationId = '${operation['operation_id'] ?? ''}';
      if (operationId.isEmpty) continue;

      await OfflineStore.instance.markOperationSyncing(operationId);
      try {
        final result = await ApiService.replayQueuedOperation(operation);
        if (result['pending'] == true) {
          await OfflineStore.instance.markOperationPending(operationId);
        } else {
          await OfflineStore.instance.markOperationSynced(operationId);
        }
      } on ApiException catch (error) {
        final statusCode = error.statusCode;
        final retryable =
            statusCode == null || statusCode == 401 || statusCode >= 500;
        if (retryable) {
          await OfflineStore.instance.markOperationPending(
            operationId,
            error: error.message,
          );
          break;
        }
        await OfflineStore.instance.markOperationError(
          operationId,
          error.message,
        );
      } catch (error) {
        await OfflineStore.instance.markOperationPending(
          operationId,
          error: error.toString(),
        );
        break;
      }
    }
  }

  Future<DateTime?> lastSuccessfulSync() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getInt('offline_last_sync_at');
    return value == null ? null : DateTime.fromMillisecondsSinceEpoch(value);
  }
}
