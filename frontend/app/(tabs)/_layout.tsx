import { router } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';

import { RouterTabBar, ScanHintProvider, appTabs } from '@/shared/ui';

/**
 * The five tabs (DESIGN.md §4) with Fatourati's own tab bar. Screen order follows appTabs. Scan is not a tab to
 * stay on: pressing it opens the scan flow full screen (D051).
 */
export default function TabsLayout() {
  return (
    <ScanHintProvider>
      <Tabs tabBar={(props) => <RouterTabBar {...props} />} screenOptions={{ headerShown: false }}>
        {appTabs.map((tab) => (
          <Tabs.Screen
            key={tab.route}
            name={tab.route}
            options={{ title: tab.label }}
            listeners={
              tab.main
                ? {
                    tabPress: (event) => {
                      event.preventDefault();
                      router.push('/scan');
                    },
                  }
                : undefined
            }
          />
        ))}
      </Tabs>
    </ScanHintProvider>
  );
}
