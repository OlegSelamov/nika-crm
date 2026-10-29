# ИСНА / Smart Bridge — диагностика на VPS 47167

## Подтверждено по состоянию на 2026-10-29

- На VPS `47167` одновременно работает служба `nika-business-test` (пользователь `www-data`) и StrongSwan IPsec `nika-smartbridge-test`.
- IPsec selector: `195.49.215.49/32 → 195.12.113.7/32`.
- Уже выполненная оператором команда `python3 /tmp/isna_gateway_probe.py` показала:
  `{"schema":1,"tcpOk":true,"httpOk":true,"httpStatus":200}`.
- Ветка `test` теперь использует **прямой локальный** фиксированный TCP+HTTP GET probe с привязкой исходящего IP к `195.49.215.49`. **Отдельный SSH-мост не нужен**.

## Проверка от пользователя службы

```bash
cd /var/www/nika-business-test
sudo -u www-data /usr/bin/python3 scripts/isna_gateway_probe.py
```

При активном VPN ожидается `"tcpOk":true`, `"httpOk":true`, `"httpStatus":200`.
Эта проверка не требует root, SSH-ключей, публикации портов или нового APK.

В Android TEST открыть **Бухгалтерия → ИСНА TEST → Проверить доступность**.
Ожидаемый источник: `VPS 47167 (локальный IPsec)`.
Если результат отличается, проверить текущий IPsec и непосредственный вызов
`sudo -u www-data /usr/bin/python3 scripts/isna_gateway_probe.py`.

Если на `47167` уже создали случайный `/etc/nika-isna/probe_id_ed25519`,
он **не нужен** для этой архитектуры и не должен быть внесён в
`authorized_keys`. Не передавайте приватные ключи в чат.

## Область безопасности

- Только TEST Flask route с авторизацией пользователя и выбранной организацией;
  точный фиксированный IP+порт+путь, только TCP и HTTP GET.
- Никакого произвольного HTTP proxy, SSH forwarding, передачи ЭЦП, SOAP POST
  или отправки реальных деклараций.
- Для отправки ФНО всё ещё требуются официальная схема XML, подтверждённые
  `senderId` и `serviceId` и подписание SOAP WS-Security ГОСТ.
- `main` и production database не меняются.
