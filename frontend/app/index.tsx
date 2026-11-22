// TODO(launch): placeholder. The launch feature replaces this body with its screen from
// src/features/launch/ui (yellow paper, large wordmark, D039). Keep the redirect rule, or move it there.
import { Redirect } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { Paper, Wordmark } from '@/shared/ui';

export default function LaunchRoute() {
  const { status } = useSession();

  if (status === 'signedIn') return <Redirect href="/(tabs)" />;
  if (status === 'signedOut') return <Redirect href="/sign-in" />;

  // Still checking the saved session.
  return (
    <Paper variant="yellow">
      <View style={styles.centre}>
        <Wordmark size="large" onYellow />
      </View>
    </Paper>
  );
}

const styles = StyleSheet.create({
  centre: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
