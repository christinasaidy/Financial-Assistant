import type { BottomTabBarProps } from 'expo-router/js-tabs';
import { Pressable, StyleSheet, View } from 'react-native';

import { sizes, spacing, useTheme } from '../theme';
import { AppText } from './AppText';
import { HighlightSwipe } from './HighlightSwipe';
import { Icon, type IconName } from './Icon';

export type TabItem = {
  /** The route file's name inside app/(tabs)/ ("index" is Home). */
  route: string;
  /** Normal case; shown as a section label in capitals. */
  label: string;
  icon: IconName;
  /** The main action, drawn as a pen-blue square (Scan, D033). */
  main?: boolean;
};

/** The five tabs, in order (D033). */
export const appTabs: readonly TabItem[] = [
  { route: 'index', label: 'Home', icon: 'home' },
  { route: 'receipts', label: 'Receipts', icon: 'receipts' },
  { route: 'scan', label: 'Scan', icon: 'scan', main: true },
  { route: 'budgets', label: 'Budgets', icon: 'budgets' },
  { route: 'assistant', label: 'Assistant', icon: 'assistant' },
];

export type TabBarProps = {
  tabs: readonly TabItem[];
  selectedRoute: string;
  onSelect: (route: string) => void;
  /** The home-indicator area, added under the 64 px bar. */
  bottomInset: number;
};

/**
 * The tab bar (D033, D038): five equal tabs on paper with a solid 1 px top rule, 64 px plus the home
 * indicator. Each tab is a printed icon over a section-label caption. The selected tab is ink, with the
 * yellow highlighter swipe behind its label (ink text on it); the others are ink-2. Scan is a 44 px
 * pen-blue square with a paper-coloured icon and its label in ink.
 */
export function TabBar({ tabs, selectedRoute, onSelect, bottomInset }: TabBarProps) {
  const { colors } = useTheme();
  return (
    <View
      accessibilityRole="tablist"
      style={[
        styles.bar,
        { backgroundColor: colors.paper, borderTopColor: colors.rule, paddingBottom: bottomInset },
      ]}
    >
      {tabs.map((tab, index) => {
        const selected = tab.route === selectedRoute;
        return (
          <Pressable
            key={tab.route}
            accessibilityRole="tab"
            accessibilityLabel={tab.label}
            accessibilityHint={`Tab ${index + 1} of ${tabs.length}`}
            accessibilityState={{ selected }}
            onPress={() => onSelect(tab.route)}
            style={styles.tab}
            testID={`tab-${tab.route}`}
          >
            {tab.main ? (
              <View style={[styles.mainSquare, { backgroundColor: colors.primary }]}>
                <Icon name={tab.icon} color="paper" />
              </View>
            ) : (
              <Icon name={tab.icon} color={selected ? 'ink' : 'ink-2'} />
            )}
            <TabLabel label={tab.label} selected={selected} ink={tab.main === true} />
          </Pressable>
        );
      })}
    </View>
  );
}

function TabLabel({ label, selected, ink }: { label: string; selected: boolean; ink: boolean }) {
  const text = (
    <AppText
      variant="section-label"
      color={selected ? 'on-highlight' : ink ? 'ink' : 'ink-2'}
      numberOfLines={1}
      adjustsFontSizeToFit
    >
      {label}
    </AppText>
  );
  if (!selected) return <View style={styles.label}>{text}</View>;
  return (
    <HighlightSwipe shape="tab" style={styles.label}>
      {text}
    </HighlightSwipe>
  );
}

/**
 * TabBar wired to expo-router: pass it as `<Tabs tabBar={(props) => <RouterTabBar {...props} />}>`.
 * It keeps React Navigation's tab-press event, so a screen can still listen for a second tap.
 */
export function RouterTabBar({ state, emitter, navigateToTab, insets }: BottomTabBarProps) {
  const focused = state.routes[state.index];
  const shown = appTabs.filter((tab) => state.routes.some((route) => route.name === tab.route));
  return (
    <TabBar
      tabs={shown}
      selectedRoute={focused?.name ?? ''}
      bottomInset={insets.bottom}
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
  bar: {
    flexDirection: 'row',
    borderTopWidth: sizes.hairline,
  },
  tab: {
    flex: 1,
    minHeight: sizes.tabBar,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  mainSquare: {
    width: sizes.scanSquare,
    height: sizes.scanSquare,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { paddingHorizontal: spacing.xs, maxWidth: '100%' },
});
