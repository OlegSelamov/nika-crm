import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'scanner_screen.dart';

class AddClientScreen extends StatefulWidget {
  final Map<String, dynamic>? client;
  final String initialIdentifier;

  const AddClientScreen({super.key, this.client, this.initialIdentifier = ''});

  bool get isEditing => client != null;

  @override
  State<AddClientScreen> createState() => _AddClientScreenState();
}

class _AddClientScreenState extends State<AddClientScreen> {
  final _formKey = GlobalKey<FormState>();
  final fullNameController = TextEditingController();
  final phoneController = TextEditingController();
  final iinController = TextEditingController();
  final companyController = TextEditingController();
  final addressController = TextEditingController();
  final contractNumberController = TextEditingController();
  final contractDateController = TextEditingController();
  final commentController = TextEditingController();

  String status = 'Новый';
  String category = 'Клиент';
  String payment = 'Не оплачено';
  bool loading = false;
  bool lookupLoading = false;
  String lookupMessage = '';
  Color lookupColor = AppColors.muted;
  Timer? _lookupTimer;

  static const statuses = ['Новый', 'В работе', 'Ожидание', 'Завершен'];
  static const categories = ['Клиент', 'Предприниматель', 'Партнер', 'Другое'];
  static const payments = ['Наличные', 'Безнал', 'Kaspi QR', 'Не оплачено'];

