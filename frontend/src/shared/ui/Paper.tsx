import type { ReactNode } from 'react';
import { Image, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { launchBackground, useTheme } from '../theme';

const yellowGrain = require('../../../assets/paper/grain-light.png');

export type PaperProps = {
  /**
   * plain: the flat paper colour, no texture: white in light mode, #17181b in dark (D042). Sign in, create
   * account, Home and the app's screens.
   * yellow: the launch screen, yellow paper with a fine grain, the same in both themes (D039).
   */
  variant: 'plain' | 'yellow';
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
};

/** A screen's background (D039, D042). Use it as the screen's root and put any ScrollView inside it. */
export function Paper({ variant, children, style }: PaperProps) {
  const { colors } = useTheme();
  const yellow = variant === 'yellow';
  return (
    <View style={[styles.fill, { backgroundColor: yellow ? launchBackground : colors.paper }, style]} testID={`paper-${variant}`}>
      {yellow ? (
        <Image
          source={yellowGrain}
          resizeMode="repeat"
          style={styles.layer}
          accessibilityElementsHidden
          importantForAccessibility="no"
        />
      ) : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  layer: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' },
});
