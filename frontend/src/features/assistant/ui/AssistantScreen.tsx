import { useRef, useState, type ComponentRef } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { monthName } from '@/shared/format/dates';
import { colors, fonts, radius, touchTarget } from '@/shared/theme';
import { AppText, Chip, LineIcon, TextLink } from '@/shared/ui';

import type { AssistantService } from '../application/assistantService';
import { byDay, ratableAnswerId, unavailableSentence, type AssistantMode } from '../domain';
import { AnswerCard, DaySeparator, PendingCard, UserBubble } from './MessageViews';
import { useAssistant, useAssistantService } from './useAssistant';

type Props = {
  /** Defaults to the app's AssistantService from the container; tests pass one built on a fake. */
  service?: AssistantService;
  /** Today, for the day separators and the suggestions; tests fix it. */
  today?: () => Date;
};

const placeholders: Record<AssistantMode, string> = {
  standard: 'Ask about your spending…',
  beta: 'Es2al bel arabizi… e.g. addeh dafa3et?',
};

/**
 * The Assistant (design/screens/07-assistant-sonnet.png and 08-assistant-arabizi-beta.png): the title with +
 * (new conversation), the switch between Assistant (Claude Sonnet) and Arabizi Beta (fine-tuned Qwen), the
 * conversation, suggestions in Standard, and the message field. Answers are text cards for now (D047).
 */
export function AssistantScreen({ service, today = () => new Date() }: Props) {
  const assistant = useAssistant(useAssistantService(service));
  const insets = useSafeAreaInsets();
  const [draft, setDraft] = useState('');
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const { mode, state } = assistant;
  const now = today();
  const blocked = unavailableSentence(assistant.modeStatus);
  const lastMonth = monthName(new Date(now.getFullYear(), now.getMonth() - 1, 1));
  const ratable = ratableAnswerId(state.messages, mode);
  const canSend = draft.trim().length > 0 && !state.pending && !blocked && state.status === 'ready';

  const send = async (question: string) => {
    setDraft('');
    const failed = await assistant.ask(question);
    if (failed !== null) setDraft(failed);
  };

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[styles.header, { paddingTop: insets.top + 14 }]}>
        <AppText weight={600} size={20} tracking={-0.01} accessibilityRole="header">
          Assistant
        </AppText>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="New conversation"
          onPress={assistant.newConversation}
          style={styles.iconButton}
          testID="new-conversation"
        >
          <LineIcon name="newConversation" />
        </Pressable>
      </View>

      <ModeSwitch mode={mode} onChange={assistant.setMode} />

      <ScrollView
        ref={scroll}
        style={styles.fill}
        contentContainerStyle={[styles.messages, mode === 'beta' ? styles.betaMessages : null]}
        onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}
        keyboardShouldPersistTaps="handled"
        testID="conversation"
      >
        {mode === 'beta' ? <BetaNote /> : null}
        {state.status === 'loading' ? <ActivityIndicator color={colors.inkMuted} accessibilityLabel="Loading" /> : null}
        {state.status === 'failed' ? (
          <View style={styles.problem}>
            <AppText size={14} color="inkMuted">
              {state.error}
            </AppText>
            <TextLink label="Try again" onPress={assistant.retry} />
          </View>
        ) : null}
        {byDay(state.messages).map((group) => (
          <View key={group.day} style={[styles.group, mode === 'beta' ? styles.betaGroup : null]}>
            <DaySeparator createdAt={group.first} today={now} />
            {group.messages.map((message) =>
              message.role === 'user' ? (
                <UserBubble key={message.id} message={message} mode={mode} />
              ) : (
                <AnswerCard key={message.id} message={message} mode={mode} ratable={message.id === ratable} onRate={(item, rating) => void assistant.rate(item, rating)} />
              ),
            )}
          </View>
        ))}
        {state.pending ? <PendingCard mode={mode} /> : null}
        {mode === 'standard' && state.status === 'ready' && !state.pending && !blocked ? (
          <View style={styles.suggestions}>
            {['Where can I cut back?', `Compare to ${lastMonth}`].map((suggestion) => (
              <Chip key={suggestion} role="button" label={suggestion} onPress={() => void send(suggestion)} />
            ))}
          </View>
        ) : null}
      </ScrollView>

      {blocked || (state.status === 'ready' && state.error) ? (
        <AppText size={13} color={blocked ? 'inkMuted' : 'redText'} style={styles.notice} accessibilityLiveRegion="polite" testID="assistant-notice">
          {blocked ?? state.error}
        </AppText>
      ) : null}

      <View style={styles.composer}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder={placeholders[mode]}
          placeholderTextColor={colors.placeholder}
          selectionColor={colors.cobalt}
          accessibilityLabel="Message"
          returnKeyType="send"
          submitBehavior="blurAndSubmit"
          onSubmitEditing={() => canSend && void send(draft)}
          autoCapitalize={mode === 'beta' ? 'none' : 'sentences'}
          autoCorrect={mode !== 'beta'}
          style={styles.input}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Send"
          accessibilityState={{ disabled: !canSend }}
          disabled={!canSend}
          onPress={() => void send(draft)}
          style={({ pressed }) => [styles.send, { backgroundColor: pressed ? colors.cobaltPressed : colors.cobalt, opacity: canSend ? 1 : 0.5 }]}
          testID="send"
        >
          <LineIcon name="send" size={18} color="white" />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

