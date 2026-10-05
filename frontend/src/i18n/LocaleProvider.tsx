import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { dictionary } from './dictionaries';
import {
  DEFAULT_LOCALE,
  Locale,
  LOCALE_META,
  LOCALES,
  TranslationValues,
} from './types';

/**
 * SmartHR localization - one provider, one hook, no dependency.
 *
 * **Why not react-i18next.** The project has no i18n library and a deliberately
 * short dependency list (`app/ai/provider.py` uses `urllib` rather than adding
 * an HTTP client for two POSTs, and the same judgement applies here). What
 * SmartHR needs is a string lookup, an interpolation, a persisted choice and a
 * document direction - about a hundred lines. A library would add a bundle, a
 * loader, a plural engine and a config file to do the same thing, and the
 * translations would still have to be written by hand. If the app later needs
 * lazy-loaded locales or ICU plurals, `useT()` is the seam to swap behind.
 *
 * **What the provider owns:**
 *  - the current locale, read once from localStorage on mount;
 *  - `document.documentElement.lang` and `.dir`, kept in step with it;
 *  - `t()`, memoised per locale so a language change re-renders once.
 *
 * Mounted in `main.tsx` **outside** `<App />`, which matters: the switcher has
 * to work on the sign-in screen, before there is a session, and the language
 * must survive the sign-in that replaces the whole authenticated tree.
 */

const STORAGE_KEY = 'smarthr_locale';

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  dir: 'ltr' | 'rtl';
  isRtl: boolean;
  /** Translate a key. Unknown keys return the key, which is visibly wrong. */
  t: (key: string, values?: TranslationValues) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

const isLocale = (value: unknown): value is Locale =>
  typeof value === 'string' && (LOCALES as string[]).includes(value);

/**
 * The stored preference, or English.
 *
 * Read synchronously in `useState`'s initialiser rather than in an effect, so
 * the first paint is already in the right language and direction - an Arabic
 * user never sees a frame of English sliding from LTR to RTL.
 */
const readStoredLocale = (): Locale => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // Private mode or blocked storage: fall through to the default.
  }
  return DEFAULT_LOCALE;
};

/** `{name}` placeholders, filled from `values`. Missing keys are left alone. */
const interpolate = (template: string, values?: TranslationValues): string => {
  if (!values) return template;

  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match
  );
};

export const LocaleProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage blocked: the language still changes, it just is not remembered.
    }
  }, []);

  // The document itself carries the language and direction. Everything RTL in
  // the UI keys off `dir` on <html> - logical CSS properties, the `rtl:`
  // Tailwind variant, and the browser's own bidi algorithm for mixed text -
  // so this effect is what actually flips the layout. Nothing else has to.
  useEffect(() => {
    const meta = LOCALE_META[locale];
    const root = document.documentElement;

    root.lang = meta.code;
    root.dir = meta.dir;
    // Lets stylesheets target the language without a class hook.
    root.setAttribute('data-locale', meta.code);
  }, [locale]);

  const value = useMemo<LocaleContextValue>(() => {
    const meta = LOCALE_META[locale];

    const t = (key: string, values?: TranslationValues): string => {
      const entry = dictionary[key];

      if (!entry) {
        // Returning the key is deliberate: a missing string shows up as
        // `hr.candidates.title` on screen, which is noticed immediately.
        // Falling back to a prettified guess would hide it until a user found
        // it. Warn once per key in development.
        if (import.meta.env?.DEV) {
          warnOnce(key);
        }
        return key;
      }

      // An empty Arabic string falls back to English rather than rendering
      // blank - a partially translated entry should read oddly, not vanish.
      const text = entry[locale] || entry.en;

      return interpolate(text, values);
    };

    return {
      locale,
      setLocale,
      dir: meta.dir,
      isRtl: meta.dir === 'rtl',
      t,
    };
  }, [locale, setLocale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
};

const warned = new Set<string>();
const warnOnce = (key: string) => {
  if (warned.has(key)) return;
  warned.add(key);
  console.warn(`[i18n] missing translation key: ${key}`);
};

/**
 * The hook every component uses.
 *
 *     const { t, isRtl } = useT();
 *     <h1>{t('hr.candidates.title')}</h1>
 *
 * Throws outside the provider rather than silently returning English, because
 * a component rendered outside it would otherwise never switch language and
 * nobody would know why.
 */
export const useT = (): LocaleContextValue => {
  const context = useContext(LocaleContext);

  if (!context) {
    throw new Error('useT must be used inside <LocaleProvider>.');
  }

  return context;
};

export { STORAGE_KEY as LOCALE_STORAGE_KEY };
