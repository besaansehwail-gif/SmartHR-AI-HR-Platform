import { Dictionary } from '../types';

import { admin } from './admin';
import { ai } from './ai';
import { aiInterview } from './aiInterview';
import { applicant } from './applicant';
import { auth } from './auth';
import { common } from './common';
import { hr } from './hr';
import { nav } from './nav';
import { social } from './social';
import { ui } from './ui';
import { workforce } from './workforce';

/**
 * Every SmartHR string, in both languages.
 *
 * Split by area only so the files stay readable; the lookup is one flat map,
 * because a key like `hr.candidates.title` already carries its namespace and
 * nesting would buy nothing but deeper property access.
 *
 * Adding a screen means adding its keys to the matching file. Adding a
 * language means adding a third property to `Translation` in `../types`, at
 * which point `tsc` lists every entry that still needs it - which is the
 * whole reason both languages live in one entry.
 */
export const dictionary: Dictionary = {
  ...common,
  ...ui,
  ...nav,
  ...auth,
  ...admin,
  ...hr,
  ...workforce,
  ...applicant,
  ...ai,
  ...aiInterview,
  ...social,
};

/** Diagnostics: how many strings exist, used by the i18n self-check. */
export const TRANSLATION_COUNT = Object.keys(dictionary).length;
