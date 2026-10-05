import React from 'react';
import { UserRole, UserStatus, WorkMode, AuditActionType } from '../../types';
import { useT } from '../../i18n';

/**
 * Badges carry meaning, not decoration.
 *
 *   brand (a.k.a. `purple`, kept as an alias)  - identity / category
 *   success | warning | danger | info          - state, and only state
 *   neutral | outline | default                - quiet metadata
 *
 * Every variant is a tint + a matching border + text dark enough to read at
 * 11px, which is the size these render at inside tables.
 */
export interface BadgeProps {
  children?: React.ReactNode;
  variant?:
    | 'default'
    | 'brand'
    | 'emerald'
    | 'purple'
    | 'success'
    | 'warning'
    | 'danger'
    | 'info'
    | 'neutral'
    | 'outline'
    | 'coral';
  size?: 'sm' | 'md';
  dot?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

const SIZES: Record<NonNullable<BadgeProps['size']>, string> = {
  sm: 'text-3xs px-1.5 py-0.5 rounded-md',
  md: 'text-2xs px-2 py-0.5 rounded-md',
};

const VARIANTS: Record<NonNullable<BadgeProps['variant']>, string> = {
  default: 'bg-stone-100 text-stone-700 border-stone-200',
  brand: 'bg-brand-50 text-brand-700 border-brand-200',
  purple: 'bg-brand-50 text-brand-700 border-brand-200',
  emerald: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  warning: 'bg-amber-50 text-amber-800 border-amber-200',
  danger: 'bg-red-50 text-red-700 border-red-200',
  coral: 'bg-red-50 text-red-700 border-red-200',
  info: 'bg-sky-50 text-sky-800 border-sky-200',
  neutral: 'bg-stone-50 text-stone-600 border-stone-200',
  outline: 'bg-white text-stone-700 border-stone-300',
};

const DOTS: Record<NonNullable<BadgeProps['variant']>, string> = {
  default: 'bg-stone-400',
  brand: 'bg-brand-600',
  purple: 'bg-brand-600',
  emerald: 'bg-emerald-600',
  success: 'bg-emerald-600',
  warning: 'bg-amber-500',
  danger: 'bg-red-500',
  coral: 'bg-red-500',
  info: 'bg-sky-500',
  neutral: 'bg-stone-400',
  outline: 'bg-stone-400',
};

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'md',
  dot = false,
  icon,
  className = '',
}) => (
  <span
    className={`inline-flex items-center gap-1.5 whitespace-nowrap border font-semibold tracking-tight ${SIZES[size]} ${VARIANTS[variant]} ${className}`}
  >
    {dot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOTS[variant]}`} aria-hidden="true" />}
    {icon && <span className="shrink-0" aria-hidden="true">{icon}</span>}
    {children}
  </span>
);

/**
 * A bare status dot + label, for dense rows where a full badge is too heavy.
 */
export const StatusDot: React.FC<{
  tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand';
  label: React.ReactNode;
  pulse?: boolean;
}> = ({ tone = 'neutral', label, pulse = false }) => (
  <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-700">
    <span
      className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOTS[tone]} ${pulse ? 'animate-pulse' : ''}`}
      aria-hidden="true"
    />
    {label}
  </span>
);

export const RoleBadge: React.FC<{ role: UserRole }> = ({ role }) => {
  const { t } = useT();
  switch (role) {
    case 'Admin':
      return <Badge variant="brand" dot>{t('role.1')}</Badge>;
    case 'HR':
      return <Badge variant="info" dot>{t('role.2')}</Badge>;
    case 'Manager':
      return <Badge variant="emerald" dot>{t('role.3')}</Badge>;
    case 'Employee':
    default:
      return <Badge variant="neutral" dot>{t('role.4')}</Badge>;
  }
};

export const StatusBadge: React.FC<{
  status: UserStatus | 'Active' | 'Restructuring' | 'Draft' | 'Archived';
}> = ({ status }) => {
  const { t } = useT();
  const label = t(`badge.status.${status}`);
  switch (status) {
    case 'Active':
      return <Badge variant="success" dot>{label}</Badge>;
    case 'Inactive':
      return <Badge variant="neutral" dot>{label}</Badge>;
    case 'Pending':
      return <Badge variant="warning" dot>{label}</Badge>;
    case 'Suspended':
      return <Badge variant="danger" dot>{label}</Badge>;
    case 'Restructuring':
      return <Badge variant="warning" dot>{label}</Badge>;
    case 'Draft':
      return <Badge variant="neutral" dot>{label}</Badge>;
    case 'Archived':
      return <Badge variant="neutral" dot>{label}</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
};

export const WorkModeBadge: React.FC<{ mode: WorkMode }> = ({ mode }) => {
  const { t } = useT();
  switch (mode) {
    case 'Remote':
      return <Badge variant="info">{t('badge.workMode.remote')}</Badge>;
    case 'Hybrid':
      return <Badge variant="brand">{t('badge.workMode.hybrid')}</Badge>;
    case 'Onsite':
      return <Badge variant="success">{t('badge.workMode.onsite')}</Badge>;
    default:
      return <Badge>{mode}</Badge>;
  }
};

/**
 * Audit actions. The colour says how consequential the action was, so a
 * security reviewer can scan the column rather than read it.
 */
export const ActionTypeBadge: React.FC<{ type: AuditActionType }> = ({ type }) => {
  const { t } = useT();
  const label = t(`badge.action.${type}`);
  switch (type) {
    case 'CREATE':
      return <Badge variant="success" size="sm">{label}</Badge>;
    case 'UPDATE':
      return <Badge variant="info" size="sm">{label}</Badge>;
    case 'DELETE':
      return <Badge variant="danger" size="sm">{label}</Badge>;
    case 'APPROVE':
      return <Badge variant="success" size="sm">{label}</Badge>;
    case 'SECURITY':
      return <Badge variant="warning" size="sm">{label}</Badge>;
    case 'EXPORT':
      return <Badge variant="brand" size="sm">{label}</Badge>;
    case 'LOGIN':
    default:
      return <Badge variant="neutral" size="sm">{label}</Badge>;
  }
};
