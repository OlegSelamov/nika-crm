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
    // raw is the exact scanner value that must be forwarded as excise_stamp.
    // payload is only a normalized copy used for GTIN/EAN lookup.
    final raw = value;
    var payload = raw.replaceFirst(
      RegExp(r'^[\u0000-\u001c\u001e-\u0020\u007f]+'),
      '',
    );

    // Some scanners prepend an AIM symbology identifier such as ]d2.
    // Remove it only from the lookup copy, never from the raw marking.
    payload = payload.replaceFirst(RegExp(r'^\][A-Za-z0-9]{2}'), '');
    payload = payload.replaceFirst(
      RegExp(r'^[\u0000-\u001c\u001e-\u0020\u007f]+'),
      '',
    );
    payload = payload.replaceFirst(
      RegExp(r'[\u0000-\u001c\u001e-\u0020\u007f]+$'),
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
      markingCode: hasMarkingTail ? raw : null,
    );
  }

  bool get isEmpty => payload.isEmpty;
  bool get isMarkingCode => markingCode != null;

  String get lookupCode => ean13 ?? gtin ?? payload;

  List<String> get lookupCandidates {
    final result = <String>[];

    void add(String? value) {
      final normalized = value?.trim() ?? '';
      if (normalized.isNotEmpty && !result.contains(normalized)) {
        result.add(normalized);
      }
    }

    if (gtin != null) {
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
