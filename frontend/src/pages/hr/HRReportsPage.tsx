import React, { useState, useEffect } from 'react';
import {
  Download,
  Users,
  Briefcase,
  CheckCircle2,
  Clock,
  GraduationCap,
  Star,
  Info,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { ReportsData } from '../../types';
import { SmartHRApi } from '../../services/api';
import { useT } from '../../i18n';

/**
 * Every figure on this page is aggregated by GET /dashboard/reports from the
 * live tables. Two panels that the original layout carried cannot be answered
 * by the schema and say so instead of showing a number:
 *
 *   - Work mode (remote / hybrid / on-site): employees has no such column.
 *   - Turnover / retention: there is no termination or exit date anywhere, so
 *     departures cannot be counted. The headcount series is therefore a
 *     cumulative hire curve, labelled as such.
 */

/** Renders a panel the database cannot populate, rather than inventing one. */
const NotTracked: React.FC<{ title: string; reason: string }> = ({ title, reason }) => (
  <div className="p-4 rounded-xl bg-stone-50 border border-dashed border-stone-300 text-center">
    <Info className="w-5 h-5 text-stone-400 mx-auto mb-2" />
    <p className="text-xs font-bold text-stone-700">{title}</p>
    <p className="text-2xs text-stone-500 mt-1 leading-relaxed max-w-sm mx-auto">{reason}</p>
  </div>
);

const BarRow: React.FC<{
  label: string;
  valueLabel: string;
  percentage: number;
  color?: string;
}> = ({ label, valueLabel, percentage, color }) => (
  <div className="space-y-1">
    <div className="flex justify-between text-xs">
      <span className="font-bold text-stone-800">{label}</span>
      <span className="text-stone-500 font-semibold">{valueLabel}</span>
    </div>
    <div className="w-full h-2 rounded-full bg-stone-100 overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${Math.min(Math.max(percentage, percentage > 0 ? 2 : 0), 100)}%`,
          backgroundColor: color ?? '#C45A2A',
        }}
      />
    </div>
  </div>
);

