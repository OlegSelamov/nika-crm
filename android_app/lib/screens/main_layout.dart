import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/nika_assistant_controller.dart';
import '../services/sales_voice_bridge.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/module_page.dart';
import 'accounting_screen.dart';
import 'analytics_screen.dart';
import 'assistant_screen.dart';
import 'clients_screen.dart';
import 'dashboard_screen.dart';
import 'employees_screen.dart';
import 'expenses_screen.dart';
import 'items_screen.dart';
import 'income_screen.dart';
import 'login_screen.dart';
import 'movements_screen.dart';
import 'notifications_screen.dart';
import 'reports_screen.dart';
import 'sales_history_screen.dart';
import 'sales_screen.dart';
import 'settings_screen.dart';
import 'shift_screen.dart';
import 'stock_screen.dart';
import 'storefront_screen.dart';
import 'tasks_screen.dart';
import 'whatsapp_screen.dart';
import 'writeoff_screen.dart';
import 'cto_screen.dart';

class MainLayout extends StatefulWidget {
  const MainLayout({super.key});

  @override
  State<MainLayout> createState() => _MainLayoutState();
}

class _MainLayoutState extends State<MainLayout> {
  int selectedIndex = 0;
  final nika = NikaAssistantController.instance;

  static const titles = ['Главная', 'Продажи', 'История', 'Все разделы'];

