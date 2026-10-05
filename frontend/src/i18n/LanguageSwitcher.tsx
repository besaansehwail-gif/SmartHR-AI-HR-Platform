import React, { useEffect, useRef, useState } from 'react';
import { Check, Globe } from 'lucide-react';

import { useT } from './LocaleProvider';
import { LOCALES, LOCALE_META, Locale } from './types';

/**
 * The global language switcher.
 *
 * Mounted once, in the top bar of `GlobalLayout`, and again on the two
 * signed-out screens. There is deliberately no per-page copy: the locale lives
 * in one provider above the whole tree, so any instance sets it for everything.
 *
 * Each language is written **in its own script** - "English" and "العربية" -
 * because somebody who cannot read the current language still has to find
 * their own. That is why this is not a "Language: English / Arabic" label.
 */

interface LanguageSwitcherProps {
  /** `compact` is the icon-only button used in the dense top bar. */
  variant?: 'compact' | 'full';
  className?: string;
}

export const LanguageSwitcher: React.FC<LanguageSwitcherProps> = ({
  variant = 'compact',
  className = '',
}) => {
  const { locale, setLocale, t } = useT();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape - the same behaviour as the other
  // dropdowns in the top bar.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const choose = (next: Locale) => {
    setLocale(next);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('language.change')}
        title={t('language.change')}
        className={
          variant === 'compact'
            ? 'w-9 h-9 rounded-lg border border-stone-200 bg-white text-stone-600 hover:text-brand-700 hover:border-brand-200 hover:bg-brand-50/60 flex items-center justify-center transition-colors'
            : 'h-9 px-3 rounded-lg border border-stone-200 bg-white text-stone-700 hover:border-brand-200 hover:bg-brand-50/60 inline-flex items-center gap-2 text-xs font-semibold transition-colors'
        }
      >
        <Globe className="w-4 h-4" aria-hidden="true" />
        {variant === 'full' && <span>{LOCALE_META[locale].nativeName}</span>}
      </button>

      {open && (
        <div
          role="menu"
          /*
           * `end-0` rather than `right-0`: a logical inset, so the menu hangs
           * off the trailing edge of its button in both directions instead of
           * escaping the viewport in Arabic.
           */
          className="absolute end-0 mt-2 w-44 rounded-xl border border-stone-200 bg-white shadow-pop py-1.5 z-50 animate-in fade-in slide-in-from-top-2"
        >
          <p className="px-3 pb-1.5 text-3xs font-bold uppercase tracking-wider text-stone-400">
            {t('language.label')}
          </p>

          {LOCALES.map((code) => {
            const meta = LOCALE_META[code];
            const selected = code === locale;

            return (
              <button
                key={code}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => choose(code)}
                /*
                 * Each option renders in its own direction, so the Arabic row
                 * reads right-to-left even while the app is still in English.
                 * Without this the native name sits on the wrong side of its
                 * own row and looks like a rendering bug.
                 */
                dir={meta.dir}
                lang={meta.code}
                className={`w-full px-3 py-2 flex items-center gap-2 text-xs text-start transition-colors ${
                  selected
                    ? 'text-brand-700 font-bold bg-brand-50/70'
                    : 'text-stone-700 hover:bg-sand-100'
                }`}
              >
                <span className="flex-1 min-w-0 truncate">{meta.nativeName}</span>
                {selected && <Check className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
