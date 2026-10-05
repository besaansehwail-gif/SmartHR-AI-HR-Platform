import { Locale } from './types';

/**
 * Locale-aware dates and numbers.
 *
 * **Arabic here uses Western digits, deliberately.** `Intl` with a plain `ar`
 * locale renders Arabic-Indic numerals (٢٠٢٦, ٤٥٪). They are correct Arabic,
 * but business and HR software across the Levant and the Gulf overwhelmingly
 * writes figures in Western digits, and SmartHR shows employee ids, salaries,
 * match percentages and dates beside English-sourced data (a CV, a job title,
 * an email) that stays Latin. Mixing numeral systems down one column is harder
 * to scan, not more authentic. `-u-nu-latn` pins Latin digits while keeping
 * Arabic month names, ordering and the bidi behaviour.
 *
 * If a deployment wants Arabic-Indic numerals, changing `ARABIC_LOCALE` to
 * `'ar'` is the whole change - which is why every formatter goes through here
 * rather than calling `toLocaleDateString` inline.
 */

const ARABIC_LOCALE = 'ar-u-nu-latn';
const ENGLISH_LOCALE = 'en-GB';

const intlLocale = (locale: Locale): string =>
  locale === 'ar' ? ARABIC_LOCALE : ENGLISH_LOCALE;

/** A date as `12 Sep 2026` / `١٢ سبتمبر ٢٠٢٦`-style, in Latin digits. */
export const formatDate = (
  value: string | Date | null | undefined,
  locale: Locale
): string => {
  if (!value) return '—';

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat(intlLocale(locale), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
};

/** A date with the time, for audit rows and interview slots. */
export const formatDateTime = (
  value: string | Date | null | undefined,
  locale: Locale
): string => {
  if (!value) return '—';

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat(intlLocale(locale), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const formatTime = (
  value: string | Date | null | undefined,
  locale: Locale
): string => {
  if (!value) return '—';

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat(intlLocale(locale), {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const formatNumber = (
  value: number | null | undefined,
  locale: Locale,
  options?: Intl.NumberFormatOptions
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';

  return new Intl.NumberFormat(intlLocale(locale), options).format(value);
};

/** `45%` in both languages; Arabic uses the Arabic percent sign. */
export const formatPercent = (
  value: number | null | undefined,
  locale: Locale,
  fractionDigits = 0
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';

  const number = new Intl.NumberFormat(intlLocale(locale), {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);

  return locale === 'ar' ? `${number}٪` : `${number}%`;
};

/**
 * `2 hours ago` / `منذ ساعتين`, for feed and chat timestamps.
 *
 * Uses `Intl.RelativeTimeFormat`, so the wording - including Arabic's dual
 * form, which a hand-written dictionary entry would get wrong - comes from the
 * platform rather than from a translated string with a `{count}` in it. Falls
 * back to the absolute date beyond a week, because "34 days ago" is harder to
 * place than a date.
 */
export const formatRelativeTime = (
  value: string | Date | null | undefined,
  locale: Locale
): string => {
  if (!value) return '—';

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absolute = Math.abs(seconds);

  const formatter = new Intl.RelativeTimeFormat(intlLocale(locale), {
    numeric: 'auto',
  });

  if (absolute < 60) return formatter.format(Math.round(seconds), 'second');
  if (absolute < 3600) return formatter.format(Math.round(seconds / 60), 'minute');
  if (absolute < 86400) return formatter.format(Math.round(seconds / 3600), 'hour');
  if (absolute < 604800) return formatter.format(Math.round(seconds / 86400), 'day');

  return formatDate(date, locale);
};

/**
 * The locale a non-React module should format with.
 *
 * `LocaleProvider` stamps the choice onto `<html lang>`, so reading it back is
 * the one place a plain function (the notification adapters, for instance) can
 * learn the language without being handed the context it cannot subscribe to.
 */
export const documentLocale = (): Locale =>
  typeof document !== 'undefined' &&
  document.documentElement.lang.toLowerCase().startsWith('ar')
    ? 'ar'
    : 'en';
