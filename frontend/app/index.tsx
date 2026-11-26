import { Redirect } from 'expo-router';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { LaunchScreen } from '@/features/launch/ui/LaunchScreen';
import { useLaunchHold } from '@/features/launch/ui/useLaunchHold';

/**
 * The launch route: the launch screen for at least 1.5 s after the app opens and until the saved session is
 * checked, then sign in or Home. The launch screen stays drawn under the redirect, so the next screen slides
 * in over it instead of over an empty frame.
 */
export default function LaunchRoute() {
  const { status } = useSession();
  const holding = useLaunchHold();
  return (
    <>
      <LaunchScreen />
      {!holding && status === 'signedIn' ? <Redirect href="/(tabs)" /> : null}
      {!holding && status === 'signedOut' ? <Redirect href="/sign-in" /> : null}
    </>
  );
}
