import React, { useState, useEffect, useCallback } from 'react';
import {
  Users,
  UserPlus,
  Briefcase,
  UserCheck,
  Calendar,
  Clock,
  GraduationCap,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
  Filter,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Eye,
  Check,
  X,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { KpiCard } from '../../components/ui/KpiCard';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge, WorkModeBadge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import {
  AttentionItemRecord,
  HRDashboardData,
  LeaveBrief,
} from '../../types';
import { SmartHRApi } from '../../services/api';
import { useT } from '../../i18n';

export interface HRDashboardPageProps {
  onNavigate: (page: PageId) => void;
  onSelectEmployee?: (employeeId: string) => void;
}

export const HRDashboardPage: React.FC<HRDashboardPageProps> = ({
  onNavigate,
  onSelectEmployee,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  // Everything on this page is aggregated by /dashboard/hr from the live
  // tables; nothing is precomputed or stored.
  const [data, setData] = useState<HRDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedLeave, setSelectedLeave] = useState<LeaveBrief | null>(null);
  const [isLeaveModalOpen, setIsLeaveModalOpen] = useState(false);
  const [isDeciding, setIsDeciding] = useState(false);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      setData(await SmartHRApi.getHRDashboard());
    } catch (err) {
      showToast(t('hr.dash.metricsFailed'), {
        message: err instanceof Error ? err.message : t('hr.dash.unreachable'),
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const kpis = data?.kpis;
  const pendingLeaves = data?.pending_leave ?? [];
  const attentionItems: AttentionItemRecord[] = (data?.attention_items ?? []).filter(
    (item) => !acknowledged.includes(item.id)
  );
  const pipelineStages = data?.recruitment.stages ?? [];
  const attendance = data?.attendance_today;

  // Approving or rejecting writes through PATCH /leave-requests/{id}/status,
  // then the whole dashboard is re-read so every dependent count moves too.
  const decideLeave = async (id: number, status: 'Approved' | 'Rejected') => {
    setIsDeciding(true);
    try {
      await SmartHRApi.updateLeaveStatus(id, status);
      setIsLeaveModalOpen(false);
      setSelectedLeave(null);
      await load();
      showToast(`Leave ${status}`, {
        message: `Request #${id} was ${status.toLowerCase()} and saved to the database.`,
        type: status === 'Approved' ? 'success' : 'info',
      });
    } catch (err) {
      showToast(t('hr.dash.updateFailed'), {
        message: err instanceof Error ? err.message : t('hr.dash.updateRejected'),
        type: 'error',
      });
    } finally {
      setIsDeciding(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title={t('hr.dash.title')}
        subtitle={t('hr.dash.subtitle')}
        badge={
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-brand-100 text-brand-800 border border-brand-200">
            <span className="w-2 h-2 rounded-full bg-brand-600 animate-pulse" />
            {t('hr.dash.workspace')}
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<TrendingUp className="w-3.5 h-3.5" />}
              onClick={() => onNavigate('hr-reports')}
            >
              {t('hr.dash.analytics')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<UserPlus className="w-3.5 h-3.5" />}
              onClick={() => onNavigate('hr-employees')}
            >
              + Add Employee
            </Button>
          </div>
        }
      />

      {/* 7 Key Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title={t('hr.dash.totalEmployees')}
          value={kpis?.total_employees ?? 0}
          change={`${kpis?.new_hires_90d ?? 0} in 90 days`}
          changeType={(kpis?.new_hires_90d ?? 0) > 0 ? 'positive' : 'neutral'}
          comparison="from the employees table"
          icon={<Users className="w-5 h-5 text-brand-600" />}
          description={`${data?.department_distribution.length ?? 0} departments staffed`}
        />
        <KpiCard
          title={t('hr.dash.newHires')}
          value={kpis?.new_hires_30d ?? 0}
          change={`${kpis?.new_hires_90d ?? 0} in 90 days`}
          changeType={(kpis?.new_hires_30d ?? 0) > 0 ? 'positive' : 'neutral'}
          comparison="by hire_date"
          icon={<UserPlus className="w-5 h-5 text-emerald-600" />}
          description={t('hr.dash.newHiresHint')}
        />
        <KpiCard
          title={t('hr.dash.openPositions')}
          value={kpis?.open_positions ?? 0}
          change={`${data?.recruitment.total_applications ?? 0} applications`}
          changeType="neutral"
          comparison="jobs with status open"
          icon={<Briefcase className="w-5 h-5 text-sky-600" />}
          description={`${kpis?.active_candidates ?? 0} active candidates`}
        />
        <KpiCard
          title={t('hr.dash.upcomingInterviews')}
          value={kpis?.interviews_upcoming ?? 0}
          change={`${kpis?.interviews_total ?? 0} on record`}
          changeType="neutral"
          comparison="scheduled from now"
          icon={<Calendar className="w-5 h-5 text-brand-600" />}
          description={t('hr.dash.upcomingHint')}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard
          title={t('hr.dash.activeCandidates')}
          value={kpis?.active_candidates ?? 0}
          change={`${kpis?.total_candidates ?? 0} total`}
          changeType="neutral"
          comparison="not hired or rejected"
          icon={<UserCheck className="w-5 h-5 text-brand-600" />}
          description={t('hr.dash.activeCandidatesHint')}
        />
        <KpiCard
          title={t('hr.dash.pendingLeave')}
          value={kpis?.pending_leave_requests ?? 0}
          change={(kpis?.pending_leave_requests ?? 0) > 0 ? t('hr.dash.requiresAction') : t('hr.dash.allClear')}
          changeType={(kpis?.pending_leave_requests ?? 0) > 0 ? 'negative' : 'positive'}
          comparison="awaiting a decision"
          icon={<Clock className="w-5 h-5 text-amber-600" />}
          description={t('hr.dash.pendingLeaveHint')}
        />
        <KpiCard
          title={t('hr.dash.trainingCompletion')}
          value={`${kpis?.training_completion_rate ?? 0}%`}
          change={`${kpis?.training_completed ?? 0} / ${kpis?.training_assignments ?? 0}`}
          changeType={(kpis?.training_completion_rate ?? 0) >= 50 ? 'positive' : 'neutral'}
          comparison={`${kpis?.training_courses ?? 0} courses`}
          icon={<GraduationCap className="w-5 h-5 text-emerald-600" />}
          description={t('hr.dash.trainingHint')}
        />
      </div>

      {/* Main Grid: Attention Center + Recruitment Pipeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Attention Center (2 Cols) */}
        <div className="lg:col-span-2 space-y-6">
          <Card
            title={t('hr.dash.attention')}
            subtitle={t('hr.dash.attentionHint')}
            headerAction={
              <Badge variant="warning" dot>
                {attentionItems.length} Open Items
              </Badge>
            }
          >
            <div className="divide-y divide-stone-100">
              {attentionItems.length === 0 && (
                <div className="py-6 text-center text-xs text-stone-400">
                  {isLoading
                    ? t('hr.dash.checkingOpenItems')
                    : t('hr.dash.noPendingItems')}
                </div>
              )}
              {attentionItems.map((item) => (
                <div
                  key={item.id}
                  className="py-3.5 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3 group hover:bg-stone-50/70 p-2 rounded-lg transition-colors"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                        item.severity === 'high'
                          ? 'bg-rose-50 text-rose-600 border border-rose-200'
                          : item.severity === 'medium'
                          ? 'bg-amber-50 text-amber-600 border border-amber-200'
                          : 'bg-sky-50 text-sky-600 border border-sky-200'
                      }`}
                    >
                      <AlertTriangle className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-stone-900 group-hover:text-brand-700 transition-colors">
                          {item.title}
                        </span>
                        <span className="text-2xs font-semibold px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                          {item.context}
                        </span>
                      </div>
                      <p className="text-xs text-stone-500 mt-0.5 line-clamp-1">{item.description}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                    <span className="text-2xs font-semibold text-rose-600">{item.due_label}</span>
                    <Button
                      variant="purple-soft"
                      size="sm"
                      onClick={() => onNavigate(item.target_page as PageId)}
                      rightIcon={<ChevronRight className="w-3.5 h-3.5" data-flip-rtl />}
                    >
                      {item.action_label}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Visual Recruitment Pipeline */}
          <Card
            title={t('hr.dash.funnel')}
            subtitle={`${data?.recruitment.total_applications ?? 0} applications across ${kpis?.open_positions ?? 0} open requisitions`}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                onClick={() => onNavigate('hr-jobs')}
                rightIcon={<ArrowRight className="w-3.5 h-3.5" data-flip-rtl />}
              >
                {t('hr.dash.viewJobs')}
              </Button>
            }
          >
            <div className="space-y-4">
              {/* Stepper Pipeline Bar */}
              <div className="grid grid-cols-4 lg:grid-cols-7 gap-2 text-center pb-2">
                {pipelineStages.map((stage) => (
                  <div
                    key={stage.token}
                    className="p-2.5 rounded-lg border border-stone-200/80 bg-stone-50/50 hover:bg-brand-50/60 hover:border-brand-200 transition-all cursor-pointer group"
                    onClick={() => onNavigate('hr-candidates')}
                  >
                    <span className="text-3xs font-bold uppercase tracking-wider text-stone-400 group-hover:text-brand-700 block">
                      {stage.stage}
                    </span>
                    <span className="text-lg font-extrabold text-stone-900 group-hover:text-brand-700 block mt-0.5">
                      {stage.count}
                    </span>
                    <span className="text-3xs font-medium text-stone-500">
                      {stage.rate}
                    </span>
                  </div>
                ))}
              </div>

              {/* Progress bars visual funnel */}
              <div className="space-y-2 pt-2 border-t border-stone-100">
                {pipelineStages.map((stage) => (
                  <div key={stage.token} className="flex items-center gap-3">
                    <span className="w-20 text-xs font-semibold text-stone-700 text-end">
                      {stage.stage}
                    </span>
                    <div className="flex-1 h-3 rounded-full bg-stone-100 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${Math.max(
                            (stage.count / Math.max(data?.recruitment.total_applications ?? 1, 1)) * 100,
                            stage.count > 0 ? 6 : 2
                          )}%`,
                          backgroundColor: stage.color,
                        }}
                      />
                    </div>
                    <span className="w-10 text-xs font-bold text-stone-800 text-end">
                      {stage.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>

        {/* Right Column: Workforce Overview & Recent Activity */}
        <div className="space-y-6">
          {/* The employees table has no work-mode column, so this slot reports
              today's attendance, which the attendance table does record. */}
          <Card
            title={t('hr.dash.attendanceToday')}
            subtitle={attendance?.date ?? t('hr.dash.noRecords')}
            headerAction={
              <Badge variant="purple">
                {attendance?.total_records ?? 0} logged
              </Badge>
            }
          >
            {(attendance?.total_records ?? 0) === 0 ? (
              <p className="py-6 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('hr.dash.nobodyClockedIn')}
              </p>
            ) : (
              <div className="space-y-4">
                <div className="h-3 w-full rounded-full bg-stone-100 flex overflow-hidden">
                  {attendance!.by_status.map((slice, idx) => (
                    <div
                      key={slice.status}
                      className="h-full"
                      style={{
                        width: `${slice.percentage}%`,
                        backgroundColor: ['#C45A2A', '#0284C7', '#059669', '#D97706', '#DB2777'][idx % 5],
                      }}
                      title={`${slice.status}: ${slice.percentage}%`}
                    />
                  ))}
                </div>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-100">
                    <CheckCircle2 className="w-4 h-4 mx-auto text-emerald-600 mb-1" />
                    <p className="text-base font-bold text-stone-900">{attendance!.present}</p>
                    <p className="text-3xs text-stone-500 font-medium">{t('hr.dash.present')}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-100">
                    <Clock className="w-4 h-4 mx-auto text-amber-600 mb-1" />
                    <p className="text-base font-bold text-stone-900">{attendance!.late}</p>
                    <p className="text-3xs text-stone-500 font-medium">Late</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-sky-50 border border-sky-100">
                    <Calendar className="w-4 h-4 mx-auto text-sky-600 mb-1" />
                    <p className="text-base font-bold text-stone-900">{attendance!.on_leave}</p>
                    <p className="text-3xs text-stone-500 font-medium">{t('hr.dash.onLeave')}</p>
                  </div>
                </div>

                <div className="pt-2 border-t border-stone-100 text-xs space-y-1">
                  <div className="flex justify-between items-center py-1">
                    <span className="text-stone-600 font-medium">{t('hr.dash.onTimeRate')}</span>
                    <span className="font-bold text-stone-900">{attendance!.punctuality_rate}%</span>
                  </div>
                  {attendance!.avg_worked_hours !== null && (
                    <div className="flex justify-between items-center py-1">
                      <span className="text-stone-600 font-medium">{t('hr.dash.averageWorked')}</span>
                      <span className="font-bold text-stone-900">{attendance!.avg_worked_hours}h</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </Card>

          {/* Recent Activity Feed */}
          <Card
            title={t('hr.dash.upcomingInterviews')}
            subtitle={t('hr.dash.scheduledFrom')}
            headerAction={
              <button
                onClick={() => onNavigate('hr-interviews')}
                className="text-xs font-semibold text-brand-700 hover:text-brand-900 flex items-center gap-1"
              >
                {t('hr.dash.allInterviews')} <ArrowRight className="w-3 h-3" data-flip-rtl />
              </button>
            }
          >
            <div className="space-y-3.5">
              {(data?.upcoming_interviews.length ?? 0) === 0 && (
                <p className="py-4 text-center text-xs text-stone-400">
                  {isLoading ? t('state.loading') : t('hr.dash.noInterviews')}
                </p>
              )}
              {(data?.upcoming_interviews ?? []).map((item) => (
                <div key={item.id} className="flex items-start gap-3 text-xs">
                  <div className="p-1.5 rounded-lg border shrink-0 mt-0.5 bg-brand-50 border-brand-200">
                    <Calendar className="w-4 h-4 text-brand-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-stone-900">
                      {item.candidate_name ?? t('hr.dash.unnamedCandidate')}
                    </p>
                    <p className="text-stone-500 text-2xs mt-0.5 leading-relaxed">
                      {item.job_title ?? t('hr.dash.noJobLinked')}
                      {item.interviewer_name ? ` • ${item.interviewer_name}` : ''}
                    </p>
                    <span className="text-3xs font-medium text-stone-400 mt-1 block">
                      {item.scheduled_at
                        ? new Date(item.scheduled_at).toLocaleString()
                        : t('hr.dash.notScheduled')}
                      {item.location ? ` • ${item.location}` : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* Leave Request Review Modal */}
      {selectedLeave && (
        <Modal
          isOpen={isLeaveModalOpen}
          onClose={() => setIsLeaveModalOpen(false)}
          title={t('hr.dash.reviewLeave')}
          subtitle={`Request #${selectedLeave.id} • ${selectedLeave.leave_type ?? 'Leave'}`}
          footer={
            <div className="flex items-center justify-between w-full">
              <span className="text-xs text-stone-500">
                {selectedLeave.department_name ?? t('hr.dash.noDepartment')}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => decideLeave(selectedLeave.id, 'Rejected')}
                  disabled={isDeciding}
                  leftIcon={<X className="w-3.5 h-3.5 text-rose-600" />}
                >
                  {t('action.reject')}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => decideLeave(selectedLeave.id, 'Approved')}
                  disabled={isDeciding}
                  leftIcon={<Check className="w-3.5 h-3.5" />}
                >
                  {isDeciding ? t('state.saving') : t('hr.dash.approveLeave')}
                </Button>
              </div>
            </div>
          }
        >
          <div className="space-y-4">
            <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200/80 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold text-stone-900">
                  {selectedLeave.employee_name ?? t('hr.dash.unknownEmployee')}
                </p>
                <p className="text-xs text-stone-500">
                  {selectedLeave.department_name ?? t('hr.dash.noDepartment')}
                </p>
              </div>
              <Badge variant="warning">{selectedLeave.status}</Badge>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg border border-stone-100 bg-white">
                <span className="text-stone-400 font-medium">{t('hr.dash.leaveDates')}</span>
                <p className="font-bold text-stone-900 mt-1">
                  {selectedLeave.start_date} → {selectedLeave.end_date}
                </p>
              </div>
              <div className="p-3 rounded-lg border border-stone-100 bg-white">
                <span className="text-stone-400 font-medium">{t('hr.dash.duration')}</span>
                <p className="font-bold text-stone-900 mt-1">
                  {selectedLeave.duration_days} day{selectedLeave.duration_days === 1 ? '' : 's'}
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-lg border border-stone-100 bg-white text-xs">
              <span className="text-stone-400 font-medium block mb-1">{t('hr.dash.reason')}</span>
              <p className="text-stone-700 leading-relaxed">
                {selectedLeave.reason ?? t('hr.dash.noReason')}
              </p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