  @override
  void initState() {
    super.initState();
    SalesVoiceBridge.instance.setSalesVisible(false);
    nika.setHandlers(
      onNavigate: _openVoiceTarget,
      onOpenChat: _openAssistant,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) nika.activate();
    });
  }

  @override
  void dispose() {
    SalesVoiceBridge.instance.setSalesVisible(false);
    nika.clearHandlers();
    nika.deactivate();
    super.dispose();
  }

  Future<void> logout() async {
    await AuthService.logout();
    await ApiService.logout();
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  void openCore(int index) {
    final next = index.clamp(0, 3).toInt();
    SalesVoiceBridge.instance.setSalesVisible(next == 1);
    setState(() => selectedIndex = next);
  }

  Future<void> openPage(Widget page) async {
    SalesVoiceBridge.instance.setSalesVisible(false);
    await Navigator.push(context, MaterialPageRoute(builder: (_) => page));
    if (mounted) {
      SalesVoiceBridge.instance.setSalesVisible(selectedIndex == 1);
    }
  }

  void _openAssistant() {
    if (!mounted) return;
    openPage(const AssistantScreen());
  }

  void _openVoiceTarget(String rawTarget) {
    if (!mounted) return;
    final target = rawTarget.startsWith('/')
        ? (Uri.tryParse(rawTarget)?.path ?? rawTarget)
        : rawTarget;
    final navigator = Navigator.of(context);
    navigator.popUntil((route) => route.isFirst);

    if (target == '/dashboard') {
      openCore(0);
      return;
    }
    if (target == '/sales') {
      openCore(1);
      return;
    }
    if (target == '/sales/history') {
      openCore(2);
      return;
    }

    late final String title;
    late final Widget page;
    var standalone = false;
    switch (target) {
      case '/clients':
        title = 'Клиенты';
        page = const ClientsScreen();
        break;
      case '/items':
        title = 'Товары и услуги';
        page = const ItemsScreen();
        break;
      case '/stock':
        title = 'Склад';
        page = const StockScreen();
        break;
      case '/stock/income':
        title = 'Приход товара';
        page = const IncomeScreen();
        break;
      case '/stock/movements':
        title = 'Движение товара';
        page = const MovementsScreen();
        break;
      case '/stock/writeoff':
        title = 'Списание';
        page = const WriteoffScreen();
        break;
      case '/analytics':
        title = 'Аналитика';
        page = const AnalyticsScreen();
        break;
      case '/reports':
        title = 'Отчёты';
        page = const ReportsScreen();
        break;
      case '/tasks':
        title = 'Задачи';
        page = const TasksScreen();
        break;
      case '/expenses':
        title = 'Расходы';
        page = const ExpensesScreen();
        break;
      case '/accounting':
        title = 'Бухгалтерия';
        page = const AccountingScreen();
        break;
      case '/users':
        title = 'Сотрудники';
        page = const EmployeesScreen();
        break;
      case '/storefront/':
      case '/storefront':
        title = 'Онлайн-витрина';
        page = const StorefrontScreen();
        break;
      case '/cto':
        title = 'CTO';
        page = const CtoScreen();
        break;
      case '/settings':
      case '/profile':
      case '/subscription':
        title = 'Настройки';
        page = const SettingsScreen();
        break;
      case 'notifications':
        title = 'Уведомления';
        page = const NotificationsScreen();
        standalone = true;
        break;
      case 'chat':
        title = 'WhatsApp';
        page = const WhatsappScreen();
        standalone = true;
        break;
      default:
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Этот раздел пока нельзя открыть голосом')),
        );
        return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      openPage(
        standalone ? page : ModulePage(title: title, child: page),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(onOpenSection: openCore),
      const SalesScreen(),
      const SalesHistoryScreen(),
      _MoreScreen(openPage: openPage, logout: logout),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final tablet = constraints.maxWidth >= AppBreakpoints.tablet;
        final extendedRail = constraints.maxWidth >= AppBreakpoints.desktop;
        final content = AdaptiveContent(
          child: IndexedStack(index: selectedIndex, children: screens),
        );

        return Scaffold(
          drawer: tablet
              ? null
              : _AppDrawer(
                  selectedIndex: selectedIndex,
                  openCore: (index) {
                    Navigator.pop(context);
                    openCore(index);
                  },
                  openPage: openPage,
                  logout: logout,
                ),
          appBar: AppBar(
            titleSpacing: tablet ? 16 : 0,
            title: Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: AppColors.primarySoft,
                    borderRadius: BorderRadius.circular(11),
                  ),
                  padding: const EdgeInsets.all(5),
                  child: Image.asset('assets/images/logo.png', fit: BoxFit.contain),
                ),
                const SizedBox(width: 10),
                Flexible(
                  child: Text(
                    titles[selectedIndex],
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            actions: [
              IconButton(
                tooltip: 'Nika AI',
                onPressed: _openAssistant,
                icon: const Icon(Icons.auto_awesome_rounded, color: AppColors.primary),
              ),
              IconButton(
                tooltip: 'Уведомления',
                onPressed: () => openPage(const NotificationsScreen()),
                icon: const Icon(Icons.notifications_none_rounded),
              ),
              const SizedBox(width: 4),
            ],
          ),
          body: tablet
              ? Row(children: [
                  NavigationRail(
                    selectedIndex: selectedIndex,
                    onDestinationSelected: openCore,
                    extended: extendedRail,
                    minExtendedWidth: 220,
                    groupAlignment: -.78,
                    backgroundColor: AppColors.surface,
                    leading: Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Icon(
                        Icons.business_center_rounded,
                        color: AppColors.primary,
                      ),
                    ),
                    destinations: const [
                      NavigationRailDestination(
                        icon: Icon(Icons.home_outlined),
                        selectedIcon: Icon(Icons.home_rounded),
                        label: Text('Главная'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.point_of_sale_outlined),
                        selectedIcon: Icon(Icons.point_of_sale_rounded),
                        label: Text('Продажа'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.history_outlined),
                        selectedIcon: Icon(Icons.history_rounded),
                        label: Text('История'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.grid_view_outlined),
                        selectedIcon: Icon(Icons.grid_view_rounded),
                        label: Text('Разделы'),
                      ),
                    ],
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(child: content),
                ])
              : content,
          bottomNavigationBar: tablet
              ? null
              : NavigationBar(
                  selectedIndex: selectedIndex,
                  onDestinationSelected: openCore,
                  destinations: const [
                    NavigationDestination(
                      icon: Icon(Icons.home_outlined),
                      selectedIcon: Icon(Icons.home_rounded),
                      label: 'Главная',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.point_of_sale_outlined),
                      selectedIcon: Icon(Icons.point_of_sale_rounded),
                      label: 'Продажа',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.history_outlined),
                      selectedIcon: Icon(Icons.history_rounded),
                      label: 'История',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.grid_view_outlined),
                      selectedIcon: Icon(Icons.grid_view_rounded),
                      label: 'Разделы',
                    ),
                  ],
                ),
        );
      },
    );
  }
}

class _MoreScreen extends StatelessWidget {
  final Future<void> Function(Widget page) openPage;
  final Future<void> Function() logout;

  const _MoreScreen({required this.openPage, required this.logout});

