import React, { useState } from 'react';
import {
  Star,
  TrendingUp,
  Target,
  Award,
  Calendar,
  CheckCircle2,
  AlertCircle,
  MessageSquare,
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Edit3,
  ThumbsUp,
  Compass,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { Modal } from '../../components/ui/Modal';
import { useToast } from '../../components/ui/Toast';
import { initialEmployeeGoals, EmployeeGoal } from '../../mock/employeeData';
import { useT } from '../../i18n';

/** Sample reviewer for this demo page - a name, not a translatable label. */
const REVIEWER_NAME = 'Marcus Vance';

export const MyPerformancePage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [goals, setGoals] = useState<EmployeeGoal[]>(initialEmployeeGoals);
  const [isSelfReviewModalOpen, setIsSelfReviewModalOpen] = useState(false);
  const [selfReflectionText, setSelfReflectionText] = useState(
    t('emp.perf.selfAssessPlaceholder')
  );

  const handleSaveSelfReview = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSelfReviewModalOpen(false);
    showToast(t('emp.perf.submitted'), {
      message: t('emp.perf.submittedMessageNamed', { name: REVIEWER_NAME }),
      type: 'success',
    });
  };

  const performanceHistory = [
    { period: 'Q3 2023', score: 4.4, tier: t('emp.perf.tierMeetsHighBar'), notes: t('emp.perf.tierSolidDelivery') },
    { period: 'Q4 2023', score: 4.5, tier: t('emp.perf.tierExceeds'), notes: t('emp.perf.tierAuthRefactor') },
    { period: 'Q1 2024', score: 4.65, tier: t('emp.perf.tierExceeds'), notes: t('emp.perf.tierPromoted') },
    { period: 'Q2 2024', score: 4.75, tier: t('emp.perf.tierExceptional'), notes: t('emp.perf.tierCaching') },
    { period: 'Q3 2024 (Est)', score: 4.8, tier: t('emp.perf.tierExceptional'), notes: t('emp.perf.tierStaffScope') },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.perf.title')}
        subtitle={t('emp.perf.subtitle')}
        breadcrumbs={[
          { label: t('workspace.employee'), href: '#' },
          { label: t('emp.perf.myPerformance'), active: true },
        ]}
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Edit3 className="w-4 h-4" />}
            onClick={() => setIsSelfReviewModalOpen(true)}
          >
            {t('emp.perf.submitTitle')}
          </Button>
        }
      />

      {/* 1. Rating Overview & Review Dates */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title={t('emp.perf.currentRating')}
          value="4.8 / 5.0"
          change="Exceptional Tier"
          changeType="positive"
          comparison="Top 5% bracket across Org"
          icon={<Star className="w-5 h-5 text-amber-500 fill-amber-500" />}
        />
        <KpiCard
          title={t('emp.perf.goalsProgress')}
          value="89% Avg"
          change="3 On Track, 1 Done"
          changeType="positive"
          comparison="Target: 100% by Q3 end"
          icon={<Target className="w-5 h-5 text-brand-600" />}
        />
        <KpiCard
          title={t('emp.perf.lastReview')}
          value="July 15, 2024"
          change="Mid-Year Cycle"
          changeType="neutral"
          comparison="Score: 4.75 / 5.0"
          icon={<Calendar className="w-5 h-5 text-brand-600" />}
        />
        <KpiCard
          title={t('emp.perf.nextMilestone')}
          value="Oct 20, 2024"
          change="Q3 Formal Cycle"
          changeType="neutral"
          comparison="Self-appraisal due Oct 10"
          icon={<Award className="w-5 h-5 text-emerald-600" />}
        />
      </div>

      {/* 2. Rating Trend & Manager Feedback */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Rating Trend History (2 cols) */}
        <div className="lg:col-span-2">
          <Card
            title={t('emp.perf.history')}
            subtitle={t('emp.perf.historyHint')}
          >
            <div className="space-y-4 pt-1">
              {/* Visual Multi-Bar Chart */}
              <div className="p-4 rounded-xl bg-stone-50 border border-stone-200">
                <div className="flex items-end justify-between gap-2 sm:gap-4 h-40 pt-4">
                  {performanceHistory.map((item, idx) => {
                    const heightPercent = ((item.score - 3.0) / 2.0) * 100;
                    const isLatest = idx === performanceHistory.length - 1;

                    return (
                      <div
                        key={item.period}
                        className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end"
                      >
                        <span
                          className={`text-2xs font-mono font-bold ${
                            isLatest ? 'text-brand-700' : 'text-stone-600'
                          }`}
                        >
                          {item.score.toFixed(2)}
                        </span>
                        <div className="w-full max-w-[48px] bg-stone-200 rounded-t-lg overflow-hidden flex flex-col justify-end h-full">
                          <div
                            className={`w-full rounded-t-lg transition-all duration-500 ${
                              isLatest
                                ? 'bg-gradient-to-t from-brand-700 to-brand-500 shadow-sm'
                                : 'bg-stone-400 hover:bg-stone-500'
                            }`}
                            style={{ height: `${heightPercent}%` }}
                          />
                        </div>
                        <span
                          className={`text-3xs font-extrabold uppercase truncate ${
                            isLatest ? 'text-brand-900' : 'text-stone-500'
                          }`}
                        >
                          {item.period}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Table of Historic Cycles */}
              <div className="divide-y divide-stone-100 text-xs">
                {performanceHistory.map((item) => (
                  <div key={item.period} className="py-2.5 flex items-center justify-between">
                    <div>
                      <span className="font-bold text-stone-900 me-2">{item.period}</span>
                      <span className="text-2xs text-stone-500">{item.notes}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant={item.score >= 4.7 ? 'success' : 'purple'}>
                        {item.tier}
                      </Badge>
                      <span className="font-mono font-extrabold text-stone-900 w-12 text-end">
                        {item.score.toFixed(2)} / 5
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>

        {/* Manager Feedback Column (1 col) */}
        <div className="space-y-6">
          <Card
            title={t('emp.perf.supervisorFeedback')}
            subtitle={t('emp.perf.feedbackFrom', { name: REVIEWER_NAME })}
          >
            <div className="space-y-3.5 pt-1">
              <div className="p-4 rounded-xl bg-brand-50/60 border border-brand-100 space-y-2 relative">
                <div className="flex items-center gap-2.5">
                  <img
                    src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80"
                    alt={REVIEWER_NAME}
                    className="w-10 h-10 rounded-full object-cover border border-brand-200"
                  />
                  <div>
                    <span className="text-xs font-bold text-stone-900 block">{REVIEWER_NAME}</span>
                    <span className="text-3xs text-brand-700 font-medium block">
                      {t('emp.perf.vpReview')}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-stone-700 italic leading-relaxed pt-1">
                  "Alex continues to execute with outstanding velocity and rigorous architectural discipline. His leadership on the microservice gateway transition and proactive peer mentoring demonstrate clear readiness for Staff-level (L5) scope."
                </p>

                <div className="flex justify-between items-center text-3xs font-semibold text-brand-900 pt-2 border-t border-brand-200/60">
                  <span>{t('emp.perf.recommendation')}</span>
                  <span>{t('emp.perf.q2MidYear')}</span>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 text-xs space-y-1">
                <span className="text-3xs font-bold uppercase text-stone-400 block">
                  {t('emp.perf.nextCheckpoint')}
                </span>
                <p className="text-stone-800 font-semibold">
                  {t('emp.perf.q3Formal')}
                </p>
                <p className="text-2xs text-stone-500">
                  {t('emp.perf.selfAssessOpen')}
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* 3. Active OKRs & Quarterly Goals */}
      <Card
        title={t('emp.perf.goals')}
        subtitle={t('emp.perf.goalsQuarter')}
        headerAction={
          <Badge variant="success" dot>
            4 Active Goals
          </Badge>
        }
      >
        <div className="space-y-4 pt-1">
          {goals.map((goal) => (
            <div
              key={goal.id}
              className="p-4 rounded-xl bg-stone-50 border border-stone-200 hover:border-brand-200 transition-colors space-y-3"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-3xs font-extrabold uppercase px-2 py-0.5 rounded-full bg-brand-100 text-brand-800">
                      {goal.category}
                    </span>
                    <span className="text-xs font-bold text-stone-900">{goal.title}</span>
                  </div>
                  <span className="text-2xs text-stone-400">Target Date: {goal.targetDate}</span>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <Badge
                    variant={goal.status === t('emp.perf.goalCompleted') ? 'success' : 'purple'}
                    dot={goal.status === t('emp.perf.goalOnTrack')}
                  >
                    {goal.status}
                  </Badge>
                  <span className="text-xs font-mono font-extrabold text-brand-700 w-12 text-end">
                    {goal.progress}%
                  </span>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    goal.progress === 100 ? 'bg-emerald-600' : 'bg-brand-700'
                  }`}
                  style={{ width: `${goal.progress}%` }}
                />
              </div>

              {/* Key Results Checklist */}
              <div className="space-y-1.5 pt-1">
                <span className="text-3xs font-bold uppercase tracking-wider text-stone-400 block">
                  {t('emp.perf.keyResults')}
                </span>
                <ul className="space-y-1 text-2xs text-stone-600">
                  {goal.keyResults.map((kr, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                      <span>{kr}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 4. Strengths & Growth Areas */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Core Strengths */}
        <Card
          title={t('emp.perf.strengths')}
          subtitle={t('emp.perf.strengthsHint')}
          headerAction={<ThumbsUp className="w-4 h-4 text-emerald-600" />}
        >
          <ul className="space-y-2.5 text-xs text-stone-700 pt-1">
            <li className="p-3 rounded-xl bg-emerald-50/50 border border-emerald-100 flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <strong className="text-stone-900 block font-bold">
                  {t('emp.perf.strength1')}
                </strong>
                <span className="text-2xs text-stone-600">
                  {t('emp.perf.strength1Body')}
                </span>
              </div>
            </li>
            <li className="p-3 rounded-xl bg-emerald-50/50 border border-emerald-100 flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <strong className="text-stone-900 block font-bold">
                  {t('emp.perf.strength2')}
                </strong>
                <span className="text-2xs text-stone-600">
                  {t('emp.perf.strength2Body')}
                </span>
              </div>
            </li>
            <li className="p-3 rounded-xl bg-emerald-50/50 border border-emerald-100 flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <strong className="text-stone-900 block font-bold">
                  {t('emp.perf.strength3')}
                </strong>
                <span className="text-2xs text-stone-600">
                  {t('emp.perf.strength3Body')}
                </span>
              </div>
            </li>
          </ul>
        </Card>

        {/* Growth & Development Opportunities */}
        <Card
          title={t('emp.perf.development')}
          subtitle={t('emp.perf.developmentTarget')}
          headerAction={<Compass className="w-4 h-4 text-brand-600" />}
        >
          <ul className="space-y-2.5 text-xs text-stone-700 pt-1">
            <li className="p-3 rounded-xl bg-brand-50/50 border border-brand-100 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
              <div>
                <strong className="text-stone-900 block font-bold">
                  {t('emp.perf.growth1')}
                </strong>
                <span className="text-2xs text-stone-600">
                  {t('emp.perf.growth1Body')}
                </span>
              </div>
            </li>
            <li className="p-3 rounded-xl bg-brand-50/50 border border-brand-100 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
              <div>
                <strong className="text-stone-900 block font-bold">
                  {t('emp.perf.growth2')}
                </strong>
                <span className="text-2xs text-stone-600">
                  {t('emp.perf.growth2Body')}
                </span>
              </div>
            </li>
            <li className="p-3 rounded-xl bg-brand-50/50 border border-brand-100 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
              <div>
                <strong className="text-stone-900 block font-bold">
                  {t('emp.perf.growth3')}
                </strong>
                <span className="text-2xs text-stone-600">
                  {t('emp.perf.growth3Body')}
                </span>
              </div>
            </li>
          </ul>
        </Card>
      </div>

      {/* Self Assessment Modal */}
      <Modal
        isOpen={isSelfReviewModalOpen}
        onClose={() => setIsSelfReviewModalOpen(false)}
        title={t('emp.perf.submitQ3')}
        subtitle={t('emp.perf.submitQ3Subtitle', { name: REVIEWER_NAME })}
        size="lg"
        footer={
          <div className="flex justify-end gap-2.5">
            <Button variant="outline" onClick={() => setIsSelfReviewModalOpen(false)}>
              {t('action.cancel')}
            </Button>
            <Button variant="primary" onClick={handleSaveSelfReview}>
              {t('emp.perf.submitTitle')}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSaveSelfReview} className="space-y-4 text-xs">
          <div>
            <label className="block text-2xs font-bold text-stone-700 mb-1">
              {t('emp.perf.accomplishmentsQ3')}
            </label>
            <textarea
              rows={4}
              value={selfReflectionText}
              onChange={(e) => setSelfReflectionText(e.target.value)}
              className="w-full p-2.5 text-xs rounded-xl border border-stone-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
              required
            />
          </div>

          <div className="p-3.5 rounded-xl bg-brand-50 border border-brand-100 text-2xs text-brand-900 space-y-1">
            <span className="font-bold block">{t('emp.perf.criteriaRef')}</span>
            <p className="text-stone-600">
              {t('emp.perf.criteriaBodyNamed', { name: REVIEWER_NAME })}
            </p>
          </div>
        </form>
      </Modal>
    </div>
  );
};
