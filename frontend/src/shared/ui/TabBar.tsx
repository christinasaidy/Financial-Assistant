import type { BottomTabBarProps } from 'expo-router/js-tabs';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { colors, radius } from '../theme';
import { AppText } from './AppText';
import { Icon, type IconName } from './Icon';
import { Perforation } from './paper';

export type TabItem = {
  /** The route file's name inside app/(tabs)/ ("index" is Home). */
  route: string;
  label: string;
  icon: IconName;
  /** Scan: the cobalt square, no label (DESIGN.md §4). */
  main?: boolean;
};

/** The five tabs, in order (DESIGN.md §4). The icons are Christina's own (D044). */
export const appTabs: readonly TabItem[] = [
  { route: 'index', label: 'Home', icon: 'home' },
  { route: 'receipts', label: 'Receipts', icon: 'receipts' },
  { route: 'scan', label: 'Scan a receipt', icon: 'scan', main: true },
  { route: 'budgets', label: 'Budgets', icon: 'budgets' },
  { route: 'assistant', label: 'Assistant', icon: 'assistant' },
];

/** Whether Scan wears its faint cobalt ring: the empty Home asks for it (DESIGN.md §6, screen 04). */
const ScanHintContext = createContext<{ on: boolean; set: (on: boolean) => void }>({ on: false, set: () => undefined });

export function ScanHintProvider({ children }: { children: ReactNode }) {
  const [on, set] = useState(false);
  const value = useMemo(() => ({ on, set }), [on]);
  return <ScanHintContext.Provider value={value}>{children}</ScanHintContext.Provider>;
}

/** A screen asks for the ring around Scan while `on` is true. */
export function useScanHint(on: boolean) {
  const { set } = useContext(ScanHintContext);
  useEffect(() => {
    set(on);
    return () => set(false);
  }, [on, set]);
}

export type TabBarProps = {
  tabs: readonly TabItem[];
  selectedRoute: string;
  onSelect: (route: string) => void;
  /** The home-indicator area; the bar keeps at least 12 px under its labels. */
  bottomInset: number;
  scanHint?: boolean;
};

/**
 * The tab bar (DESIGN.md §4): `tabBar` background with the perforation on top, five slots. Active tab is ink
 * with a 600 label, the others `inkMuted` 500; icons 22 px. Scan is a 56 px cobalt square, radius 16, with
 * a white icon.
 */
export function TabBar({ tabs, selectedRoute, onSelect, bottomInset, scanHint = false }: TabBarProps) {
  return (
    <View style={styles.bar}>
      <Perforation />
      <View accessibilityRole="tablist" style={[styles.row, { paddingBottom: Math.max(12, bottomInset) }]}>
        {tabs.map((tab, index) => {
          const selected = tab.route === selectedRoute;
          const a11y = {
            accessibilityRole: 'tab' as const,
            accessibilityLabel: tab.label,
            accessibilityHint: `Tab ${index + 1} of ${tabs.length}`,
            accessibilityState: { selected },
            onPress: () => onSelect(tab.route),
            testID: `tab-${tab.route}`,
          };
          if (tab.main) {
            return (
              <View key={tab.route} style={styles.slot}>
                {scanHint ? <View style={styles.ring} testID="scan-ring" /> : null}
                <Pressable {...a11y} style={({ pressed }) => [styles.scan, { backgroundColor: pressed ? colors.cobaltPressed : colors.cobalt }]}>
                  <Icon name={tab.icon} size={24} color="white" />
                </Pressable>
              </View>
            );
          }
          return (
            <Pressable key={tab.route} {...a11y} style={styles.tab}>
              <Icon name={tab.icon} color={selected ? 'ink' : 'inkMuted'} />
              <AppText weight={selected ? 600 : 500} size={11.5} color={selected ? 'ink' : 'inkMuted'} numberOfLines={1}>
                {tab.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/**
 * TabBar wired to expo-router: pass it as `<Tabs tabBar={(props) => <RouterTabBar {...props} />}>`, inside
 * ScanHintProvider. It keeps React Navigation's tab-press event.
 */
export function RouterTabBar({ state, emitter, navigateToTab, insets }: BottomTabBarProps) {
  const { on } = useContext(ScanHintContext);
  const focused = state.routes[state.index];
  const shown = appTabs.filter((tab) => state.routes.some((route) => route.name === tab.route));
  return (
    <TabBar
      tabs={shown}
      selectedRoute={focused?.name ?? ''}
      bottomInset={insets.bottom}
      scanHint={on}
      onSelect={(name) => {
        const route = state.routes.find((candidate) => candidate.name === name);
        if (!route) return;
        const event = emitter.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
        if (route.key !== focused?.key && !event.defaultPrevented) navigateToTab(route.key);
      }}
    />
  );
}

const styles = StyleSheet.create({
  bar: { backgroundColor: colors.tabBar },
  row: { flexDirection: 'row', alignItems: 'center', paddingTop: 2, paddingHorizontal: 6 },
  tab: { flex: 1, minHeight: 52, alignItems: 'center', justifyContent: 'center', gap: 4 },
  slot: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scan: { width: 56, height: 56, borderRadius: radius.scan, alignItems: 'center', justifyContent: 'center' },
  ring: {
    position: 'absolute',
    width: 66,
    height: 66,
    borderRadius: radius.scan + 5,
    backgroundColor: colors.scanRing,
  },
});
