import React from 'react';
import { Briefcase, Clock, GraduationCap, MapPin, Sparkles, ExternalLink } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { MatchResult, OpportunityRecord, OpportunityType } from '../../types';
import { useT } from '../../i18n';
import { formatDate } from '../../i18n';

/**
 * One opportunity, as a job seeker sees it.
 *
 * Shared by Opportunities, the dashboard and the Career Agent so a listing
 * looks the same wherever it appears. It renders only fields the applicant
 * projection carries - there is nothing here to accidentally print an internal
 * requisition field, because the payload does not contain one.
 */

export const TYPE_META: Record<
  OpportunityType,
  { labelKey: string; variant: 'brand' | 'info' | 'success' | 'neutral'; icon: React.ReactNode }
> = {
  job: {
    labelKey: 'app.opportunities.typeLabel.job',
    variant: 'brand',
    icon: <Briefcase className="w-3.5 h-3.5" />,
  },
  internship: {
    labelKey: 'app.opportunities.typeLabel.internship',
    variant: 'info',
    icon: <GraduationCap className="w-3.5 h-3.5" />,
  },
  training: {
    labelKey: 'app.opportunities.typeLabel.training',
    variant: 'neutral',
    icon: <GraduationCap className="w-3.5 h-3.5" />,
  },
  free_course: {
    labelKey: 'app.opportunities.typeLabel.free_course',
    variant: 'success',
    icon: <Sparkles className="w-3.5 h-3.5" />,
  },
};

/**
 * The match panel.
 *
 * Every appearance of a score carries the words "AI Match / Recommendation"
 * and the disclaimer, because a bare percentage next to a person's name reads
 * as a verdict on them. The backend sends both strings for exactly this
 * reason; neither is written here.
 */
export const MatchPanel: React.FC<{ match: MatchResult; compact?: boolean }> = ({
  match,
  compact = false,
}) => {
  const { t } = useT();

  if (!match.score_available || match.score === null) {
    return (
      <div className="rounded-xl bg-sand-50 border border-stone-200 p-3">
        <p className="text-2xs text-stone-600 leading-relaxed">{match.score_basis}</p>
      </div>
    );
  }

  const tone =
    match.score >= 75 ? 'text-emerald-700' : match.score >= 40 ? 'text-amber-700' : 'text-stone-600';

  return (
    <div className="rounded-xl bg-sand-50 border border-stone-200 p-3 space-y-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-3xs font-extrabold uppercase tracking-wider text-stone-400">
          {match.label}
        </span>
        <span className={`text-base font-black tabular-nums ${tone}`}>{match.score}%</span>
      </div>

      <div className="h-1.5 rounded-full bg-stone-200 overflow-hidden">
        <div
          className="h-full rounded-full bg-brand-500 transition-[width] duration-500"
          style={{ width: `${match.score}%` }}
        />
      </div>

      <p className="text-3xs text-stone-500">{match.score_basis}</p>

      {match.matching_skills.length > 0 && (
        <div>
          <p className="text-3xs font-bold uppercase tracking-wider text-stone-400 mb-1">
            {t('ai.match.matchingSkills')}
          </p>
          <div className="flex flex-wrap gap-1">
            {match.matching_skills.map((skill) => (
              <span
                key={skill}
                className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-3xs font-semibold"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {match.skill_gaps.length > 0 && (
        <div>
          <p className="text-3xs font-bold uppercase tracking-wider text-stone-400 mb-1">
            {t('ai.match.skillGaps')}
          </p>
          <div className="flex flex-wrap gap-1">
            {match.skill_gaps.map((skill) => (
              <span
                key={skill}
                className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 text-3xs font-semibold"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {!compact && (
        <p className="text-3xs text-stone-500 leading-relaxed pt-1 border-t border-stone-200">
          {match.disclaimer}
        </p>
      )}
    </div>
  );
};

export const OpportunityCard: React.FC<{
  opportunity: OpportunityRecord;
  onOpen?: (opportunityId: string) => void;
  showMatch?: boolean;
}> = ({ opportunity, onOpen, showMatch = true }) => {
  const { t, locale } = useT();
  const meta = TYPE_META[opportunity.opportunity_type];

  return (
    <Card variant="hover" padding="md" className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-stone-900 tracking-tight break-words">
            {opportunity.title}
          </h3>
          <p className="text-2xs text-stone-500 mt-0.5">
            {opportunity.organization}
            {opportunity.department_name ? ` • ${opportunity.department_name}` : ''}
          </p>
        </div>
        <Badge variant={meta.variant} size="sm">
          {t(meta.labelKey)}
        </Badge>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-stone-500">
        {opportunity.location && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5" /> {opportunity.location}
          </span>
        )}
        {opportunity.employment_type_label && (
          <span className="inline-flex items-center gap-1">
            <Briefcase className="w-3.5 h-3.5" /> {opportunity.employment_type_label}
          </span>
        )}
        {typeof opportunity.duration_hours === 'number' && (
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />{' '}
            {t('unit.hours', { count: opportunity.duration_hours })}
          </span>
        )}
        {opportunity.deadline && (
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />{' '}
            {t('app.opportunities.deadline', {
              date: formatDate(opportunity.deadline, locale),
            })}
          </span>
        )}
      </div>

      {opportunity.description && (
        <p className="text-xs text-stone-600 leading-relaxed line-clamp-3">
          {opportunity.description}
        </p>
      )}

      {opportunity.skills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {opportunity.skills.slice(0, 6).map((skill) => (
            <span
              key={skill}
              className="px-2 py-0.5 rounded-md bg-sand-100 border border-sand-300 text-stone-700 text-3xs font-semibold"
            >
              {skill}
            </span>
          ))}
        </div>
      )}

      {showMatch && opportunity.match && <MatchPanel match={opportunity.match} compact />}

      <div className="flex items-center gap-2 pt-1 mt-auto">
        {onOpen && (
          <Button size="sm" variant="outline" onClick={() => onOpen(opportunity.opportunity_id)}>
            {t('app.opportunities.viewDetails')}
          </Button>
        )}
        {!opportunity.can_apply && opportunity.external_url && (
          <a
            href={opportunity.external_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 text-2xs font-semibold text-brand-700 hover:text-brand-800"
          >
            {t('app.opportunities.goToProvider')} <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>
    </Card>
  );
};
