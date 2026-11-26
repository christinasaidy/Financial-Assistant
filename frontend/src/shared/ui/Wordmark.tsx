import { StyleSheet, View } from 'react-native';

import { AppText } from './AppText';

/**
 * The header wordmark (DESIGN.md §4): "Fatourati" in Geist 600 18 and فاتورتي in Noto Naskh Arabic 600 15,
 * `inkMuted`, 8 px apart on one baseline. VoiceOver reads it as "Fatourati".
 */
export function Wordmark() {
  return (
    <View style={styles.row} accessible accessibilityLabel="Fatourati" accessibilityRole="header" testID="wordmark">
      <AppText weight={600} size={18} tracking={-0.01}>
        Fatourati
      </AppText>
      <AppText font="arabic" weight={600} size={15} color="inkMuted">
        فاتورتي
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'baseline', gap: 8 },
});
