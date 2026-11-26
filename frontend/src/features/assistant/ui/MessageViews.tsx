import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { shortMonthName } from '@/shared/format/dates';
import { colors, radius } from '@/shared/theme';
import { AppText, DashedLine, LineIcon, PaperSheet } from '@/shared/ui';

import { answerPieces, relativeDay, type AssistantMode, type Message, type Rating } from '../domain';

/** The answer cards' shadow (design/reference/07: .card). */
const CARD_SHADOW = {
  shadowColor: 'rgb(40,35,25)',
  shadowOpacity: 0.12,
  shadowRadius: 12,
  shadowOffset: { width: 0, height: 8 },
} as const;

/** "Today · 26 Nov", centred between days. */
export function DaySeparator({ createdAt, today }: { createdAt: string; today: Date }) {
  const date = new Date(createdAt);
  const day = `${date.getDate()} ${shortMonthName(date)}`;
  const relative = relativeDay(createdAt, today);
  return (
    <AppText cap style={styles.day}>
      {relative ? `${relative} · ${day}` : day}
    </AppText>
  );
}

/** The user's question: an ink bubble on the right, radius 14 14 4 14; Arabizi questions in Geist Mono. */
export function UserBubble({ message, mode }: { message: Message; mode: AssistantMode }) {
  return (
    <View style={styles.me} testID={`message-${message.id}`}>
      <AppText font={mode === 'beta' ? 'mono' : 'sans'} size={mode === 'beta' ? 14.5 : 15} color="userBubbleText" style={styles.meText}>
        {message.content}
      </AppText>
    </View>
  );
}

/** The answer's text, amounts in bold Geist Mono (design/reference/07). */
function AnswerText({ content }: { content: string }) {
  return (
    <AppText size={15} style={styles.answer}>
      {answerPieces(content).map((piece, index) =>
        piece.style === 'plain' ? (
          piece.text
        ) : (
          <AppText key={index} font={piece.style === 'amount' ? 'mono' : 'sans'} weight={600} size={15}>
            {piece.text}
          </AppText>
        ),
      )}
    </AppText>
  );
}

/** An answer shown as a table (the backend's fallback when no sentence passed its number check). */
function AnswerTable({ table }: { table: NonNullable<Message['table']> }) {
  return (
    <View style={styles.table}>
      {[table.columns, ...table.rows].map((row, rowIndex) => (
        <View key={rowIndex} style={[styles.tableRow, rowIndex > 0 ? styles.tableRule : null]}>
          {row.map((cell, cellIndex) => (
            <AppText key={cellIndex} cap={rowIndex === 0} font="mono" size={rowIndex === 0 ? 10.5 : 13} style={styles.cell}>
              {cell ?? '—'}
            </AppText>
          ))}
        </View>
      ))}
    </View>
  );
}

type AnswerProps = {
  message: Message;
  mode: AssistantMode;
  /** Beta's latest answer asks "Was this right?" (DESIGN.md §6: stored as training data). */
  ratable: boolean;
  onRate: (message: Message, rating: Rating) => void;
};

/**
 * An answer: a small creased card with a torn edge, at most 88% wide (92% in Beta), with ASSISTANT or
 * ARABIZI · BETA in cobalt at the top. Beta answers can show the query that ran, and the latest one asks
 * "Was this right?".
 */
