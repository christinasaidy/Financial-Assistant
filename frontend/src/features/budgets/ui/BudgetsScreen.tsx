import { useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { toApiMonth } from '@/shared/format/dates';
import { colors, radius, touchTarget } from '@/shared/theme';
import { AppText, LineIcon, TextLink } from '@/shared/ui';

import type { BudgetsService } from '../application/budgetsService';
import { daysLeft, everythingElse, isCurrentMonth, sheetSummary, type BudgetMonth } from '../domain';
import { BudgetSlip, EverythingElseBox, SummarySheet } from './BudgetSheets';
import { errorSentence, monthLabel } from './budgetsText';
import { useBudgetMonth, useBudgetsService } from './useBudgetMonth';

type Props = {
  /** Defaults to the app's BudgetsService from the container; tests pass one built on a fake. */
  service?: BudgetsService;
  /** Today, for the current month and its days left; tests fix it. */
  today?: () => Date;
};

/**
 * Budgets (design/screens/06-budgets.png): the title with the month switcher and the black + (new budget),
 * the budget sheet, one creased slip per budget, and the dashed Everything else box. A slip opens the budget
 * form to change it; + and Set budget open it for a new one (D046).
 */
export function BudgetsScreen({ service, today = () => new Date() }: Props) {
  const budgets = useBudgetMonth(useBudgetsService(service), today);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const now = today();
  const current = isCurrentMonth(budgets.month, now);
  const month = toApiMonth(budgets.month);

  const openForm = (categoryId?: number) =>
    router.navigate({ pathname: '/budget-form', params: categoryId === undefined ? { month } : { month, categoryId: String(categoryId) } });

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: insets.top }]} testID="budgets-scroll">
        <View style={styles.header}>
          <AppText weight={600} size={20} tracking={-0.01} accessibilityRole="header">
            Budgets
          </AppText>
          <View style={styles.controls}>
            <Pressable accessibilityRole="button" accessibilityLabel="Previous month" onPress={budgets.previous} style={styles.iconButton} testID="month-previous">
              <LineIcon name="chevronLeft" size={18} />
            </Pressable>
            <AppText font="mono" weight={500} size={13} testID="budgets-month">
              {monthLabel(budgets.month)}
            </AppText>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Next month"
              accessibilityState={{ disabled: current }}
              disabled={current}
              onPress={budgets.next}
              style={[styles.iconButton, current ? styles.disabled : null]}
              testID="month-next"
            >
              <LineIcon name="chevronRight" size={18} />
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="New budget"
              onPress={() => openForm()}
              style={({ pressed }) => [styles.add, { opacity: pressed ? 0.8 : 1 }]}
              testID="budget-new"
            >
              <LineIcon name="plus" size={18} color="white" />
            </Pressable>
          </View>
        </View>

        {budgets.state.status === 'loading' ? (
          <View style={styles.message}>
            <ActivityIndicator color={colors.inkMuted} accessibilityLabel="Loading" />
          </View>
        ) : null}
        {budgets.state.status === 'failed' ? (
          <View style={styles.message} testID="budgets-error">
            <AppText size={14} color="inkMuted">
              {errorSentence(budgets.state.error, 'load')}
            </AppText>
            <TextLink label="Try again" onPress={budgets.retry} />
          </View>
        ) : null}
        {budgets.state.status === 'loaded' ? <MonthBudgets data={budgets.state.data} days={daysLeft(budgets.month, now)} onOpen={openForm} /> : null}
      </ScrollView>
    </View>
  );
}

function MonthBudgets({ data, days, onOpen }: { data: BudgetMonth; days: number | null; onOpen: (categoryId?: number) => void }) {
  const summary = sheetSummary(data.budgets, data.spending.lbpPerUsd);
  const rest = everythingElse(data.spending, data.budgets);
  const showRest = data.budgets.length === 0 || Number(rest) > 0;
  return (
    <>
      <SummarySheet month={data.month} summary={summary} days={days} />
      <View style={styles.list}>
        {data.budgets.map((budget) => (
          <BudgetSlip key={budget.categoryId} budget={budget} days={days} onPress={() => onOpen(budget.categoryId)} />
        ))}
        {showRest ? <EverythingElseBox amount={rest} onSetBudget={() => onOpen()} /> : null}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { paddingBottom: 24 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, paddingRight: 8, paddingLeft: 20 },
  controls: { flexDirection: 'row', alignItems: 'center' },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  disabled: { opacity: 0.35 },
  add: { width: 40, height: 40, marginLeft: 4, borderRadius: radius.button, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' },
  message: { marginTop: 14, marginHorizontal: 20, gap: 8 },
  list: { marginTop: 16, marginHorizontal: 14, gap: 12 },
});
