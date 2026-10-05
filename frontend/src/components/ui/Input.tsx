import React from 'react';
import { Search, X, ChevronDown } from 'lucide-react';
import { useT } from '../../i18n';

/**
 * Form controls.
 *
 * One shared shell so every input on every page is the same height, radius,
 * border and focus treatment. Labels are real <label for> elements, required
 * fields are marked in text as well as colour, and errors are wired up with
 * aria-invalid / aria-describedby rather than being colour-only.
 */

const FIELD_BASE =
  'block w-full rounded-lg border bg-white text-sm text-stone-900 transition-colors ' +
  'placeholder:text-stone-400 focus:outline-none focus:ring-2 disabled:bg-sand-100 ' +
  'disabled:text-stone-500 disabled:cursor-not-allowed';

const FIELD_TONE = (hasError: boolean) =>
  hasError
    ? 'border-red-300 focus:border-red-500 focus:ring-red-100'
    : 'border-stone-200 hover:border-stone-300 focus:border-brand-500 focus:ring-brand-100';

const slug = (label?: string) =>
  label ? label.toLowerCase().replace(/[^a-z0-9]+/g, '-') : undefined;

const Label: React.FC<{ htmlFor?: string; children: React.ReactNode; required?: boolean }> = ({
  htmlFor,
  children,
  required,
}) => {
  const { t } = useT();
  return (
  <label
    htmlFor={htmlFor}
    className="block text-2xs font-bold uppercase tracking-wider text-stone-500 mb-1.5"
  >
    {children}
    {required && (
      <span className="text-red-600 ms-1" title={t('ui.form.required')}>
        *
      </span>
    )}
  </label>
  );
};

const HelpText: React.FC<{ id?: string; error?: string; helperText?: string }> = ({
  id,
  error,
  helperText,
}) => {
  if (error) {
    return (
      <p id={id} role="alert" className="mt-1.5 text-2xs font-semibold text-red-600">
        {error}
      </p>
    );
  }
  if (helperText) {
    return (
      <p id={id} className="mt-1.5 text-2xs text-stone-500 leading-relaxed">
        {helperText}
      </p>
    );
  }
  return null;
};

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  helperText,
  error,
  leftIcon,
  rightIcon,
  id,
  className = '',
  ...props
}) => {
  const inputId = id || slug(label);
  const describedBy = inputId ? inputId + '-help' : undefined;

  return (
    <div className="w-full">
      {label && (
        <Label htmlFor={inputId} required={props.required}>
          {label}
        </Label>
      )}
      <div className="relative">
        {leftIcon && (
          <div className="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3 text-stone-400">
            {leftIcon}
          </div>
        )}
        <input
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || helperText ? describedBy : undefined}
          className={`${FIELD_BASE} ${FIELD_TONE(!!error)} h-10 px-3 ${leftIcon ? 'ps-9' : ''} ${
            rightIcon ? 'pe-9' : ''
          } ${className}`}
          {...props}
        />
        {rightIcon && (
          <div className="absolute inset-y-0 end-0 flex items-center pe-3 text-stone-400">
            {rightIcon}
          </div>
        )}
      </div>
      <HelpText id={describedBy} error={error} helperText={helperText} />
    </div>
  );
};

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  helperText?: string;
  error?: string;
  options?: { label: string; value: string | number }[];
}

export const Select: React.FC<SelectProps> = ({
  label,
  helperText,
  error,
  options,
  id,
  className = '',
  children,
  ...props
}) => {
  const selectId = id || slug(label);
  const describedBy = selectId ? selectId + '-help' : undefined;

  return (
    <div className="w-full">
      {label && (
        <Label htmlFor={selectId} required={props.required}>
          {label}
        </Label>
      )}
      <div className="relative">
        <select
          id={selectId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || helperText ? describedBy : undefined}
          className={`${FIELD_BASE} ${FIELD_TONE(!!error)} h-10 ps-3 pe-9 appearance-none cursor-pointer ${className}`}
          {...props}
        >
          {children
            ? children
            : options?.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400"
          aria-hidden="true"
        />
      </div>
      <HelpText id={describedBy} error={error} helperText={helperText} />
    </div>
  );
};

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  helperText,
  error,
  id,
  className = '',
  ...props
}) => {
  const textareaId = id || slug(label);
  const describedBy = textareaId ? textareaId + '-help' : undefined;

  return (
    <div className="w-full">
      {label && (
        <Label htmlFor={textareaId} required={props.required}>
          {label}
        </Label>
      )}
      <textarea
        id={textareaId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error || helperText ? describedBy : undefined}
        className={`${FIELD_BASE} ${FIELD_TONE(!!error)} px-3 py-2.5 leading-relaxed resize-y min-h-[84px] ${className}`}
        {...props}
      />
      <HelpText id={describedBy} error={error} helperText={helperText} />
    </div>
  );
};

/**
 * The standard filter/search box that sits above every table in the app.
 * Shows a clear button once there is something to clear.
 */
export const SearchInput: React.FC<{
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  className?: string;
}> = ({ value, onChange, placeholder, label, className = '' }) => {
  const { t } = useT();
  return (
  <div className={`relative ${className}`}>
    <Search
      className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400"
      aria-hidden="true"
    />
    <input
      type="search"
      value={value}
      aria-label={label ?? t('ui.search.label')}
      placeholder={placeholder ?? t('ui.search.placeholder')}
      onChange={(e) => onChange(e.target.value)}
      className={`${FIELD_BASE} ${FIELD_TONE(false)} h-10 ps-9 pe-9`}
    />
    {value.length > 0 && (
      <button
        type="button"
        onClick={() => onChange('')}
        aria-label={t('ui.search.clear')}
        className="absolute end-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    )}
  </div>
  );
};

export interface ToggleProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export const Toggle: React.FC<ToggleProps> = ({
  label,
  description,
  checked,
  onChange,
  disabled = false,
}) => {
  const id = slug(label);
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-semibold text-stone-900 cursor-pointer select-none">
          {label}
        </label>
        {description && (
          <p className="text-2xs text-stone-500 mt-0.5 leading-relaxed">{description}</p>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed ${
          checked ? 'bg-brand-600' : 'bg-stone-300'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
            checked ? 'translate-x-5' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  );
};
