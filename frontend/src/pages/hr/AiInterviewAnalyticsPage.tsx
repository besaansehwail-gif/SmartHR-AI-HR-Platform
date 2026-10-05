import React, { useCallback, useEffect, useState } from 'react';
import {
  BarChart3,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  Clock,
  FileText,
  GitBranch,
  Hourglass,
  Layers,
  ListOrdered,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { KpiCard } from '../../components/ui/KpiCard';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState, InfoPanel, LoadingState } from '../../components/ui/States';
import { SmartHRApi } from '../../services/api';
import { AiInterviewAnalytics } from '../../types';
import { useT } from '../../i18n';

/**
 * AI Interview Analytics (Phase 11.5.4) - HR workspace, Admin and HR only.
 *
 *   GET /ai-interview/analytics  -> counts over recorded AI Interview activity
 *
 * Descriptive only: every figure is a count of recorded sessions, answers and
 * analyses (or the highest question number reached). Nothing here is a score,
 * a ranking or a hiring decision, and the page says so above the figures.
 * Zero is a valid answer - a fresh system shows zeros, not an error.
 *
 * "Not reached" and order comparability are measured against TODAY's
 * Question Bank: the questions planned for each session were not recorded,
 * so the page never presents today's bank as the original plan.
 */

const ICON = 'w-5 h-5';

const Section: React.FC<{ title: string; note?: string; children: React.ReactNode; testId: string }> = ({
  title,
  note,
  children,
  testId,
}) => (
  <section className="space-y-3" data-testid={testId}>
    <div>
      <h2 className="text-sm font-extrabold text-stone-900">{title}</h2>
      {note && <p className="text-xs text-stone-500 mt-0.5 leading-relaxed">{note}</p>}
    </div>
    {children}
  </section>
);

