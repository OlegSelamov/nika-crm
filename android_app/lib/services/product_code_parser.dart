class ScannedProductCode {
  final String raw;
  final String payload;
  final String? gtin;
  final String? ean13;
  final String? markingCode;

  const ScannedProductCode._({
    required this.raw,
    required this.payload,
    required this.gtin,
    required this.ean13,
    required this.markingCode,
  });

  factory ScannedProductCode.parse(String value) {
    final raw = value.trim();
    var payload = raw.replaceFirst(
      RegExp(r'^[\u0000-\u0020\u007f]+'),
      '',
    );

    // Some hardware scanners prepend an AIM symbology identifier (for
    // example ]d2 for GS1 DataMatrix). It describes the scanner format and is
    // not part of the marking code itself.
    payload = payload.replaceFirst(RegExp(r'^\][A-Za-z0-9]{2}'), '');
    payload = payload.replaceFirst(
      RegExp(r'^[\u0000-\u0020\u007f]+'),
      '',
    );

    final parenthesized = RegExp(r'^\(01\)(\d{14})').firstMatch(payload);
    final compact = RegExp(r'^01(\d{14})').firstMatch(payload);
    final match = parenthesized ?? compact;
    final gtin = match?.group(1);
    final ean13 = gtin != null && gtin.startsWith('0')
        ? gtin.substring(1)
        : null;
    final hasMarkingTail = match != null && payload.length > match.end;

    return ScannedProductCode._(
      raw: raw,
      payload: payload,
      gtin: gtin,
      ean13: ean13,
      markingCode: hasMarkingTail ? payload : null,
    );
  }

  bool get isEmpty => payload.isEmpty;

  bool get isMarkingCode => markingCode != null;

  String get lookupCode =>
      ean13 ?? gtin ?? payload;

  List<String> get lookupCandidates {
    final result = <String>[];

    void add(String? value) {
      final normalized = value?.trim() ?? '';
      if (normalized.isNotEmpty && !result.contains(normalized)) {
        result.add(normalized);
      }
    }

    if (gtin != null) {
      // Catalog barcodes are commonly stored as EAN-13 while the marking code
      // carries the same value as GTIN-14 with a leading zero.
      add(ean13);
      add(gtin);
    } else {
      add(payload);
    }

    return result;
  }

  bool matchesItem(Map<String, dynamic> item) {
    final identifiers = <String>{
      '${item['barcode'] ?? ''}'.trim(),
      '${item['gtin'] ?? ''}'.trim(),
      '${item['ntin'] ?? ''}'.trim(),
    }..remove('');

    return lookupCandidates.any(identifiers.contains);
  }
}
