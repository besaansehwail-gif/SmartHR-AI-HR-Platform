import React, { useState, useEffect } from 'react';
import {
  Users,
  CheckCircle2,
  Clock,
  Calendar,
  Star,
  GraduationCap,
  AlertTriangle,
  ArrowRight,
  Laptop,
  Building2,
  MapPin,
  TrendingUp,
  Activity,
  Plus,
  ShieldAlert,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import { ManagerDashboardData } from '../../types';
import { SmartHRApi } from '../../services/api';
import { useT } from '../../i18n';

export interface ManagerDashboardPageProps {
  onNavigate: (page: PageId) => void;
}

export const ManagerDashboardPage: React.FC<ManagerDashboardPageProps> = ({ onNavigate }) => {
  const { t } = useT();
  const { showToast } = useToast();

  // /dashboard/manager resolves the signed-in user to their employees row and
  // scopes every figure to the people whose manager_id points at it.
  const [data, setData] = useState<ManagerDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;

    SmartHRApi.getManagerDashboard()
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((err) => {
        if (active) {
          showToast(t('mgr.dashboard.metricsFailed'), {
            message: err instanceof Error ? err.message : t('mgr.dashboard.statsUnreachable'),
            type: 'error',
          });
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const kpis = data?.kpis;
  const team = data?.team ?? [];
  const totalTeam = kpis?.team_size ?? 0;
  const pendingApprovals = kpis?.pending_leave_requests ?? 0;
  const attendance = data?.attendance_today;

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('mgr.dashboard.title')}
        subtitle={
          data?.linked_employee
            ? `Direct reports of ${data.linked_employee.name} (${data.linked_employee.department_name ?? 'no department'}) - attendance, approvals and review activity.`
            : t('mgr.dashboard.subtitle')
        }
        badge={
          <Badge variant="purple" dot>
            {t('mgr.dashboard.teamOpsLive')}
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Calendar className="w-3.5 h-3.5" />}
              onClick={() => onNavigate('mgr-attendance')}
            >
              {t('mgr.dashboard.todaysRoster')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
              onClick={() => onNavigate('mgr-leave')}
            >
              Approvals ({pendingApprovals})
            </Button>
          </div>
        }
      />

      {/* Not every account is linked to an employees row, and not every
          employee has direct reports. Say so rather than showing zeros with
          no explanation. */}
      {!isLoading && !data?.is_linked && (
        <Card>
          <div className="py-5 px-1 text-center">
            <p className="text-sm font-bold text-stone-800">
              {t('mgr.dashboard.notLinked')}
            </p>
            <p className="text-xs text-stone-500 mt-1 max-w-xl mx-auto leading-relaxed">
              A team is read from employees whose manager_id points at the signed-in
              user&apos;s own employees row. Link this user on the Users page to see
              team figures here.
            </p>
          </div>
        </Card>
      )}

      {!isLoading && data?.is_linked && !data.has_team && (
        <Card>
          <div className="py-5 px-1 text-center">
            <p className="text-sm font-bold text-stone-800">{t('mgr.dashboard.noDirectReports')}</p>
            <p className="text-xs text-stone-500 mt-1 max-w-xl mx-auto leading-relaxed">
              Nobody currently has {data.linked_employee?.name ?? 'this employee'} set as
              their manager, so the team figures below are genuinely zero. Set a
              manager on an employee record to populate them.
            </p>
          </div>
        </Card>
      )}

      {/* 6 Executive Manager KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <KpiCard
          title={t('mgr.dashboard.teamSizeLabel')}
          value={totalTeam}
          change={`${kpis?.not_logged_today ?? 0} not clocked in`}
          changeType="neutral"
          comparison="direct reports"
          icon={<Users className="w-5 h-5 text-brand-600" />}
          description="employees.manager_id"
        />
        <KpiCard
          title={t('mgr.dashboard.presentTodayLabel')}
          value={`${kpis?.present_today ?? 0} / ${totalTeam}`}
          change={`${attendance?.punctuality_rate ?? 0}% on time`}
          changeType={(kpis?.present_today ?? 0) > 0 ? 'positive' : 'neutral'}
          comparison={`${kpis?.late_today ?? 0} late`}
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
          description={t('mgr.dashboard.fromToday')}
        />
        <KpiCard
          title={t('mgr.dashboard.onLeaveToday')}
          value={kpis?.on_leave_today ?? 0}
          change="Approved time-off"
          changeType="neutral"
          comparison="covering today"
          icon={<Calendar className="w-5 h-5 text-sky-600" />}
          description={t('mgr.dashboard.approvedSpanning')}
        />
        <KpiCard
          title={t('mgr.dashboard.pendingApprovals')}
          value={pendingApprovals}
          change={pendingApprovals > 0 ? t('mgr.dashboard.actionRequired') : t('mgr.dashboard.allClear')}
          changeType={pendingApprovals > 0 ? 'negative' : 'positive'}
          comparison="team leave requests"
          icon={<Clock className="w-5 h-5 text-amber-500" />}
          description={t('mgr.dashboard.statusPending')}
        />
        <KpiCard
          title={t('mgr.dashboard.teamPerformance')}
          value={kpis?.average_rating ?? t('mgr.dashboard.notRated')}
          change={`${kpis?.performance_reviews ?? 0} review${(kpis?.performance_reviews ?? 0) === 1 ? '' : 's'}`}
          changeType="neutral"
          comparison="out of 5"
          icon={<Star className="w-5 h-5 text-amber-500" />}
          description={t('mgr.dashboard.meanRatings')}
        />
        <KpiCard
          title={t('mgr.dashboard.trainingProgress')}
          value={`${kpis?.training_completed ?? 0} / ${kpis?.training_assignments ?? 0}`}
          change={
            (kpis?.training_assignments ?? 0) > 0
              ? `${Math.round(((kpis?.training_completed ?? 0) / (kpis?.training_assignments ?? 1)) * 100)}% complete`
              : t('mgr.dashboard.noneAssigned')
          }
          changeType="neutral"
          comparison="team assignments"
          icon={<GraduationCap className="w-5 h-5 text-brand-600" />}
          description="employee_trainings"
        />
      </div>

      {/* Attention Center & Work Mode Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Attention Center (2 Cols) */}
        <div className="lg:col-span-2">
          <Card
            title={t('mgr.dashboard.leaveAwaiting')}
            subtitle={t('mgr.dashboard.pendingFromReports')}
            headerAction={
              <Badge variant={pendingApprovals > 0 ? 'warning' : 'success'} dot>
                {pendingApprovals} Pending
              </Badge>
            }
          >
            <div className="divide-y divide-stone-100">
              {(data?.pending_leave.length ?? 0) === 0 && (
                <div className="py-6 text-center text-xs text-stone-400">
                  {isLoading
                    ? t('state.loading')
                    : t('mgr.dashboard.noPendingLeave')}
                </div>
              )}

              {(data?.pending_leave ?? []).map((item) => (
                <div
                  key={item.id}
                  className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-amber-50 text-amber-600 border border-amber-200">
                      <AlertTriangle className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <h4 className="text-xs font-bold text-stone-900">
                        {item.employee_name ?? t('mgr.dashboard.unknownEmployee')} — {item.leave_type ?? 'Leave'}
                      </h4>
                      <p className="text-2xs text-stone-500 mt-0.5">
                        {item.start_date} → {item.end_date} • {item.duration_days} day
                        {item.duration_days === 1 ? '' : 's'}
                      </p>
                      {item.reason && (
                        <p className="text-2xs text-stone-400 mt-0.5 line-clamp-1">{item.reason}</p>
                      )}
                    </div>
                  </div>

                  <Button
                    variant="purple-soft"
                    size="sm"
                    onClick={() => onNavigate('mgr-leave' as PageId)}
                  >
                    {t('mgr.dashboard.review')}
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Work Mode Distribution (1 Col) */}
        <div>
          {/* The employees table has no work-mode column, so this slot reports
              the team's attendance today, which the attendance table records. */}
          <Card
            title={t('mgr.dashboard.attendanceToday')}
            subtitle={attendance?.date ?? "Today's roster"}
            headerAction={
              <Badge variant="neutral">{totalTeam} Team Members</Badge>
            }
          >
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-3 rounded-xl bg-emerald-50/80 border border-emerald-100">
                  <CheckCircle2 className="w-5 h-5 text-emerald-700 mx-auto mb-1" />
                  <p className="text-xl font-black text-emerald-950">{kpis?.present_today ?? 0}</p>
                  <p className="text-3xs font-bold text-emerald-700">{t('mgr.dashboard.present')}</p>
                </div>
                <div className="p-3 rounded-xl bg-amber-50/80 border border-amber-100">
                  <Clock className="w-5 h-5 text-amber-700 mx-auto mb-1" />
                  <p className="text-xl font-black text-amber-950">{kpis?.late_today ?? 0}</p>
                  <p className="text-3xs font-bold text-amber-700">Late</p>
                </div>
                <div className="p-3 rounded-xl bg-sky-50/80 border border-sky-100">
                  <Calendar className="w-5 h-5 text-sky-700 mx-auto mb-1" />
                  <p className="text-xl font-black text-sky-950">{kpis?.on_leave_today ?? 0}</p>
                  <p className="text-3xs font-bold text-sky-700">{t('mgr.dashboard.onLeave')}</p>
                </div>
              </div>

              <div className="space-y-2 pt-1 border-t border-stone-100 text-xs">
                <div className="flex justify-between items-center text-2xs py-1">
                  <span className="text-stone-500 font-medium">{t('mgr.dashboard.notClockedIn')}</span>
                  <span className="font-bold text-stone-800">{kpis?.not_logged_today ?? 0}</span>
                </div>
                <div className="flex justify-between items-center text-2xs py-1">
                  <span className="text-stone-500 font-medium">{t('mgr.dashboard.onTimeRate')}</span>
                  <span className="font-bold text-stone-800">
                    {attendance?.punctuality_rate ?? 0}%
                  </span>
                </div>
                <div className="flex justify-between items-center text-2xs py-1">
                  <span className="text-stone-500 font-medium">{t('mgr.dashboard.interviewsRunning')}</span>
                  <span className="font-bold text-stone-800">{kpis?.interviews_upcoming ?? 0}</span>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Lower Row: Recent Team Activity & Quick Team Snapshot */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Team Activity */}
        <Card
          title={t('mgr.dashboard.interviewsRunning')}
          subtitle={t('mgr.dashboard.interviewsRunningHint')}
          headerAction={
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-brand-700"
              onClick={() => onNavigate('hr-interviews')}
            >
              {t('mgr.dashboard.allInterviews')}
            </Button>
          }
        >
          <div className="divide-y divide-stone-100">
            {(data?.upcoming_interviews.length ?? 0) === 0 && (
              <div className="py-6 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('mgr.dashboard.noInterviews')}
              </div>
            )}
            {(data?.upcoming_interviews ?? []).map((item) => (
              <div key={item.id} className="py-2.5 flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-stone-100 text-stone-700 font-bold text-2xs flex items-center justify-center shrink-0 mt-0.5">
                    <Calendar className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <p className="text-xs text-stone-900 font-medium">
                      <strong className="font-bold text-brand-950">
                        {item.candidate_name ?? t('mgr.dashboard.unnamedCandidate')}
                      </strong>{' '}
                      — {item.job_title ?? t('mgr.dashboard.noJobLinked')}
                    </p>
                    <span className="text-3xs text-stone-400">
                      {item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : t('mgr.dashboard.notScheduled')}
                      {item.location ? ` • ${item.location}` : ''}
                    </span>
                  </div>
                </div>
                <span className="text-3xs font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-stone-100 text-stone-600 shrink-0">
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Quick Team Roster Preview */}
        <Card
          title={t('mgr.dashboard.rosterSnapshot')}
          subtitle={`${totalTeam} direct report${totalTeam === 1 ? '' : 's'} under your reporting line`}
          headerAction={
            <Button
              variant="outline"
              size="sm"
              onClick={() => onNavigate('mgr-team')}
            >
              {t('mgr.dashboard.viewFullTeam')}
            </Button>
          }
        >
          <div className="divide-y divide-stone-100 max-h-72 overflow-y-auto pe-1">
            {team.length === 0 && (
              <div className="py-6 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('mgr.dashboard.nobodyReports')}
              </div>
            )}
            {team.slice(0, 5).map((member) => (
              <div key={member.id} className="py-2.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-brand-700 text-white font-bold text-xs flex items-center justify-center shrink-0 ring-2 ring-brand-100">
                    {(member.name ?? '?')
                      .split(' ')
                      .filter(Boolean)
                      .map((n) => n[0])
                      .join('')
                      .slice(0, 2)
                      .toUpperCase()}
                  </div>
                  <div>
                    <h5 className="font-bold text-stone-900 text-xs">{member.name}</h5>
                    <p className="text-2xs text-stone-500">
                      {member.position_title ?? t('mgr.dashboard.noPosition')}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`text-3xs font-bold px-2 py-0.5 rounded-full ${
                      member.today_status === t('mgr.dashboard.present')
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : member.today_status === 'Late'
                        ? 'bg-amber-50 text-amber-700 border border-amber-200'
                        : 'bg-stone-100 text-stone-600'
                    }`}
                  >
                    {member.on_leave_today
                      ? t('mgr.dashboard.onLeave')
                      : member.today_status ?? t('mgr.dashboard.notLogged')}
                  </span>
                  <span className="text-2xs font-medium text-stone-400">
                    {member.department_name ?? '-'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
};
