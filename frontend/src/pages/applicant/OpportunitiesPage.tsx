import React, { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, Compass, ExternalLink, Send } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, Field } from '../../components/ui/Card';
import { SearchInput } from '../../components/ui/Input';
import { PageHeader } from '../../components/ui/PageHeader';
import { Tabs } from '../../components/ui/Tabs';
import { ErrorState, InfoPanel, InlineEmpty, LoadingState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import { formatDate, useT } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import {
  OpportunityDetailResponse,
  OpportunityListResponse,
  OpportunityType,
} from '../../types';
import { MatchPanel, OpportunityCard } from './OpportunityCard';

/* Tab labels are `app.opportunities.tab.all` and
 * `app.opportunities.type.<type>`, resolved at render time. */
const TABS: { id: string; labelKey: string }[] = [
  { id: 'all', labelKey: 'app.opportunities.tab.all' },
  { id: 'job', labelKey: 'app.opportunities.type.job' },
  { id: 'internship', labelKey: 'app.opportunities.type.internship' },
  { id: 'training', labelKey: 'app.opportunities.type.training' },
  { id: 'free_course', labelKey: 'app.opportunities.type.free_course' },
];

/**
 * Browse and apply.
 *
 * Two views in one page: the list, and one opportunity's detail. The detail
 * view is where applying happens, and it deliberately requires a deliberate
 * click on a named opportunity - there is no "apply to all" and no apply
 * button on a list card.
 */
export const OpportunitiesPage: React.FC<{
  selectedOpportunityId?: string;
  onSelectOpportunity: (opportunityId: string | undefined) => void;
  onNavigate: (page: PageId) => void;
}> = ({ selectedOpportunityId, onSelectOpportunity, onNavigate }) => {
  const { t, locale } = useT();
  const [data, setData] = useState<OpportunityListResponse | null>(null);
  const [detail, setDetail] = useState<OpportunityDetailResponse | null>(null);
  const [tab, setTab] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { showToast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await SmartHRApi.getOpportunities({
          search: search.trim() || undefined,
          opportunity_type: tab === 'all' ? undefined : (tab as OpportunityType),
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t('app.opps.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [search, tab]);

  useEffect(() => {
    if (!selectedOpportunityId) load();
  }, [load, selectedOpportunityId]);

  const loadDetail = useCallback(async (opportunityId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await SmartHRApi.getOpportunity(opportunityId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('app.opps.loadOneFailed'));
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOpportunityId) loadDetail(selectedOpportunityId);
    else setDetail(null);
  }, [selectedOpportunityId, loadDetail]);

  const handleApply = async () => {
    if (!detail || detail.opportunity.source !== 'job') return;

    setApplying(true);
    try {
      const result = await SmartHRApi.applyToOpportunity(detail.opportunity.id);
      showToast(t('app.opps.submitted'), {
        message: `${detail.opportunity.title} — you can follow it on My Applications.`,
        type: 'success',
      });
      result.warnings.forEach((warning) =>
        showToast(t('app.opps.worthKnowing'), { message: warning, type: 'info' })
      );
      await loadDetail(detail.opportunity.opportunity_id);
    } catch (err) {
      showToast(t('app.opps.applyFailed'), {
        message: err instanceof Error ? err.message : t('app.opps.tryAgain'),
        type: 'error',
      });
    } finally {
      setApplying(false);
    }
  };

  /* ---------------- detail view ---------------- */

  if (selectedOpportunityId) {
    if (detailLoading) return <LoadingState title={t('app.opportunities.loadingOne')} />;
    if (error || !detail)
      return (
        <ErrorState
          message={error ?? t('app.opportunities.notFound')}
          onRetry={() => loadDetail(selectedOpportunityId)}
        />
      );

    const { opportunity, match, my_application: mine, has_cv: hasCv } = detail;

    return (
      <div className="space-y-6">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<ArrowLeft className="w-4 h-4" data-flip-rtl />}
          onClick={() => onSelectOpportunity(undefined)}
        >
          {t('app.opportunities.backToList')}
        </Button>

        <PageHeader
          title={opportunity.title}
          subtitle={`${opportunity.organization}${
            opportunity.department_name ? ` • ${opportunity.department_name}` : ''
          }`}
          icon={<Compass className="w-5 h-5" />}
          badge={
            <Badge variant="brand">
              {t(`app.opportunities.typeLabel.${opportunity.opportunity_type}`)}
            </Badge>
          }
          actions={
            opportunity.can_apply ? (
              mine ? (
                <Badge variant={mine.is_successful ? 'success' : 'info'}>
                  {t('app.opportunities.appliedStatus', { status: mine.status_label })}
                </Badge>
              ) : (
                <Button
                  variant="primary"
                  leftIcon={<Send className="w-4 h-4" />}
                  onClick={handleApply}
                  isLoading={applying}
                  disabled={!hasCv || opportunity.is_expired}
                >
                  {t('app.opportunities.apply')}
                </Button>
              )
            ) : opportunity.external_url ? (
              <a
                href={opportunity.external_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-2 text-xs font-semibold text-brand-700 hover:text-brand-800"
              >
                {t('app.opportunities.goToProvider')} <ExternalLink className="w-4 h-4" />
              </a>
            ) : null
          }
        />

        {opportunity.can_apply && !hasCv && !mine && (
          <InfoPanel title={t('app.opportunities.uploadCvFirst')} tone="warning">
            <p>{t('app.opportunities.cvNeededBody')}</p>
            <Button size="sm" variant="soft" className="mt-3" onClick={() => onNavigate('app-cv')}>
              {t('app.opportunities.goToMyCv')}
            </Button>
          </InfoPanel>
        )}

        {opportunity.is_expired && (
          <InfoPanel title={t('app.opportunities.deadlinePassed')} tone="warning">
            <p>
              {t('app.opportunities.closedOn', {
                date: formatDate(opportunity.deadline, locale),
              })}
            </p>
          </InfoPanel>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card padding="md">
              <CardHeader title={t('app.opportunities.about')} />
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-5">
                {/*
                  Values are database content and are shown as stored - the
                  organisation's name, the location a recruiter typed. Only the
                  labels and the "not stated" fallbacks are translated.
                */}
                <Field
                  label={t('app.opportunities.type')}
                  value={t(`app.opportunities.typeLabel.${opportunity.opportunity_type}`)}
                />
                <Field
                  label={t('app.opportunities.organisation')}
                  value={opportunity.organization}
                />
                {opportunity.employment_type && (
                  <Field
                    label={t('app.opportunities.employment')}
                    value={t(`employment.${opportunity.employment_type}`)}
                  />
                )}
                <Field
                  label={t('app.opportunities.location')}
                  value={opportunity.location ?? t('app.opportunities.notStated')}
                />
                <Field
                  label={t('app.opportunities.deadlineLabel')}
                  value={
                    opportunity.deadline
                      ? formatDate(opportunity.deadline, locale)
                      : t('app.opportunities.noDeadline')
                  }
                />
                {typeof opportunity.duration_hours === 'number' && (
                  <Field
                    label={t('app.opportunities.duration')}
                    value={t('unit.hours', { count: opportunity.duration_hours })}
                  />
                )}
              </dl>

              <p className="text-sm text-stone-700 leading-relaxed whitespace-pre-line">
                {opportunity.description || t('app.opportunities.noDescription')}
              </p>
            </Card>

            <Card padding="md">
              <CardHeader
                title={t('app.opportunities.requirements')}
                subtitle={t('app.opportunities.requirementsExact')}
              />
              {opportunity.skills.length === 0 ? (
                <InlineEmpty
                  title={t('app.opportunities.noRequirements')}
                  description={t('app.opportunities.noRequirementsHint')}
                  icon={<AlertCircle className="w-5 h-5" />}
                />
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {opportunity.skills.map((skill) => (
                    <li
                      key={skill}
                      className="px-2.5 py-1 rounded-lg bg-sand-100 border border-sand-300 text-stone-800 text-xs font-semibold"
                    >
                      {skill}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card padding="md">
              <CardHeader title={t('app.opportunities.howToApply')} />
              <p className="text-sm text-stone-700 leading-relaxed">{opportunity.how_to_apply}</p>
            </Card>
          </div>

          <div className="space-y-6">
            <Card padding="md">
              <CardHeader
                title={t('ai.match.label')}
                subtitle={t('app.opportunities.matchSubtitle')}
              />
              <MatchPanel match={match} />
            </Card>
          </div>
        </div>
      </div>
    );
  }

  /* ---------------- list view ---------------- */

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('app.opportunities.title')}
        subtitle={t('app.opportunities.subtitle')}
        icon={<Compass className="w-5 h-5" />}
        toolbar={
          <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
            <Tabs
              tabs={TABS.map((item) => ({
                id: item.id,
                label: t(item.labelKey),
                count:
                  item.id === 'all'
                    ? data?.count
                    : data?.counts_by_type?.[item.id as OpportunityType],
              }))}
              activeTab={tab}
              onTabChange={setTab}
            />
            <div className="sm:ms-auto sm:w-72">
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder={t('app.opportunities.searchLabel')}
              />
            </div>
          </div>
        }
      />

      {loading ? (
        <LoadingState title={t('app.opportunities.loadingList')} />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !data || data.opportunities.length === 0 ? (
        <InlineEmpty
          title={t('app.opportunities.nothingMatches')}
          description={
            search
              ? t('app.opportunities.noneMatchingSearch', { search })
              : t('app.opportunities.noneOfThisKind')
          }
          icon={<Compass className="w-5 h-5" />}
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {data.opportunities.map((opportunity) => (
            <OpportunityCard
              key={opportunity.opportunity_id}
              opportunity={opportunity}
              onOpen={onSelectOpportunity}
              showMatch={false}
            />
          ))}
        </div>
      )}
    </div>
  );
};