export const AiInterviewAnalyticsPage: React.FC = () => {
  const { t } = useT();
  const [data, setData] = useState<AiInterviewAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setData(await SmartHRApi.getAiInterviewAnalytics());
    } catch (err) {
      setError(err instanceof Error ? err.message : t('hr.aiAnalytics.loadFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const header = (
    <PageHeader
      title={t('hr.aiAnalytics.title')}
      subtitle={t('hr.aiAnalytics.subtitle')}
      icon={<BarChart3 className="w-5 h-5" />}
      actions={
        <Button
          variant="outline"
          size="sm"
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          isLoading={isLoading && data !== null}
          onClick={() => void load()}
        >
          {t('hr.aiAnalytics.refresh')}
        </Button>
      }
    />
  );

  const notice = (
    <InfoPanel tone="brand" icon={<ShieldCheck className="w-5 h-5" />} title={t('hr.aiAnalytics.noticeTitle')}>
      <p>{t('hr.aiAnalytics.noticeBody')}</p>
    </InfoPanel>
  );

  if (isLoading && !data) {
    return (
      <div className="space-y-6">
        {header}
        <LoadingState title={t('hr.aiAnalytics.loading')} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState title={t('hr.aiAnalytics.loadFailed')} message={error} onRetry={() => void load()} />
      </div>
    );
  }

  if (!data) return null;

  const { overview, activity, analysis, context, question_flow: flow } = data;
  // Zero is a valid state, not an error: say so, and still show the zeros.
  const nothingYet = overview.total_interviews === 0 && activity.answers_recorded === 0;

  return (
    <div className="space-y-6">
      {header}
      {notice}

      {error && (
        <InfoPanel tone="warning" title={t('hr.aiAnalytics.loadFailed')}>
          <p>{error}</p>
        </InfoPanel>
      )}

      {nothingYet && (
        <div data-testid="ai-analytics-empty">
          <InfoPanel tone="neutral" title={t('hr.aiAnalytics.emptyTitle')}>
            <p>{t('hr.aiAnalytics.emptyBody')}</p>
          </InfoPanel>
        </div>
      )}

      <Section testId="ai-analytics-overview" title={t('hr.aiAnalytics.section.overview')} note={t('hr.aiAnalytics.overviewNote')}>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard emphasis title={t('hr.aiAnalytics.overview.total')} value={overview.total_interviews}
            icon={<Layers className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.overview.scheduled')} value={overview.scheduled}
            icon={<CalendarClock className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.overview.inProgress')} value={overview.in_progress}
            icon={<Clock className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.overview.completed')} value={overview.completed}
            icon={<CheckCircle2 className={ICON} />} />
        </div>
      </Section>

      <Section testId="ai-analytics-activity" title={t('hr.aiAnalytics.section.activity')}>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard title={t('hr.aiAnalytics.activity.answers')} value={activity.answers_recorded}
            icon={<MessageSquareText className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.activity.mainReached')} value={activity.main_questions_reached}
            description={t('hr.aiAnalytics.activity.mainReachedHint')} icon={<ListOrdered className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.activity.followUps')} value={activity.follow_ups_answered}
            icon={<GitBranch className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.activity.highest')}
            value={activity.highest_question_reached ?? t('hr.aiAnalytics.activity.highestNone')}
            icon={<BarChart3 className={ICON} />} />
        </div>
      </Section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Section testId="ai-analytics-analysis" title={t('hr.aiAnalytics.section.analysis')} note={t('hr.aiAnalytics.analysisNote')}>
          <div className="grid grid-cols-3 gap-4">
            <KpiCard title={t('hr.aiAnalytics.analysis.completed')} value={analysis.completed}
              icon={<CheckCircle2 className={ICON} />} />
            <KpiCard title={t('hr.aiAnalytics.analysis.pending')} value={analysis.pending}
              icon={<Hourglass className={ICON} />} />
            <KpiCard title={t('hr.aiAnalytics.analysis.failed')} value={analysis.failed}
              icon={<XCircle className={ICON} />} />
          </div>
        </Section>

        <Section testId="ai-analytics-context" title={t('hr.aiAnalytics.section.context')} note={t('hr.aiAnalytics.contextNote')}>
          <div className="grid grid-cols-3 gap-4">
            <KpiCard title={t('hr.aiAnalytics.context.job')} value={context.job}
              icon={<Briefcase className={ICON} />} />
            <KpiCard title={t('hr.aiAnalytics.context.cv')} value={context.cv}
              icon={<FileText className={ICON} />} />
            <KpiCard title={t('hr.aiAnalytics.context.matching')} value={context.matching}
              description={t('hr.aiAnalytics.context.matchingHint')} icon={<Sparkles className={ICON} />} />
          </div>
        </Section>
      </div>

      <Section testId="ai-analytics-flow" title={t('hr.aiAnalytics.section.flow')}>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard title={t('hr.aiAnalytics.flow.main')} value={flow.main_questions}
            description={t('hr.aiAnalytics.flow.mainHint')} icon={<ListOrdered className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.flow.followUps')} value={flow.follow_ups}
            description={t('hr.aiAnalytics.flow.followUpsHint')} icon={<GitBranch className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.flow.notReached')} value={flow.not_reached}
            description={t('hr.aiAnalytics.flow.notReachedHint')} icon={<Hourglass className={ICON} />} />
          <KpiCard title={t('hr.aiAnalytics.flow.order')}
            value={flow.order_comparable ? t('hr.aiAnalytics.order.comparable') : t('hr.aiAnalytics.order.notComparable')}
            icon={<Layers className={ICON} />} />
        </div>
        <Card padding="md" className="text-xs text-stone-600 leading-relaxed space-y-1.5" data-testid="ai-analytics-order-note">
          <p>{flow.order_comparable ? t('hr.aiAnalytics.order.comparableNote') : t('hr.aiAnalytics.order.notComparableNote')}</p>
          <p className="text-stone-500">{t('hr.aiAnalytics.planNote')}</p>
        </Card>
      </Section>
    </div>
  );
};
