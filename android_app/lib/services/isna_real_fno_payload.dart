import 'dart:convert';

/// Turns an *already official* FNO_INTEGRATION JSON request into an unsigned
/// inner document. No guessed fields, taxpayer defaults or network calls.
///
/// "Values object" copied from the ISNA browser console is NOT necessarily
/// the same as the service's fnoDto JSON: never silently wrap arbitrary data.
String buildUnsignedRealFnoXml({
  required String sourceJson,
  required String expectedCode,
}) {
  if (!const {'200.00', '910.00'}.contains(expectedCode)) {
    throw const FormatException('Поддерживаются только ФНО 200.00 и 910.00.');
  }
  if (sourceJson.trim().isEmpty ||
      utf8.encode(sourceJson).length > 100000) {
    throw const FormatException('Нужен JSON ФНО размером до 100 КБ.');
  }
  dynamic decoded;
  try {
    decoded = jsonDecode(sourceJson);
  } on FormatException {
    throw const FormatException('JSON заполненной ФНО содержит ошибку.');
  }
  if (decoded is! Map<String, dynamic> ||
      decoded.length != 2 ||
      !decoded.containsKey('code') ||
      !decoded.containsKey('fnoDto') ||
      decoded['code'] != expectedCode ||
      decoded['fnoDto'] is! Map<String, dynamic> ||
      (decoded['fnoDto'] as Map).isEmpty) {
    throw const FormatException(
      'Ожидается полный JSON сервиса с code и fnoDto выбранной ФНО. '
      'Values object из кабинета нельзя выдавать за готовый fnoDto '
      'без сверки с официальной схемой.',
    );
  }
  final payload = decoded['fnoDto'] as Map<String, dynamic>;
  if (payload.containsKey('nikaOfflineDemo')) {
    throw const FormatException('Демонстрационные данные запрещены.');
  }

  // Serialize the exact supplied two-field business object. The XML signer
  // signs <root><data>...literal JSON text...</data></root>, then encloses
  // XMLDSig. Any semantic changes after signing would invalidate the signature.
  final jsonText = jsonEncode(decoded);
  final escaped = const HtmlEscape(HtmlEscapeMode.element).convert(jsonText);
  return '<?xml version="1.0" encoding="UTF-8"?>'
      '<root><data>$escaped</data></root>';
}
