import { useEffect, useRef } from 'react';

import { useSession } from './SessionProvider';

/**
 * Runs `reset` when the session goes from signed in back to signed out.
 *
 * Sign in and create account stay busy after they succeed, until the tabs replace them. On the iPhone the
 * native stack can keep that same screen alive under the tabs, so after signing out it came back with its
 * button still busy (disabled, and busy has no look yet), and SIGN IN did nothing. The screens use this to
 * become ready again, and to drop the old password.
 */
export function useSignedOutAgain(reset: () => void) {
  const { status } = useSession();
  const previous = useRef(status);
  const latestReset = useRef(reset);

  useEffect(() => {
    latestReset.current = reset;
  });

  useEffect(() => {
    if (previous.current === 'signedIn' && status === 'signedOut') latestReset.current();
    previous.current = status;
  }, [status]);
}
