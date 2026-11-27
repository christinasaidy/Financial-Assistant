import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState, type ReactNode } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '@/shared/theme';
import { AppText, Button, Chip, PaperSheet, TextLink } from '@/shared/ui';

import type { ReceiptsService } from '../application/receiptsService';
import { categoryName, itemName, lineCategory, ReceiptsError, type ReceiptPage } from '../domain';
import { errorSentence, lineAmount } from './receiptsText';
import { useReceiptsService } from './useReceipts';

type Props = { service?: ReceiptsService };

function useOnce(service: ReceiptsService, id: number) {
  const [page, setPage] = useState<ReceiptPage | null>(null);
  const [error, setError] = useState<ReceiptsError | null>(null);
  useEffect(() => {
    let active = true;
    service
      .loadReceipt(id)
      .then((loaded) => active && setPage(loaded))
      .catch((caught: unknown) => active && setError(caught instanceof ReceiptsError ? caught : new ReceiptsError('unexpected', String(caught))));
    return () => {
      active = false;
    };
  }, [service, id]);
  return { page, error };
}

/** The sheets' frame: the budget form's clean paper (D046), a cobalt cap, a heading and a sentence. */
function SheetFrame({ eyebrow, corner, heading, sentence, children }: { eyebrow: string; corner: string; heading: string; sentence: string; children: ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <PaperSheet color="paperClean" crease={0.15} creaseTileWidth={520} tear={null} shadow={null} outerStyle={styles.fill} style={styles.fill}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: 22 + insets.bottom }]}>
        <View style={styles.between}>
          <AppText cap color="cobalt">
            {eyebrow}
          </AppText>
          <AppText cap color="capOnForm" numberOfLines={1} style={styles.corner}>
            {corner}
          </AppText>
        </View>
        <AppText weight={600} size={25} tracking={-0.02} accessibilityRole="header" style={styles.heading}>
          {heading}
        </AppText>
        <AppText size={15} color="formSoft" style={styles.sentence}>
          {sentence}
        </AppText>
        {children}
      </ScrollView>
    </PaperSheet>
  );
}

function Waiting({ error }: { error: ReceiptsError | null }) {
  const router = useRouter();
  if (!error) return <ActivityIndicator color={colors.inkMuted} accessibilityLabel="Loading" />;
  return (
    <View style={styles.gap}>
      <AppText size={14} color="redText">
        {errorSentence(error, 'load')}
      </AppText>
      <TextLink label="Close" onPress={() => router.back()} />
    </View>
  );
}

/** Change category (D050): one category for the receipt; every item follows it. */
export function ChangeCategoryScreen({ service }: Props) {
  const receipts = useReceiptsService(service);
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const { page, error } = useOnce(receipts, id);
  const router = useRouter();
  const [chosen, setChosen] = useState<number | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const current = chosen === undefined ? (page?.receipt.categoryId ?? null) : chosen;

  const save = async () => {
    if (!page || busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await receipts.changeCategory(page.receipt, current);
      router.back();
    } catch (caught) {
      setFailure(errorSentence(caught instanceof ReceiptsError ? caught : new ReceiptsError('unexpected', String(caught)), 'save'));
      setBusy(false);
    }
  };

  return (
    <SheetFrame
      eyebrow="Change category"
      corner={page?.receipt.shopName ?? ''}
      heading="Which category?"
      sentence="Every item on this receipt moves with it."
    >
      {!page ? <Waiting error={error} /> : null}
      {page ? (
        <View style={styles.gap22}>
          <View accessibilityRole="radiogroup" accessibilityLabel="Category" style={styles.chips}>
            {page.categories.map((category) => (
              <Chip key={category.id} label={category.name} selected={category.id === current} onPress={() => setChosen(category.id)} testID={`category-${category.id}`} />
            ))}
          </View>
          {failure ? (
            <AppText size={14} color="redText" accessibilityLiveRegion="polite">
              {failure}
            </AppText>
          ) : null}
          <Button label="Save category" onPress={() => void save()} busy={busy} disabled={current === null} />
        </View>
      ) : null}
    </SheetFrame>
  );
}

/** Split items (D050): a category per item, as chips under each item. */
export function SplitItemsScreen({ service }: Props) {
  const receipts = useReceiptsService(service);
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const { page, error } = useOnce(receipts, id);
  const router = useRouter();
  const [chosen, setChosen] = useState<(number | null)[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const current = chosen ?? page?.receipt.lines.map((line) => lineCategory(line, page.receipt)) ?? [];
  const main = page ? categoryName(page.categories, page.receipt.categoryId) : null;

  const save = async () => {
    if (!page || busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await receipts.splitItems(page.receipt, current);
      router.back();
    } catch (caught) {
      setFailure(errorSentence(caught instanceof ReceiptsError ? caught : new ReceiptsError('unexpected', String(caught)), 'save'));
      setBusy(false);
    }
  };

  return (
    <SheetFrame
      eyebrow="Split items"
      corner={page?.receipt.shopName ?? ''}
      heading="Give items their own category."
      sentence={main ? `The rest stay in ${main}.` : 'Choose a category for each item.'}
    >
      {!page ? <Waiting error={error} /> : null}
      {page ? (
        <View style={styles.gap22}>
          {page.receipt.lines.length === 0 ? (
            <AppText size={14} color="formSoft">
              This receipt has no items to split.
            </AppText>
          ) : null}
          {page.receipt.lines.map((line, index) => (
            <View key={line.id ?? index} style={styles.item} testID={`split-${index}`}>
              <View style={[styles.between, styles.baseline]}>
                <AppText weight={500} size={15} style={styles.itemName}>
                  {itemName(line)}
                </AppText>
                <AppText font="mono" size={14}>
                  {lineAmount(line.lineTotal, page.receipt)}
                </AppText>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.lineChips} accessibilityRole="radiogroup" accessibilityLabel={`${itemName(line)} category`}>
                {page.categories.map((category) => (
                  <Chip
                    key={category.id}
                    compact
                    label={category.name}
                    selected={current[index] === category.id}
                    onPress={() => setChosen(current.map((value, at) => (at === index ? category.id : value)))}
                    testID={`split-${index}-${category.id}`}
                  />
                ))}
              </ScrollView>
            </View>
          ))}
          {failure ? (
            <AppText size={14} color="redText" accessibilityLiveRegion="polite">
              {failure}
            </AppText>
          ) : null}
          {page.receipt.lines.length > 0 ? <Button label="Save split" onPress={() => void save()} busy={busy} /> : null}
        </View>
      ) : null}
    </SheetFrame>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingTop: 30, paddingHorizontal: 22 },
  between: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  baseline: { alignItems: 'baseline' },
  corner: { flexShrink: 1 },
  heading: { marginTop: 14, marginBottom: 4, lineHeight: 27.5 },
  sentence: { lineHeight: 21, marginBottom: 18 },
  gap: { gap: 8 },
  gap22: { gap: 22 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  item: { gap: 8 },
  itemName: { flexShrink: 1 },
  chipRow: { flexGrow: 0 },
  lineChips: { gap: 8, alignItems: 'center' },
});
