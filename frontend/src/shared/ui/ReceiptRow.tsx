import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from './AppText';
import { DashedLine } from './paper';

export type ReceiptRowProps = {
  /** "18" over "Nov". */
  day: string;
  month: string;
  name: string;
  /** "Groceries · 9 items". */
  sub: string | null;
  /** "$38.40", "450,000 LBP". */
  amount: string;
  /** "≈ $5.03" under a pound amount. */
  approx: string | null;
  /** On the grey background (Home) or on the paper roll (Receipts): their greys and dashes differ in the design. */
  on: 'bg' | 'paper';
  onPress?: () => void;
  testID?: string;
};

/**
 * A receipt in a list (design/reference/03 and 13): the date block, the shop over "Category · N items", the
 * amount on the right with "≈ $" under pounds. On Home the dashed rule is under each row; on the roll above it.
 */
export function ReceiptRow({ day, month, name, sub, amount, approx, on, onPress, testID }: ReceiptRowProps) {
  const soft = on === 'paper' ? 'inkSoft' : 'inkMuted';
  const row = (
    <View style={[styles.row, on === 'paper' ? styles.paperRow : null]}>
      <View style={styles.date}>
        <AppText font="mono" weight={500} size={18} style={styles.day}>
          {day}
        </AppText>
        <AppText cap size={9.5}>
          {month}
        </AppText>
      </View>
      <View style={styles.middle}>
        <AppText weight={500} size={15} numberOfLines={1}>
          {name}
        </AppText>
        {sub ? (
          <AppText size={12.5} color={soft} numberOfLines={1}>
            {sub}
          </AppText>
        ) : null}
      </View>
      <View style={styles.amount}>
        <AppText font="mono" weight={500} size={15}>
          {amount}
        </AppText>
        {approx ? (
          <AppText font="mono" size={11.5} color={soft}>
            {approx}
          </AppText>
        ) : null}
      </View>
    </View>
  );
  const content =
    on === 'paper' ? (
      <>
        <DashedLine />
        {row}
      </>
    ) : (
      <>
        {row}
        <DashedLine color="dashedBg" />
      </>
    );
  if (!onPress) return <View testID={testID}>{content}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${name}, ${amount}${sub ? `, ${sub}` : ''}`}
      accessibilityHint="Opens the receipt"
      onPress={onPress}
      style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}
      testID={testID}
    >
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 58 },
  paperRow: { minHeight: 60 },
  date: { width: 36, alignItems: 'center', gap: 3 },
  day: { lineHeight: 18 },
  middle: { flex: 1, minWidth: 0, gap: 3 },
  amount: { alignItems: 'flex-end', gap: 3 },
});
