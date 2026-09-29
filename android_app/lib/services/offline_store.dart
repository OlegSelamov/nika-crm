import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite/sqflite.dart';

import 'product_code_parser.dart';

class OfflineStore {
  OfflineStore._();

  static final OfflineStore instance = OfflineStore._();

  Database? _database;

  Future<Database> get _db async {
    final current = _database;
    if (current != null) return current;

    final path = p.join(await getDatabasesPath(), 'nika_business_offline.db');
    final db = await openDatabase(
      path,
      version: 1,
      onCreate: (database, version) async {
        await database.execute('''
          CREATE TABLE offline_items (
            company_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            barcode TEXT,
            gtin TEXT,
            ntin TEXT,
            name TEXT,
            item_type TEXT,
            category TEXT,
            payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (company_id, item_id)
          )
        ''');
        await database.execute(
          'CREATE INDEX idx_offline_items_barcode ON offline_items(company_id, barcode)',
        );
        await database.execute(
          'CREATE INDEX idx_offline_items_gtin ON offline_items(company_id, gtin)',
        );
        await database.execute(
          'CREATE INDEX idx_offline_items_ntin ON offline_items(company_id, ntin)',
        );
        await database.execute(
          'CREATE INDEX idx_offline_items_name ON offline_items(company_id, name)',
        );

        await database.execute('''
          CREATE TABLE offline_clients (
            company_id INTEGER NOT NULL,
            client_id TEXT NOT NULL,
            iin TEXT,
            phone TEXT,
            full_name TEXT,
            company_name TEXT,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (company_id, client_id)
          )
        ''');
        await database.execute(
          'CREATE INDEX idx_offline_clients_iin ON offline_clients(company_id, iin)',
        );

        await database.execute('''
          CREATE TABLE offline_stock (
            company_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (company_id, item_id)
          )
        ''');

        await database.execute('''
          CREATE TABLE offline_snapshots (
            company_id INTEGER NOT NULL,
            cache_key TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (company_id, cache_key)
          )
        ''');

        await database.execute('''
          CREATE TABLE sync_queue (
            operation_id TEXT PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER,
            operation_type TEXT NOT NULL,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            body TEXT,
            state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
          )
        ''');
        await database.execute(
          'CREATE INDEX idx_sync_queue_state ON sync_queue(company_id, state, created_at)',
        );
      },
    );
    _database = db;
    return db;
  }

  Future<void> setIdentity({
    required int companyId,
    required int userId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('offline_company_id', companyId);
    await prefs.setInt('offline_user_id', userId);
  }

  Future<void> clearActiveIdentity() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('offline_company_id');
    await prefs.remove('offline_user_id');
  }

