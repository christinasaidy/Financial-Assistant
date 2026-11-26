import { Pressable, StyleSheet, View } from 'react-native';

import { colors, type ColorName } from '@/shared/theme';
import { formatUsd } from '@/shared/format/money';
import { AppText, PaperSheet } from '@/shared/ui';

import { barWidthPercent, isOver, type Budget, type SheetSummary } from '../domain';
import { daysLeftLabel, leftAcross, monthLabel, perDayLine, remainderLine, roundDollars, spentOfLimit } from './budgetsText';

/** The budgets' sheets have a slightly softer shadow than Home's invoice (design/reference/06: .sh). */
const SHEET_SHADOW = {
  shadowColor: 'rgb(40,35,25)',
  shadowOpacity: 0.12,
  shadowRadius: 12,
  shadowOffset: { width: 0, height: 8 },
} as const;

function Bar({ percent, color }: { percent: number; color: ColorName }) {
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width: `${percent}%`, backgroundColor: colors[color] }]} />
    </View>
  );
}

/**
 * The budget sheet (screen 06): BUDGET SHEET · NOV 2026 and the days left, the dollars spent "of $390
 * budgeted", a 4 px bar, and what is left across the budgets with the percentage. With no budgets, a blank
 * sheet with a grey $0.00 and one sentence (D046).
 */
export function SummarySheet({ month, summary, days }: { month: Date; summary: SheetSummary; days: number | null }) {
  const blank = summary.count === 0;
  return (
    <PaperSheet on="bg" shadow={SHEET_SHADOW} outerStyle={styles.summaryPlace} style={styles.summary} testID="budget-sheet">
      <View style={styles.between}>
        <AppText cap color="cobalt">
          Budget sheet · {monthLabel(month)}
        </AppText>
        <AppText cap>{daysLeftLabel(days)}</AppText>
      </View>
      <View style={styles.totalRow}>
        <AppText font="mono" weight={500} size={40} tracking={-0.04} color={blank ? 'zeroAmount' : 'ink'} style={styles.total} testID="budget-sheet-spent">
          {formatUsd(summary.spent)}
        </AppText>
        {blank ? null : (
          <AppText size={14} color="noteText">
            of {roundDollars(summary.budgeted)} budgeted
          </AppText>
        )}
      </View>
      {blank ? (
        <AppText size={13} color="inkSoft" style={styles.blankLine}>
          No budgets yet. Set a monthly limit for a category.
        </AppText>
      ) : (
        <>
          <View style={styles.summaryBar}>
            <Bar percent={barWidthPercent(summary.spent, summary.budgeted)} color={Number(summary.spent) > Number(summary.budgeted) ? 'red' : 'ink'} />
          </View>
          <View style={[styles.between, styles.summaryFoot]}>
            <AppText size={12.5} color="noteText">
              {leftAcross(summary)}
            </AppText>
            <AppText font="mono" size={12.5} color="noteText">
              {summary.percent}%
            </AppText>
          </View>
        </>
      )}
    </PaperSheet>
  );
}

/** One creased slip per budget (screen 06): name and spent / limit, a 4 px bar, what is left and the pace. */
export function BudgetSlip({ budget, days, onPress }: { budget: Budget; days: number | null; onPress: () => void }) {
  const over = isOver(budget);
  const amounts = spentOfLimit(budget);
  const rest = remainderLine(budget);
  const pace = perDayLine(budget, days);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${budget.name}, ${amounts.spent} of ${amounts.limit}, ${rest.text}`}
      accessibilityHint="Opens the budget to change or remove it"
      onPress={onPress}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
      testID={`budget-slip-${budget.categoryId}`}
    >
      <PaperSheet on="bg" shadow={SHEET_SHADOW} style={styles.slip}>
        <View style={[styles.between, styles.baseline]}>
          <AppText weight={600} size={16} style={styles.name} numberOfLines={1}>
            {budget.name}
          </AppText>
          <AppText font="mono" size={14}>
            <AppText font="mono" size={14} weight={over ? 600 : 400} color={over ? 'redText' : 'ink'}>
              {amounts.spent}
            </AppText>
            {` / ${amounts.limit}`}
          </AppText>
        </View>
        <View style={styles.slipBar}>
          <Bar percent={barWidthPercent(budget.spent, budget.limit)} color={over ? 'red' : 'ink'} />
        </View>
        <View style={[styles.between, styles.slipFoot]}>
          <AppText size={12.5} weight={over ? 600 : 400} color={over ? 'redText' : 'noteText'}>
            {rest.text}
          </AppText>
          {pace ? (
            <AppText font="mono" size={12.5} color="noteText">
              {pace}
            </AppText>
          ) : null}
        </View>
      </PaperSheet>
    </Pressable>
  );
}

/** The dashed "Everything else · $126.90 / Not in any budget yet / Set budget" box at the end (screen 06). */
export function EverythingElseBox({ amount, onSetBudget }: { amount: string; onSetBudget: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Everything else, ${formatUsd(amount)}, not in any budget yet. Set budget`}
      onPress={onSetBudget}
      style={({ pressed }) => [styles.else, { opacity: pressed ? 0.7 : 1 }]}
      testID="everything-else-box"
    >
      <View style={styles.elseText}>
        <AppText weight={500} size={15}>
          Everything else{' '}
          <AppText font="mono" size={15}>
            · {formatUsd(amount)}
          </AppText>
        </AppText>
        <AppText size={12.5} color="inkSoft">
          Not in any budget yet
        </AppText>
      </View>
      <AppText weight={600} size={14} color="cobalt">
        Set budget
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  baseline: { alignItems: 'baseline', gap: 12 },
  summaryPlace: { marginTop: 10, marginHorizontal: 14 },
  summary: { paddingTop: 14, paddingHorizontal: 16, paddingBottom: 20 },
  totalRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 10 },
  total: { lineHeight: 44 },
  blankLine: { marginTop: 8 },
  summaryBar: { marginTop: 12 },
  summaryFoot: { marginTop: 8 },
  track: { height: 4, backgroundColor: colors.barTrack },
  fill: { height: 4 },
  slip: { paddingTop: 12, paddingHorizontal: 14, paddingBottom: 16 },
  name: { flexShrink: 1 },
  slipBar: { marginTop: 9 },
  slipFoot: { marginTop: 7 },
  else: {
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.dashedBg,
    borderRadius: 6,
    paddingVertical: 12,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  elseText: { flex: 1, gap: 3 },
});
