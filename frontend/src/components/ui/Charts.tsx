import React from 'react';
import { Laptop, Building2, Home } from 'lucide-react';
import { chartColor } from '../../services/chartPalette';
import { useT } from '../../i18n';

/**
 * Lightweight charts drawn with CSS rather than a charting dependency.
 *
 * Every one of these renders values the page received from the API. When a
 * caller does not pass a colour, the Amber Sand ramp supplies one by index -
 * colour is chosen here, the numbers never are.
 *
 * Each chart is also readable without its colours: the label and the value are
 * always written out next to the bar.
 */

export const EmployeeDistributionChart: React.FC<{
  data: { department: string; count: number; percentage: number; color?: string }[];
}> = ({ data }) => {
  const { t } = useT();
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  if (data.length === 0) {
    return (
      <p className="text-2xs text-stone-500 py-6 text-center">
        {t('ui.chart.noDepartments')}
      </p>
    );
  }

  return (
    <ul className="space-y-3.5">
      {data.map((item, idx) => {
        const color = item.color || chartColor(idx);
        return (
          <li key={item.department} className="space-y-1.5">
            <div className="flex items-center justify-between gap-3 text-2xs">
              <span className="font-bold text-stone-700 flex items-center gap-2 min-w-0">
                <span
                  className="w-2.5 h-2.5 rounded-sm shrink-0"
                  style={{ backgroundColor: color }}
                  aria-hidden="true"
                />
                <span className="truncate">{item.department}</span>
              </span>
              <span className="flex items-baseline gap-1.5 shrink-0 tabular-nums">
                <span className="font-extrabold text-stone-900">{item.count}</span>
                <span className="text-stone-400 font-semibold">{item.percentage}%</span>
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-sand-100 overflow-hidden">
              <div
                className="h-full rounded-full transition-[width] duration-500 ease-out"
                style={{ width: `${(item.count / maxCount) * 100}%`, backgroundColor: color }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
};

export const RecruitmentFunnelChart: React.FC<{
  stages: { stage: string; count: number; rate: string; color?: string }[];
}> = ({ stages }) => {
  const { t } = useT();
  const maxCount = stages[0]?.count || 1;

  if (stages.length === 0) {
    return (
      <p className="text-2xs text-stone-500 py-6 text-center">{t('ui.chart.noPipeline')}</p>
    );
  }

  return (
    <ul className="space-y-2">
      {stages.map((stage, idx) => {
        const color = stage.color || chartColor(idx);
        const widthPercent = Math.max((stage.count / maxCount) * 100, 8);
        return (
          <li key={stage.stage} className="flex items-center gap-3">
            <span className="w-20 sm:w-24 text-2xs font-bold text-stone-600 truncate text-end shrink-0">
              {stage.stage}
            </span>
            <div className="flex-1 bg-sand-100 rounded-lg h-7 flex items-center overflow-hidden min-w-0">
              <div
                className="h-full rounded-lg flex items-center px-2.5 text-2xs font-extrabold text-white tabular-nums transition-[width] duration-500"
                style={{ width: `${widthPercent}%`, backgroundColor: color }}
              >
                {stage.count}
              </div>
            </div>
            <span className="w-11 text-3xs font-bold text-stone-500 text-end shrink-0 tabular-nums">
              {stage.rate}
            </span>
          </li>
        );
      })}
    </ul>
  );
};

/**
 * Generic horizontal bar list - the shape most report sections need. Kept
 * here so pages stop hand-rolling their own bar markup.
 */
export const BarList: React.FC<{
  items: { label: string; value: number; caption?: string; color?: string }[];
  valueSuffix?: string;
  emptyMessage?: string;
}> = ({ items, valueSuffix = '', emptyMessage }) => {
  const { t } = useT();
  const max = Math.max(...items.map((i) => i.value), 1);

  if (items.length === 0) {
    return (
      <p className="text-2xs text-stone-500 py-6 text-center">
        {emptyMessage ?? t('ui.chart.nothingYet')}
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {items.map((item, idx) => {
        const color = item.color || chartColor(idx);
        return (
          <li key={item.label} className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-3 text-2xs">
              <span className="font-bold text-stone-700 truncate">{item.label}</span>
              <span className="font-extrabold text-stone-900 tabular-nums shrink-0">
                {item.value}
                {valueSuffix}
                {item.caption && (
                  <span className="ms-1.5 font-semibold text-stone-400">{item.caption}</span>
                )}
              </span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-sand-100 overflow-hidden">
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{ width: `${(item.value / max) * 100}%`, backgroundColor: color }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
};

/** Single labelled progress bar. */
export const ProgressBar: React.FC<{
  value: number;
  max?: number;
  tone?: 'brand' | 'success' | 'warning' | 'danger';
  className?: string;
  label?: string;
}> = ({ value, max = 100, tone = 'brand', className = '', label }) => {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const tones = {
    brand: 'bg-brand-500',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-red-500',
  } as const;

  return (
    <div
      className={`w-full h-2 rounded-full bg-sand-100 overflow-hidden ${className}`}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${tones[tone]}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
};

/**
 * Work-mode split.
 *
 * The employees table has no work-mode, location or workplace column, so the
 * dashboard endpoints report `work_mode_available: false` and the pages that
 * used to show this now show attendance instead. The component is kept for the
 * case where a caller genuinely has the three counts to plot.
 */
export const WorkModeOverview: React.FC<{
  breakdown: {
    remote: { count: number; percentage: number };
    hybrid: { count: number; percentage: number };
    onsite: { count: number; percentage: number };
  };
}> = ({ breakdown }) => {
  const { t } = useT();
  return (
  <div className="space-y-4">
    <div className="h-3 w-full rounded-full bg-sand-100 flex overflow-hidden">
      <div
        className="bg-sky-500 transition-[width] duration-500"
        style={{ width: `${breakdown.remote.percentage}%` }}
        title={`${t('badge.workMode.remote')}: ${breakdown.remote.percentage}%`}
      />
      <div
        className="bg-brand-500 transition-[width] duration-500"
        style={{ width: `${breakdown.hybrid.percentage}%` }}
        title={`${t('badge.workMode.hybrid')}: ${breakdown.hybrid.percentage}%`}
      />
      <div
        className="bg-emerald-500 transition-[width] duration-500"
        style={{ width: `${breakdown.onsite.percentage}%` }}
        title={`${t('badge.workMode.onsite')}: ${breakdown.onsite.percentage}%`}
      />
    </div>

    <div className="grid grid-cols-3 gap-2">
      {[
        { icon: <Laptop className="w-4 h-4" />, label: t('badge.workMode.remote'), tone: 'text-sky-600', data: breakdown.remote },
        { icon: <Home className="w-4 h-4" />, label: t('badge.workMode.hybrid'), tone: 'text-brand-600', data: breakdown.hybrid },
        { icon: <Building2 className="w-4 h-4" />, label: t('badge.workMode.onsite'), tone: 'text-emerald-600', data: breakdown.onsite },
      ].map((entry) => (
        <div
          key={entry.label}
          className="p-3 bg-sand-50 rounded-xl border border-sand-200 text-center"
        >
          <div className={`flex items-center justify-center mb-1 ${entry.tone}`} aria-hidden="true">
            {entry.icon}
          </div>
          <p className="text-base font-extrabold text-stone-900 tabular-nums">
            {entry.data.percentage}%
          </p>
          <p className="text-3xs font-semibold text-stone-500">
            {entry.label} ({entry.data.count})
          </p>
        </div>
      ))}
    </div>
  </div>
  );
};
