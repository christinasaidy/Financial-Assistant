import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '@/shared/theme';
import { AppText, DoubleRule, PaperSheet, tears } from '@/shared/ui';

/**
 * The launch screen (design/screens/01-launch.png, reference/01-launch.html): on white, one full-screen
 * sheet of `launchPaper` with the heavier crease (0.69) and a 14 × 7 torn edge. INVOICE Nº 0001 / USD · LBP
 * over a rule at the top; at the bottom a huge فاتورتي, a double rule, "Fatourati" and TOTAL · $0.00, and the
 * tagline. Static: no animation (DESIGN.md §1). It stays as long as the saved session takes to check.
 */
export function LaunchScreen() {
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.screen} testID="launch-screen">
      <PaperSheet
        color="launchPaper"
        crease={0.69}
        tear={tears.launch}
        on="white"
        shadow={styles.shadow}
        outerStyle={styles.sheetPlace}
        style={[styles.sheet, { paddingTop: Math.max(64, insets.top + 12) }]}
      >
        <View style={styles.between}>
          <AppText cap color="launchCobalt">
            Invoice Nº 0001
          </AppText>
          <AppText cap color="slipSoft">
            USD · LBP
          </AppText>
        </View>
        <View style={styles.rule} />

        <AppText font="arabic" weight={700} size={108} style={styles.arabic} accessibilityLabel="Fatourati in Arabic">
          فاتورتي
        </AppText>
        <DoubleRule style={styles.double} />
        <View style={[styles.between, styles.nameRow]}>
          <AppText weight={600} size={30} tracking={-0.02} accessibilityRole="header">
            Fatourati
          </AppText>
          <AppText cap color="ink">
            Total · $0.00
          </AppText>
        </View>
        <AppText font="mono" size={13} color="fieldLabel" style={styles.tagline}>
          Every crumpled receipt, flattened out and accounted for.
        </AppText>
      </PaperSheet>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.white },
  sheetPlace: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 34 },
  shadow: {
    shadowColor: 'rgb(30,30,35)',
    shadowOpacity: 0.18,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 10 },
  },
  sheet: { flex: 1, paddingHorizontal: 26, paddingBottom: 40 },
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  rule: { borderTopWidth: 1, borderTopColor: colors.ink, marginTop: 14 },
  arabic: { marginTop: 'auto', lineHeight: 124, textAlign: 'right', marginRight: -6, writingDirection: 'rtl' },
  double: { marginTop: 18 },
  nameRow: { alignItems: 'baseline', paddingTop: 14 },
  tagline: { lineHeight: 19.5, marginTop: 10 },
});
