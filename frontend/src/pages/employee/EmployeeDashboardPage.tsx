import React, { useState, useEffect } from 'react';
import {
  Clock,
  Calendar,
  Award,
  BookOpen,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Sparkles,
  Zap,
  Star,
  MapPin,
  Laptop,
  Building2,
  Bell,
  ChevronRight,
  ShieldAlert,
  Play,
  UserCheck,
  CheckSquare,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import { SmartHRApi } from '../../services/api';
import { EmployeeDashboardData } from '../../types';
// Shape only - the same interface notificationAdapters maps rows into.
import { EmployeeNotificationItem } from '../../mock/employeeData';
import { toEmployeeNotification } from '../../services/notificationAdapters';
import { useT } from '../../i18n';

export interface EmployeeDashboardPageProps {
  onNavigate: (page: PageId) => void;
}

export const EmployeeDashboardPage: React.FC<EmployeeDashboardPageProps> = ({
  onNavigate,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  // /dashboard/employee is scoped to the employees row linked to the signed-in
  // user. Nothing about anybody else is returned.
  const [data, setData] = useState<EmployeeDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notifications, setNotifications] = useState<EmployeeNotificationItem[]>([]);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;

    SmartHRApi.getEmployeeDashboard()
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err) => {
        if (!cancelled) {
          showToast(t('emp.dash.loadFailed'), {
            message: err instanceof Error ? err.message : t('emp.dash.unreachable'),
            type: 'error',
          });
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    SmartHRApi.getNotifications()
      .then((rows) => {
        if (!cancelled) setNotifications(rows.map(toEmployeeNotification));
      })
      .catch(() => {
        if (!cancelled) setNotifications([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const employee = data?.employee ?? null;
  const today = data?.attendance_today ?? null;
  const attendance30d = data?.attendance_30d ?? null;
  const leave = data?.leave ?? null;
  const training = data?.training ?? null;
  const performance = data?.performance ?? null;

  const firstName = (employee?.name ?? '').split(' ')[0] || 'there';

  const formatTime = (value: string | null): string => {
    if (!value) return '—';
    const [hh, mm] = value.split(':');
    const hour = Number(hh);
    if (Number.isNaN(hour)) return value;
    const suffix = hour >= 12 ? 'PM' : 'AM';
    const display = hour % 12 === 0 ? 12 : hour % 12;
    return `${display}:${mm} ${suffix}`;
  };

  // Attention items are built from this employee's own records only - a
  // pending request, an unfinished course, a missing clock-in. Nothing is
  // invented, so an employee with nothing outstanding sees an empty list.
  const attentionItems = [
    ...(leave && leave.pending > 0
      ? [{
          id: 'my-pending-leave',
          severity: 'medium' as const,
          title: `${leave.pending} leave request${leave.pending === 1 ? '' : 's'} awaiting a decision`,
          description: t('emp.dash.pendingLeaveHint'),
          dueLabel: 'Pending',
          actionLabel: t('emp.dash.viewLeave'),
          targetPage: 'emp-leave',
        }]
      : []),
    ...(training && training.in_progress > 0
      ? [{
          id: 'my-training',
          severity: 'medium' as const,
          title: `${training.in_progress} course${training.in_progress === 1 ? '' : 's'} in progress`,
          description: t('emp.dash.startedNotComplete'),
          dueLabel: t('emp.dash.incomplete'),
          actionLabel: t('emp.dash.openTraining'),
          targetPage: 'emp-training',
        }]
      : []),
    ...(training && training.assigned > 0
      ? [{
          id: 'my-training-new',
          severity: 'low' as const,
          title: `${training.assigned} course${training.assigned === 1 ? '' : 's'} assigned to you`,
          description: t('emp.dash.assignedNotStarted'),
          dueLabel: t('emp.dash.notStarted'),
          actionLabel: t('emp.dash.openTraining'),
          targetPage: 'emp-training',
        }]
      : []),
    ...(data?.is_linked && today && !today.logged
      ? [{
          id: 'no-attendance',
          severity: 'high' as const,
          title: t('emp.dash.noAttendanceToday'),
          description: t('emp.dash.noAttendanceTodayHint'),
          dueLabel: 'Today',
          actionLabel: t('emp.dash.myAttendance'),
          targetPage: 'emp-attendance',
        }]
      : []),
  ].filter((item) => !acknowledged.includes(item.id));

  const handleDismissAttention = (id: string, title: string) => {
    setAcknowledged((prev) => [...prev, id]);
    showToast(t('emp.dash.acknowledged'), {
      message: `Hidden for this session: "${title}".`,
      type: 'info',
    });
  };

  return (
    <div className="space-y-6">
      {/* 1. Top Welcome Banner & Command Center Header */}
      <div className="p-6 rounded-2xl bg-white border border-stone-200/90 shadow-2xs relative overflow-hidden">
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-3xs font-bold tracking-widest uppercase px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-200">
                {t('emp.dash.commandCenter')}
              </span>
              <span className="text-3xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                {t('emp.dash.activeWorkday')}
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-black text-stone-900 tracking-tight">
              Hello, {firstName}!
            </h1>
            <p className="text-xs sm:text-sm text-stone-600 max-w-2xl leading-relaxed">
              {isLoading ? (
                t('emp.dash.loading')
              ) : data?.is_linked ? (
                <>
                  You are in the{' '}
                  <strong className="text-stone-900">
                    {employee?.department_name ?? 'unassigned'}
                  </strong>{' '}
                  unit as{' '}
                  <strong className="text-brand-700">
                    {employee?.position_title ?? 'no position on record'}
                  </strong>
                  .
                </>
              ) : (
                t('emp.dash.notLinked')
              )}
            </p>

            <div className="flex items-center gap-4 pt-1 text-2xs text-stone-500 flex-wrap">
              <span className="flex items-center gap-1.5 text-stone-600">
                <Building2 className="w-3.5 h-3.5 text-brand-600" />
                {employee?.department_name ?? t('emp.dash.noDepartment')}
              </span>
              <span className="flex items-center gap-1.5 text-stone-600">
                <UserCheck className="w-3.5 h-3.5 text-brand-600" />
                Hired:{' '}
                <strong className="text-stone-900">{employee?.hire_date ?? t('emp.dash.notRecorded')}</strong>
              </span>
              <span className="flex items-center gap-1.5 text-stone-600">
                <Clock className="w-3.5 h-3.5 text-brand-600" />
                {t('emp.dash.statusLabel')} <strong className="text-stone-900">{employee?.employment_status ?? '—'}</strong>
              </span>
            </div>
          </div>

          {/* Today's attendance row, read from the attendance table. Clocking
              in and out is done on the My Attendance page, which owns the write. */}
          <div className="p-4 rounded-xl bg-stone-50 border border-stone-200 shrink-0 sm:min-w-[260px]">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-3xs font-bold uppercase tracking-wider text-brand-700 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-brand-600" />
                {t('emp.dash.todaysAttendance')}
              </span>
              <span
                className={`text-3xs font-bold px-2 py-0.5 rounded-full ${
                  today?.status === 'Present'
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : today?.status === 'Late'
                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                    : 'bg-stone-200 text-stone-700'
                }`}
              >
                {today?.status ?? t('emp.dash.notLogged')}
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-3">
              <div>
                <span className="text-2xs text-stone-500 block">{t('emp.dash.checkIn')}</span>
                <span className="text-base font-extrabold text-stone-900">
                  {formatTime(today?.check_in ?? null)}
                </span>
              </div>
              <div className="text-end">
                <span className="text-2xs text-stone-500 block">{t('emp.dash.checkOut')}</span>
                <span className="text-base font-extrabold text-brand-700">
                  {formatTime(today?.check_out ?? null)}
                </span>
              </div>
            </div>

            <Button
              variant="primary"
              size="sm"
              className="w-full text-xs font-bold justify-center"
              onClick={() => onNavigate('emp-attendance')}
            >
              {t('emp.dash.openMyAttendance')}
            </Button>
          </div>
        </div>
      </div>

      {/* 2. Key Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <KpiCard
          title={t('emp.dash.leaveDaysTaken')}
          value={leave?.approved_days_taken ?? 0}
          change={`${leave?.approved ?? 0} approved`}
          changeType="neutral"
          comparison="approved requests only"
          icon={<Calendar className="w-5 h-5 text-brand-600" />}
          description={
            (leave?.pending ?? 0) > 0
              ? `${leave?.pending} request pending review`
              : t('emp.dash.noPendingRequests')
          }
        />
        <KpiCard
          title={t('emp.dash.onTimeRate30')}
          value={`${attendance30d?.punctuality_rate ?? 0}%`}
          change={`${attendance30d?.total_records ?? 0} day${
            (attendance30d?.total_records ?? 0) === 1 ? '' : 's'
          } logged`}
          changeType={(attendance30d?.punctuality_rate ?? 0) >= 80 ? 'positive' : 'neutral'}
          comparison="last 30 days"
          icon={<Clock className="w-5 h-5 text-emerald-600" />}
          description={`${attendance30d?.late ?? 0} late arrival${
            (attendance30d?.late ?? 0) === 1 ? '' : 's'
          }`}
        />
        <KpiCard
          title={t('emp.dash.performanceRating')}
          value={
            performance?.latest_rating !== null && performance?.latest_rating !== undefined
              ? `${performance.latest_rating} / 5`
              : t('emp.dash.notRated')
          }
          change={performance?.latest_label ?? t('emp.dash.noReviewOnRecord')}
          changeType="neutral"
          comparison={`${performance?.reviews ?? 0} review${
            (performance?.reviews ?? 0) === 1 ? '' : 's'
          }`}
          icon={<Star className="w-5 h-5 text-amber-500 fill-amber-500" />}
          description={
            performance?.latest_review_date
              ? `Last reviewed ${performance.latest_review_date}`
              : t('emp.dash.noReviewDate')
          }
        />
        <KpiCard
          title={t('emp.dash.trainingCompleted')}
          value={`${training?.completed ?? 0} / ${training?.total ?? 0}`}
          change={`${training?.completion_rate ?? 0}% complete`}
          changeType={(training?.completion_rate ?? 0) >= 50 ? 'positive' : 'neutral'}
          comparison="assigned courses"
          icon={<TrendingUp className="w-5 h-5 text-brand-600" />}
          description={`${training?.in_progress ?? 0} in progress`}
        />
      </div>

      {/* 3. Attention Center Banner / Cards */}
      {attentionItems.length > 0 && (
        <Card
          title={t('ui.attention.title')}
          subtitle={t('emp.dash.attentionHint')}
          headerAction={
            <Badge variant="purple" dot>
              {attentionItems.length} Action Items
            </Badge>
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            {attentionItems.map((item) => {
              const isHigh = item.severity === 'high';
              const isMed = item.severity === 'medium';
              return (
                <div
                  key={item.id}
                  className={`p-3.5 rounded-xl border transition-all flex flex-col justify-between gap-2.5 ${
                    isHigh
                      ? 'bg-rose-50/50 border-rose-200'
                      : isMed
                      ? 'bg-amber-50/50 border-amber-200'
                      : 'bg-brand-50/40 border-brand-100'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-stone-900 flex items-center gap-1.5">
                        {isHigh ? (
                          <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0" />
                        ) : isMed ? (
                          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                        ) : (
                          <Sparkles className="w-4 h-4 text-brand-600 shrink-0" />
                        )}
                        {item.title}
                      </span>
                      <span
                        className={`text-3xs font-extrabold uppercase px-2 py-0.5 rounded-full ${
                          isHigh
                            ? 'bg-rose-100 text-rose-700'
                            : isMed
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-brand-100 text-brand-800'
                        }`}
                      >
                        {item.dueLabel}
                      </span>
                    </div>
                    <p className="text-2xs text-stone-600 leading-relaxed font-normal">
                      {item.description}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-stone-200/60">
                    <button
                      onClick={() => handleDismissAttention(item.id, item.title)}
                      className="text-3xs font-semibold text-stone-400 hover:text-stone-600 transition-colors"
                    >
                      {t('ui.attention.acknowledge')}
                    </button>
                    <Button
                      variant={isHigh ? 'danger' : 'primary'}
                      size="sm"
                      className="text-2xs py-1"
                      rightIcon={<ArrowRight className="w-3 h-3" data-flip-rtl />}
                      onClick={() => onNavigate(item.targetPage as PageId)}
                    >
                      {item.actionLabel}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* 4. Main Two-Column Layout: Training & Leave vs Career Growth & Goals */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Training Progress & Career Ladder Preview */}
        <div className="lg:col-span-2 space-y-6">
          {/* The schema has no career-ladder, grade or promotion-readiness
              table, so this slot shows performance_reviews instead. */}
          <Card
            title={t('emp.dash.myReview')}
            subtitle={t('emp.dash.myReviewHint')}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                rightIcon={<ChevronRight className="w-3.5 h-3.5" data-flip-rtl />}
                onClick={() => onNavigate('emp-performance')}
              >
                {t('emp.dash.viewAll')}
              </Button>
            }
          >
            {(performance?.reviews ?? 0) === 0 ? (
              <div className="py-8 text-center space-y-2">
                <Award className="w-7 h-7 text-stone-300 mx-auto" />
                <p className="text-xs text-stone-500 font-semibold">
                  {isLoading ? t('state.loading') : t('emp.dash.noReviewYet')}
                </p>
                <p className="text-2xs text-stone-400 max-w-sm mx-auto leading-relaxed">
                  {t('emp.dash.noReviewHint')}
                </p>
              </div>
            ) : (
              <div className="space-y-4 pt-1">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="p-4 rounded-xl bg-brand-50 border border-brand-100 text-center min-w-[110px]">
                    <p className="text-3xl font-black text-brand-900 leading-none">
                      {performance?.latest_rating}
                    </p>
                    <p className="text-3xs font-bold text-brand-700 mt-1">out of 5</p>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-stone-900">
                      {performance?.latest_label ?? t('emp.dash.unrated')}
                    </p>
                    <p className="text-2xs text-stone-500 mt-0.5">
                      Reviewed {performance?.latest_review_date ?? 'on an unrecorded date'} •{' '}
                      {performance?.reviews} review
                      {performance?.reviews === 1 ? '' : 's'} on record
                    </p>
                    {performance?.average_rating !== null &&
                      performance?.average_rating !== undefined && (
                        <p className="text-2xs text-stone-400 mt-0.5">
                          Average across all reviews: {performance.average_rating}
                        </p>
                      )}
                  </div>
                </div>

                {performance?.latest_feedback && (
                  <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200">
                    <span className="text-3xs font-bold uppercase text-stone-400 block mb-1">
                      {t('emp.dash.reviewerFeedback')}
                    </span>
                    <p className="text-xs text-stone-700 leading-relaxed">
                      {performance.latest_feedback}
                    </p>
                  </div>
                )}

                <p className="text-3xs text-stone-400 leading-relaxed pt-1 border-t border-stone-100">
                  Ratings are whole numbers 1-5; the column carries a database CHECK
                  constraint, so fractional scores cannot be stored.
                </p>
              </div>
            )}
          </Card>

          {/* Active Training Courses */}
          <Card
            title={t('emp.dash.learningHub')}
            subtitle={t('emp.dash.learningHubHint')}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                rightIcon={<ChevronRight className="w-3.5 h-3.5" data-flip-rtl />}
                onClick={() => onNavigate('emp-training')}
              >
                {t('emp.dash.exploreCourses')}
              </Button>
            }
          >
            <div className="space-y-3.5 pt-1">
              {(training?.items.length ?? 0) === 0 && (
                <div className="py-8 text-center space-y-2">
                  <BookOpen className="w-7 h-7 text-stone-300 mx-auto" />
                  <p className="text-xs text-stone-500 font-semibold">
                    {isLoading ? t('state.loading') : t('emp.dash.noCourses')}
                  </p>
                  <p className="text-2xs text-stone-400 max-w-sm mx-auto leading-relaxed">
                    {t('emp.dash.trainingEmptyHint')}
                  </p>
                </div>
              )}

              {(training?.items ?? []).map((course) => (
                <div
                  key={course.id}
                  className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 hover:border-brand-300 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-xs text-stone-900 truncate">
                        {course.title ?? t('emp.dash.untitledCourse')}
                      </span>
                      <Badge
                        variant={
                          course.status === 'completed'
                            ? 'success'
                            : course.status === 'in_progress'
                            ? 'info'
                            : 'neutral'
                        }
                      >
                        {(course.status ?? 'assigned').replace('_', ' ')}
                      </Badge>
                    </div>
                    <p className="text-2xs text-stone-500 line-clamp-1">
                      {course.provider ?? t('emp.dash.noProvider')}
                      {course.duration_hours ? ` • ${course.duration_hours}h` : ''}
                      {course.started_at ? ` • started ${course.started_at.split('T')[0]}` : ''}
                      {course.completed_at ? ` • completed ${course.completed_at.split('T')[0]}` : ''}
                    </p>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <Button
                      variant="primary"
                      size="sm"
                      className="text-2xs"
                      onClick={() => onNavigate('emp-training')}
                    >
                      Open
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            {(training?.total ?? 0) > 0 && (
              <p className="text-3xs text-stone-400 leading-relaxed mt-3 pt-2 border-t border-stone-100">
                employee_trainings records status and timestamps only - there is no
                percentage-complete column, so per-course progress bars are not shown.
              </p>
            )}
          </Card>
        </div>

        {/* Right Column (1 Col): Leave Balances & Skills Overview & Recent Notices */}
        <div className="space-y-6">
          {/* There is no leave-entitlement or balance table, so this card
              reports what has actually been taken rather than what remains. */}
          <Card
            title={t('emp.dash.leaveTimeOff')}
            subtitle={t('emp.dash.leaveHint')}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="text-2xs"
                onClick={() => onNavigate('emp-leave')}
              >
                {t('emp.dash.requestLeave')}
              </Button>
            }
          >
            <div className="space-y-3 pt-1">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-100">
                  <p className="text-lg font-black text-emerald-900">{leave?.approved ?? 0}</p>
                  <p className="text-3xs font-bold text-emerald-700">Approved</p>
                </div>
                <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-100">
                  <p className="text-lg font-black text-amber-900">{leave?.pending ?? 0}</p>
                  <p className="text-3xs font-bold text-amber-700">Pending</p>
                </div>
                <div className="p-2.5 rounded-lg bg-stone-50 border border-stone-200">
                  <p className="text-lg font-black text-stone-800">
                    {leave?.approved_days_taken ?? 0}
                  </p>
                  <p className="text-3xs font-bold text-stone-600">Days</p>
                </div>
              </div>

              {(leave?.days_by_type.length ?? 0) === 0 ? (
                <p className="text-2xs text-stone-400 py-3 text-center">
                  {isLoading ? t('state.loading') : t('emp.dash.noApprovedLeave')}
                </p>
              ) : (
                <div className="space-y-2 pt-1">
                  {(leave?.days_by_type ?? []).map((bal) => (
                    <div key={bal.leave_type} className="space-y-1">
                      <div className="flex justify-between text-xs font-semibold">
                        <span className="text-stone-800">{bal.leave_type}</span>
                        <span className="text-stone-500">
                          {bal.days} day{bal.days === 1 ? '' : 's'}
                        </span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-stone-100 overflow-hidden">
                        <div
                          className="h-full bg-brand-600 rounded-full"
                          style={{
                            width: `${Math.min(
                              (bal.days / Math.max(leave?.approved_days_taken ?? 1, 1)) * 100,
                              100
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {(data?.upcoming_leave.length ?? 0) > 0 && (
                <div className="pt-2 border-t border-stone-100 space-y-1.5">
                  <span className="text-3xs font-bold uppercase text-stone-400">{t('emp.dash.upcoming')}</span>
                  {(data?.upcoming_leave ?? []).map((item) => (
                    <div key={item.id} className="flex justify-between text-2xs">
                      <span className="text-stone-600">{item.leave_type ?? 'Leave'}</span>
                      <span className="font-semibold text-stone-800">
                        {item.start_date} ({item.status})
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <p className="text-3xs text-stone-400 leading-relaxed pt-1 border-t border-stone-100">
                Remaining balance is not shown: the database has no leave-entitlement
                table, so an allowance cannot be derived.
              </p>
            </div>
          </Card>

          {/* Recent Notifications Widget */}
          <Card
            title={t('emp.dash.notifications')}
            subtitle={t('emp.dash.notificationsHint')}
            headerAction={
              <Button
                variant="ghost"
                size="sm"
                className="text-2xs text-brand-700 font-bold"
                onClick={() => onNavigate('emp-notifications')}
              >
                {t('emp.dash.viewAllArrow')}
              </Button>
            }
          >
            <div className="space-y-2.5 pt-1">
              {notifications.length === 0 ? (
                <p className="text-2xs text-stone-400 py-4 text-center">
                  {t('emp.dash.noNotifications')}
                </p>
              ) : null}
              {notifications.slice(0, 3).map((notif) => (
                <div
                  key={notif.id}
                  className={`p-2.5 rounded-lg border text-xs space-y-1 transition-colors ${
                    !notif.read ? 'bg-brand-50/50 border-brand-200' : 'bg-white border-stone-100'
                  }`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-bold text-stone-900 truncate">{notif.title}</span>
                    <span className="text-3xs text-stone-400 shrink-0">{notif.timestamp}</span>
                  </div>
                  <p className="text-2xs text-stone-600 line-clamp-2">{notif.message}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
