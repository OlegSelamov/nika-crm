import 'dart:typed_data';

import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:printing/printing.dart';

import '../services/api_service.dart';
import '../services/printer_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class AccountingScreen extends StatefulWidget {
  const AccountingScreen({super.key});

  @override
  State<AccountingScreen> createState() => _AccountingScreenState();
}

class _AccountingScreenState extends State<AccountingScreen> {
  bool loading = true;
  bool syncing = false;
  String? error;
  Map<String, dynamic> data = {};

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await ApiService.mobileAccounting();
      if (mounted) setState(() => data = result);
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> sync() async {
    setState(() => syncing = true);
    try {
      await ApiService.syncMobileAccounting();
      await load();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Бухгалтерия обновлена')));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    } finally {
      if (mounted) setState(() => syncing = false);
    }
  }

  Future<void> markPaid(String kind, Map<String, dynamic> item) async {
    try {
      await ApiService.markMobileAccountingPaid(kind, item['id'] as int);
      await load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(readableError(e))));
    }
  }

  void openOperation(Map<String, dynamic> item) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _DocumentSheet(
        title: '${item['title'] ?? 'Документы операции'}',
        loader: () => ApiService.accountingOperationDocuments(item['id'] as int),
      ),
    );
  }

  void openDocument(Map<String, dynamic> item) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _DocumentSheet(
        title: '${item['title'] ?? 'Документ'}',
        loader: () => ApiService.accountingDocumentPreview(item['id'] as int),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return ScreenStateView(
        icon: Icons.account_balance_outlined,
        title: 'Бухгалтерия недоступна',
        message: error!,
        onAction: load,
      );
    }

    final summary = Map<String, dynamic>.from(data['summary'] ?? const {});
    return DefaultTabController(
      length: 4,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 10),
          child: Column(children: [
            Row(children: [
              const Expanded(child: SectionTitle('Финансы', subtitle: 'Операции и обязательства')),
              OutlinedButton.icon(
                onPressed: syncing ? null : sync,
                icon: syncing
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.sync_rounded),
                label: const Text('Сверить'),
              ),
            ]),
            const SizedBox(height: 12),
            LayoutBuilder(
              builder: (_, constraints) {
                final wide = constraints.maxWidth >= 760;
                final cards = <Widget>[
                  _SummaryCard(width: wide ? null : 174, title: 'Общий баланс', value: money(summary['balance']), icon: Icons.account_balance_wallet_outlined, color: AppColors.primary),
                  _SummaryCard(width: wide ? null : 174, title: 'Все доходы', value: money(summary['income']), icon: Icons.trending_up_rounded, color: AppColors.success),
                  _SummaryCard(width: wide ? null : 174, title: 'Все расходы', value: money(summary['expense']), icon: Icons.trending_down_rounded, color: AppColors.danger),
                  _SummaryCard(width: wide ? null : 174, title: 'Обязательства к оплате', value: money(summary['debt_total']), icon: Icons.schedule_rounded, color: AppColors.warning),
                ];
                return SizedBox(
                  height: 142,
                  child: wide
                      ? Row(
                          children: [
                            Expanded(child: cards[0]),
                            const SizedBox(width: 9),
                            Expanded(child: cards[1]),
                            const SizedBox(width: 9),
                            Expanded(child: cards[2]),
                            const SizedBox(width: 9),
                            Expanded(child: cards[3]),
                          ],
                        )
                      : ListView.separated(
                          scrollDirection: Axis.horizontal,
                          physics: const BouncingScrollPhysics(),
                          itemCount: cards.length,
                          separatorBuilder: (_, __) => const SizedBox(width: 9),
                          itemBuilder: (_, index) => cards[index],
                        ),
                );
              },
            ),
          ]),
        ),
        const TabBar(
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          tabs: [
            Tab(text: 'Операции'),
            Tab(text: 'Документы'),
            Tab(text: 'Налоги'),
            Tab(text: 'Долги'),
          ],
        ),
        Expanded(
          child: TabBarView(children: [
            _AccountingList(
              items: List<dynamic>.from(data['operations'] ?? const []),
              kind: 'operations',
              onRefresh: load,
              onOpen: openOperation,
            ),
            _AccountingList(
              items: List<dynamic>.from(data['documents'] ?? const []),
              kind: 'documents',
              onRefresh: load,
              onOpen: openDocument,
            ),
            _AccountingList(
              items: List<dynamic>.from(data['taxes'] ?? const []),
              kind: 'taxes',
              onRefresh: load,
              onPaid: (item) => markPaid('taxes', item),
            ),
            _AccountingList(
              items: List<dynamic>.from(data['debts'] ?? const []),
              kind: 'debts',
              onRefresh: load,
              onPaid: (item) => markPaid('debts', item),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final double? width;
  final String title;
  final String value;
  final IconData icon;
  final Color color;

  const _SummaryCard({
    this.width = 174,
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(13),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(color: color.withOpacity(.11), borderRadius: BorderRadius.circular(11)),
              child: Icon(icon, color: color, size: 19),
            ),
            const SizedBox(height: 9),
            SizedBox(
              width: double.infinity,
              height: 25,
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900)),
              ),
            ),
            const SizedBox(height: 4),
            Expanded(
              child: Align(
                alignment: Alignment.topLeft,
                child: Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.muted, fontSize: 12, height: 1.2),
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _AccountingList extends StatelessWidget {
  final List<dynamic> items;
  final String kind;
  final Future<void> Function() onRefresh;
  final Future<void> Function(Map<String, dynamic> item)? onPaid;
  final void Function(Map<String, dynamic> item)? onOpen;

  const _AccountingList({
    required this.items,
    required this.kind,
    required this.onRefresh,
    this.onPaid,
    this.onOpen,
  });

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: onRefresh,
    child: items.isEmpty
        ? ListView(children: const [
            SizedBox(height: 90),
            Center(child: Text('Записей пока нет', style: TextStyle(color: AppColors.muted))),
          ])
        : ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
            itemCount: items.length,
            itemBuilder: (_, index) {
              final item = Map<String, dynamic>.from(items[index] as Map);
              return Padding(padding: const EdgeInsets.only(bottom: 10), child: _row(item));
            },
          ),
  );

  Widget _row(Map<String, dynamic> item) {
    final type = '${item['type'] ?? ''}';
    final status = '${item['status'] ?? ''}';
    final isIncome = type == 'income';
    final color = isIncome
        ? AppColors.success
        : type == 'expense' || type == 'refund'
            ? AppColors.danger
            : status == 'paid'
                ? AppColors.success
                : status == 'overdue'
                    ? AppColors.danger
                    : AppColors.primary;
    final title = '${item['title'] ?? item['type_label'] ?? 'Запись'}';
    final dueLabel = item['due_date'] != null
        ? '${item['due_date']}'
        : '${item['day'] ?? ''} ${item['month'] ?? ''}'.trim();
    final detail = kind == 'operations'
        ? '${item['date'] ?? ''} · ${item['payment_method'] ?? ''} · ${item['counterparty'] ?? ''}'
        : kind == 'documents'
            ? '${item['type_label'] ?? ''} · ${item['date'] ?? ''}'
            : dueLabel;

    final content = Padding(
      padding: const EdgeInsets.all(16),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: color.withOpacity(.1), borderRadius: BorderRadius.circular(13)),
          child: Icon(
            kind == 'documents'
                ? Icons.description_outlined
                : kind == 'taxes'
                    ? Icons.event_note_outlined
                    : kind == 'debts'
                        ? Icons.schedule_outlined
                        : isIncome
                            ? Icons.arrow_upward_rounded
                            : Icons.arrow_downward_rounded,
            color: color,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 5),
            Text(detail, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
            const SizedBox(height: 8),
            Row(children: [
              if (item['status_label'] != null) StatusPill('${item['status_label']}', color: color),
              const Spacer(),
              if (item['amount'] != null) Text(money(item['amount']), style: TextStyle(color: color, fontWeight: FontWeight.w900)),
            ]),
          ]),
        ),
        if (onOpen != null)
          const Padding(
            padding: EdgeInsets.only(left: 5, top: 9),
            child: Icon(Icons.chevron_right_rounded, color: AppColors.muted),
          ),
        if (onPaid != null && status != 'paid')
          IconButton(
            tooltip: 'Отметить оплаченным',
            onPressed: () => onPaid!(item),
            icon: const Icon(Icons.check_circle_outline_rounded, color: AppColors.success),
          ),
      ]),
    );

    return Card(
      child: onOpen == null
          ? content
          : InkWell(
              onTap: () => onOpen!(item),
              borderRadius: BorderRadius.circular(20),
              child: content,
            ),
    );
  }
}

