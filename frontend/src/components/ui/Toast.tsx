import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';
import { useT } from '../../i18n';

/**
 * Toasts. One provider wraps the whole app; `useToast().showToast` is the
 * standard way any page reports the outcome of a write.
 *
 * The stack is an aria-live region so the outcome is announced, not just seen,
 * and each toast carries a coloured rail plus an icon so the type does not
 * depend on colour alone.
 */
export type ToastType = 'success' | 'warning' | 'error' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastContextValue {
  showToast: (
    title: string,
    options?: { message?: string; type?: ToastType; durationMs?: number }
  ) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONES: Record<ToastType, { rail: string; icon: React.ReactNode }> = {
  success: {
    rail: 'bg-emerald-500',
    icon: <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" aria-hidden="true" />,
  },
  warning: {
    rail: 'bg-amber-500',
    icon: <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" aria-hidden="true" />,
  },
  error: {
    rail: 'bg-red-500',
    icon: <AlertCircle className="w-4 h-4 text-red-600 shrink-0" aria-hidden="true" />,
  },
  info: {
    rail: 'bg-brand-500',
    icon: <Info className="w-4 h-4 text-brand-600 shrink-0" aria-hidden="true" />,
  },
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { t } = useT();
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (title: string, options?: { message?: string; type?: ToastType; durationMs?: number }) => {
      const id = Math.random().toString(36).substring(2, 9);
      setToasts((prev) => [
        ...prev,
        { id, title, message: options?.message, type: options?.type || 'success' },
      ]);

      const duration = options?.durationMs ?? 4000;
      setTimeout(() => removeToast(id), duration);
    },
    [removeToast]
  );

  return (
    <ToastContext.Provider value={{ showToast, removeToast }}>
      {children}

      <div
        role="status"
        aria-live="polite"
        className="fixed bottom-4 end-4 start-4 sm:start-auto z-[60] flex flex-col gap-2 sm:max-w-sm pointer-events-none"
      >
        {toasts.map((toast) => {
          const tone = TONES[toast.type];
          return (
            <div
              key={toast.id}
              className="pointer-events-auto flex items-stretch rounded-xl border border-stone-200 bg-white shadow-pop overflow-hidden animate-in fade-in slide-in-from-bottom-3"
            >
              <span className={`w-1 shrink-0 ${tone.rail}`} aria-hidden="true" />
              <div className="flex items-start gap-3 p-3.5 flex-1 min-w-0">
                <span className="mt-0.5">{tone.icon}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-stone-900 leading-tight">{toast.title}</p>
                  {toast.message && (
                    <p className="text-2xs text-stone-500 mt-1 leading-relaxed">{toast.message}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeToast(toast.id)}
                  aria-label={t('ui.toast.dismiss')}
                  className="text-stone-400 hover:text-stone-700 p-0.5 rounded transition-colors shrink-0"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
