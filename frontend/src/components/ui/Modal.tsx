import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { useT } from '../../i18n';

/**
 * Dialog shell used by every create / edit / detail panel in SmartHR.
 *
 * Behaviour worth knowing:
 *  - Escape and a backdrop click both close it.
 *  - Focus moves into the dialog on open and returns to the trigger on close,
 *    and Tab is kept inside while it is open.
 *  - On phones it becomes a bottom sheet: full width, rounded at the top only,
 *    so the action footer stays within thumb reach.
 */
export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  icon?: React.ReactNode;
  /** Set for destructive dialogs: tints the header rail red. */
  tone?: 'brand' | 'danger';
}

const SIZES: Record<NonNullable<ModalProps['size']>, string> = {
  sm: 'sm:max-w-md',
  md: 'sm:max-w-lg',
  lg: 'sm:max-w-2xl',
  xl: 'sm:max-w-3xl',
  '2xl': 'sm:max-w-5xl',
};

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  icon,
  tone = 'brand',
}) => {
  const { t } = useT();
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return undefined;

    restoreFocusTo.current = document.activeElement as HTMLElement | null;
    document.body.style.overflow = 'hidden';

    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
    (focusables?.[0] ?? panelRef.current)?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !panelRef.current) return;

      // tsconfig does not enable downlevelIteration, so the NodeList is walked
      // with forEach rather than spread into an array.
      const nodes: HTMLElement[] = [];
      panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE).forEach((el) => {
        if (el.offsetParent !== null) nodes.push(el);
      });
      if (nodes.length === 0) return;

      const firstNode = nodes[0];
      const lastNode = nodes[nodes.length - 1];

      if (e.shiftKey && document.activeElement === firstNode) {
        e.preventDefault();
        lastNode.focus();
      } else if (!e.shiftKey && document.activeElement === lastNode) {
        e.preventDefault();
        firstNode.focus();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      restoreFocusTo.current?.focus?.();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" role="presentation">
      <div
        className="fixed inset-0 bg-stone-900/40 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="flex min-h-full items-end sm:items-center justify-center sm:p-4">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="smarthr-modal-title"
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
          className={`relative w-full ${SIZES[size]} bg-white text-start shadow-pop border border-stone-200
            rounded-t-2xl sm:rounded-2xl overflow-hidden animate-in fade-in zoom-in-95
            max-h-[92vh] sm:max-h-[88vh] flex flex-col focus:outline-none`}
        >
          <div
            className={`h-1 w-full shrink-0 ${tone === 'danger' ? 'bg-red-500' : 'bg-brand-500'}`}
            aria-hidden="true"
          />

          <div className="flex items-start justify-between gap-4 border-b border-stone-100 px-5 sm:px-6 py-4 shrink-0">
            <div className="flex items-start gap-3 min-w-0">
              {icon && (
                <span
                  className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${
                    tone === 'danger'
                      ? 'bg-red-50 border-red-100 text-red-600'
                      : 'bg-brand-50 border-brand-100 text-brand-600'
                  }`}
                >
                  {icon}
                </span>
              )}
              <div className="min-w-0">
                <h3
                  id="smarthr-modal-title"
                  className="text-base font-extrabold text-stone-900 tracking-tight"
                >
                  {title}
                </h3>
                {subtitle && (
                  <p className="text-2xs text-stone-500 mt-0.5 leading-relaxed">{subtitle}</p>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label={t('ui.modal.close')}
              className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition-colors shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="px-5 sm:px-6 py-5 overflow-y-auto grow">{children}</div>

          {footer && (
            <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center sm:justify-end gap-2.5 border-t border-stone-100 bg-sand-50 px-5 sm:px-6 py-4 shrink-0">
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * Two-column responsive grid for modal forms. Collapses to one column on
 * phones so no field is ever squeezed below a usable width.
 */
export const FormGrid: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 ${className}`}>{children}</div>;

/** Spans the full width of a FormGrid. */
export const FormRow: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <div className={`sm:col-span-2 ${className}`}>{children}</div>;
