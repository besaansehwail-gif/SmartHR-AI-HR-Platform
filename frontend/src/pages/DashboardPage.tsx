import React, { useState, useEffect } from 'react';
import {
  Users,
  UserCheck,
  Building,
  Briefcase,
  AlertTriangle,
  ArrowRight,
  Shield,
  Activity,
  Plus,
  FileSpreadsheet,
  Download,
  Calendar,
  Clock,
  Sparkles,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { KpiCard } from '../components/ui/KpiCard';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge, ActionTypeBadge } from '../components/ui/Badge';
import { EmployeeDistributionChart, RecruitmentFunnelChart } from '../components/ui/Charts';
import {
  AdminDashboardData,
  AttentionItemRecord,
  AuditActionType,
  AuditLogRecord,
} from '../types';
import { SmartHRApi } from '../services/api';
import { PageId } from '../components/layout/Sidebar';
import { useToast } from '../components/ui/Toast';
import { Modal } from '../components/ui/Modal';
import { ErrorState, LoadingState } from '../components/ui/States';
import { useT } from '../i18n';

/**
 * audit_logs.action holds a finer-grained token than the seven-value
 * AuditActionType the badge renders, so it is folded onto a display category.
 * Kept in step with the same map on AuditLogsPage.
 */
const AUDIT_ACTION_CATEGORY: Record<string, AuditActionType> = {
  CREATE: 'CREATE',
  ASSIGN: 'CREATE',
  UPDATE: 'UPDATE',
  STATUS_CHANGE: 'UPDATE',
  DELETE: 'DELETE',
  APPROVE: 'APPROVE',
  REJECT: 'APPROVE',
  LOGIN: 'LOGIN',
  LOGIN_FAILED: 'SECURITY',
  ACTIVATE: 'SECURITY',
  DEACTIVATE: 'SECURITY',
  EXPORT: 'EXPORT',
};

const auditCategoryOf = (action: string): AuditActionType =>
  AUDIT_ACTION_CATEGORY[action] ?? 'SECURITY';

const formatAuditTimestamp = (value: string | null): string => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  );
};

