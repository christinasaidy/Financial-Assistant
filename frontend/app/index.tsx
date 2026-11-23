import { Redirect } from 'expo-router';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { LaunchScreen } from '@/features/launch/ui/LaunchScreen';

/**
 * The launch route: the yellow launch screen while the saved session is checked, then sign in or Home.
 * The launch screen stays drawn under the redirect, so the next screen slides in over yellow paper instead
 * of over an empty frame.
 */
export default function LaunchRoute() {
  const { status } = useSession();
  return (
    <>
      <LaunchScreen />
      {status === 'signedIn' ? <Redirect href="/(tabs)" /> : null}
      {status === 'signedOut' ? <Redirect href="/sign-in" /> : null}
    </>
  );
}
