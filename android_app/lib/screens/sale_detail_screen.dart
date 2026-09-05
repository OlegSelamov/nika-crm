import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'check_screen.dart';
import 'refund_check_screen.dart';

class SaleDetailScreen extends StatefulWidget {
  final int saleId;

  const SaleDetailScreen({super.key, required this.saleId});

  @override
  State<SaleDetailScreen> createState() => _SaleDetailScreenState();
}

class _SaleDetailScreenState extends State<SaleDetailScreen> {
  bool loading = true;
  bool refunding = false;
  String? error;
  Map<String, dynamic> sale = {};

  @override
  void initState() {
    super.initState();
    loadSale();
  }

  Future<void> loadSale() async {
    try {
      final result = await ApiService.getSale(widget.saleId);
      if (!mounted) return;
      setState(() {
        sale = result;
        loading = false;
        error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = readableError(e);
        loading = false;
      });
    }
  }

  Future<void> _refund() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.undo_rounded, color: AppColors.danger, size: 36),
        title: const Text('Оформить возврат?'),
        content: const Text(
          'Товар вернётся на склад, оплата и прибыль уменьшатся, а reKassa сформирует отдельный чек возврата. Отменить операцию нельзя.',
          textAlign: TextAlign.center,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            child: const Text('Подтвердить возврат'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => refunding = true);
    try {
      final result = await ApiService.refundSale(widget.saleId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result['success'] == true
                ? 'Возврат оформлен, чек сохранён'
                : '${result['error'] ?? 'Не удалось выполнить возврат'}',
          ),
        ),
      );
      if (result['success'] == true) {
        await loadSale();
        if (!mounted) return;
        await Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => RefundCheckScreen(
              saleId: widget.saleId,
              autoPrint: true,
            ),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(readableError(e)), backgroundColor: AppColors.danger),
      );
    } finally {
      if (mounted) setState(() => refunding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Продажа №${sale['sale_number'] ?? widget.saleId}')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? ScreenStateView(
                  icon: Icons.receipt_long_outlined,
                  title: 'Продажа не загрузилась',
                  message: error!,
                  onAction: loadSale,
                )
              : _content(),
    );
  }

  Widget _content() {
    final items = List<dynamic>.from(sale['items'] ?? const []);
    final refunded = sale['is_refunded'] == true || sale['status'] == 'Возврат';
    final payment = _paymentLabel(sale['sale_type']);

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: refunded
                  ? const [Color(0xFF8B2635), AppColors.danger]
                  : const [AppColors.navy, AppColors.navySoft],
            ),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  StatusPill(
                    refunded ? 'Возврат' : '${sale['status'] ?? 'Оплачено'}',
                    color: refunded ? const Color(0xFFFFC7CB) : const Color(0xFF73E2B8),
                  ),
                  const Spacer(),
                  Text('${sale['check_date'] ?? ''}', style: const TextStyle(color: Colors.white70)),
                ],
              ),
              const SizedBox(height: 20),
              const Text('Итого', style: TextStyle(color: Colors.white70)),
              const SizedBox(height: 4),
              Text(
                money(sale['total_amount']),
                style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 14),
              Text('$payment • ${items.length} позиций', style: const TextStyle(color: Colors.white70)),
            ],
          ),
        ),
        const SizedBox(height: 18),
        const SectionTitle('Состав продажи'),
        const SizedBox(height: 10),
        Card(
          child: Column(
            children: items.asMap().entries.map((entry) {
              final item = Map<String, dynamic>.from(entry.value as Map);
              return Column(
                children: [
                  ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                    title: Text('${item['name'] ?? 'Товар'}', style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(
                      '${item['quantity'] ?? 0} ${item['unit'] ?? 'шт'} × ${money(item['price'])}',
                      style: const TextStyle(color: AppColors.muted),
                    ),
                    trailing: Text(money(item['total']), style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                  if (entry.key < items.length - 1) const Divider(height: 1),
                ],
              );
            }).toList(),
          ),
        ),
        const SizedBox(height: 18),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                _fact('Наличные', sale['cash']),
                _fact('Карта', sale['card']),
                _fact('Kaspi POS', sale['kaspi']),
                const Divider(height: 24),
                _textFact('Смена reKassa', '${sale['rekassa_shift_number'] ?? '—'}'),
                _textFact('Фискальный документ', '${sale['rekassa_document_number'] ?? '—'}'),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => CheckScreen(saleId: widget.saleId)),
          ),
          icon: const Icon(Icons.receipt_long_rounded),
          label: Text(refunded ? 'Открыть чек продажи' : 'Открыть чек'),
        ),
        if (refunded && sale['sale_type'] != 'invoice') ...[
          const SizedBox(height: 10),
          ElevatedButton.icon(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => RefundCheckScreen(saleId: widget.saleId),
              ),
            ),
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            icon: const Icon(Icons.print_rounded),
            label: const Text('Открыть чек возврата'),
          ),
        ],
        if (!refunded && sale['sale_type'] != 'invoice') ...[
          const SizedBox(height: 10),
          ElevatedButton.icon(
            onPressed: refunding ? null : _refund,
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            icon: refunding
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.undo_rounded),
            label: Text(refunding ? 'Оформляем возврат…' : 'Оформить возврат'),
          ),
        ],
      ],
    );
  }

  String _paymentLabel(dynamic type) {
    switch ('$type') {
      case 'cash':
        return 'Наличные';
      case 'card':
        return 'Карта';
      case 'kaspi':
        return 'Kaspi POS';
      case 'invoice':
        return 'Счёт';
      default:
        return 'Оплата';
    }
  }

  Widget _fact(String label, dynamic value) {
    if (asDouble(value) <= 0) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [Expanded(child: Text(label)), Text(money(value), style: const TextStyle(fontWeight: FontWeight.w800))]),
    );
  }

  Widget _textFact(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [Expanded(child: Text(label)), Text(value, style: const TextStyle(fontWeight: FontWeight.w700))]),
    );
  }
}
