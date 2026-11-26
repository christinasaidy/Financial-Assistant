import { SegmentedChoice } from '@/shared/ui';

import { genders, type Gender } from '../domain/types';

export const genderLabels: Record<Gender, string> = {
  female: 'Female',
  male: 'Male',
  prefer_not_to_say: 'Prefer not to say',
};

const choices = genders.map((gender) => ({ value: gender, label: genderLabels[gender] }));

type Props = {
  value: Gender | null;
  onChange: (gender: Gender) => void;
  /** Shown under the choices in the same style as a field's error. */
  error?: string | null;
};

/** The gender question of create account (D041): the Assistant's segmented switch, three choices (D044). */
export function GenderChoice({ value, onChange, error }: Props) {
  return <SegmentedChoice label="Gender" choices={choices} value={value} onChange={onChange} error={error} testIDPrefix="gender" />;
}
