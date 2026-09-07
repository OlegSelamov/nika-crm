import 'dart:typed_data';

import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:printing/printing.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class SaleDocumentPreviewScreen extends StatefulWidget {
  final int saleId;
  final String documentType;
  final String title;
  final String fileName;

  const SaleDocumentPreviewScreen({
    super.key,
    required this.saleId,
    required this.documentType,
    required this.title,
    required this.fileName,
  });

  @override
  State<SaleDocumentPreviewScreen> createState() => _SaleDocumentPreviewScreenState();
}

class _SaleDocumentPreviewScreenState extends State<SaleDocumentPreviewScreen> {
  late Future<Uint8List> _pdf;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    _pdf = ApiService.downloadPdf(
      ApiService.saleDocumentPdfPath(widget.documentType, widget.saleId),
    );
  }

  Future<void> _save(Uint8List bytes) async {
    try {
      await FileSaver.instance.saveFile(
        name: widget.fileName,
        bytes: bytes,
        mimeType: MimeType.pdf,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('PDF сохранён')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    }
  }

  Future<void> _share(Uint8List bytes) async {
    try {
      await Printing.sharePdf(bytes: bytes, filename: '${widget.fileName}.pdf');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    }
  }

  Future<void> _print(Uint8List bytes) async {
    try {
      await Printing.layoutPdf(
        name: widget.title,
        onLayout: (_) async => bytes,
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(e))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F6FB),
      appBar: AppBar(title: Text(widget.title)),
      body: FutureBuilder<Uint8List>(
        future: _pdf,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || !snapshot.hasData) {
            return ScreenStateView(
              icon: Icons.picture_as_pdf_outlined,
              title: 'Документ не открылся',
              message: readableError(snapshot.error ?? 'PDF не получен'),
              onAction: () => setState(_load),
            );
          }

          final bytes = snapshot.data!;
          return Column(
            children: [
              Expanded(
                child: PdfPreview(
                  build: (_) async => bytes,
                  canChangePageFormat: false,
                  canChangeOrientation: false,
                  canDebug: false,
                  allowPrinting: false,
                  allowSharing: false,
                  pdfFileName: '${widget.fileName}.pdf',
                  loadingWidget: const Center(child: CircularProgressIndicator()),
                ),
              ),
              SafeArea(
                top: false,
                child: Container(
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    border: Border(top: BorderSide(color: AppColors.border)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => _save(bytes),
                          icon: const Icon(Icons.download_rounded),
                          label: const Text('Сохранить'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => _share(bytes),
                          icon: const Icon(Icons.share_rounded),
                          label: const Text('Поделиться'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: () => _print(bytes),
                          icon: const Icon(Icons.print_rounded),
                          label: const Text('Печать'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