class _DocumentSheet extends StatefulWidget {
  final String title;
  final Future<Map<String, dynamic>> Function() loader;

  const _DocumentSheet({required this.title, required this.loader});

  @override
  State<_DocumentSheet> createState() => _DocumentSheetState();
}

class _DocumentSheetState extends State<_DocumentSheet> {
  bool loading = true;
  String? error;
  String? message;
  List<Map<String, dynamic>> documents = [];
  int selected = 0;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await widget.loader();
      final loaded = <Map<String, dynamic>>[];
      if (result['document'] is Map) {
        loaded.add(Map<String, dynamic>.from(result['document'] as Map));
      }
      for (final raw in List<dynamic>.from(result['documents'] ?? const [])) {
        if (raw is Map) loaded.add(Map<String, dynamic>.from(raw));
      }
      if (!mounted) return;
      setState(() {
        documents = loaded;
        message = '${result['message'] ?? ''}'.trim();
        selected = 0;
      });
    } catch (e) {
      if (mounted) setState(() => error = readableError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Container(
    height: MediaQuery.sizeOf(context).height * .92,
    decoration: const BoxDecoration(
      color: AppColors.background,
      borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    ),
    child: Column(children: [
      const SizedBox(height: 10),
      Container(width: 42, height: 4, decoration: BoxDecoration(color: AppColors.border, borderRadius: BorderRadius.circular(99))),
      Padding(
        padding: const EdgeInsets.fromLTRB(18, 12, 8, 8),
        child: Row(children: [
          Expanded(child: Text(widget.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w900))),
          IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close_rounded)),
        ]),
      ),
      Expanded(
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : error != null
                ? ScreenStateView(icon: Icons.description_outlined, title: 'Документ не открылся', message: error!, onAction: load)
                : documents.isEmpty
                    ? ScreenStateView(
                        icon: Icons.article_outlined,
                        title: 'Документ не сформирован',
                        message: message?.isNotEmpty == true ? message! : 'У этой операции пока нет связанного документа.',
                      )
                    : Column(children: [
                        if (documents.length > 1)
                          SizedBox(
                            height: 48,
                            child: ListView.separated(
                              scrollDirection: Axis.horizontal,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                              itemCount: documents.length,
                              separatorBuilder: (_, __) => const SizedBox(width: 7),
                              itemBuilder: (_, index) => ChoiceChip(
                                label: Text('${documents[index]['title'] ?? 'Документ'}'),
                                selected: selected == index,
                                onSelected: (_) => setState(() => selected = index),
                              ),
                            ),
                          ),
                        Expanded(
                          child: _PdfDocument(
                            key: ValueKey(
                              '${documents[selected]['pdf_path'] ?? ''}|'
                              '${documents[selected]['kind'] ?? ''}|'
                              '${documents[selected]['source_id'] ?? ''}|'
                              '${documents[selected]['file_url'] ?? ''}',
                            ),
                            document: documents[selected],
                          ),
                        ),
                      ]),
      ),
    ]),
  );
}

