import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

class AppUpdateInfo {
  const AppUpdateInfo({
    required this.version,
    required this.downloadUrl,
    required this.notes,
  });

  final String version;
  final String downloadUrl;
  final String notes;
}

class AppUpdateService {
  AppUpdateService._();

  static const _channel = MethodChannel('com.nikabusiness.app/updates');
  static const _releaseApiUrl =
      'https://api.github.com/repos/OlegSelamov/nika-crm/releases/latest';
  static const _apkAssetName = 'NikaBusiness.apk';

  static Future<String> currentVersion() async {
    try {
      return await _channel.invokeMethod<String>('getVersionName') ?? '—';
    } catch (_) {
      return '—';
    }
  }

  static Future<AppUpdateInfo?> availableUpdate() async {
    final current = await currentVersion();
    final uri = Uri.parse(_releaseApiUrl).replace(
      queryParameters: {'t': DateTime.now().millisecondsSinceEpoch.toString()},
    );
    final response = await http.get(uri, headers: const {
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Cache-Control': 'no-cache',
      'User-Agent': 'Nika-Business-Android',
    }).timeout(const Duration(seconds: 12));

    if (response.statusCode != 200) {
      throw StateError('GitHub returned ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Invalid GitHub release response');
    }

    final latest = (decoded['tag_name'] ?? '')
        .toString()
        .trim()
        .replaceFirst(RegExp(r'^[vV]'), '');
    final assets = decoded['assets'];
    String url = '';
    if (assets is List) {
      for (final asset in assets) {
        if (asset is Map && asset['name']?.toString() == _apkAssetName) {
          url = (asset['browser_download_url'] ?? '').toString().trim();
          break;
        }
      }
    }

    if (latest.isEmpty || url.isEmpty || !_isNewer(latest, current)) {
      return null;
    }

    return AppUpdateInfo(
      version: latest,
      downloadUrl: url,
      notes: (decoded['body'] ?? 'Улучшения и исправления Nika Business')
          .toString(),
    );
  }

  static Future<bool> checkAndPrompt(
    BuildContext context, {
    bool showNoUpdateMessage = false,
  }) async {
    try {
      final update = await availableUpdate();
      if (!context.mounted) return false;
      if (update == null) {
        if (showNoUpdateMessage) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Установлена последняя версия Nika')),
          );
        }
        return false;
      }

      final accepted = await showDialog<bool>(
            context: context,
            barrierDismissible: false,
            builder: (dialogContext) => AlertDialog(
              title: Text('Доступна Nika ${update.version}'),
              content: Text(
                '${update.notes}\n\nСкачать и установить обновление сейчас?',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext, false),
                  child: const Text('Позже'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(dialogContext, true),
                  child: const Text('Обновить'),
                ),
              ],
            ),
          ) ??
          false;

      if (!accepted || !context.mounted) return false;
      final result = await _channel.invokeMethod<String>(
        'downloadAndInstall',
        {'url': update.downloadUrl, 'version': update.version},
      );
      if (!context.mounted) return true;

      final message = result == 'permission_required'
          ? 'Разрешите установку приложений для Nika и нажмите «Обновить» ещё раз'
          : 'Обновление скачивается. После загрузки откроется установка Android.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 6)),
      );
      return true;
    } catch (_) {
      if (showNoUpdateMessage && context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось проверить обновление')),
        );
      }
      return false;
    }
  }

  static bool _isNewer(String latest, String current) {
    if (current == '—') return false;
    final left = _versionParts(latest);
    final right = _versionParts(current);
    final length = left.length > right.length ? left.length : right.length;
    for (var index = 0; index < length; index++) {
      final a = index < left.length ? left[index] : 0;
      final b = index < right.length ? right[index] : 0;
      if (a != b) return a > b;
    }
    return false;
  }

  static List<int> _versionParts(String value) => value
      .split('+')
      .first
      .split('.')
      .map((part) => int.tryParse(part.replaceAll(RegExp(r'[^0-9]'), '')) ?? 0)
      .toList();
}
