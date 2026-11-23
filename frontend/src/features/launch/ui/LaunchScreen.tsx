import { StatusBar } from 'expo-status-bar';
import { StyleSheet, View } from 'react-native';

import { Paper, Wordmark } from '@/shared/ui';

/**
 * The launch screen (D039): a full page of yellow paper with the large wordmark in ink, centred, and nothing
 * else. It looks the same in dark mode, so the status bar is always dark on it.
 *
 * It matches the native splash (app.json: #f5e54a and the same 284 x 59 wordmark, centred on the whole
 * screen), so the splash hands over to it without a jump; only the fine grain appears. No delay and no
 * animation: it stays exactly as long as the saved session takes to check.
 */
export function LaunchScreen() {
  return (
    <Paper variant="yellow">
      <StatusBar style="dark" />
      <View style={styles.centre}>
        {/* The Wordmark aligns itself to the start (for headers); this box shrinks to it, so it is centred. */}
        <View>
          <Wordmark size="large" onYellow />
        </View>
      </View>
    </Paper>
  );
}

const styles = StyleSheet.create({
  // Centred on the whole screen, not inside the safe area, like the splash image.
  centre: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
