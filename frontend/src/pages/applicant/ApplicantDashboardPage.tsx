import React, { useCallback, useEffect, useState } from 'react';
import { Calendar, Compass, FileText, Radio, Send, Sparkles, User } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { KpiCard } from '../../components/ui/KpiCard';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState, InfoPanel, InlineEmpty, LoadingState } from '../../components/ui/States';
import { PageId } from '../../components/layout/Sidebar';
import { formatDateTime, useT } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import { AiInterviewListing, ApplicantDashboardData } from '../../types';
import { OpportunityCard } from './OpportunityCard';

/**
 * The applicant's landing page.
 *
 * One read of `GET /applicant/dashboard`; every figure on it is counted from
 * that applicant's own rows. Nothing here is mock data, so a brand-new account
 * correctly shows zeros and an empty recommendation list rather than a
 * populated-looking demo.
 */
export const ApplicantDashboardPage: React.FC<{
  onNavigate: (page: PageId) => void;
  onViewOpportunity: (opportunityId: string) => void;
  onOpenAiInterview: (interviewId: number) => void;
}> = ({ onNavigate, onViewOpportunity, onOpenAiInterview }) => {
  const { t, locale } = useT();
  const [data, setData] = useState<ApplicantDashboardData | null>(null);
  // The applicant's interviews that can be held as an AI Interview, earliest
  // first (the order GET /ai-interview/interviews returns).
  const [aiInterviews, setAiInterviews] = useState<AiInterviewListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await SmartHRApi.getApplicantDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : t('app.dashboard.failed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    SmartHRApi.getMyAiInterviews()
      .then(({ interviews }) => setAiInterviews(interviews))
      // An extra on the dashboard: failing to read it hides the card rather
      // than putting an error over a working page.
      .catch(() => setAiInterviews([]));
  }, []);

  if (loading) return <LoadingState title={t('app.dashboard.loading')} />;
  if (error || !data) return <ErrorState message={error ?? t('app.common.noData')} onRetry={load} />;

  const { profile, applications, recommended, opportunity_counts: counts } = data;
  const complete = profile.completeness;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome, ${profile.first_name || 'there'}`}
        subtitle={t('app.dashboard.pageSubtitle')}
        icon={<Compass className="w-5 h-5" />}
        badge={<Badge variant="brand">Applicant</Badge>}
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Sparkles className="w-4 h-4" />}
            onClick={() => onNavigate('app-agent')}
          >
            {t('app.dashboard.askCareerAgent')}
          </Button>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title={t('app.dashboard.openOpportunities')}
          value={String(
            (counts.job ?? 0) + (counts.internship ?? 0) + (counts.training ?? 0) +
              (counts.free_course ?? 0)
          )}
          icon={<Compass className="w-5 h-5" />}
          description={`${counts.job ?? 0} jobs • ${counts.internship ?? 0} internships`}
        />
        <KpiCard
          title={t('app.dashboard.myApplications')}
          value={String(applications.summary.total)}
          icon={<Send className="w-5 h-5" />}
          description={`${applications.summary.active} still in progress`}
        />
        <KpiCard
          title={t('app.dashboard.profileComplete')}
          value={`${complete.percent}%`}
          icon={<User className="w-5 h-5" />}
          description={`${complete.complete} of ${complete.total} details added`}
        />
        <KpiCard
          title={t('app.dashboard.cvOnFile')}
          value={profile.has_cv ? t('status.yes') : t('app.dash.notYet')}
          icon={<FileText className="w-5 h-5" />}
          description={profile.cv?.file_name ?? t('app.dashboard.uploadBeforeApplying')}
        />
      </div>

      {!profile.has_cv && (
        <InfoPanel title={t('app.dashboard.needCv')} tone="warning">
          <p>
            SmartHR asks for a CV on every application so the recruiter has something to read.
            Upload yours on the My CV page — it is analysed by AI and the skills it finds are
            offered to you as suggestions, never saved without you.
          </p>
          <Button size="sm" variant="soft" className="mt-3" onClick={() => onNavigate('app-cv')}>
            {t('app.dashboard.uploadMyCv')}
          </Button>
        </InfoPanel>
      )}

      {profile.skills.length === 0 && (
        <InfoPanel title={t('app.dashboard.addSkillsPrompt')} tone="info">
          <p>
            Recommendations compare the skills on your profile with what each opportunity asks
            for. Until you list some, SmartHR will not guess what you can do — it will simply show
            you the newest openings.
          </p>
          <Button size="sm" variant="soft" className="mt-3" onClick={() => onNavigate('app-profile')}>
            {t('app.dashboard.addMySkills')}
          </Button>
        </InfoPanel>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card padding="md">
            <CardHeader
              title={t('app.dashboard.recommended')}
              subtitle={
                recommended.skills_available
                  ? t('app.dashboard.rankedHint')
                  : t('app.dashboard.newestHint')
              }
              icon={<Sparkles className="w-4 h-4" />}
              action={
                <Button size="sm" variant="outline" onClick={() => onNavigate('app-opportunities')}>
                  {t('app.dashboard.browseAll')}
                </Button>
              }
            />

            {recommended.items.length === 0 ? (
              <InlineEmpty
                title={t('app.dashboard.nothingOnOffer')}
                description={t('app.dashboard.nothingOnOfferHint')}
                icon={<Compass className="w-5 h-5" />}
              />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {recommended.items.map((opportunity) => (
                  <OpportunityCard
                    key={opportunity.opportunity_id}
                    opportunity={opportunity}
                    onOpen={onViewOpportunity}
                  />
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          {aiInterviews.length > 0 && (
            <Card padding="md" variant="brand">
              <div className="flex items-start gap-3">
                <span className="w-9 h-9 rounded-xl bg-white/70 text-brand-700 flex items-center justify-center shrink-0">
                  <Radio className="w-4.5 h-4.5" />
                </span>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-stone-900">{t('aiInterview.entry.title')}</h3>
                  {/* A database value - shown as stored, never translated. */}
                  <p className="text-xs font-semibold text-stone-800 mt-1 break-words" dir="auto">
                    {aiInterviews[0].job_title}
                  </p>
                  <p className="text-2xs text-stone-600 mt-0.5 inline-flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5 shrink-0" />
                    {aiInterviews[0].scheduled_at
                      ? formatDateTime(aiInterviews[0].scheduled_at, locale)
                      : t('aiInterview.job.noDate')}
                  </p>
                  {aiInterviews.length > 1 && (
                    <p className="text-3xs text-stone-500 mt-1">
                      {t('aiInterview.entry.more', { count: aiInterviews.length - 1 })}
                    </p>
                  )}
                  <Button
                    size="sm"
                    variant="primary"
                    className="mt-3"
                    leftIcon={<Radio className="w-4 h-4" />}
                    onClick={() => onOpenAiInterview(aiInterviews[0].interview_id)}
                  >
                    {t('aiInterview.action.start')}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          <Card padding="md">
            <CardHeader
              title={t('app.dashboard.recentApplications')}
              subtitle={t('app.dashboard.recentApplicationsHint')}
              icon={<Send className="w-4 h-4" />}
              action={
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onNavigate('app-applications')}
                >
                  {t('app.dashboard.seeAll')}
                </Button>
              }
            />

            {applications.recent.length === 0 ? (
              <InlineEmpty
                title={t('app.dashboard.noApplications')}
                description={t('app.dashboard.noApplicationsHint')}
                icon={<Send className="w-5 h-5" />}
              />
            ) : (
              <ul className="space-y-2.5">
                {applications.recent.map((application) => (
                  <li
                    key={application.id}
                    className="flex items-start justify-between gap-3 p-3 rounded-xl border border-stone-200 bg-white"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-stone-900 break-words">
                        {application.job_title}
                      </p>
                      <p className="text-3xs text-stone-500 mt-0.5">
                        Applied {(application.applied_at ?? '').slice(0, 10)}
                      </p>
                    </div>
                    <Badge
                      variant={
                        application.is_successful
                          ? 'success'
                          : application.is_closed
                            ? 'neutral'
                            : 'info'
                      }
                      size="sm"
                    >
                      {application.status_label}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card padding="md" variant="brand">
            <div className="flex items-start gap-3">
              <span className="w-9 h-9 rounded-xl bg-white/70 text-brand-700 flex items-center justify-center shrink-0">
                <Sparkles className="w-4.5 h-4.5" />
              </span>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-stone-900">{t('ai.career.title')}</h3>
                <p className="text-2xs text-stone-600 mt-1 leading-relaxed">
                  Ask it what suits you, or to find a particular kind of role. It reads only your
                  own profile and the live opportunity list, and it will never submit an
                  application unless you ask it to in words.
                </p>
                <Button
                  size="sm"
                  variant="primary"
                  className="mt-3"
                  onClick={() => onNavigate('app-agent')}
                >
                  {t('app.dashboard.openCareerAgent')}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