class _PdfDocument extends StatefulWidget {
  final Map<String, dynamic> document;
  const _PdfDocument({super.key, required this.document});

  @override
  State<_PdfDocument> createState() => _PdfDocumentState();
}

class _PdfDocumentState extends State<_PdfDocument> {
  late Future<Uint8List> pdfFuture;
  bool actionInProgress = false;

  String get pdfPath {
    final direct = '${widget.document['pdf_path'] ?? ''}'.trim();
    if (direct.isNotEmpty) return direct;

    final sourceId = int.tryParse('${widget.document['source_id'] ?? ''}');
    final kind = '${widget.document['kind'] ?? ''}';
    const pdfTypes = {
      'check': 'check',
      'refund_check': 'refund-check',
      'invoice': 'invoice',
      'waybill': 'nakladnaya',
      'act': 'act',
      'invoice_facture': 'schet-factura',
    };
    if (sourceId != null && pdfTypes[kind] != null) {
      return '/api/mobile/accounting/pdf/${pdfTypes[kind]}/$sourceId';
    }

    final fileUrl = '${widget.document['file_url'] ?? ''}'.trim();
    if (fileUrl.isEmpty) return '';
    if (fileUrl.toLowerCase().split('?').first.endsWith('.pdf')) return fileUrl;

    const routeTypes = {
      'check': 'check',
      'refund-check': 'refund-check',
      'invoice': 'invoice',
      'nakladnaya': 'nakladnaya',
      'act': 'act',
      'schet-factura': 'schet-factura',
    };
    for (final entry in routeTypes.entries) {
      final marker = '/docs/${entry.key}/';
      if (fileUrl.contains(marker)) {
        return fileUrl.replaceFirst(
          marker,
          '/api/mobile/accounting/pdf/${entry.value}/',
        );
      }
    }
    return '';
  }

