import type { ReactNode } from 'react';
import { Image, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { launchBackground, useTheme } from '../theme';

const grain = {
  light: require('../../../assets/paper/grain-light.png'),
  dark: require('../../../assets/paper/grain-dark.png'),
};
const crease = {
  light: require('../../../assets/paper/wrinkle-light.png'),
  dark: require('../../../assets/paper/wrinkle-dark.png'),
};

export type PaperProps = {
  /**
   * creased: the paper colour, a fine grain (256 px tile, repeated) and soft crease shading stretched once
   * over the screen; dark versions in dark mode. Sign in, create account, Home and the app's screens.
   * yellow: the launch screen, yellow paper with the grain, the same in both themes. D039.
   */
  variant: 'creased' | 'yellow';
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
};

/**
 * A screen's background (D039). The textures are images, not gradients (D007). Use it as the screen's root
 * and put any ScrollView inside it, so the crease is stretched over the screen, not over the content.
 */
export function Paper({ variant, children, style }: PaperProps) {
  const { scheme, colors } = useTheme();
  const yellow = variant === 'yellow';
  return (
    <View style={[styles.fill, { backgroundColor: yellow ? launchBackground : colors.paper }, style]} testID={`paper-${variant}`}>
      <Image
        source={yellow ? grain.light : grain[scheme]}
        resizeMode="repeat"
        style={styles.layer}
        accessibilityElementsHidden
        importantForAccessibility="no"
      />
      {yellow ? null : (
        <Image
          source={crease[scheme]}
          resizeMode="stretch"
          style={styles.layer}
          accessibilityElementsHidden
          importantForAccessibility="no"
        />
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  layer: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' },
});