  Future<int?> get companyId async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt('offline_company_id');
  }

  Future<int?> get userId async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt('offline_user_id');
  }

  String _text(dynamic value) => '${value ?? ''}'.trim();

  double _number(dynamic value) =>
      double.tryParse('${value ?? 0}'.replaceAll(',', '.')) ?? 0;

  Map<String, dynamic>? _decodeMap(String? value) {
    if (value == null || value.isEmpty) return null;
    try {
      final decoded = jsonDecode(value);
      return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> cacheItems(
    Iterable<dynamic> items, {
    bool replaceAll = false,
  }) async {
    final cid = await companyId;
    if (cid == null) return;

    final db = await _db;
    await db.transaction((txn) async {
      if (replaceAll) {
        await txn.delete(
          'offline_items',
          where: 'company_id = ?',
          whereArgs: [cid],
        );
      }

      final now = DateTime.now().millisecondsSinceEpoch;
      final batch = txn.batch();
      for (final raw in items) {
        if (raw is! Map) continue;
        final item = Map<String, dynamic>.from(raw);
        final id = _text(item['id']);
        if (id.isEmpty) continue;

        batch.insert(
          'offline_items',
          {
            'company_id': cid,
            'item_id': id,
            'barcode': _text(item['barcode']),
            'gtin': _text(item['gtin']),
            'ntin': _text(item['ntin']),
            'name': _text(item['name']),
            'item_type': _text(item['item_type']).isEmpty
                ? 'product'
                : _text(item['item_type']),
            'category': _text(item['category']),
            'payload': jsonEncode(item),
            'updated_at': now,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      await batch.commit(noResult: true);
    });
  }

  Future<List<dynamic>> items({
    String type = 'all',
    String category = 'all',
    String query = '',
    int? limit,
    int offset = 0,
  }) async {
    final cid = await companyId;
    if (cid == null) return const [];

    final where = <String>['company_id = ?'];
    final args = <Object?>[cid];

    if (type != 'all') {
      where.add('item_type = ?');
      args.add(type);
    }
    if (category != 'all') {
      where.add('LOWER(category) = LOWER(?)');
      args.add(category);
    }

    final needle = query.trim().toLowerCase();
    if (needle.isNotEmpty) {
      where.add('''
        (
          LOWER(name) LIKE ?
          OR LOWER(barcode) LIKE ?
          OR LOWER(gtin) LIKE ?
          OR LOWER(ntin) LIKE ?
        )
      ''');
      final pattern = '%$needle%';
      args.addAll([pattern, pattern, pattern, pattern]);
    }

    final rows = await (await _db).query(
      'offline_items',
      columns: ['payload'],
      where: where.join(' AND '),
      whereArgs: args,
      orderBy: 'CAST(item_id AS INTEGER) DESC, item_id DESC',
      limit: limit,
      offset: limit == null ? null : offset,
    );

    return rows
        .map((row) => _decodeMap(row['payload'] as String?))
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  Future<Map<String, dynamic>?> findItem(String rawCode) async {
    final cid = await companyId;
    if (cid == null) return null;

    final scanned = ScannedProductCode.parse(rawCode);
    if (scanned.lookupCandidates.isEmpty) return null;

    final db = await _db;
    for (final candidate in scanned.lookupCandidates) {
      final rows = await db.query(
        'offline_items',
        columns: ['payload'],
        where: '''
          company_id = ?
          AND (barcode = ? OR gtin = ? OR ntin = ?)
        ''',
        whereArgs: [cid, candidate, candidate, candidate],
        limit: 1,
      );
      if (rows.isEmpty) continue;
      final item = _decodeMap(rows.first['payload'] as String?);
      if (item != null) return item;
    }
    return null;
  }

  Map<String, dynamic> barcodeResult(
    Map<String, dynamic> item,
    String rawCode,
  ) {
    final scanned = ScannedProductCode.parse(rawCode);
    return {
      'found': true,
      'local': true,
      'offline': true,
      'id': item['id'],
      'name': item['name'],
      'price': item['price'] ?? item['retail_price'],
      'retail_price': item['retail_price'] ?? item['price'],
      'purchase_price': item['purchase_price'],
      'unit': item['unit'],
      'category': item['category'],
      'barcode': item['barcode'],
      'gtin': item['gtin'] ?? scanned.gtin,
      'ntin': item['ntin'],
      'is_marked': item['is_marked'],
      'item_type': item['item_type'] ?? 'product',
      'quantity': item['quantity'] ?? item['stock'],
      'image': item['image'],
      'image_url': item['image_url'],
      'excise_stamp': scanned.markingCode,
      'lookup_code': scanned.lookupCode,
    };
  }

  Future<void> cacheClients(
    Iterable<dynamic> clients, {
    required bool deleted,
    bool replaceAll = false,
  }) async {
    final cid = await companyId;
    if (cid == null) return;
    final db = await _db;

    await db.transaction((txn) async {
      if (replaceAll) {
        await txn.delete(
          'offline_clients',
          where: 'company_id = ? AND is_deleted = ?',
          whereArgs: [cid, deleted ? 1 : 0],
        );
      }

      final now = DateTime.now().millisecondsSinceEpoch;
      final batch = txn.batch();
      for (final raw in clients) {
        if (raw is! Map) continue;
        final client = Map<String, dynamic>.from(raw);
        final id = _text(client['id']);
        if (id.isEmpty) continue;

        batch.insert(
          'offline_clients',
          {
            'company_id': cid,
            'client_id': id,
            'iin': _text(client['iin']),
            'phone': _text(client['phone']),
            'full_name': _text(client['full_name']),
            'company_name': _text(client['company_name']),
            'is_deleted': deleted ? 1 : 0,
            'payload': jsonEncode(client),
            'updated_at': now,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      await batch.commit(noResult: true);
    });
  }

  Future<List<dynamic>> clients({
    bool deleted = false,
    String query = '',
    int? limit,
    int offset = 0,
  }) async {
    final cid = await companyId;
    if (cid == null) return const [];

    final where = <String>['company_id = ?', 'is_deleted = ?'];
    final args = <Object?>[cid, deleted ? 1 : 0];
    final needle = query.trim().toLowerCase();
    if (needle.isNotEmpty) {
      where.add('''
        (
          LOWER(full_name) LIKE ?
          OR LOWER(company_name) LIKE ?
          OR LOWER(phone) LIKE ?
          OR LOWER(iin) LIKE ?
        )
      ''');
      final pattern = '%$needle%';
      args.addAll([pattern, pattern, pattern, pattern]);
    }

    final rows = await (await _db).query(
      'offline_clients',
      columns: ['payload'],
      where: where.join(' AND '),
      whereArgs: args,
      orderBy: 'CAST(client_id AS INTEGER) DESC, client_id DESC',
      limit: limit,
      offset: limit == null ? null : offset,
    );

    return rows
        .map((row) => _decodeMap(row['payload'] as String?))
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  Future<Map<String, dynamic>?> findClientByIin(String iin) async {
    final cid = await companyId;
    if (cid == null) return null;

    final normalized = iin.replaceAll(RegExp(r'\D'), '');
    if (normalized.isEmpty) return null;

    final rows = await (await _db).query(
      'offline_clients',
      columns: ['payload'],
      where: 'company_id = ? AND is_deleted = 0 AND iin = ?',
      whereArgs: [cid, normalized],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    return _decodeMap(rows.first['payload'] as String?);
  }

  Future<void> cacheStock(
    Iterable<dynamic> stock, {
    bool replaceAll = false,
  }) async {
    final cid = await companyId;
    if (cid == null) return;
    final values = stock.toList();
    final db = await _db;

    await db.transaction((txn) async {
      if (replaceAll) {
        await txn.delete(
          'offline_stock',
          where: 'company_id = ?',
          whereArgs: [cid],
        );
      }
      final now = DateTime.now().millisecondsSinceEpoch;
      final batch = txn.batch();
      for (final raw in values) {
        if (raw is! Map) continue;
        final item = Map<String, dynamic>.from(raw);
        final id = _text(item['id'] ?? item['item_id']);
        if (id.isEmpty) continue;
        batch.insert(
          'offline_stock',
          {
            'company_id': cid,
            'item_id': id,
            'payload': jsonEncode(item),
            'updated_at': now,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      await batch.commit(noResult: true);
    });

    await cacheItems(values);
  }

  Future<List<dynamic>> stock() async {
    final cid = await companyId;
    if (cid == null) return const [];

    final rows = await (await _db).query(
      'offline_stock',
      columns: ['payload'],
      where: 'company_id = ?',
      whereArgs: [cid],
      orderBy: 'CAST(item_id AS INTEGER) DESC, item_id DESC',
    );
    return rows
        .map((row) => _decodeMap(row['payload'] as String?))
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  Future<void> cacheSnapshot(String key, dynamic value) async {
    final cid = await companyId;
    if (cid == null) return;

    await (await _db).insert(
      'offline_snapshots',
      {
        'company_id': cid,
        'cache_key': key,
        'payload': jsonEncode(value),
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<dynamic> snapshot(String key) async {
    final cid = await companyId;
    if (cid == null) return null;

    final rows = await (await _db).query(
      'offline_snapshots',
      columns: ['payload'],
      where: 'company_id = ? AND cache_key = ?',
      whereArgs: [cid, key],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    try {
      return jsonDecode(rows.first['payload'] as String);
    } catch (_) {
      return null;
    }
  }

  Future<String> enqueue({
    required String operationType,
    required String method,
    required String path,
    Object? body,
  }) async {
    final cid = await companyId;
    if (cid == null) {
      throw StateError('Компания не определена для офлайн-операции');
    }
    final uid = await userId;
    final now = DateTime.now().millisecondsSinceEpoch;
    final operationId = '${cid}_${uid ?? 0}_${now}_${DateTime.now().microsecondsSinceEpoch}';

    await (await _db).insert(
      'sync_queue',
      {
        'operation_id': operationId,
        'company_id': cid,
        'user_id': uid,
        'operation_type': operationType,
        'method': method,
        'path': path,
        'body': body == null ? null : jsonEncode(body),
        'state': 'pending',
        'attempts': 0,
        'created_at': now,
        'updated_at': now,
      },
      conflictAlgorithm: ConflictAlgorithm.abort,
    );
    return operationId;
  }

  Future<List<Map<String, dynamic>>> pendingOperations({
    int limit = 25,
  }) async {
    final cid = await companyId;
    if (cid == null) return const [];

    final rows = await (await _db).query(
      'sync_queue',
      where: "company_id = ? AND state IN ('pending', 'syncing')",
      whereArgs: [cid],
      orderBy: 'created_at ASC',
      limit: limit,
    );

    return rows.map((row) {
      final operation = Map<String, dynamic>.from(row);
      final rawBody = operation['body'];
      if (rawBody is String && rawBody.isNotEmpty) {
        try {
          final decoded = jsonDecode(rawBody);
          operation['body'] = decoded is Map
              ? Map<String, dynamic>.from(decoded)
              : <String, dynamic>{};
        } catch (_) {
          operation['body'] = <String, dynamic>{};
        }
      } else {
        operation['body'] = <String, dynamic>{};
      }
      return operation;
    }).toList();
  }

  Future<void> markOperationSyncing(String operationId) async {
    await (await _db).update(
      'sync_queue',
      {
        'state': 'syncing',
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      where: 'operation_id = ?',
      whereArgs: [operationId],
    );
  }

  Future<void> markOperationPending(
    String operationId, {
    String? error,
  }) async {
    await (await _db).rawUpdate(
      '''
      UPDATE sync_queue
      SET state='pending',
          attempts=attempts+1,
          last_error=?,
          updated_at=?
      WHERE operation_id=?
      ''',
      [error, DateTime.now().millisecondsSinceEpoch, operationId],
    );
  }

  Future<void> markOperationSynced(String operationId) async {
    await (await _db).update(
      'sync_queue',
      {
        'state': 'synced',
        'last_error': null,
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      where: 'operation_id = ?',
      whereArgs: [operationId],
    );
  }

  Future<void> markOperationError(String operationId, String error) async {
    await (await _db).rawUpdate(
      '''
      UPDATE sync_queue
      SET state='error',
          attempts=attempts+1,
          last_error=?,
          updated_at=?
      WHERE operation_id=?
      ''',
      [error, DateTime.now().millisecondsSinceEpoch, operationId],
    );
  }

  Future<void> applyStockDelta(int itemId, double delta) async {
    final cid = await companyId;
    if (cid == null || delta == 0) return;

    final db = await _db;
    await db.transaction((txn) async {
      Future<void> updatePayload(String table) async {
        final rows = await txn.query(
          table,
          columns: ['payload'],
          where: 'company_id = ? AND item_id = ?',
          whereArgs: [cid, '$itemId'],
          limit: 1,
        );
        if (rows.isEmpty) return;

        final payload = _decodeMap(rows.first['payload'] as String?);
        if (payload == null) return;

        final current = _number(payload['stock'] ?? payload['quantity']);
        final next = current + delta;
        payload['stock'] = next;
        payload['quantity'] = next;

        await txn.update(
          table,
          {
            'payload': jsonEncode(payload),
            'updated_at': DateTime.now().millisecondsSinceEpoch,
          },
          where: 'company_id = ? AND item_id = ?',
          whereArgs: [cid, '$itemId'],
        );
      }

      await updatePayload('offline_stock');
      await updatePayload('offline_items');
    });
  }

  Future<void> applySaleStockDelta(List<dynamic> cart) async {
    for (final raw in cart) {
      if (raw is! Map) continue;
      final item = Map<String, dynamic>.from(raw);
      final itemType = '${item['item_type'] ?? 'product'}'.trim();
      if (!{'product', 'ingredient', 'semi_finished'}.contains(itemType)) {
        continue;
      }
      final itemId = int.tryParse('${item['id'] ?? ''}');
      final quantity = _number(item['qty'] ?? item['quantity']);
      if (itemId == null || quantity <= 0) continue;
      await applyStockDelta(itemId, -quantity);
    }
  }

  Future<int> pendingCount() async {
    final cid = await companyId;
    if (cid == null) return 0;
    final rows = await (await _db).rawQuery(
      '''
      SELECT COUNT(*) AS count
      FROM sync_queue
      WHERE company_id = ? AND state IN ('pending', 'syncing')
      ''',
      [cid],
    );
    return (rows.first['count'] as int?) ?? 0;
  }
}
