import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/services/organization_mode.dart';

void main() {
  test('website foodservice configuration enables restaurant navigation', () {
    expect(OrganizationMode.isFoodService('foodservice'), isTrue);
    expect(OrganizationMode.salesTitle('foodservice'), 'Заказы');
    expect(OrganizationMode.historyTitle('foodservice'), 'История заказов');
  });

  test('retail and production do not turn on food ordering', () {
    for (final mode in ['retail', 'production', null, '']) {
      expect(OrganizationMode.isFoodService(mode), isFalse);
      expect(OrganizationMode.salesTitle(mode), 'Продажи');
      expect(OrganizationMode.historyTitle(mode), 'История');
    }
  });

  test('universal business mode supports food orders as on the web', () {
    expect(OrganizationMode.isFoodService('universal'), isTrue);
  });
}
