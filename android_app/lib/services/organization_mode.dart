/// Business mode is selected on the website for each organization.
/// The mobile app must never persist a device-wide restaurant switch.
class OrganizationMode {
  static bool isFoodService(String? mode) =>
      mode == 'foodservice' || mode == 'universal';

  static String salesTitle(String? mode) =>
      isFoodService(mode) ? 'Заказы' : 'Продажи';

  static String historyTitle(String? mode) =>
      isFoodService(mode) ? 'История заказов' : 'История';
}