  String get fileName {
    final value = '${widget.document['file_name'] ?? ''}'.trim();
    return value.isEmpty ? 'document.pdf' : value;
  }

  @override
  void initState() {
    super.initState();
    pdfFuture = _load();
  }

  Future<Uint8List> _load() {
    if (pdfPath.isEmpty) {
      return Future<Uint8List>.error(
        const ApiException('Для этого документа оригинальный PDF не найден'),
      );
    }
    return ApiService.downloadPdf(pdfPath);
  }

  void retry() {
    setState(() {
      pdfFuture = _load();
    });
  }

  Future<void> runAction(Future<void> Function(Uint8List bytes) action) async {
    if (actionInProgress) return;
    setState(() => actionInProgress = true);
    try {
      final bytes = await pdfFuture;
      await action(bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => actionInProgress = false);
    }
  }

  Future<void> printPdf(Uint8List bytes) async {
    await Printing.layoutPdf(onLayout: (_) async => bytes);
  }

  Future<void> printRefundReceipt() async {
    if (actionInProgress) return;
    setState(() => actionInProgress = true);
    try {
      final printed = await PrinterService.printRefundReceipt(widget.document);
      if (!printed) {
        throw const ApiException(
          'Не удалось напечатать чек. Проверьте Bluetooth-принтер в настройках',
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => actionInProgress = false);
    }
  }

  Future<void> sharePdf(Uint8List bytes) async {
    await Printing.sharePdf(bytes: bytes, filename: fileName);
  }

  Future<void> savePdf(Uint8List bytes) async {
    final name = fileName.toLowerCase().endsWith('.pdf')
        ? fileName.substring(0, fileName.length - 4)
        : fileName;
    final savedPath = await FileSaver.instance.saveAs(
      name: name,
      bytes: bytes,
      fileExtension: 'pdf',
      mimeType: MimeType.pdf,
    );
    if (mounted && savedPath != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('PDF сохранён')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Uint8List>(
      future: pdfFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError || !snapshot.hasData) {
          return Column(
            children: [
              Expanded(
                child: ScreenStateView(
                  icon: Icons.picture_as_pdf_outlined,
                  title: 'PDF не открылся',
                  message: readableError(snapshot.error ?? 'Неизвестная ошибка'),
                  onAction: retry,
                ),
              ),
              if (widget.document['kind'] == 'refund_check')
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: actionInProgress ? null : printRefundReceipt,
                        icon: const Icon(Icons.print_outlined),
                        label: const Text('Печатать чек возврата'),
                      ),
                    ),
                  ),
                ),
            ],
          );
        }

        final bytes = snapshot.data!;
        return Column(children: [
          SizedBox(
            height: 58,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.fromLTRB(14, 6, 14, 8),
              children: [
                FilledButton.icon(
                  onPressed: actionInProgress
                      ? null
                      : widget.document['kind'] == 'refund_check'
                          ? printRefundReceipt
                          : () => runAction(printPdf),
                  icon: const Icon(Icons.print_outlined, size: 19),
                  label: Text(
                    widget.document['kind'] == 'refund_check'
                        ? 'Печать чека'
                        : 'Печать',
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: actionInProgress ? null : () => runAction(sharePdf),
                  icon: const Icon(Icons.ios_share_rounded, size: 19),
                  label: const Text('Поделиться'),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: actionInProgress ? null : () => runAction(savePdf),
                  icon: const Icon(Icons.download_rounded, size: 19),
                  label: const Text('Сохранить'),
                ),
              ],
            ),
          ),
          Expanded(
            child: PdfPreview(
              build: (_) async => bytes,
              allowPrinting: false,
              allowSharing: false,
              canChangePageFormat: false,
              canChangeOrientation: false,
              canDebug: false,
              onError: (_, error) => ScreenStateView(
                icon: Icons.picture_as_pdf_outlined,
                title: 'Не удалось показать PDF',
                message: readableError(error),
                onAction: retry,
              ),
            ),
          ),
        ]);
      },
    );
  }
}
