/**
 * The two auth screens inside a small router that guards them the way app/_layout.tsx does, with an
 * AuthService built on fakes. Lets a test press the links and see the session move to "home".
 */
import { Stack } from 'expo-router';
import { renderRouter } from 'expo-router/testing-library';
import { Text } from 'react-native';

import { AuthService } from '@/features/auth/application/authService';
import { SessionProvider, useSession } from '@/features/auth/ui/SessionProvider';
import { SignInScreen } from '@/features/auth/ui/SignInScreen';
import { SignUpScreen } from '@/features/auth/ui/SignUpScreen';

import { FakeAuthRepository, FakeTokenStore } from './fakes';

export const maya = { email: 'maya@example.com', password: 'zaatar-w-zeit', firstName: 'Maya', gender: 'female' } as const;

function Guarded() {
  const { status } = useSession();
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={status !== 'signedIn'}>
        <Stack.Screen name="sign-in" />
        <Stack.Screen name="sign-up" />
      </Stack.Protected>
      <Stack.Protected guard={status === 'signedIn'}>
        <Stack.Screen name="home" />
      </Stack.Protected>
    </Stack>
  );
}

function Home() {
  const { user } = useSession();
  return <Text>Signed in as {user?.firstName}</Text>;
}

/** Renders the auth routes at `initialUrl`, with Maya's account already on the fake backend. */
export async function renderAuthRoutes(initialUrl: '/sign-in' | '/sign-up') {
  const repository = new FakeAuthRepository();
  await repository.register({ ...maya });
  repository.calls = [];
  const service = new AuthService(repository, new FakeTokenStore());

  function Layout() {
    return (
      <SessionProvider authService={service}>
        <Guarded />
      </SessionProvider>
    );
  }

  const router = await renderRouter(
    { _layout: Layout, 'sign-in': SignInScreen, 'sign-up': SignUpScreen, home: Home },
    { initialUrl },
  );
  return { router, repository, service };
}
