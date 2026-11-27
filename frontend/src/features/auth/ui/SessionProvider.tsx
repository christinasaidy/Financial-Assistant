import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { getContainer } from '@/container';

import type { AuthService } from '../application/authService';
import type { SignUpDetails, User } from '../domain/types';

export type SessionStatus = 'loading' | 'signedOut' | 'signedIn';

export type SessionValue = {
  /** 'loading' until the saved session has been checked at launch. */
  status: SessionStatus;
  /** The signed-in user; null unless status is 'signedIn'. */
  user: User | null;
  /** Throws AuthError (code: 'invalid-credentials' | 'network' | ...) when it fails. */
  signIn: (email: string, password: string) => Promise<User>;
  /** Creates the account and signs in. Throws AuthError ('email-taken', 'invalid-details', ...). */
  signUp: (details: SignUpDetails) => Promise<User>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

type Props = {
  children: ReactNode;
  /** Defaults to the app's AuthService from the container; tests pass one built on fakes. */
  authService?: AuthService;
};

/**
 * Holds the session for the whole app (mounted once in app/_layout.tsx). On mount it restores the saved
 * session; afterwards it follows the AuthService, so a 401 anywhere in the app signs the user out here.
 */
export function SessionProvider({ children, authService }: Props) {
  const service = useMemo(() => authService ?? getContainer().auth, [authService]);
  const [state, setState] = useState<{ status: SessionStatus; user: User | null }>({
    status: 'loading',
    user: null,
  });

  useEffect(() => {
    let active = true;
    const unsubscribe = service.subscribe((user) => {
      if (active) setState({ status: user ? 'signedIn' : 'signedOut', user });
    });
    service
      .restoreSession()
      .catch(() => null)
      .then((user) => {
        if (active) setState({ status: user ? 'signedIn' : 'signedOut', user });
      });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [service]);

  const value = useMemo<SessionValue>(
    () => ({
      ...state,
      signIn: (email, password) => service.signIn(email, password),
      signUp: (details) => service.signUp(details),
      signOut: () => service.signOut(),
    }),
    [state, service],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/** The session, from any screen inside SessionProvider. */
export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used inside <SessionProvider>');
  return value;
}
