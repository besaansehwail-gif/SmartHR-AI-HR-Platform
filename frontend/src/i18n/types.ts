/**
 * SmartHR localization - the shared types.
 *
 * One entry holds **both** languages:
 *
 *     'common.save': { en: 'Save', ar: 'حفظ' }
 *
 * rather than two parallel `en.ts` / `ar.ts` files. That is deliberate: with
 * parallel files a key added to English and forgotten in Arabic type-checks
 * cleanly and then renders an English word in the middle of an Arabic page.
 * Here `Translation` requires both, so the same omission is a compile error -
 * `tsc --noEmit` is the only check this project has, so the design leans on
 * it. It also puts the two wordings on adjacent lines, which is how anyone
 * reviewing a translation actually wants to read them.
 */

export type Locale = 'en' | 'ar';

export const LOCALES: Locale[] = ['en', 'ar'];

export const DEFAULT_LOCALE: Locale = 'en';

/** Every string in the application, in both languages. Both are required. */
export interface Translation {
  en: string;
  ar: string;
}

export type Dictionary = Record<string, Translation>;

/** What a locale means for the document and for layout. */
export interface LocaleMeta {
  code: Locale;
  /** Written in its own language, which is how a language picker should read. */
  nativeName: string;
  englishName: string;
  dir: 'ltr' | 'rtl';
}

export const LOCALE_META: Record<Locale, LocaleMeta> = {
  en: { code: 'en', nativeName: 'English', englishName: 'English', dir: 'ltr' },
  ar: { code: 'ar', nativeName: 'العربية', englishName: 'Arabic', dir: 'rtl' },
};

/** Values a translation may interpolate: `t('x', { count: 3 })` -> `{count}`. */
export type TranslationValues = Record<string, string | number>;