  @override
  Widget build(BuildContext context) {
    final sections = <_SectionData>[
      const _SectionData('Клиенты', 'CRM и история покупок', Icons.people_alt_outlined, AppColors.cyan, ClientsScreen()),
      const _SectionData('Товары и услуги', 'Каталог и цены', Icons.inventory_2_outlined, AppColors.warning, ItemsScreen()),
      const _SectionData('Склад', 'Остатки и движения', Icons.warehouse_outlined, AppColors.success, StockScreen()),
      const _SectionData('Аналитика', 'Выручка и прибыль', Icons.query_stats_rounded, AppColors.primary, AnalyticsScreen()),
      const _SectionData(
        'Отчёты',
        'Товары, услуги и Excel · v2026.08.17.2',
        Icons.summarize_outlined,
        Color(0xFF8A54D1),
        ReportsScreen(
          key: ValueKey<String>('reports-2026.08.17.2'),
        ),
      ),
      const _SectionData('Задачи', 'Команда и контроль сроков', Icons.task_alt_outlined, Color(0xFF4776E6), TasksScreen()),
      const _SectionData('Расходы', 'Затраты и категории', Icons.payments_outlined, AppColors.danger, ExpensesScreen()),
      const _SectionData('Бухгалтерия', 'Налоги, долги и документы', Icons.account_balance_outlined, Color(0xFF6941C6), AccountingScreen()),
      const _SectionData('Сотрудники', 'Доступы и показатели', Icons.badge_outlined, Color(0xFF0E9384), EmployeesScreen()),
      const _SectionData('Онлайн‑витрина', 'Заказы и бронирования', Icons.storefront_outlined, Color(0xFFDC6803), StorefrontScreen()),
      const _SectionData('CTO', 'Технический контроль', Icons.developer_board_outlined, Color(0xFF475467), CtoScreen()),
      const _SectionData('Смены reKassa', 'X/Z‑отчёты и архив', Icons.point_of_sale_rounded, Color(0xFFEF6C57), ShiftScreen()),
      const _SectionData('WhatsApp', 'Диалоги с клиентами', Icons.forum_outlined, AppColors.success, WhatsappScreen(), standalone: true),
      const _SectionData('Nika AI', 'Помощник по бизнесу', Icons.auto_awesome_rounded, AppColors.primary, AssistantScreen(), standalone: true),
      const _SectionData('Настройки', 'POS, принтер и приложение', Icons.settings_outlined, AppColors.muted, SettingsScreen()),
    ];

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
      children: [
        ResponsiveGrid(
          minItemWidth: 190,
          minColumns: 2,
          maxColumns: 4,
          childAspectRatio: 1.2,
          children: sections.map((item) => Card(
              child: InkWell(
                borderRadius: BorderRadius.circular(20),
                onTap: () => openPage(
                  item.standalone
                      ? item.page
                      : ModulePage(title: item.title, child: item.page),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(15),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(color: item.color.withOpacity(.12), borderRadius: BorderRadius.circular(13)),
                        child: Icon(item.icon, color: item.color),
                      ),
                      const Spacer(),
                      Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 3),
                      Text(item.subtitle, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                    ],
                  ),
                ),
              ),
            )).toList(),
        ),
        const SizedBox(height: 18),
        OutlinedButton.icon(
          onPressed: logout,
          style: OutlinedButton.styleFrom(foregroundColor: AppColors.danger),
          icon: const Icon(Icons.logout_rounded),
          label: const Text('Выйти из аккаунта'),
        ),
      ],
    );
  }
}

