import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// A manual Kaspi tender is not a Kaspi POS transaction. No transaction ID
/// means there is no bank operation that this application can reverse.
bool isManualKaspiSale(Map<String, dynamic> sale) {
  final method = '${sale['sale_type'] ?? ''}'.trim().toLowerCase();
  final transactionId = '${sale['kaspi_transaction_id'] ?? ''}'.trim();
  return method == 'kaspi' && transactionId.isEmpty;
}

/// Returns true for explicitly confirmed fiscal-only Kaspi reversals, false
/// for ordinary refunds, and null when the operator cancels.
Future<bool?> confirmSaleRefund(
  BuildContext context,
  Map<String, dynamic> sale,
) async {
  final manualKaspi = isManualKaspiSale(sale);
  final hasFiscalReceipt = '${sale['rekassa_ticket_id'] ?? ''}'.trim().isNotEmpty;

  final message = manualKaspi
      ? 'В этом чеке вручную указан способ оплаты «Kaspi», '
          'но transactionId терминала отсутствует.\n\n'
          '${hasFiscalReceipt ? 'reKassa сформирует чек возврата. ' : 'Исходного фискального чека reKassa нет. '}'
          'Товар вернётся на склад, сумма продажи будет скорректирована.\n\n'
          'ДЕНЬГИ ЧЕРЕЗ KASPI НЕ ВОЗВРАЩАЮТСЯ.\n\n'
          'Подтверждайте только для ошибочного или дублирующего чека, '
          'если банковский возврат не требуется.'
      : 'Товар вернётся на склад, сумма продажи и прибыль уменьшатся, '
          'а при наличии исходного фискального чека reKassa '
          'оформит чек возврата. Отменить операцию нельзя.';

  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      icon: const Icon(Icons.undo_rounded, color: AppColors.danger, size: 36),
      title: Text(
        manualKaspi ? 'Отменить ошибочный чек Kaspi?' : 'Оформить возврат?',
      ),
      content: Text(message, textAlign: TextAlign.center),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, false),
          child: const Text('Отмена'),
        ),
        ElevatedButton(
          onPressed: () => Navigator.pop(dialogContext, true),
          style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
          child: Text(
            manualKaspi ? 'Возврат без Kaspi POS' : 'Подтвердить возврат',
          ),
        ),
      ],
    ),
  );
  return confirmed == true ? manualKaspi : null;
}
