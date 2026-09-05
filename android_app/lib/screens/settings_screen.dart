import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:print_bluetooth_thermal/print_bluetooth_thermal.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import '../services/app_update_service.dart';
import '../services/printer_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final ipController = TextEditingController();
  String kaspiStatus = 'Не проверен';
  String printerName = 'Не выбран';
  String printerMac = '';
  bool autoPrint = false;
  int printerPaperWidth = 58;
  String printerEncoding = PrinterService.gbkEncoding;
  bool loading = true;
  Map<String, dynamic> shift = {};

  String appVersion = '—';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    ipController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final version = await AppUpdateService.currentVersion();
    Map<String, dynamic> shiftData = {};
    try {
      shiftData = await ApiService.shiftStatus();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      ipController.text = prefs.getString('kaspi_ip') ?? '';
      printerName = prefs.getString('printer_name') ?? 'Не выбран';
      printerMac = prefs.getString('printer_mac') ?? '';
      autoPrint = prefs.getBool('auto_print') ?? false;
      printerPaperWidth = prefs.getInt('printer_paper_width') ?? 58;
      final savedEncoding =
          prefs.getString(PrinterService.printerEncodingPreference);
      printerEncoding = savedEncoding == PrinterService.cp866Encoding
          ? PrinterService.cp866Encoding
          : PrinterService.gbkEncoding;
      shift = shiftData;
      appVersion = version;
      loading = false;
    });
  }

  Future<void> _saveKaspi() async {
    final ip = ipController.text.trim();
    if (ip.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('kaspi_ip', ip);
    if (!mounted) return;
    setState(() => kaspiStatus = 'Сохранён');
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('IP терминала сохранён')));
  }

  Future<void> _checkKaspi() async {
    final ip = ipController.text.trim();
    if (ip.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Укажите IP терминала')));
      return;
    }
    setState(() => kaspiStatus = 'Проверяем…');
    try {
      final response = await http
          .get(Uri.parse('http://$ip:8080/v2/deviceinfo'))
          .timeout(const Duration(seconds: 4));
      if (!mounted) return;
      setState(() => kaspiStatus = response.statusCode == 200 ? 'Подключён' : 'Недоступен');
    } catch (_) {
      if (mounted) setState(() => kaspiStatus = 'Недоступен');
    }
  }

  Future<void> _pickPrinter() async {
    final devices = await PrintBluetoothThermal.pairedBluetooths;
    if (!mounted) return;
    if (devices.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала подключите принтер в настройках Bluetooth телефона')),
      );
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(18, 4, 18, 10),
              child: Text('Выберите принтер', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
            ),
            ...devices.map((device) => ListTile(
                  leading: const Icon(Icons.print_outlined),
                  title: Text(device.name),
                  subtitle: Text(device.macAdress),
                  onTap: () async {
                    final prefs = await SharedPreferences.getInstance();
                    await prefs.setString('printer_name', device.name);
                    await prefs.setString('printer_mac', device.macAdress);
                    if (!mounted) return;
                    setState(() {
                      printerName = device.name;
                      printerMac = device.macAdress;
                    });
                    Navigator.pop(context);
                  },
                )),
          ],
        ),
      ),
    );
  }

  Future<void> _testPrint() async {
    if (printerMac.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Сначала выберите принтер')));
      return;
    }
    final ok = await PrinterService.printReceipt(
      text: '       NIKA BUSINESS\n\nТестовая печать\nПринтер подключен\n',
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(ok ? 'Тестовый чек отправлен' : 'Не удалось напечатать чек')),
    );
  }

  Future<void> _setAutoPrint(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('auto_print', value);
    if (mounted) setState(() => autoPrint = value);
  }

  Future<void> _setPrinterPaperWidth(int value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('printer_paper_width', value);
    if (mounted) setState(() => printerPaperWidth = value);
  }

  Future<void> _setPrinterEncoding(String value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(PrinterService.printerEncodingPreference, value);
    if (mounted) setState(() => printerEncoding = value);
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    final reKassaConnected = shift['success'] == true;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 30),
      children: [
        const SectionTitle('Интеграции', subtitle: 'Статусы синхронизируются с сайтом'),
        const SizedBox(height: 12),
        _statusCard(
          icon: Icons.receipt_long_outlined,
          title: 'reKassa',
          subtitle: reKassaConnected
              ? '${shift['name'] ?? 'Касса'} • ${shift['shift_open'] == true ? 'смена открыта' : 'смена закрыта'}'
              : 'Подключите кассу на сайте Nika Business',
          color: reKassaConnected ? AppColors.success : AppColors.muted,
        ),
        const SizedBox(height: 10),
        _statusCard(
          icon: Icons.forum_outlined,
          title: 'WhatsApp',
          subtitle: 'Настройка подключения и AI выполняется на сайте',
          color: AppColors.success,
        ),
        const SizedBox(height: 24),
        const SectionTitle('Kaspi POS', subtitle: 'Терминал в одной Wi‑Fi сети с телефоном'),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text('Статус: $kaspiStatus', style: const TextStyle(fontWeight: FontWeight.w700))),
                    StatusPill(kaspiStatus, color: kaspiStatus == 'Подключён' ? AppColors.success : AppColors.muted),
                  ],
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: ipController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'IP терминала', hintText: '10.23.221.105', prefixIcon: Icon(Icons.lan_outlined)),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(child: OutlinedButton(onPressed: _checkKaspi, child: const Text('Проверить'))),
                    const SizedBox(width: 8),
                    Expanded(child: ElevatedButton(onPressed: _saveKaspi, child: const Text('Сохранить'))),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        const SectionTitle('Принтер чеков', subtitle: 'Bluetooth ESC/POS'),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const CircleAvatar(
                    backgroundColor: AppColors.primarySoft,
                    foregroundColor: AppColors.primary,
                    child: Icon(Icons.print_outlined),
                  ),
                  title: Text(printerName, style: const TextStyle(fontWeight: FontWeight.w800)),
                  subtitle: Text(printerMac.isEmpty ? 'Принтер не выбран' : printerMac),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: _pickPrinter,
                ),
                const Divider(),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Автопечать', style: TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: const Text('Печатать чек сразу после продажи или возврата'),
                  value: autoPrint,
                  onChanged: _setAutoPrint,
                ),
                const Divider(),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Ширина ленты', style: TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 3),
                    const Text(
                      'Форматирование строк чека',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: SegmentedButton<int>(
                        segments: const [
                          ButtonSegment(value: 58, label: Text('58 мм')),
                          ButtonSegment(value: 80, label: Text('80 мм')),
                        ],
                        selected: {printerPaperWidth},
                        showSelectedIcon: false,
                        onSelectionChanged: (values) =>
                            _setPrinterPaperWidth(values.first),
                      ),
                    ),
                  ],
                ),
                const Divider(height: 24),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Кодировка принтера', style: TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 3),
                    const Text(
                      'GBK — текущий режим, CP866 — для русской печати на Xprinter',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: SegmentedButton<String>(
                        segments: const [
                          ButtonSegment(value: PrinterService.gbkEncoding, label: Text('GBK')),
                          ButtonSegment(value: PrinterService.cp866Encoding, label: Text('CP866')),
                        ],
                        selected: {printerEncoding},
                        showSelectedIcon: false,
                        onSelectionChanged: (values) =>
                            _setPrinterEncoding(values.first),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                OutlinedButton.icon(onPressed: _testPrint, icon: const Icon(Icons.print_rounded), label: const Text('Тестовая печать')),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        const SectionTitle('О приложении'),
        const SizedBox(height: 12),
        Card(
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 15, vertical: 7),
            leading: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(.12),
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Icon(Icons.system_update_rounded, color: AppColors.primary),
            ),
            title: Text('Nika Business $appVersion', style: const TextStyle(fontWeight: FontWeight.w800)),
            subtitle: const Text('Автоматическая проверка обновлений'),
            trailing: TextButton(
              onPressed: () => AppUpdateService.checkAndPrompt(
                context,
                showNoUpdateMessage: true,
              ),
              child: const Text('Проверить'),
            ),
          ),
        ),
      ],
    );
  }

  Widget _statusCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required Color color,
  }) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 15, vertical: 7),
        leading: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(color: color.withOpacity(.12), borderRadius: BorderRadius.circular(14)),
          child: Icon(icon, color: color),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text(subtitle),
      ),
    );
  }
}
