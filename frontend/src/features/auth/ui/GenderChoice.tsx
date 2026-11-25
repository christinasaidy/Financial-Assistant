import { OptionRow } from '@/shared/ui';

import { genders, type Gender } from '../domain/types';

/** Written in normal case; shown in capitals by the section-label style (D012). */
export const genderLabels: Record<Gender, string> = {
  female: 'Female',
  male: 'Male',
  prefer_not_to_say: 'Prefer not to say',
};

const options = genders.map((gender) => ({ value: gender, label: genderLabels[gender] }));

type Props = {
  value: Gender | null;
  onChange: (gender: Gender) => void;
  /** Shown under the options in the same style as a field's error. */
  error?: string | null;
};

/** The gender question of create account (D041): a GENDER caption over three equal square options. */
export function GenderChoice({ value, onChange, error }: Props) {
  return <OptionRow caption="Gender" options={options} value={value} onChange={onChange} error={error} testIDPrefix="gender" />;
}
