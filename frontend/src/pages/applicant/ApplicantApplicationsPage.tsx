import React, { useCallback, useEffect, useState } from 'react';
import { Calendar, Compass, MapPin, Radio, Send } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { KpiCard } from '../../components/ui/KpiCard';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState, InfoPanel, InlineEmpty, LoadingState } from '../../components/ui/States';
import { PageId } from '../../components/layout/Sidebar';
import { SmartHRApi } from '../../services/api';
import { ApplicantApplication, ApplicantApplicationSummary } from '../../types';
import { useT } from '../../i18n';

/**
 * My Applications.
 *
 * The stage words here are the applicant-facing labels the backend sends
 * (`screening` arrives as "Under Review"), so the page never has to interpret
 * a recruiter's vocabulary. Interview notes, the interviewer's identity and
 * anything about other candidates are absent because the payload does not
 * carry them.
 */

/** The seven stages an application moves through, for the progress rail.
 *  "Not selected" is deliberately not on it: it is an outcome, not a step. */
const STAGE_TOKENS = [
  'applied',
  'screening',
  'shortlisted',
  'interview',
  'assessment',
  'offer',
  'hired',
];

const ProgressRail: React.FC<{ application: ApplicantApplication }> = ({ application }) => {
  const { t } = useT();

  if (application.status === 'rejected') {
    return (
      <div className="rounded-xl bg-stone-50 border border-stone-200 p-3">
        <p className="text-2xs text-stone-600">
          This application was not taken forward. SmartHR does not record a reason, so none is
          shown here.
        </p>
      </div>
    );
  }

  const current = application.step ?? 1;

  return (
    <div>
      <div className="flex items-center gap-1">
        {STAGE_TOKENS.map((stage, index) => {
          const reached = index < current;
          const isCurrent = index === current - 1;
          return (
            <div key={stage} className="flex-1 min-w-0">
              <div
                className={`h-1.5 rounded-full ${
                  reached ? (isCurrent ? 'bg-brand-600' : 'bg-brand-300') : 'bg-stone-200'
                }`}
              />
              <p
                className={`mt-1.5 text-3xs truncate ${
                  isCurrent ? 'font-bold text-brand-700' : 'text-stone-400'
                }`}
              >
                {t(`app.stage.${stage}`)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const ApplicantApplicationsPage: React.FC<{
  onNavigate: (page: PageId) => void;
  onViewOpportunity: (opportunityId: string) => void;
  onOpenAiInterview: (interviewId: number) => void;
}> = ({ onNavigate, onViewOpportunity, onOpenAiInterview }) => {
  const { t } = useT();
  const [applications, setApplications] = useState<ApplicantApplication[]>([]);
  // Which of these interviews can be held as an AI Interview right now - the
  // same list the AI Interview page offers (GET /ai-interview/interviews), so
  // the button appears exactly where that page would accept the interview.
  const [aiInterviewIds, setAiInterviewIds] = useState<Set<number>>(new Set());
  const [summary, setSummary] = useState<ApplicantApplicationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await SmartHRApi.getMyApplications();
      setApplications(data.applications);
      setSummary(data.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('app.applications.failed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    SmartHRApi.getMyAiInterviews()
      .then(({ interviews }) => setAiInterviewIds(new Set(interviews.map((i) => i.interview_id))))
      // An extra on this page: if it cannot be read, the list simply shows
      // no AI Interview buttons rather than an error over working data.
      .catch(() => setAiInterviewIds(new Set()));
  }, []);

  if (loading) return <LoadingState title={t('app.applications.loading')} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('app.applications.title')}
        subtitle={t('app.applications.pageSubtitle')}
        icon={<Send className="w-5 h-5" />}
        actions={
          <Button variant="outline" size="sm" onClick={() => onNavigate('app-opportunities')}>
            {t('app.applications.browseOpportunities')}
          </Button>
        }
      />

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <KpiCard
            title={t('app.applications.totalApplications')}
            value={String(summary.total)}
            icon={<Send className="w-5 h-5" />}
          />
          <KpiCard
            title={t('app.applications.inProgress')}
            value={String(summary.active)}
            icon={<Compass className="w-5 h-5" />}
            description={t('app.applications.notYetDecided')}
          />
          <KpiCard
            title={t('app.applications.interviewsScheduled')}
            value={String(
              applications.reduce((total, a) => total + a.interviews.length, 0)
            )}
            icon={<Calendar className="w-5 h-5" />}
          />
        </div>
      )}

      {applications.length === 0 ? (
        <InlineEmpty
          title={t('app.applications.noneYet')}
          description={t('app.applications.noneYetHint')}
          icon={<Send className="w-5 h-5" />}
        />
      ) : (
        <div className="space-y-4">
          {applications.map((application) => (
            <Card key={application.id} padding="md">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-stone-900 break-words">
                    {application.job_title}
                  </h3>
                  <p className="text-2xs text-stone-500 mt-0.5">
                    {application.opportunity?.organization ?? t('app.apps.organizationFallback')}
                    {application.opportunity?.department_name
                      ? ` • ${application.opportunity.department_name}`
                      : ''}
                    {' • '}
                    Applied {(application.applied_at ?? '').slice(0, 10)}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Badge
                    variant={
                      application.is_successful
                        ? 'success'
                        : application.status === 'rejected'
                          ? 'neutral'
                          : 'info'
                    }
                  >
                    {application.status_label}
                  </Badge>
                  {application.opportunity && (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() =>
                        onViewOpportunity(application.opportunity!.opportunity_id)
                      }
                    >
                      View
                    </Button>
                  )}
                </div>
              </div>

              <ProgressRail application={application} />

              {application.interviews.length > 0 && (
                <div className="mt-4 pt-4 border-t border-stone-100">
                  <p className="text-3xs font-bold uppercase tracking-wider text-stone-400 mb-2">
                    {t('app.applications.scheduledInterviews')}
                  </p>
                  <ul className="space-y-2">
                    {application.interviews.map((interview) => (
                      <li
                        key={interview.id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-stone-700"
                      >
                        <Calendar className="w-3.5 h-3.5 text-brand-600 shrink-0" />
                        <span className="font-semibold">
                          {(interview.scheduled_at ?? '').replace('T', ' ').slice(0, 16)}
                        </span>
                        {interview.location && (
                          <span className="inline-flex items-center gap-1 text-stone-500">
                            <MapPin className="w-3.5 h-3.5" /> {interview.location}
                          </span>
                        )}
                        {aiInterviewIds.has(interview.id) && (
                          <Button
                            size="xs"
                            variant="primary"
                            className="ms-auto"
                            leftIcon={<Radio className="w-3.5 h-3.5" />}
                            onClick={() => onOpenAiInterview(interview.id)}
                          >
                            {t('aiInterview.action.start')}
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <InfoPanel title={t('app.applications.whatYouSee')} tone="neutral">
        <p>
          You see your own applications and their current stage. Interviewers' notes, internal
          scoring and anything about other candidates are not shown — not hidden by this page, but
          never sent to it. Stages are moved by SmartHR recruiters; neither you nor the Career
          Agent can change one.
        </p>
      </InfoPanel>
    </div>
  );
};