class _AppDrawer extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> openCore;
  final Future<void> Function(Widget page) openPage;
  final Future<void> Function() logout;

  const _AppDrawer({
    required this.selectedIndex,
    required this.openCore,
    required this.openPage,
    required this.logout,
  });

  @override
  Widget build(BuildContext context) {
    return Drawer(
      width: 310,
      backgroundColor: AppColors.navy,
      child: SafeArea(
        child: Column(
          children: [
            FutureBuilder<List<String>>(
              future: Future.wait([AuthService.getUsername(), AuthService.getRole()]),
              builder: (_, snapshot) => Padding(
                padding: const EdgeInsets.all(20),
                child: Row(
                  children: [
                    Container(
                      width: 54,
                      height: 54,
                      padding: const EdgeInsets.all(7),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(17)),
                      child: Image.asset('assets/images/logo.png'),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Nika Business', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w900)),
                          const SizedBox(height: 4),
                          Text(snapshot.data?[0] ?? 'Пользователь', style: const TextStyle(color: Colors.white70)),
                          Text(snapshot.data?[1] ?? '', style: const TextStyle(color: Colors.white54, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const Divider(color: Colors.white12, height: 1),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(vertical: 10),
                children: [
                  _drawerItem(Icons.home_rounded, 'Главная', () => openCore(0), active: selectedIndex == 0),
                  _drawerItem(Icons.point_of_sale_rounded, 'Продажи', () => openCore(1), active: selectedIndex == 1),
                  _drawerItem(Icons.history_rounded, 'История продаж', () => openCore(2), active: selectedIndex == 2),
                  const Padding(
                    padding: EdgeInsets.fromLTRB(20, 18, 20, 7),
                    child: Text('УПРАВЛЕНИЕ', style: TextStyle(color: Colors.white38, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.1)),
                  ),
                  _drawerItem(Icons.people_alt_outlined, 'Клиенты', () { Navigator.pop(context); openPage(const ModulePage(title: 'Клиенты', child: ClientsScreen())); }),
                  _drawerItem(Icons.inventory_2_outlined, 'Товары и услуги', () { Navigator.pop(context); openPage(const ModulePage(title: 'Товары и услуги', child: ItemsScreen())); }),
                  _drawerItem(Icons.warehouse_outlined, 'Склад', () { Navigator.pop(context); openPage(const ModulePage(title: 'Склад', child: StockScreen())); }),
                  _drawerItem(Icons.query_stats_rounded, 'Аналитика', () { Navigator.pop(context); openPage(const ModulePage(title: 'Аналитика', child: AnalyticsScreen())); }),
                  _drawerItem(Icons.summarize_outlined, 'Отчёты', () {
                    Navigator.pop(context);
                    openPage(
                      const ModulePage(
                        title: 'Отчёты',
                        child: ReportsScreen(
                          key: ValueKey<String>('reports-2026.08.17.2'),
                        ),
                      ),
                    );
                  }),
                  _drawerItem(Icons.task_alt_outlined, 'Задачи', () { Navigator.pop(context); openPage(const ModulePage(title: 'Задачи', child: TasksScreen())); }),
                  _drawerItem(Icons.payments_outlined, 'Расходы', () { Navigator.pop(context); openPage(const ModulePage(title: 'Расходы', child: ExpensesScreen())); }),
                  _drawerItem(Icons.account_balance_outlined, 'Бухгалтерия', () { Navigator.pop(context); openPage(const ModulePage(title: 'Бухгалтерия', child: AccountingScreen())); }),
                  _drawerItem(Icons.badge_outlined, 'Сотрудники', () { Navigator.pop(context); openPage(const ModulePage(title: 'Сотрудники', child: EmployeesScreen())); }),
                  _drawerItem(Icons.storefront_outlined, 'Онлайн‑витрина', () { Navigator.pop(context); openPage(const ModulePage(title: 'Онлайн‑витрина', child: StorefrontScreen())); }),
                  _drawerItem(Icons.developer_board_outlined, 'CTO', () { Navigator.pop(context); openPage(const ModulePage(title: 'CTO', child: CtoScreen())); }),
                  _drawerItem(Icons.lock_clock_outlined, 'Смены reKassa', () { Navigator.pop(context); openPage(const ModulePage(title: 'Смены reKassa', child: ShiftScreen())); }),
                  _drawerItem(Icons.forum_outlined, 'WhatsApp', () { Navigator.pop(context); openPage(const WhatsappScreen()); }),
                  _drawerItem(Icons.settings_outlined, 'Настройки', () { Navigator.pop(context); openPage(const ModulePage(title: 'Настройки', child: SettingsScreen())); }),
                ],
              ),
            ),
            _drawerItem(Icons.logout_rounded, 'Выйти', logout, danger: true),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Widget _drawerItem(IconData icon, String title, VoidCallback onTap, {bool active = false, bool danger = false}) {
    final color = danger ? const Color(0xFFFF8790) : active ? Colors.white : Colors.white70;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(color: active ? Colors.white.withOpacity(.12) : Colors.transparent, borderRadius: BorderRadius.circular(14)),
      child: ListTile(
        dense: true,
        leading: Icon(icon, color: color),
        title: Text(title, style: TextStyle(color: color, fontWeight: active ? FontWeight.w800 : FontWeight.w500)),
        onTap: onTap,
      ),
    );
  }
}

class _SectionData {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final Widget page;
  final bool standalone;

  const _SectionData(
    this.title,
    this.subtitle,
    this.icon,
    this.color,
    this.page, {
    this.standalone = false,
  });
}