  @override
  void initState() {
    super.initState();
    final client = widget.client;
    if (client != null) {
      fullNameController.text = '${client['full_name'] ?? ''}';
      phoneController.text = '${client['phone'] ?? ''}';
      iinController.text = '${client['iin'] ?? ''}';
      companyController.text = '${client['company_name'] ?? ''}';
      addressController.text = '${client['address'] ?? ''}';
      contractNumberController.text = '${client['contract_number'] ?? ''}';
      contractDateController.text = _dateValue(client['contract_date']);
      commentController.text = '${client['comment'] ?? ''}';
      status = _allowed('${client['status'] ?? ''}', statuses, 'Новый');
      category = _allowed('${client['category'] ?? ''}', categories, 'Клиент');
      payment = _allowed('${client['payment'] ?? ''}', payments, 'Не оплачено');
    } else if (widget.initialIdentifier.isNotEmpty) {
      iinController.text = widget.initialIdentifier;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _scheduleLookup(widget.initialIdentifier);
      });
    }
  }

  static String _allowed(String value, List<String> values, String fallback) =>
      values.contains(value) ? value : fallback;

  static String _dateValue(dynamic value) {
    final text = '${value ?? ''}';
    final match = RegExp(r'^\d{4}-\d{2}-\d{2}').firstMatch(text);
    return match?.group(0) ?? '';
  }

  @override
  void dispose() {
    _lookupTimer?.cancel();
    fullNameController.dispose();
    phoneController.dispose();
    iinController.dispose();
    companyController.dispose();
    addressController.dispose();
    contractNumberController.dispose();
    contractDateController.dispose();
    commentController.dispose();
    super.dispose();
  }

  void _scheduleLookup(String value) {
    _lookupTimer?.cancel();
    final identifier = value.replaceAll(RegExp(r'\D'), '');
    if (identifier.length != 12) {
      setState(() {
        lookupLoading = false;
        lookupMessage = identifier.isEmpty
            ? ''
            : 'Введите ещё ${12 - identifier.length} цифр';
        lookupColor = AppColors.muted;
      });
      return;
    }
    _lookupTimer = Timer(const Duration(milliseconds: 450), () {
      _lookup(identifier);
    });
  }

  Future<void> _lookup(String identifier) async {
    if (!mounted) return;
    setState(() {
      lookupLoading = true;
      lookupMessage = 'Ищем данные…';
      lookupColor = AppColors.primary;
    });
    try {
      final response = await ApiService.lookupClient(identifier);
      if (!mounted || iinController.text != identifier) return;
      final found = response['found'] == true;
      final data = response['data'];
      if (found && data is Map) {
        void fill(TextEditingController controller, dynamic value) {
          if (controller.text.trim().isEmpty && '${value ?? ''}'.trim().isNotEmpty) {
            controller.text = '$value'.trim();
          }
        }
        fill(companyController, data['company_name']);
        fill(fullNameController, data['full_name']);
        fill(addressController, data['address']);
        fill(phoneController, data['phone']);
      }
      setState(() {
        lookupMessage = '${response['message'] ?? (found ? 'Данные подставлены' : 'Данные не найдены')}';
        lookupColor = response['source'] == 'local'
            ? AppColors.warning
            : found
                ? AppColors.success
                : AppColors.warning;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        lookupMessage = readableError(error);
        lookupColor = AppColors.danger;
      });
    } finally {
      if (mounted) setState(() => lookupLoading = false);
    }
  }

  Future<void> _scanIin() async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ScannerScreen()),
    );
    if (result == null) return;
    final identifier = result.toString().replaceAll(RegExp(r'\D'), '');
    iinController.text = identifier.length > 12
        ? identifier.substring(0, 12)
        : identifier;
    _scheduleLookup(iinController.text);
  }

  Future<void> _pickContractDate() async {
    final initial = DateTime.tryParse(contractDateController.text) ?? DateTime.now();
    final selected = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (selected != null) {
      contractDateController.text =
          '${selected.year.toString().padLeft(4, '0')}-${selected.month.toString().padLeft(2, '0')}-${selected.day.toString().padLeft(2, '0')}';
    }
  }

  Map<String, dynamic> get _payload => {
        'full_name': fullNameController.text.trim(),
        'phone': phoneController.text.trim(),
        'iin': iinController.text.trim(),
        'company_name': companyController.text.trim(),
        'address': addressController.text.trim(),
        'contract_number': contractNumberController.text.trim(),
        'contract_date': contractDateController.text.trim(),
        'status': status,
        'category': category,
        'payment': payment,
        'comment': commentController.text.trim(),
      };

  Future<void> _saveClient() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => loading = true);
    try {
      if (widget.isEditing) {
        await ApiService.updateClient(widget.client!['id'] as int, _payload);
      } else {
        await ApiService.createClient(
          fullName: fullNameController.text.trim(),
          phone: phoneController.text.trim(),
          iin: iinController.text.trim(),
          companyName: companyController.text.trim(),
          address: addressController.text.trim(),
          comment: commentController.text.trim(),
          status: status,
          category: category,
          payment: payment,
          contractNumber: contractNumberController.text.trim(),
          contractDate: contractDateController.text.trim(),
        );
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.isEditing ? 'Изменения сохранены' : 'Клиент добавлен')),
      );
      Navigator.pop(context, true);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(readableError(error))),
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Widget _field({
    required String label,
    required TextEditingController controller,
    TextInputType type = TextInputType.text,
    int maxLines = 1,
    String? Function(String?)? validator,
    Widget? suffixIcon,
    bool readOnly = false,
    VoidCallback? onTap,
    List<TextInputFormatter>? inputFormatters,
    ValueChanged<String>? onChanged,
  }) =>
      TextFormField(
        controller: controller,
        keyboardType: type,
        maxLines: maxLines,
        validator: validator,
        readOnly: readOnly,
        onTap: onTap,
        inputFormatters: inputFormatters,
        onChanged: onChanged,
        decoration: InputDecoration(labelText: label, suffixIcon: suffixIcon),
      );

  Widget _dropdown({
    required String label,
    required String value,
    required List<String> values,
    required ValueChanged<String?> onChanged,
  }) =>
      DropdownButtonFormField<String>(
        value: value,
        decoration: InputDecoration(labelText: label),
        items: values.map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
        onChanged: onChanged,
      );

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.isEditing ? 'Изменить клиента' : 'Новый клиент')),
        body: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _field(
                label: 'ИИН / БИН',
                controller: iinController,
                type: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(12)],
                onChanged: _scheduleLookup,
                suffixIcon: lookupLoading
                    ? const Padding(
                        padding: EdgeInsets.all(14),
                        child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
                      )
                    : IconButton(icon: const Icon(Icons.qr_code_scanner), onPressed: _scanIin),
              ),
              if (lookupMessage.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(lookupMessage, style: TextStyle(color: lookupColor, fontSize: 12)),
              ],
              const SizedBox(height: 14),
              _field(label: 'Наименование ИП / Организации', controller: companyController),
              const SizedBox(height: 14),
              _field(
                label: 'ФИО *',
                controller: fullNameController,
                validator: (value) => value == null || value.trim().isEmpty ? 'Укажите имя клиента' : null,
              ),
              const SizedBox(height: 14),
              _field(label: 'Телефон', controller: phoneController, type: TextInputType.phone),
              const SizedBox(height: 14),
              _field(label: 'Адрес', controller: addressController, maxLines: 2),
              const SizedBox(height: 14),
              _field(label: 'Номер договора', controller: contractNumberController),
              const SizedBox(height: 14),
              _field(
                label: 'Дата договора',
                controller: contractDateController,
                readOnly: true,
                onTap: _pickContractDate,
                suffixIcon: IconButton(icon: const Icon(Icons.calendar_month), onPressed: _pickContractDate),
              ),
              const SizedBox(height: 14),
              _dropdown(label: 'Статус', value: status, values: statuses, onChanged: (value) => setState(() => status = value!)),
              const SizedBox(height: 14),
              _dropdown(label: 'Категория', value: category, values: categories, onChanged: (value) => setState(() => category = value!)),
              const SizedBox(height: 14),
              _dropdown(label: 'Оплата', value: payment, values: payments, onChanged: (value) => setState(() => payment = value!)),
              const SizedBox(height: 14),
              _field(label: 'Комментарий', controller: commentController, maxLines: 4),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: loading ? null : _saveClient,
                icon: loading
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                    : const Icon(Icons.save_outlined),
                label: Text(widget.isEditing ? 'Сохранить изменения' : 'Сохранить клиента'),
              ),
            ],
          ),
        ),
      );
}