export function AnswerCard({ message, mode, ratable, onRate }: AnswerProps) {
  const [queryShown, setQueryShown] = useState(false);
  const beta = mode === 'beta';
  return (
    <PaperSheet on="bg" shadow={CARD_SHADOW} outerStyle={[styles.card, { maxWidth: beta ? '92%' : '88%' }]} style={styles.paper} testID={`message-${message.id}`}>
      <AppText cap color="cobalt" style={styles.label}>
        {beta ? 'Arabizi · Beta' : 'Assistant'}
      </AppText>
      {message.content ? <AnswerText content={message.content} /> : null}
      {message.table ? <AnswerTable table={message.table} /> : null}

      {beta && message.sql ? (
        <View style={styles.section}>
          <DashedLine />
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: queryShown }}
            onPress={() => setQueryShown((shown) => !shown)}
            style={styles.queryToggle}
            testID={`query-toggle-${message.id}`}
          >
            <AppText weight={500} size={13} color="cobalt">
              {queryShown ? 'Hide query' : 'Show query'}
            </AppText>
            <View style={queryShown ? styles.turned : null}>
              <LineIcon name="chevronDown" size={14} color="cobalt" />
            </View>
          </Pressable>
          {queryShown ? (
            <View style={styles.code}>
              <AppText font="mono" size={11.5} color="codeText" style={styles.codeText} selectable>
                {message.sql}
              </AppText>
            </View>
          ) : null}
        </View>
      ) : null}

      {ratable ? (
        <View style={styles.section}>
          <DashedLine />
          <View style={styles.rateRow}>
            <AppText size={13} color="noteText" style={styles.rateQuestion}>
              Was this right?
            </AppText>
            <RateButton label="Yes, correct" icon="check" chosen={message.rating === 'up'} onPress={() => onRate(message, 'up')} />
            <RateButton label="No, wrong" icon="cross" chosen={message.rating === 'down'} onPress={() => onRate(message, 'down')} />
          </View>
        </View>
      ) : null}
    </PaperSheet>
  );
}

/** ✓ or ✗: 40 × 36, outlined; once chosen, ink with a white mark (D047). */
function RateButton({ label, icon, chosen, onPress }: { label: string; icon: 'check' | 'cross'; chosen: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: chosen }}
      onPress={onPress}
      style={[styles.rate, chosen ? styles.rateChosen : null]}
      testID={`rate-${icon}`}
    >
      <LineIcon name={icon} size={16} color={chosen ? 'white' : 'ink'} />
    </Pressable>
  );
}

/** While the answer is coming: the card with a small spinner (D047). */
export function PendingCard({ mode }: { mode: AssistantMode }) {
  return (
    <PaperSheet on="bg" shadow={CARD_SHADOW} outerStyle={[styles.card, styles.pending]} style={styles.paper} testID="answer-pending">
      <AppText cap color="cobalt" style={styles.label}>
        {mode === 'beta' ? 'Arabizi · Beta' : 'Assistant'}
      </AppText>
      <View style={styles.thinking}>
        <ActivityIndicator size="small" color={colors.inkMuted} />
        <AppText size={14} color="noteText">
          {mode === 'beta' ? 'Reading your receipts…' : 'Thinking…'}
        </AppText>
      </View>
    </PaperSheet>
  );
}

const styles = StyleSheet.create({
  day: { alignSelf: 'center' },
  me: {
    alignSelf: 'flex-end',
    maxWidth: '78%',
    backgroundColor: colors.ink,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
    borderBottomRightRadius: 4,
    borderBottomLeftRadius: 14,
  },
  meText: { lineHeight: 21 },
  card: { alignSelf: 'flex-start' },
  pending: { minWidth: '60%' },
  paper: { paddingTop: 12, paddingHorizontal: 14, paddingBottom: 18 },
  label: { marginBottom: 8 },
  answer: { lineHeight: 21.75 },
  table: { marginTop: 4 },
  tableRow: { flexDirection: 'row', gap: 12, paddingVertical: 6 },
  tableRule: { borderTopWidth: 1, borderTopColor: colors.ruleSoft },
  cell: { flex: 1 },
  section: { marginTop: 10 },
  queryToggle: { minHeight: 36, paddingTop: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  turned: { transform: [{ rotate: '180deg' }] },
  code: { marginTop: 6, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: colors.ink, borderRadius: 6 },
  codeText: { lineHeight: 17.8 },
  rateRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 8 },
  rateQuestion: { flex: 1 },
  rate: {
    width: 40,
    height: 36,
    borderWidth: 1,
    borderColor: colors.betaLine,
    borderRadius: radius.button - 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rateChosen: { backgroundColor: colors.ink, borderColor: colors.ink },
  thinking: { flexDirection: 'row', alignItems: 'center', gap: 8 },
});
