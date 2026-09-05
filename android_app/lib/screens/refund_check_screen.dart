import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../services/api_service.dart';
import '../services/printer_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class RefundCheckScreen extends StatefulWidget {
  final int saleId;
  final bool autoPrint;

  const RefundCheckScreen({
    super.key,
    required this.saleId,
    this.autoPrint = false,
  });

  @override
  State<RefundCheckScreen> createState() => _RefundCheckScreenState();
}

class _RefundCheckScreenState extends State<RefundCheckScreen> {
  Map<String, dynamic>? refund;
  int columns = 32;
  bool printing = false;
  String? error;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final results = await Future.wait<dynamic>([
        ApiService.refundReceipt(widget.saleId),
        PrinterService.receiptColumns(),
      ]);
      final document = Map<String, dynamic>.from(results[0] as Map);
      if (!mounted) return;
      setState(() {
        refund = document;
        columns = results[1] as int;
        error = null;
      });
      if (widget.autoPrint) {
        await PrinterService.autoPrintRefundIfEnabled(document);
      }
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    }
  }

  Future<void> printReceipt() async {
    final document = refund;
    if (document == null || printing) return;
    setState(() => printing = true);
    final ok = await PrinterService.printRefundReceipt(document);
    if (!mounted) return;
    setState(() => printing = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok
              ? 'Чек возврата отправлен на принтер'
              : 'Не удалось напечатать. Проверьте подключение принтера',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Чек возврата')),
      body: AdaptiveContent(
        maxWidth: 680,
        child: error != null
            ? ScreenStateView(
                icon: Icons.receipt_long_outlined,
                title: 'Чек возврата не загрузился',
                message: error!,
                onAction: load,
              )
            : refund == null
                ? const Center(child: CircularProgressIndicator())
                : _content(),
      ),
    );
  }

  Widget _content() {
    final document = refund!;
    final fiscal = document['fiscal'] is Map
        ? Map<String, dynamic>.from(document['fiscal'] as Map)
        : <String, dynamic>{};
    final qr = '${fiscal['qr'] ?? ''}'.trim();
    final receipt = PrinterService.buildPrintTextFromRefund(
      document,
      width: columns,
    );

    return Column(children: [
      Expanded(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: AppColors.danger.withOpacity(.08),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Row(children: [
                Icon(Icons.undo_rounded, color: AppColors.danger),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Макет подготовлен для Bluetooth ESC/POS принтера',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
              ]),
            ),
            const SizedBox(height: 12),
            Card(
              color: Colors.white,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(children: [
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SelectableText(
                      receipt,
                      style: TextStyle(
                        fontFamily: 'monospace',
                        fontSize: columns > 32 ? 10 : 12,
                        height: 1.35,
                        color: Colors.black,
                      ),
                    ),
                  ),
                  if (qr.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    QrImageView(data: qr, size: 150),
                  ],
                ]),
              ),
            ),
          ],
        ),
      ),
      Material(
        color: AppColors.surface,
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: printing ? null : printReceipt,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.danger,
                ),
                icon: printing
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.print_rounded),
                label: Text(printing ? 'Печатаем…' : 'Печатать чек возврата'),
              ),
            ),
          ),
        ),
      ),
    ]);
  }
}