export const HRReportsPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();
  const [data, setData] = useState<ReportsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeReportTab, setActiveReportTab] = useState<
    'all' | 'headcount' | 'recruitment' | 'attendance' | 'learning'
  >('all');

  useEffect(() => {
    let active = true;

    SmartHRApi.getReports()
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((err) => {
        if (active) {
          showToast(t('hr.reports.loadFailed'), {
            message: err instanceof Error ? err.message : t('hr.reports.unreachable'),
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

  const handleExportReport = (reportType: string, rows: string[][], header: string[]) => {
    if (rows.length === 0) {
      showToast(t('hr.reports.nothingToExport'), {
        message: `The ${reportType} report has no rows yet.`,
        type: 'info',
      });
      return;
    }

    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute(
      'download',
      `SmartHR_${reportType.replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showToast(t('hr.reports.exported'), {
      message: `${reportType}: ${rows.length} row${rows.length === 1 ? '' : 's'} downloaded.`,
      type: 'success',
    });
  };

  const headcount = data?.headcount;
  const history = headcount?.history ?? [];
  const peak = Math.max(...history.map((h) => h.cumulative), 1);

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('hr.reports.title')}
        subtitle={t('hr.reports.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {headcount?.total ?? 0} Total Headcount
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <span className="text-2xs text-stone-500 font-medium hidden sm:inline">
              {data ? `As of ${new Date(data.generated_at).toLocaleString()}` : t('state.loading')}
            </span>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Download className="w-3.5 h-3.5" />}
              onClick={() =>
                handleExportReport(
                  t('hr.reports.deptHeadcount'),
                  (data?.department_breakdown ?? []).map((d) => [
                    d.department,
                    String(d.count),
                    `${d.percentage}%`,
                  ]),
                  [t('table.department'), t('hr.reports.colHeadcount'), 'Share']
                )
              }
            >
              {t('hr.reports.exportHeadcount')}
            </Button>
          </div>
        }
      />

      {/* Top 4 KPI Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title={t('hr.reports.totalHeadcount')}
          value={headcount?.total ?? 0}
          change={`${headcount?.active ?? 0} active`}
          changeType="neutral"
          comparison="employees on record"
          icon={<Users className="w-5 h-5 text-brand-600" />}
          description={`Across ${data?.department_breakdown.length ?? 0} departments`}
        />
        <KpiCard
          title={t('hr.reports.averageTenure')}
          value={
            headcount?.avg_tenure_years !== null && headcount?.avg_tenure_years !== undefined
              ? `${headcount.avg_tenure_years} yrs`
              : t('hr.reports.noHireDates')
          }
          change={`${headcount?.with_hire_date ?? 0} with a hire date`}
          changeType="neutral"
          comparison="from employees.hire_date"
          icon={<Clock className="w-5 h-5 text-brand-600" />}
          description={t('hr.reports.tenureHint')}
        />
        <KpiCard
          title={t('hr.reports.onTimeRate')}
          value={`${data?.attendance.punctuality_rate ?? 0}%`}
          change={`${data?.attendance.total_records ?? 0} records`}
          changeType={(data?.attendance.punctuality_rate ?? 0) >= 80 ? 'positive' : 'neutral'}
          comparison="all logged attendance"
          icon={<CheckCircle2 className="w-5 h-5 text-sky-600" />}
          description={`${data?.attendance.late ?? 0} late arrivals`}
        />
        <KpiCard
          title={t('hr.reports.averageRating')}
          value={
            data?.performance.average_rating !== null && data?.performance.average_rating !== undefined
              ? data.performance.average_rating
              : t('hr.reports.notRated')
          }
          change={`${data?.performance.reviews ?? 0} review${(data?.performance.reviews ?? 0) === 1 ? '' : 's'}`}
          changeType="neutral"
          comparison="out of 5"
          icon={<Star className="w-5 h-5 text-amber-500" />}
          description={t('hr.reports.ratingHint')}
        />
      </div>

      {/* Report Section Navigation */}
      <div className="flex items-center gap-2 border-b border-stone-200/80 pb-3 overflow-x-auto">
        {[
          { id: 'all', label: t('hr.reports.tabAll') },
          { id: 'headcount', label: t('hr.reports.tabHeadcount') },
          { id: 'recruitment', label: t('hr.reports.tabDepartments') },
          { id: 'attendance', label: t('hr.reports.tabAttendance') },
          { id: 'learning', label: t('hr.reports.tabTraining') },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() =>
              setActiveReportTab(tab.id as 'all' | 'headcount' | 'recruitment' | 'attendance' | 'learning')
            }
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
              activeReportTab === tab.id
                ? 'bg-brand-700 text-white shadow-xs'
                : 'text-stone-600 hover:bg-stone-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* REPORT 1 & 2: HEADCOUNT GROWTH & TENURE */}
      {(activeReportTab === 'all' || activeReportTab === 'headcount') && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card
            title={t('hr.reports.headcountByHire')}
            subtitle={t('hr.reports.trailing12')}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-3xs px-2"
                onClick={() =>
                  handleExportReport(
                    t('hr.reports.headcountTrend'),
                    history.map((h) => [h.label, String(h.hires), String(h.cumulative)]),
                    ['Month', 'Hires', t('hr.reports.cumulative')]
                  )
                }
              >
                CSV
              </Button>
            }
          >
            {history.length === 0 ? (
              <p className="py-10 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('hr.reports.noHireDatesRecorded')}
              </p>
            ) : (
              <div className="space-y-4">
                <div className="h-48 flex items-end justify-between gap-1.5 pt-6 pb-2 px-2 border-b border-stone-100">
                  {history.map((item) => {
                    const heightPct = Math.round((item.cumulative / peak) * 100);
                    return (
                      <div key={item.month} className="flex-1 flex flex-col items-center gap-1 group">
                        <span className="text-3xs font-extrabold text-brand-700 opacity-0 group-hover:opacity-100 transition-opacity">
                          {item.cumulative}
                        </span>
                        <div
                          className="w-full bg-brand-600 rounded-t-md group-hover:bg-brand-800 transition-all"
                          style={{ height: `${heightPct}%`, minHeight: '4px' }}
                        />
                        <span className="text-3xs font-semibold text-stone-400 group-hover:text-stone-900 mt-1">
                          {item.label.split(' ')[0]}
                        </span>
                      </div>
                    );
                  })}
                </div>

                <div className="flex items-center justify-between text-xs text-stone-500 pt-1">
                  <span>
                    Hired in window:{' '}
                    <strong className="text-brand-700">
                      {history.reduce((sum, h) => sum + h.hires, 0)}
                    </strong>
                  </span>
                  <span>
                    {t('hr.reports.currentTotal')} <strong className="text-stone-800">{headcount?.total ?? 0}</strong>
                  </span>
                </div>

                <p className="text-3xs text-stone-400 leading-relaxed pt-1 border-t border-stone-100">
                  This is a cumulative hire curve, not a net headcount series: the schema
                  records no termination or exit date, so departures cannot be subtracted.
                </p>
              </div>
            )}
          </Card>

          <Card
            title={t('hr.reports.tenureStatus')}
            subtitle={t('hr.reports.tenureStatusHint')}
            headerAction={
              <Badge variant="purple">
                {headcount?.avg_tenure_years !== null && headcount?.avg_tenure_years !== undefined
                  ? `${headcount.avg_tenure_years} yrs avg`
                  : t('hr.reports.noDates')}
              </Badge>
            }
          >
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-center">
                <div className="p-3.5 rounded-xl bg-brand-50 border border-brand-100">
                  <span className="text-3xs font-bold uppercase text-brand-700 block">
                    {t('hr.reports.averageTenure')}
                  </span>
                  <p className="text-3xl font-black text-brand-900 mt-1">
                    {headcount?.avg_tenure_years ?? '-'}
                  </p>
                  <span className="text-3xs text-brand-600 font-semibold">years since hire</span>
                </div>

                <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200">
                  <span className="text-3xs font-bold uppercase text-stone-500 block">
                    {t('hr.reports.activeEmployees')}
                  </span>
                  <p className="text-3xl font-black text-stone-700 mt-1">{headcount?.active ?? 0}</p>
                  <span className="text-3xs text-stone-400 font-medium">
                    of {headcount?.total ?? 0} total
                  </span>
                </div>
              </div>

              <div className="space-y-2 pt-1">
                {(headcount?.by_status ?? []).map((slice) => (
                  <BarRow
                    key={slice.status}
                    label={slice.status}
                    valueLabel={`${slice.count} (${slice.percentage}%)`}
                    percentage={slice.percentage}
                  />
                ))}
              </div>

              <NotTracked
                title={t('hr.reports.turnoverUnavailable')}
                reason="Counting departures needs a termination or exit date. No such column exists on employees, and employment_status only ever holds active in this database."
              />
            </div>
          </Card>
        </div>
      )}

      {/* REPORT 3 & 4: DEPARTMENT DISTRIBUTION & RECRUITMENT */}
      {(activeReportTab === 'all' || activeReportTab === 'recruitment') && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card
            title={t('hr.reports.deptAllocation')}
            subtitle={`Distribution of ${headcount?.total ?? 0} employees across ${
              data?.department_breakdown.length ?? 0
            } departments`}
          >
            {(data?.department_breakdown.length ?? 0) === 0 ? (
              <p className="py-8 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('hr.reports.noDeptEmployees')}
              </p>
            ) : (
              <div className="space-y-3">
                {data!.department_breakdown.map((dept) => (
                  <BarRow
                    key={dept.department}
                    label={dept.department}
                    valueLabel={`${dept.count} (${dept.percentage}%)`}
                    percentage={dept.percentage}
                    color={dept.color}
                  />
                ))}
              </div>
            )}
          </Card>

          {/* The work-mode panel is replaced by recruitment, which the schema
              can answer: jobs, applications and interviews are all real. */}
          <Card
            title={t('hr.reports.funnel')}
            subtitle={t('hr.reports.funnelHint')}
            headerAction={
              <Badge variant="purple">
                {data?.recruitment.conversion_rate ?? 0}% hired
              </Badge>
            }
          >
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 rounded-xl bg-sky-50 border border-sky-100">
                  <Users className="w-5 h-5 text-sky-600 mx-auto mb-1" />
                  <p className="text-xl font-extrabold text-stone-900">
                    {data?.recruitment.total_candidates ?? 0}
                  </p>
                  <p className="text-3xs font-semibold text-sky-700">{t('hr.reports.candidates')}</p>
                </div>
                <div className="p-3 rounded-xl bg-brand-50 border border-brand-100">
                  <Briefcase className="w-5 h-5 text-brand-600 mx-auto mb-1" />
                  <p className="text-xl font-extrabold text-stone-900">
                    {data?.recruitment.total_applications ?? 0}
                  </p>
                  <p className="text-3xs font-semibold text-brand-700">{t('hr.reports.applications')}</p>
                </div>
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-100">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 mx-auto mb-1" />
                  <p className="text-xl font-extrabold text-stone-900">
                    {data?.recruitment.hired ?? 0}
                  </p>
                  <p className="text-3xs font-semibold text-emerald-700">{t('hr.reports.hired')}</p>
                </div>
              </div>

              <div className="space-y-2 pt-1 border-t border-stone-100">
                {(data?.recruitment.stages ?? []).map((stage) => (
                  <BarRow
                    key={stage.token}
                    label={stage.stage}
                    valueLabel={`${stage.count} (${stage.rate})`}
                    percentage={
                      (stage.count /
                        Math.max(data?.recruitment.total_applications ?? 1, 1)) *
                      100
                    }
                    color={stage.color}
                  />
                ))}
              </div>

              <NotTracked
                title={t('hr.reports.workModeUnavailable')}
                reason="Remote, hybrid and on-site cannot be reported: the employees table has no work-mode, location or workplace column."
              />
            </div>
          </Card>
        </div>
      )}

      {/* REPORT 5 & 6: ATTENDANCE & LEAVE */}
      {(activeReportTab === 'all' || activeReportTab === 'attendance') && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card
            title={t('hr.reports.attendanceAudit')}
            subtitle={t('hr.reports.attendanceAuditHint')}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-3xs px-2"
                onClick={() =>
                  handleExportReport(
                    t('hr.reports.colAttendance'),
                    (data?.attendance.by_status ?? []).map((a) => [
                      a.status,
                      String(a.count),
                      `${a.percentage}%`,
                    ]),
                    [t('table.status'), t('hr.reports.colRecords'), 'Share']
                  )
                }
              >
                CSV
              </Button>
            }
          >
            {(data?.attendance.total_records ?? 0) === 0 ? (
              <p className="py-8 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('hr.reports.noAttendance')}
              </p>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 text-center">
                  <div className="p-3 bg-brand-50 rounded-xl border border-brand-100">
                    <span className="text-3xs font-bold uppercase text-brand-700">{t('hr.reports.onTimeRate')}</span>
                    <p className="text-2xl font-black text-brand-900 mt-0.5">
                      {data!.attendance.punctuality_rate}%
                    </p>
                    <span className="text-3xs text-brand-600">
                      {data!.attendance.present} present
                    </span>
                  </div>
                  <div className="p-3 bg-sky-50 rounded-xl border border-sky-100">
                    <span className="text-3xs font-bold uppercase text-sky-700">{t('hr.reports.avgWorked')}</span>
                    <p className="text-2xl font-black text-sky-900 mt-0.5">
                      {data!.attendance.avg_worked_hours ?? '-'}
                      {data!.attendance.avg_worked_hours !== null ? 'h' : ''}
                    </p>
                    <span className="text-3xs text-sky-600">check-out minus check-in</span>
                  </div>
                </div>

                <div className="space-y-2">
                  {data!.attendance.by_status.map((slice) => (
                    <BarRow
                      key={slice.status}
                      label={slice.status}
                      valueLabel={`${slice.count} (${slice.percentage}%)`}
                      percentage={slice.percentage}
                    />
                  ))}
                </div>

                <div className="p-3 rounded-lg border border-stone-100 bg-white text-xs flex justify-between items-center">
                  <span className="text-stone-600 font-medium">{t('hr.reports.totalLogged')}</span>
                  <span className="font-bold text-stone-900">
                    {data!.attendance.total_records}
                  </span>
                </div>
              </div>
            )}
          </Card>

          <Card
            title={t('hr.reports.leaveUtilization')}
            subtitle={`${data?.leave.total_days ?? 0} leave day${
              (data?.leave.total_days ?? 0) === 1 ? '' : 's'
            } across ${data?.leave.total_requests ?? 0} request${
              (data?.leave.total_requests ?? 0) === 1 ? '' : 's'
            }`}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-3xs px-2"
                onClick={() =>
                  handleExportReport(
                    'Leave',
                    (data?.leave.by_type ?? []).map((l) => [
                      l.leave_type,
                      String(l.requests),
                      String(l.days),
                      `${l.percentage}%`,
                    ]),
                    [t('hr.reports.colLeaveType'), t('hr.reports.colRequests'), 'Days', 'Share']
                  )
                }
              >
                CSV
              </Button>
            }
          >
            {(data?.leave.total_requests ?? 0) === 0 ? (
              <p className="py-8 text-center text-xs text-stone-400">
                {isLoading ? t('state.loading') : t('hr.reports.noLeave')}
              </p>
            ) : (
              <div className="space-y-4">
                <div className="space-y-3">
                  {data!.leave.by_type.map((lv) => (
                    <BarRow
                      key={lv.leave_type}
                      label={lv.leave_type}
                      valueLabel={`${lv.days} day${lv.days === 1 ? '' : 's'} (${lv.percentage}%)`}
                      percentage={lv.percentage}
                      color={lv.color}
                    />
                  ))}
                </div>

                <div className="pt-2 border-t border-stone-100 space-y-1.5">
                  {data!.leave.by_status.map((slice) => (
                    <div
                      key={slice.status}
                      className="flex justify-between items-center text-xs py-0.5"
                    >
                      <span className="text-stone-600 font-medium">{slice.status}</span>
                      <span className="font-bold text-stone-900">
                        {slice.count} ({slice.percentage}%)
                      </span>
                    </div>
                  ))}
                </div>

                <p className="text-3xs text-stone-400 leading-relaxed">
                  Days are an inclusive span of start_date to end_date. There is no
                  leave-entitlement table, so remaining balance is not reported.
                </p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* REPORT 7 & 8: TRAINING & PERFORMANCE */}
      {(activeReportTab === 'all' || activeReportTab === 'learning') && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card
            title={t('hr.reports.trainingByDept')}
            subtitle={`${data?.training.completed ?? 0} of ${
              data?.training.assignments ?? 0
            } assignments complete across ${data?.training.courses ?? 0} courses`}
            headerAction={
              <Badge variant={(data?.training.completion_rate ?? 0) >= 50 ? 'success' : 'neutral'}>
                {data?.training.completion_rate ?? 0}%
              </Badge>
            }
          >
            {(data?.training.assignments ?? 0) === 0 ? (
              <div className="py-6 space-y-3">
                <p className="text-center text-xs text-stone-400">
                  {isLoading
                    ? t('state.loading')
                    : t('hr.reports.noTraining')}
                </p>
                {!isLoading && (
                  <p className="text-center text-3xs text-stone-400">
                    {data?.training.courses ?? 0} course
                    {(data?.training.courses ?? 0) === 1 ? '' : 's'} in the catalogue.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {data!.training.by_department.map((dept) => (
                  <div key={dept.department} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-stone-800">{dept.department}</span>
                      <span
                        className={`font-black ${
                          dept.rate >= 90
                            ? 'text-emerald-600'
                            : dept.rate >= 50
                            ? 'text-brand-700'
                            : 'text-amber-600'
                        }`}
                      >
                        {dept.rate}% ({dept.completed}/{dept.assigned})
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-stone-100 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          dept.rate >= 90
                            ? 'bg-emerald-500'
                            : dept.rate >= 50
                            ? 'bg-brand-600'
                            : 'bg-amber-500'
                        }`}
                        style={{ width: `${dept.rate}%` }}
                      />
                    </div>
                  </div>
                ))}

                <div className="pt-2 border-t border-stone-100 space-y-1.5">
                  {data!.training.by_status.map((slice) => (
                    <div
                      key={slice.status}
                      className="flex justify-between items-center text-xs py-0.5"
                    >
                      <span className="text-stone-600 font-medium capitalize">
                        {slice.status.replace('_', ' ')}
                      </span>
                      <span className="font-bold text-stone-900">
                        {slice.count} ({slice.percentage}%)
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          <Card
            title={t('hr.reports.ratingDistribution')}
            subtitle={`${data?.performance.rated ?? 0} rated review${
              (data?.performance.rated ?? 0) === 1 ? '' : 's'
            } - ratings are whole numbers 1-5 (database CHECK constraint)`}
            headerAction={
              <Badge variant="purple">
                {data?.performance.average_rating ?? t('hr.reports.noData')}
              </Badge>
            }
          >
            {(data?.performance.rated ?? 0) === 0 ? (
              <div className="py-6 space-y-2">
                <GraduationCap className="w-6 h-6 text-stone-300 mx-auto" />
                <p className="text-center text-xs text-stone-400">
                  {isLoading
                    ? t('state.loading')
                    : t('hr.reports.noReviews')}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {data!.performance.by_rating.map((tier) => (
                  <BarRow
                    key={tier.rating}
                    label={`${tier.rating} - ${tier.label ?? t('hr.reports.unrated')}`}
                    valueLabel={`${tier.count} review${tier.count === 1 ? '' : 's'} (${tier.percentage}%)`}
                    percentage={tier.percentage}
                    color={tier.color}
                  />
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
};