export interface DashboardPageProps {
  onNavigate: (page: PageId) => void;
  onQuickAction: (action: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ onNavigate, onQuickAction }) => {
  const { t } = useT();
  const { showToast } = useToast();

  // Every figure on this page comes from /dashboard/admin, which aggregates
  // the live tables on each request. Nothing is stored for reporting.
  const [data, setData] = useState<AdminDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // A failed request is not "zero employees". The page says it could not
  // reach the statistics endpoint rather than presenting empty tiles as if
  // they were real counts.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Acknowledging an item hides it for this session only. The underlying
  // records are what generate it, so it returns on reload until they are
  // actually dealt with - there is no "dismissed" column to write to.
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [selectedAttentionItem, setSelectedAttentionItem] =
    useState<AttentionItemRecord | null>(null);

  useEffect(() => {
    let active = true;

    setIsLoading(true);

    SmartHRApi.getAdminDashboard()
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setLoadError(null);
      })
      .catch((err) => {
        if (!active) return;
        setData(null);
        setLoadError(
          err instanceof Error ? err.message : t('dash.unreachable')
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [reloadToken]);

  // Each block of the payload is read once here with a safe default, so a
  // response that is missing a section renders that section empty rather than
  // throwing halfway through the tree. The guards below then only ever deal
  // with "is there anything to show", never with "does this object exist".
  const kpis = data?.kpis;
  const recruitment = data?.recruitment;
  const attendanceToday = data?.attendance_today;
  const departmentSlices = data?.department_distribution ?? [];
  const pipelineStages = recruitment?.stages ?? [];
  const attendanceStatuses = attendanceToday?.by_status ?? [];
  const activeAttention = (data?.attention_items ?? []).filter(
    (item) => !acknowledged.includes(item.id)
  );

  const handleResolveAttention = (id: string, title: string) => {
    setAcknowledged((prev) => [...prev, id]);
    showToast(t('dash.itemAcknowledged'), {
      message: `"${title}" hidden for this session. It reappears until the underlying records are cleared.`,
      type: 'info',
    });
    setSelectedAttentionItem(null);
  };

  // Recent activity is read straight from audit_logs; the feed is the newest
  // five rows of the same trail the Audit Logs page renders in full.
  const [recentLogs, setRecentLogs] = useState<AuditLogRecord[]>([]);

  useEffect(() => {
    let active = true;

    // Only the newest five rows are shown, so only those are requested.
    SmartHRApi.getAuditLogs({ limit: 5 })
      .then((rows) => {
        if (active) setRecentLogs(rows);
      })
      .catch(() => {
        // The feed is supplementary; the rest of the dashboard still renders.
        if (active) setRecentLogs([]);
      });

    return () => {
      active = false;
    };
  }, [reloadToken]);

  if (isLoading && !data) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('dash.title')}
          subtitle={t('dash.subtitle')}
          icon={<Shield className="w-5 h-5" />}
        />
        <LoadingState
          title={t('dash.loadingTitle')}
          description={t('dash.loadingBody')}
        />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('dash.title')}
          subtitle={t('dash.subtitle')}
          icon={<Shield className="w-5 h-5" />}
        />
        <ErrorState
          title={t('dash.unavailable')}
          message={`${loadError} Every figure on this page is counted from the database by GET /dashboard/admin, so nothing is shown rather than showing zeros that are not real.`}
          onRetry={() => setReloadToken((n) => n + 1)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Welcome & Command Status Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-white text-stone-900 p-6 sm:p-8 shadow-2xs border border-stone-200/90">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 text-xs font-semibold border border-brand-200/80">
              <Shield className="w-3.5 h-3.5" />
              <span>{t('dash.liveOps')}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-stone-900">
              {t('dash.title')}
            </h1>
            <p className="text-stone-600 text-xs sm:text-sm max-w-2xl leading-relaxed">
              {isLoading ? (
                t('dash.loadingLive')
              ) : (
                <>
                  {t('dash.tracking')} <span className="text-stone-900 font-semibold">{kpis?.total_employees ?? 0}</span> employee
                  {' '}records across <span className="text-stone-900 font-semibold">{kpis?.departments ?? 0}</span> departments.
                  {' '}
                  {activeAttention.length > 0 ? (
                    <span className="text-amber-700 font-semibold">
                      {activeAttention.length} item{activeAttention.length === 1 ? '' : 's'} need attention.
                    </span>
                  ) : (
                    <span className="text-emerald-700 font-semibold">{t('dash.nothingNeedsAttention')}</span>
                  )}
                </>
              )}
            </p>
          </div>

          {/* Header Quick Metrics Summary */}
          <div className="flex items-center gap-3 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onNavigate('audit')}
              leftIcon={<Activity className="w-4 h-4" />}
            >
              {t('dash.systemAudit')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => onQuickAction('add-user')}
              leftIcon={<Plus className="w-4 h-4" />}
            >
              {t('dash.addEmployee')}
            </Button>
          </div>
        </div>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
        <KpiCard
          title={t('dash.totalEmployees')}
          value={kpis?.total_employees ?? 0}
          change={`${kpis?.new_hires_30d ?? 0} hired in 30d`}
          changeType={(kpis?.new_hires_30d ?? 0) > 0 ? 'positive' : 'neutral'}
          comparison={`${kpis?.active_employees ?? 0} active`}
          description={t('dash.totalEmployeesHint')}
          icon={<Users className="w-5 h-5" />}
        />
        <KpiCard
          title={t('dash.userAccounts')}
          value={kpis?.total_users ?? 0}
          change={`${kpis?.signed_in_30d ?? 0} signed in (30d)`}
          changeType="neutral"
          comparison={`${kpis?.active_user_accounts ?? 0} enabled`}
          description={t('dash.signInsHint')}
          icon={<UserCheck className="w-5 h-5" />}
        />
        <KpiCard
          title={t('dash.departments')}
          value={kpis?.departments ?? 0}
          change={`${kpis?.positions ?? 0} positions`}
          changeType="neutral"
          comparison="Org structure"
          description={t('dash.departmentsHint')}
          icon={<Building className="w-5 h-5" />}
        />
        <KpiCard
          title={t('dash.openJobs')}
          value={kpis?.open_jobs ?? 0}
          change={`${kpis?.total_jobs ?? 0} total`}
          changeType={(kpis?.open_jobs ?? 0) > 0 ? 'positive' : 'neutral'}
          comparison={`${recruitment?.total_applications ?? 0} applications`}
          description={t('dash.openJobsHint')}
          icon={<Briefcase className="w-5 h-5" />}
        />
      </div>

      {/* Attention Center (Critical Operational Alerts) */}
      <Card className="border-amber-200/80 bg-gradient-to-b from-amber-50/30 to-white">
        <CardHeader
          title={
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              <span>{t('ui.attention.title')}</span>
              <span className="text-2xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                {activeAttention.length} Action Items
              </span>
            </div>
          }
          subtitle={t('dash.attentionHint')}
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setAcknowledged((data?.attention_items ?? []).map((item) => item.id));
                showToast(t('dash.attentionCleared'), {
                  message: t('dash.attentionClearedHint'),
                  type: 'info',
                });
              }}
            >
              {t('dash.acknowledgeAll')}
            </Button>
          }
        />

        {activeAttention.length === 0 ? (
          <div className="py-8 text-center text-xs text-stone-500 flex flex-col items-center justify-center">
            <CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" />
            <span className="font-semibold text-stone-800 text-sm">
              {isLoading ? t('dash.checkingOpenItems') : t('dash.nothingNeedsAttentionTitle')}
            </span>
            <span className="text-stone-400 mt-0.5">
              {t('dash.noPendingItems')}
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {activeAttention.map((item) => (
              <div
                key={item.id}
                className="p-4 rounded-xl border border-stone-200/90 bg-white hover:border-brand-300 hover:shadow-xs transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={`text-3xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${
                        item.severity === 'high'
                          ? 'bg-rose-100 text-rose-800 border border-rose-200'
                          : 'bg-amber-100 text-amber-800 border border-amber-200'
                      }`}
                    >
                      {item.severity === 'high' ? t('dash.urgent') : t('dash.actionRequired')}
                    </span>
                    <span className="text-2xs font-medium text-stone-500 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-stone-400" /> {item.due_label}
                    </span>
                  </div>

                  <h4 className="text-sm font-bold text-stone-900 mt-2.5 tracking-tight">{item.title}</h4>
                  <p className="text-xs text-stone-500 mt-1 leading-relaxed">{item.description}</p>
                </div>

                <div className="mt-4 pt-3 border-t border-stone-100 flex items-center justify-between">
                  <span className="text-2xs font-semibold text-brand-700">{item.context}</span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="purple-soft"
                      size="sm"
                      onClick={() => setSelectedAttentionItem(item)}
                    >
                      {item.action_label}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Operational Visuals Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Employee Distribution Chart */}
        <Card className="lg:col-span-1">
          <CardHeader
            title={t('dash.employeeDistribution')}
            subtitle={`Headcount across ${departmentSlices.length} departments`}
            action={
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onNavigate('departments')}
                className="text-xs text-brand-700"
              >
                {t('dash.viewOrg')} <ArrowRight className="w-3 h-3 ms-1" data-flip-rtl />
              </Button>
            }
          />
          {departmentSlices.length === 0 ? (
            <p className="py-8 text-center text-xs text-stone-400">
              {isLoading ? t('state.loading') : t('dash.noDeptEmployees')}
            </p>
          ) : (
            <EmployeeDistributionChart data={departmentSlices} />
          )}
        </Card>

        {/* Recruitment Pipeline Overview */}
        <Card className="lg:col-span-1">
          <CardHeader
            title={t('dash.recruitmentPipeline')}
            subtitle={`${recruitment?.total_applications ?? 0} applications across the funnel`}
            action={
              <span className="text-2xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                {recruitment?.rejected ?? 0} rejected
              </span>
            }
          />
          {(recruitment?.total_applications ?? 0) === 0 ? (
            <p className="py-8 text-center text-xs text-stone-400">
              {isLoading ? t('state.loading') : t('dash.noApplications')}
            </p>
          ) : (
            <RecruitmentFunnelChart stages={pipelineStages} />
          )}
        </Card>

        {/* Work Mode Overview & Quick Actions */}
        <div className="space-y-6 lg:col-span-1">
          {/* The employees table has no work-mode column, so this slot shows
              today's attendance - which the attendance table does record. */}
          <Card>
            <CardHeader
              title={t('dash.attendanceToday')}
              subtitle={attendanceToday?.date ?? t('dash.noDate')}
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onNavigate('mgr-attendance')}
                  className="text-xs text-brand-700"
                >
                  {t('dash.roster')} <ArrowRight className="w-3 h-3 ms-1" data-flip-rtl />
                </Button>
              }
            />
            {(attendanceToday?.total_records ?? 0) === 0 ? (
              <p className="py-6 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('dash.noAttendanceToday')}
              </p>
            ) : (
              <div className="space-y-3">
                <div className="flex items-end justify-between">
                  <div>
                    <p className="text-3xl font-black text-stone-900 leading-none">
                      {attendanceToday?.punctuality_rate ?? 0}%
                    </p>
                    <p className="text-2xs text-stone-500 mt-1">on time today</p>
                  </div>
                  <p className="text-2xs text-stone-500">
                    {attendanceToday?.total_records ?? 0} record
                    {(attendanceToday?.total_records ?? 0) === 1 ? '' : 's'} logged
                  </p>
                </div>

                <div className="space-y-1.5">
                  {attendanceStatuses.map((slice) => (
                    <div key={slice.status}>
                      <div className="flex items-center justify-between text-2xs font-semibold">
                        <span className="text-stone-700">{slice.status}</span>
                        <span className="text-stone-500">
                          {slice.count} ({slice.percentage}%)
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-stone-100 mt-1 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-brand-600"
                          style={{ width: `${slice.percentage}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {attendanceToday?.avg_worked_hours !== null &&
                  attendanceToday?.avg_worked_hours !== undefined && (
                  <p className="text-2xs text-stone-400 pt-1 border-t border-stone-100">
                    Average worked: {attendanceToday.avg_worked_hours}h (check-out minus check-in)
                  </p>
                )}
              </div>
            )}
          </Card>

          {/* Quick Actions Card */}
          <Card>
            <CardHeader
              title={t('dash.shortcuts')}
              subtitle={t('dash.shortcutsHint')}
            />
            <div className="grid grid-cols-2 gap-2.5">
              <Button
                variant="outline"
                size="sm"
                className="justify-start text-xs font-semibold"
                onClick={() => onQuickAction('add-user')}
                leftIcon={<Users className="w-3.5 h-3.5 text-brand-600" />}
              >
                {t('dash.addUser')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start text-xs font-semibold"
                onClick={() => onQuickAction('add-department')}
                leftIcon={<Building className="w-3.5 h-3.5 text-brand-600" />}
              >
                {t('dash.addDept')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start text-xs font-semibold"
                onClick={() => onQuickAction('add-position')}
                leftIcon={<Briefcase className="w-3.5 h-3.5 text-brand-600" />}
              >
                {t('dash.postJob')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start text-xs font-semibold"
                onClick={() => onQuickAction('export-audit')}
                leftIcon={<FileSpreadsheet className="w-3.5 h-3.5 text-brand-600" />}
              >
                {t('dash.exportLog')}
              </Button>
            </div>
          </Card>
        </div>
      </div>

      {/* Recent System Activity Feed */}
      <Card>
        <CardHeader
          title={t('dash.recentActivity')}
          subtitle={t('dash.recentActivityHint')}
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => onNavigate('audit')}
              leftIcon={<Activity className="w-3.5 h-3.5 text-brand-600" />}
            >
              {t('dash.fullAuditStream')}
            </Button>
          }
        />

        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs text-stone-600">
            <thead>
              <tr className="border-b border-stone-100 text-3xs font-bold text-stone-400 uppercase tracking-wider">
                <th className="py-2.5 px-3">Type</th>
                <th className="py-2.5 px-3">User</th>
                <th className="py-2.5 px-3">{t('dash.colActivity')}</th>
                <th className="py-2.5 px-3">{t('dash.colTargetEntity')}</th>
                <th className="py-2.5 px-3 text-end">{t('dash.colTimestamp')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 font-medium">
              {recentLogs.map((log) => (
                <tr key={log.id} className="hover:bg-stone-50/70 transition-colors">
                  <td className="py-3 px-3">
                    <ActionTypeBadge type={auditCategoryOf(log.action)} />
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-brand-100 text-brand-700 font-bold text-3xs flex items-center justify-center">
                        {log.user.name.split(' ').filter(Boolean).map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                      </div>
                      <span className="font-bold text-stone-900">{log.user.name}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-stone-700 font-semibold">{log.description}</td>
                  <td className="py-3 px-3 text-stone-500 font-mono text-2xs truncate max-w-[200px]">
                    {log.entity_type ?? '-'}{log.entity_id === null ? '' : ` #${log.entity_id}`}
                  </td>
                  <td className="py-3 px-3 text-end text-stone-400 font-mono text-2xs">
                    {formatAuditTimestamp(log.timestamp)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Attention Item Action Modal */}
      {selectedAttentionItem && (
        <Modal
          isOpen={!!selectedAttentionItem}
          onClose={() => setSelectedAttentionItem(null)}
          title={selectedAttentionItem.title}
          subtitle={`${selectedAttentionItem.context} • ${selectedAttentionItem.due_label}`}
          footer={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  handleResolveAttention(selectedAttentionItem.id, selectedAttentionItem.title)
                }
              >
                {t('ui.attention.acknowledge')}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  onNavigate(selectedAttentionItem.target_page as PageId);
                  setSelectedAttentionItem(null);
                }}
              >
                {selectedAttentionItem.action_label}
              </Button>
            </>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="p-3.5 rounded-lg bg-brand-50 border border-brand-200/80 text-brand-900">
              <p className="font-semibold text-sm mb-1">{selectedAttentionItem.description}</p>
              <p className="text-brand-700">
                This item is generated from live records, so it clears itself once those
                records are actioned in the module below.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-stone-50 rounded-lg border border-stone-200">
                <span className="text-3xs text-stone-400 uppercase font-bold">{t('dash.recordsInvolved')}</span>
                <p className="text-sm font-bold text-stone-800 mt-0.5">{selectedAttentionItem.count}</p>
              </div>
              <div className="p-3 bg-stone-50 rounded-lg border border-stone-200">
                <span className="text-3xs text-stone-400 uppercase font-bold">{t('dash.severityLevel')}</span>
                <p className="text-sm font-bold text-amber-700 mt-0.5 uppercase">{selectedAttentionItem.severity}</p>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
