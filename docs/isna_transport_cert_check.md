# ИСНА: проверка соответствия зарегистрированного .cer и ключа .p12

Для работы Smart Bridge должен использоваться тот же GOST-сертификат, который
прикреплён в заявке на подключение (публичная часть транспортной ЭЦП).

В Android TEST уже есть нативная кнопка **«Подписать пробный XML (.p12)»**.
Она подписывает безопасный локальный XML с помощью KalkanCrypt и не
отправляет его на сервер.

## Порядок теста

1. На телефоне открыть TEST → Бухгалтерия → ИСНА TEST.
2. Выбрать **тот GOST .p12, для которого вы на pki.gov.kz скачали .cer**.
   Ввести пароль **только в приложении на своём телефоне**. Нажать
   **«Подписать пробный XML»** и **«Сохранить подписанный XML»**.
   Не включать отправку в ИСНА.
3. На своём компьютере сохранить **ту же публичную .cer**, которая была
   прикреплена в заявку Smart Bridge. Скопировать с телефона только
   подписанный тестовый XML на этот компьютер.
4. Запустить сравнение **на своём компьютере, не загружая файлы на VPS**:

   Windows PowerShell:
   ```powershell
   py scripts\isna_compare_transport_cert.py "C:\certificates\registered.cer" "C:\Users\user\Downloads\nika-isna-local-xml-signature-test.xml"
   ```

   Linux / macOS:
   ```bash
   python3 scripts/isna_compare_transport_cert.py /private/registered.cer /private/nika-isna-local-xml-signature-test.xml
   ```

   Если локального репозитория нет, скачайте **только скрипт**, без ключей:
   ```powershell
   Invoke-WebRequest "https://raw.githubusercontent.com/OlegSelamov/nika-crm/test/scripts/isna_compare_transport_cert.py" -OutFile "$env:USERPROFILE\Downloads\isna_compare_transport_cert.py"
   py "$env:USERPROFILE\Downloads\isna_compare_transport_cert.py" "C:\certificates\registered.cer" "C:\Users\user\Downloads\nika-isna-local-xml-signature-test.xml"
   ```

## Интерпретация

- `CERT_MATCH: YES`: сертификат, встроенный в пробную подпись, побайтно
  совпадает с публичным сертификатом, зарегистрированным в Smart Bridge.
- `CERT_MATCH: NO`: подписан другим сертификатом. Проверьте, какой именно
  GOST .p12 выбран в приложении и какая .cer загружена в Smart Bridge.
- `ERROR`: файл не подходит по формату, XML не содержит ds:Signature
  или встроенный X509Certificate, либо файл повреждён.

**Важно:** это **сравнение сертификатов**, а не независимая
криптографическая проверка XML-подписи. Самостоятельно не доказывает
владение закрытым ключом, не проверяет срок действия/отзыв сертификата и
не является подписью WS-Security SOAP. Настоящий запрос ФНО всё ещё
заблокирован, до официальной спецификации и теста транспортной подписи.

Никогда не отправляйте в чат или GitHub файл `.p12`, `.pfx` и пароль ЭЦП.
Сверку можно выполнить полностью локально; в чат достаточно прислать
только строку `CERT_MATCH`.
