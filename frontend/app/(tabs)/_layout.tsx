import { Tabs } from 'expo-router/js-tabs';

import { RouterTabBar, appTabs } from '@/shared/ui';

/** The five tabs (D033) with Fatourati's own tab bar. Screen order follows appTabs. */
export default function TabsLayout() {
  return (
    <Tabs tabBar={(props) => <RouterTabBar {...props} />} screenOptions={{ headerShown: false }}>
      {appTabs.map((tab) => (
        <Tabs.Screen key={tab.route} name={tab.route} options={{ title: tab.label }} />
      ))}
    </Tabs>
  );
}
