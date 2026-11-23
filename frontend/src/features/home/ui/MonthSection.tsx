import { StyleSheet, View } from 'react-native';

import { spacing } from '@/shared/theme';
import { AppText, Button } from '@/shared/ui';

import type { MonthSpending } from '../domain/types';
import { monthCaption, monthLabel, monthTotal } from './homeText';

/** THIS MONTH · NOVEMBER, the month total in dollars and the combined-currency line (D034, D035). */
export function MonthSection({ spending }: { spending: MonthSpending }) {
  const caption = monthCaption(spending);
  return (
    <View style={styles.section}>
      <AppText variant="section-label">{monthLabel(spending)}</AppText>
      <AppText variant="total-hero" testID="home-month-total">
        {monthTotal(spending)}
      </AppText>
      {caption ? (
        <AppText variant="caption" testID="home-month-caption">
          {caption}
        </AppText>
      ) : null}
    </View>
  );
}

/** Before the month's first receipt: what scanning does, and the main button (D037). */
export function ScanPrompt({ onScan }: { onScan: () => void }) {
  return (
    <View style={styles.prompt}>
      <AppText variant="sentence">
        Take a photo of a receipt. Fatourati reads the shop, the items and the total, in dollars or pounds.
      </AppText>
      <Button label="Scan a receipt" icon="scan" onPress={onScan} testID="home-scan" />
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.xs },
  prompt: { gap: spacing.lg },
});
