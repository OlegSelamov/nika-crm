import 'package:shared_preferences/shared_preferences.dart';
import 'package:print_bluetooth_thermal/print_bluetooth_thermal.dart';
import 'package:charset_converter/charset_converter.dart';
import 'package:intl/intl.dart';

class PrinterService {
  static const String printerEncodingPreference = 'printer_encoding';
  static const String gbkEncoding = 'gbk';
  static const String cp866Encoding = 'cp866';

  static bool _isPrinting = false;

  static Future<int> receiptColumns() async {
    final prefs = await SharedPreferences.getInstance();
    final paperWidth = prefs.getInt('printer_paper_width') ?? 58;
    return paperWidth >= 80 ? 48 : 32;
  }

  static Future<bool> printReceipt({
    required String text,
	String? qrData,
  }) async {
    if (_isPrinting) return false;

    _isPrinting = true;

    try {
      final prefs = await SharedPreferences.getInstance();
      final mac = prefs.getString("printer_mac");

      if (mac == null || mac.isEmpty) {
        return false;
      }

      try {
        await PrintBluetoothThermal.disconnect;
        await Future.delayed(const Duration(milliseconds: 500));
      } catch (_) {}

      final connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: mac,
      );

      if (!connected) {
        return false;
      }

      final bytes = <int>[];

      // init printer
      bytes.addAll([0x1B, 0x40]);

      // Keep the original GBK mode for compatible printers. XP-P810 can use
      // PC866 (Cyrillic #2): ESC/POS table 17 + CP866-encoded text.
      final configuredEncoding =
          prefs.getString(printerEncodingPreference) ?? gbkEncoding;
      final useCp866 = configuredEncoding == cp866Encoding;
      bytes.addAll([0x1B, 0x74, useCp866 ? 17 : 22]);

	  final encoded = await CharsetConverter.encode(
		useCp866 ? "CP866" : "GBK",
		text,
	  );

	bytes.addAll(encoded);
	
	  if (qrData != null && qrData.isNotEmpty) {
	    bytes.addAll([0x1B, 0x61, 1]); // центр

	    final qrBytes =
		    await CharsetConverter.encode(
		  "GBK",
		  qrData,
	    );

	    bytes.addAll([0x1D, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00]);
	    bytes.addAll([0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, 0x06]);
	    bytes.addAll([0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x30]);

	    final len = qrBytes.length + 3;
	    final pL = len % 256;
	    final pH = len ~/ 256;

	    bytes.addAll([0x1D, 0x28, 0x6B, pL, pH, 0x31, 0x50, 0x30]);
	    bytes.addAll(qrBytes);

	    bytes.addAll([0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30]);

	    bytes.addAll([0x1B, 0x61, 0]); // влево
	  }

      // feed paper
      bytes.addAll([0x0A, 0x0A, 0x0A]);

      final ok = await PrintBluetoothThermal.writeBytes(bytes);

      await Future.delayed(const Duration(seconds: 2));

      try {
        await PrintBluetoothThermal.disconnect;
      } catch (_) {}

      return ok;
    } catch (e) {
      print("PRINT ERROR: $e");

      try {
        await PrintBluetoothThermal.disconnect;
      } catch (_) {}

      return false;
    } finally {
      _isPrinting = false;
    }
  }

  static Future<void> autoPrintIfEnabled(
    Map<String, dynamic> sale,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final autoPrint = prefs.getBool("auto_print") ?? false;

    if (!autoPrint) return;

	await printSaleReceipt(sale);
  }

  static Future<void> autoPrintRefundIfEnabled(
    Map<String, dynamic> refund,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final autoPrint = prefs.getBool('auto_print') ?? false;
    if (autoPrint) await printRefundReceipt(refund);
  }

  static Future<bool> printSaleReceipt(Map<String, dynamic> sale) async {
    final width = await receiptColumns();
    final fiscal = sale['rekassa_qr']?.toString().trim() ?? '';
    return printReceipt(
      text: buildPrintTextFromSale(sale, width: width),
      qrData: fiscal.isNotEmpty ? fiscal : "SALE-${sale['id']}",
    );
  }

  static Future<bool> printRefundReceipt(Map<String, dynamic> refund) async {
    final width = await receiptColumns();
    final fiscal = refund['fiscal'] is Map
        ? Map<String, dynamic>.from(refund['fiscal'] as Map)
        : <String, dynamic>{};
    final qr = '${fiscal['qr'] ?? ''}'.trim();
    return printReceipt(
      text: buildPrintTextFromRefund(refund, width: width),
      qrData: qr.isNotEmpty ? qr : null,
    );
  }

  static String _repeat(String value, int count) =>
      List<String>.filled(count > 0 ? count : 0, value).join();

  static String lineLR(String left, String right, {int width = 32}) {
    final safeRight = right.length >= width
        ? right.substring(right.length - width)
        : right;
    if (safeRight.length >= width) return safeRight;
    final maxLeft = width - safeRight.length - 1;
    final safeLeft = maxLeft <= 0
        ? ''
        : left.length > maxLeft ? left.substring(0, maxLeft) : left;
    final spaces = width - safeLeft.length - safeRight.length;
    return safeLeft + _repeat(' ', spaces > 0 ? spaces : 0) + safeRight;
  }

  static String centerText(String text, {int width = 32}) {
    final safe = text.length > width ? text.substring(0, width) : text;
    final spaces = ((width - safe.length) / 2).floor();
    return _repeat(' ', spaces > 0 ? spaces : 0) + safe;
  }

  static List<String> wrapText(String text, {int width = 32}) {
    final normalized = text.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (normalized.isEmpty) return const [];
    final result = <String>[];
    var line = '';
    for (final word in normalized.split(' ')) {
      if (word.length > width) {
        if (line.isNotEmpty) {
          result.add(line);
          line = '';
        }
        for (var start = 0; start < word.length; start += width) {
          final end = (start + width).clamp(0, word.length).toInt();
          result.add(word.substring(start, end));
        }
      } else if (line.isEmpty) {
        line = word;
      } else if (line.length + word.length + 1 <= width) {
        line = '$line $word';
      } else {
        result.add(line);
        line = word;
      }
    }
    if (line.isNotEmpty) result.add(line);
    return result;
  }

  static String _plainNumber(dynamic value) {
    final number = double.tryParse('${value ?? 0}') ?? 0;
    return number == number.roundToDouble()
        ? number.toInt().toString()
        : number.toStringAsFixed(2);
  }

  static String buildPrintTextFromSale(
    Map<String, dynamic> sale, {
    int width = 32,
  }) {
    final buffer = StringBuffer();

	buffer.writeln(
	  centerText(
		sale["company_name"] ?? "",
		width: width,
	  ),
	);

	buffer.writeln(
	  lineLR(
		"БИН/ИИН:",
		"${sale["company_bin"] ?? ""}",
		width: width,
	  ),
	);

	final address =
		(sale["company_address"] ?? "")
			.toString();

	for (final line in address.split(",")) {
	  if (line.trim().isNotEmpty) {
		buffer.writeln(
		  centerText(
			line.trim(),
			width: width,
		  ),
		);
	  }
	}

    buffer.writeln(_repeat('=', width));

	final createdAt = (sale["created_at"] ?? "").toString();
	String formattedDate = (sale["check_date"] ?? "").toString();

	// Сервер уже отдаёт check_date во времени Казахстана. Не прибавляем
	// ещё пять часов: это приводило к двойному смещению на VPS.
	if (formattedDate.isEmpty) {
	  formattedDate = createdAt;
	  try {
	    final date = DateTime.parse(createdAt);
	    formattedDate = DateFormat('dd.MM.yyyy HH:mm').format(date);
	  } catch (_) {}
	}

	buffer.writeln(
	  lineLR(
		"Чек №${sale["sale_number"] ?? sale["id"]}",
		formattedDate,
		width: width,
	  ),
	);

    buffer.writeln(_repeat('-', width));

    final items = sale["items"] as List? ?? [];

    for (final item in items) {
      final qty = item["quantity"] ?? 0;
      final price = item["price"] ?? 0;
      final total = item["total"] ?? 0;

      for (final line in wrapText('${item["name"] ?? ""}', width: width)) {
        buffer.writeln(line);
      }

      buffer.writeln(lineLR(
        "$qty ${item["unit"] ?? "шт"} × $price",
        "$total тг",
        width: width,
      ));

      if ((item["gtin"] ?? "")
          .toString()
          .isNotEmpty) {
        buffer.writeln(
          "GTIN: ${item["gtin"]}",
        );
      }

      if ((item["ntin"] ?? "")
          .toString()
          .isNotEmpty) {
        buffer.writeln(
          "NTIN: ${item["ntin"]}",
        );
      }

      buffer.writeln(_repeat('-', width));
    }

    buffer.writeln("");

	buffer.writeln(
	  lineLR(
		"ИТОГО:",
		"${sale["total_amount"]} тг",
		width: width,
	  ),
	);

	String paymentName = "Неизвестно";

	switch ((sale["sale_type"] ?? "").toString()) {
	  case "cash":
		paymentName = "Наличные";
		break;

	  case "card":
		paymentName = "Банковская карта";
		break;

	  case "kaspi":
		paymentName = "Kaspi QR";
		break;
	}

	buffer.writeln(
	  lineLR(
		"Оплата:",
		paymentName,
		width: width,
	  ),
	);

    return buffer.toString();
  }

  static String buildPrintTextFromRefund(
    Map<String, dynamic> refund, {
    int width = 32,
  }) {
    final buffer = StringBuffer();
    final company = refund['company'] is Map
        ? Map<String, dynamic>.from(refund['company'] as Map)
        : <String, dynamic>{};
    final fiscal = refund['fiscal'] is Map
        ? Map<String, dynamic>.from(refund['fiscal'] as Map)
        : <String, dynamic>{};
    final items = List<dynamic>.from(refund['items'] ?? const []);

    buffer.writeln(centerText('${company['name'] ?? ''}', width: width));
    if ('${company['bin'] ?? ''}'.trim().isNotEmpty) {
      buffer.writeln(lineLR('БИН/ИИН:', '${company['bin']}', width: width));
    }
    for (final line in wrapText('${company['address'] ?? ''}', width: width)) {
      buffer.writeln(centerText(line, width: width));
    }
    buffer.writeln(_repeat('=', width));
    buffer.writeln(centerText('ЧЕК ВОЗВРАТА', width: width));
    buffer.writeln(lineLR(
      'Возврат №${refund['number'] ?? refund['source_id']}',
      '${refund['date'] ?? ''}',
      width: width,
    ));
    if ('${refund['original_date'] ?? ''}'.trim().isNotEmpty) {
      buffer.writeln(lineLR(
        'Исходный чек:',
        '${refund['original_date']}',
        width: width,
      ));
    }
    if ('${fiscal['document_number'] ?? ''}'.trim().isNotEmpty) {
      buffer.writeln(lineLR(
        'Документ №${fiscal['document_number']}',
        'Смена ${fiscal['shift_number'] ?? '-'}',
        width: width,
      ));
    }
    if ('${fiscal['ticket_number'] ?? ''}'.trim().isNotEmpty) {
      buffer.writeln('ФП: ${fiscal['ticket_number']}');
    }
    if ('${fiscal['rnm'] ?? ''}'.trim().isNotEmpty) {
      buffer.writeln('РНМ: ${fiscal['rnm']}');
    }
    if ('${fiscal['znm'] ?? ''}'.trim().isNotEmpty) {
      buffer.writeln('ЗНМ: ${fiscal['znm']}');
    }
    buffer.writeln(_repeat('-', width));

    for (final raw in items) {
      if (raw is! Map) continue;
      final item = Map<String, dynamic>.from(raw);
      for (final line in wrapText('${item['name'] ?? ''}', width: width)) {
        buffer.writeln(line);
      }
      buffer.writeln(lineLR(
        '${_plainNumber(item['quantity'])} ${item['unit'] ?? 'шт'} '
            '× ${_plainNumber(item['price'])}',
        '${_plainNumber(item['total'])} тг',
        width: width,
      ));
      if ('${item['gtin'] ?? ''}'.trim().isNotEmpty) {
        buffer.writeln('GTIN: ${item['gtin']}');
      }
      if ('${item['ntin'] ?? ''}'.trim().isNotEmpty) {
        buffer.writeln('NTIN: ${item['ntin']}');
      }
      buffer.writeln(_repeat('-', width));
    }

    buffer.writeln(lineLR(
      'К ВОЗВРАТУ:',
      '${_plainNumber(refund['total'])} тг',
      width: width,
    ));
    buffer.writeln(lineLR(
      'Возврат:',
      '${refund['payment_method'] ?? 'Оплата'}',
      width: width,
    ));
    if ('${fiscal['transaction_id'] ?? ''}'.trim().isNotEmpty) {
      for (final line in wrapText(
        'Транзакция: ${fiscal['transaction_id']}',
        width: width,
      )) {
        buffer.writeln(line);
      }
    }
    buffer.writeln(_repeat('=', width));
    buffer.writeln(centerText('ВОЗВРАТ ОФОРМЛЕН', width: width));
    return buffer.toString();
  }
}
