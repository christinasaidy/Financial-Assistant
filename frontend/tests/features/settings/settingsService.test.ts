import { SettingsService } from '@/features/settings/application/settingsService';
import { StoredAppearanceStore } from '@/features/settings/data/storedAppearanceStore';
import { forcedScheme } from '@/features/settings/domain/appearance';
import type { SecureValue } from '@/shared/storage/tokenStore';

import { FakeAppearanceStore } from './fakes';

function memoryValue(initial: string | null = null): SecureValue & { text: string | null } {
  const value = {
    text: initial,
    read: async () => value.text,
    write: async (text: string) => {
      value.text = text;
    },
    remove: async () => {
      value.text = null;
    },
  };
  return value;
}

describe('the appearance (D043)', () => {
  it('forces light or dark, and follows the phone for "phone"', () => {
    expect(forcedScheme('phone')).toBeNull();
    expect(forcedScheme('light')).toBe('light');
    expect(forcedScheme('dark')).toBe('dark');
  });
});

describe('SettingsService', () => {
  it('follows the phone until something is saved, then returns the saved choice', async () => {
    const store = new FakeAppearanceStore();
    const service = new SettingsService(store);
    expect(await service.loadAppearance()).toBe('phone');

    await service.setAppearance('dark');
    expect(store.saved).toBe('dark');
    expect(await service.loadAppearance()).toBe('dark');
  });

  it('never fails when the store does: it follows the phone and drops the save', async () => {
    const store = new FakeAppearanceStore();
    store.fail = true;
    const service = new SettingsService(store);
    expect(await service.loadAppearance()).toBe('phone');
    await expect(service.setAppearance('light')).resolves.toBeUndefined();
  });
});

describe('StoredAppearanceStore', () => {
  it('keeps the choice as its plain name', async () => {
    const value = memoryValue();
    const store = new StoredAppearanceStore(value);
    expect(await store.load()).toBeNull();
    await store.save('light');
    expect(value.text).toBe('light');
    expect(await store.load()).toBe('light');
  });

  it('reads anything else as nothing saved', async () => {
    expect(await new StoredAppearanceStore(memoryValue('sepia')).load()).toBeNull();
  });
});
