// TODO(home): placeholder. Replace with the Home screen from src/features/home/ui (D035-D037, mockups
// Wrinkle.dc.html and Empty.dc.html). The sign-out button below is only here to try the session flow.
import { useSession } from '@/features/auth/ui/SessionProvider';
import { Button, PlaceholderScreen } from '@/shared/ui';

export default function HomeRoute() {
  const { user, signOut } = useSession();
  return (
    <PlaceholderScreen title={user?.firstName ? `Hello, ${user.firstName}` : 'Home'} owner="home">
      <Button label="Sign out" onPress={() => void signOut()} />
    </PlaceholderScreen>
  );
}
