import { StyleSheet, View } from 'react-native';

import { useTheme, spacing } from '@/shared/theme';
import { AppText } from '@/shared/ui';

import { barWidthPercent, budgetStateWords, budgetTone } from '../domain/rules';
import type { BudgetUse } from '../domain/types';
import { budgetAccessibilityLabel, budgetAmounts } from './homeText';
import { TextLink } from './TextLink';

/** 4 px budget bars (D032). */
const BAR_HEIGHT = 4;

type Props = {
  /** Already the closest to their limit, closest first. Empty when the month has no budgets. */
  budgets: BudgetUse[];
  onOpenBudgets: () => void;
};

/** BUDGETS with SEE ALL and the budgets closest to their limit; before any budget, what a budget does (D035, D037). */
export function BudgetsSection({ budgets, onOpenBudgets }: Props) {
  if (budgets.length === 0) {
    return (
      <View style={styles.section}>
        <AppText variant="section-label" accessibilityRole="header">
          Budgets
        </AppText>
        <AppText variant="sentence" color="ink-2">
          Set a monthly limit for groceries, fuel or eating out, and see how close you are.
        </AppText>
        <TextLink label="Set a budget" onPress={onOpenBudgets} testID="home-set-budget" />
      </View>
    );
  }
  return (
    <View style={styles.section}>
      <View style={styles.heading}>
        <AppText variant="section-label" accessibilityRole="header">
          Budgets
        </AppText>
        <TextLink label="See all" onPress={onOpenBudgets} testID="home-see-all-budgets" />
      </View>
      <View style={styles.rows}>
        {budgets.map((budget) => (
          <BudgetRow key={budget.categoryId} budget={budget} />
        ))}
      </View>
    </View>
  );
}

/**
 * Name and "$spent / $limit", the bar, and the state in words when it needs attention (D021-D023):
 * fine is ink, near the limit is ochre, at the limit is red, so colour is never the only signal.
 */
function BudgetRow({ budget }: { budget: BudgetUse }) {
  const { colors } = useTheme();
  const tone = budgetTone(budget.state);
  const words = budgetStateWords(budget);
  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel={budgetAccessibilityLabel(budget)}
      testID={`home-budget-${budget.categoryId}`}
    >
      <View style={styles.line}>
        <AppText variant="receipt-line" style={styles.name}>
          {budget.name}
        </AppText>
        <AppText variant="receipt-line" style={styles.amounts}>
          {budgetAmounts(budget)}
        </AppText>
      </View>
      <View style={[styles.track, { backgroundColor: colors.track }]}>
        <View
          style={{
            width: `${barWidthPercent(budget.percentUsed)}%`,
            height: BAR_HEIGHT,
            backgroundColor: colors[tone],
          }}
          testID={`home-budget-bar-${budget.categoryId}`}
        />
      </View>
      {words ? (
        <AppText variant="meta" color={tone} style={styles.capitals}>
          {words}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm },
  heading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rows: { gap: spacing.lg },
  row: { gap: spacing.sm },
  // The name wraps; the amounts stay on the right and wrap only when they alone fill the line.
  line: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md },
  name: { flexShrink: 1 },
  amounts: { flexShrink: 1, textAlign: 'right' },
  track: { height: BAR_HEIGHT, alignSelf: 'stretch' },
  capitals: { textTransform: 'uppercase' },
});