/** The segmented switch (design/reference/07): two lines per segment, the mode's name over its model. */
function ModeSwitch({ mode, onChange }: { mode: AssistantMode; onChange: (mode: AssistantMode) => void }) {
  const segments: { value: AssistantMode; name: string; model: string }[] = [
    { value: 'standard', name: 'Assistant', model: 'Claude Sonnet' },
    { value: 'beta', name: 'Arabizi', model: 'Fine-tuned Qwen' },
  ];
  return (
    <View accessibilityRole="tablist" style={styles.switch}>
      {segments.map((segment) => {
        const chosen = segment.value === mode;
        return (
          <Pressable
            key={segment.value}
            accessibilityRole="tab"
            accessibilityLabel={segment.value === 'beta' ? `${segment.name} Beta, ${segment.model}` : `${segment.name}, ${segment.model}`}
            accessibilityState={{ selected: chosen }}
            onPress={() => onChange(segment.value)}
            style={[styles.segment, chosen ? styles.segmentChosen : null]}
            testID={`mode-${segment.value}`}
          >
            <View style={styles.segmentName}>
              <AppText weight={chosen ? 600 : 500} size={14} color={chosen ? 'ink' : 'fieldLabel'}>
                {segment.name}
              </AppText>
              {segment.value === 'beta' ? (
                <View style={styles.badge}>
                  <AppText cap size={9} color="cobalt">
                    Beta
                  </AppText>
                </View>
              ) : null}
            </View>
            <AppText font="mono" size={10.5} color="inkMuted">
              {segment.model}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

/** The dashed BETA note at the top of the Arabizi conversation (design/reference/08). */
function BetaNote() {
  return (
    <View style={styles.note}>
      <AppText cap color="cobalt" style={styles.noteCap}>
        Beta
      </AppText>
      <AppText size={13} color="noteText" style={styles.noteText}>
        Ask in Lebanese Arabizi. Answers come straight from your receipts.
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  fill: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingRight: 16, paddingLeft: 20 },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  switch: { marginTop: 8, marginHorizontal: 16, flexDirection: 'row', padding: 3, borderRadius: radius.button, backgroundColor: colors.segmentTrack },
  segment: { flex: 1, minHeight: 44, borderRadius: 9, alignItems: 'center', justifyContent: 'center', paddingVertical: 4 },
  segmentChosen: {
    backgroundColor: colors.paperClean,
    shadowColor: '#000000',
    shadowOpacity: 0.12,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
  },
  segmentName: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  badge: { borderWidth: 1, borderColor: colors.cobalt, borderRadius: 4, paddingVertical: 2, paddingHorizontal: 4 },
  messages: { paddingTop: 18, paddingHorizontal: 16, paddingBottom: 12, gap: 14, flexGrow: 1 },
  betaMessages: { paddingTop: 10, gap: 10 },
  group: { gap: 14 },
  betaGroup: { gap: 10 },
  problem: { gap: 8 },
  suggestions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  note: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.betaLine,
    borderRadius: 8,
  },
  noteCap: { marginTop: 2 },
  noteText: { flex: 1, lineHeight: 18.2 },
  notice: { marginHorizontal: 16, marginBottom: 8 },
  composer: {
    marginHorizontal: 12,
    marginBottom: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.paperClean,
    borderWidth: 1,
    borderColor: colors.inputBorder,
    borderRadius: radius.input,
    paddingVertical: 4,
    paddingRight: 4,
    paddingLeft: 14,
  },
  input: { flex: 1, minHeight: 44, fontFamily: fonts.sans.regular, fontSize: 16, color: colors.ink, paddingVertical: 0 },
  send: { width: 44, height: 44, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
});
