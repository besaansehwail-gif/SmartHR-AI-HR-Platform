import React, { useState, useEffect, useMemo } from 'react';
import {
  Clock,
  Calendar as CalendarIcon,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Filter,
  ArrowUpDown,
  Download,
  Building2,
  Laptop,
  Check,
  ChevronLeft,
  ChevronRight,
  Info,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { AttendanceRecord, MyEmployeeIdentity } from '../../types';
import { SmartHRApi } from '../../services/api';
import { useT } from '../../i18n';

/** attendance.check_in / check_out are SQL time values (HH:MM:SS). */
const formatTime = (value: string | null): string => {
  if (!value) return '—';
  const [hh, mm] = value.split(':');
  const hour = Number(hh);
  if (Number.isNaN(hour)) return value;
  const suffix = hour >= 12 ? 'PM' : 'AM';
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}:${mm} ${suffix}`;
};

const dayOfWeek = (iso: string): string => {
  const d = new Date(iso + 'T00:00:00');
  return Number.isNaN(d.getTime())
    ? ''
    : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
};

const monthKey = (iso: string): string => iso.slice(0, 7);

export const MyAttendancePage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  // GET /attendance/me is scoped server-side to the employees row linked to
  // the signed-in account, so this page can only ever show one person.
  const [identity, setIdentity] = useState<MyEmployeeIdentity | null>(null);
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [linkError, setLinkError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [monthFilter, setMonthFilter] = useState<string>('all');

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [me, rows] = await Promise.all([
          SmartHRApi.getMyEmployee(),
          SmartHRApi.getMyAttendance(),
        ]);
        if (!cancelled) {
          setIdentity(me);
          setRecords(rows);
        }
      } catch (err) {
        if (!cancelled) {
          setLinkError(
            err instanceof Error ? err.message : t('emp.att.loadError')
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const months = useMemo(() => {
    const set = new Set(records.map((r) => monthKey(r.date)));
    return Array.from(set).sort().reverse();
  }, [records]);

  const statuses = useMemo(
    () => Array.from(new Set(records.map((r) => r.status))).sort(),
    [records]
  );

  const filteredHistory = useMemo(
    () =>
      records.filter((rec) => {
        const matchesStatus = statusFilter === 'all' || rec.status === statusFilter;
        const matchesMonth = monthFilter === 'all' || monthKey(rec.date) === monthFilter;
        return matchesStatus && matchesMonth;
      }),
    [records, statusFilter, monthFilter]
  );

  // Summary counted from the rows actually returned - no target or quota is
  // stored anywhere, so only what happened is reported.
  const summary = useMemo(() => {
    const scope = monthFilter === 'all' ? records : records.filter((r) => monthKey(r.date) === monthFilter);
    const present = scope.filter((r) => r.status === 'Present').length;
    const late = scope.filter((r) => r.status === 'Late').length;
    const absent = scope.filter((r) => r.status === 'Absent').length;
    const hours = scope.reduce((sum, r) => sum + (r.worked_hours ?? 0), 0);
    return {
      total: scope.length,
      present,
      late,
      absent,
      hours: Math.round(hours * 10) / 10,
      rate: scope.length ? Math.round((present / scope.length) * 1000) / 10 : 0,
    };
  }, [records, monthFilter]);

  const todayIso = new Date().toISOString().slice(0, 10);
  const todayRecord = records.find((r) => r.date === todayIso) ?? null;

  const handleExport = () => {
    if (filteredHistory.length === 0) {
      showToast(t('emp.att.nothingToExport'), { message: t('emp.att.noRowsMatch'), type: 'info' });
      return;
    }
    const header = 'Date,Day,CheckIn,CheckOut,WorkedHours,Status';
    const rows = filteredHistory.map((r) =>
      [r.date, dayOfWeek(r.date), r.check_in ?? '', r.check_out ?? '', r.worked_hours ?? '', r.status].join(',')
    );
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `My_Attendance_${todayIso}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast(t('emp.att.exported'), {
      message: `${filteredHistory.length} record(s) downloaded.`,
      type: 'success',
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.att.title')}
        subtitle={
          identity
            ? `Attendance recorded for ${identity.full_name} (${identity.department_name ?? 'no department'})`
            : t('emp.att.subtitle')
        }
        breadcrumbs={[
          { label: t('workspace.employee'), href: '#' },
          { label: t('emp.att.title'), active: true },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Download className="w-4 h-4" />}
              onClick={() => {
                showToast(t('emp.att.exported'), {
                  message: t('emp.att.exportedMessage'),
                  type: 'success',
                });
              }}
            >
              {t('emp.att.export')}
            </Button>
          </div>
        }
      />

      {/* An account with no linked employees row has nothing personal to
          show. Say so plainly rather than rendering an empty page. */}
      {linkError && (
        <Card>
          <div className="py-6 text-center">
            <Info className="w-6 h-6 text-stone-400 mx-auto mb-2" />
            <p className="text-sm font-bold text-stone-800">{t('emp.att.noneAvailable')}</p>
            <p className="text-xs text-stone-500 mt-1 max-w-xl mx-auto leading-relaxed">
              {linkError}
            </p>
          </div>
        </Card>
      )}

      {/* 1. Today's record, read from the attendance table */}
      {!linkError && (
        <div className="p-6 rounded-2xl bg-white border border-stone-200 shadow-sm relative overflow-hidden">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="purple">{todayIso}</Badge>
                <Badge variant={todayRecord ? 'success' : 'neutral'} dot>
                  {todayRecord ? `Logged as ${todayRecord.status}` : t('emp.att.noRecordToday')}
                </Badge>
                {identity?.position_title && (
                  <Badge variant="neutral">{identity.position_title}</Badge>
                )}
              </div>

              <h2 className="text-xl sm:text-2xl font-black text-stone-900 tracking-tight">
                {identity?.full_name ?? (isLoading ? t('state.loading') : t('emp.att.yourAttendance'))}
              </h2>
              <p className="text-xs sm:text-sm text-stone-500">
                Check-in and check-out times come straight from the attendance table.
                Worked hours are derived from the two, never stored.
              </p>

              <div className="flex items-center gap-6 pt-2 text-xs">
                <div>
                  <span className="text-stone-400 block text-3xs font-bold uppercase">{t('emp.att.checkIn')}</span>
                  <span className="text-sm font-black text-stone-900">
                    {formatTime(todayRecord?.check_in ?? null)}
                  </span>
                </div>
                <div className="h-8 w-px bg-stone-200" />
                <div>
                  <span className="text-stone-400 block text-3xs font-bold uppercase">{t('emp.att.checkOut')}</span>
                  <span className="text-sm font-black text-stone-900">
                    {formatTime(todayRecord?.check_out ?? null)}
                  </span>
                </div>
                <div className="h-8 w-px bg-stone-200" />
                <div>
                  <span className="text-stone-400 block text-3xs font-bold uppercase">{t('emp.att.workedHours')}</span>
                  <span className="text-sm font-black text-brand-700">
                    {todayRecord?.worked_hours !== null && todayRecord?.worked_hours !== undefined
                      ? `${todayRecord.worked_hours}h`
                      : '—'}
                  </span>
                </div>
              </div>
            </div>

            {/* Clocking in writes to the attendance table, which only Admin, HR
                and Managers may do (POST /attendance/ is roles 1,2,3). An
                employee therefore views their record here rather than creating
                one, and the buttons say so instead of pretending to work. */}
            <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 text-xs text-stone-600 max-w-xs leading-relaxed shrink-0">
              <span className="font-bold text-stone-800 block mb-1">{t('emp.att.selfCheckInOff')}</span>
              Attendance rows are created by HR or your manager. Ask them to correct a
              missing or wrong entry.
            </div>
          </div>
        </div>
      )}

      {/* 2. Summary, counted from the rows returned for this employee */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        <KpiCard
          title={t('emp.att.onTimeRate')}
          value={`${summary.rate}%`}
          change={`${summary.total} record${summary.total === 1 ? '' : 's'}`}
          changeType={summary.rate >= 80 ? 'positive' : 'neutral'}
          comparison="present / all logged"
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
        />
        <KpiCard
          title={t('emp.att.presentDays')}
          value={summary.present}
          change={monthFilter === 'all' ? 'all time' : monthFilter}
          changeType="positive"
          comparison="status Present"
          icon={<Clock className="w-5 h-5 text-brand-600" />}
        />
        <KpiCard
          title={t('emp.att.lateDays')}
          value={summary.late}
          change={summary.late > 0 ? 'logged late' : 'none'}
          changeType={summary.late > 0 ? 'negative' : 'positive'}
          comparison="status Late"
          icon={<AlertTriangle className="w-5 h-5 text-amber-500" />}
        />
        <KpiCard
          title={t('emp.att.absentDays')}
          value={summary.absent}
          change={summary.absent > 0 ? 'recorded' : 'none recorded'}
          changeType={summary.absent > 0 ? 'negative' : 'positive'}
          comparison="status Absent"
          icon={<XCircle className="w-5 h-5 text-stone-400" />}
        />
        <KpiCard
          title={t('emp.att.totalHours')}
          value={`${summary.hours} hrs`}
          change={
            summary.total
              ? `${Math.round((summary.hours / Math.max(summary.total, 1)) * 10) / 10} avg / day`
              : 'no data'
          }
          changeType="neutral"
          comparison="check-out minus check-in"
          icon={<CalendarIcon className="w-5 h-5 text-brand-600" />}
        />
      </div>

      {/* 3. Attendance history, this employee only */}
      <Card
        title={t('emp.att.logs')}
        subtitle={t('emp.att.logsHint')}
        headerAction={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={monthFilter}
              onChange={(e) => setMonthFilter(e.target.value)}
              className="px-2.5 py-1 text-xs rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="all">{t('emp.att.allMonths')}</option>
              {months.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2.5 py-1 text-xs rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="all">{t('filter.allStatusesLabel')}</option>
              {statuses.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          </div>
        }
      >
        <div className="overflow-x-auto -mx-6">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-y border-stone-200 bg-stone-50/70 text-stone-500 uppercase tracking-wider text-3xs font-bold">
                <th className="py-2.5 px-6">Date</th>
                <th className="py-2.5 px-4">{t('emp.att.checkIn')}</th>
                <th className="py-2.5 px-4">{t('emp.att.checkOut')}</th>
                <th className="py-2.5 px-4">{t('emp.att.workedHours')}</th>
                <th className="py-2.5 px-4">{t('table.status')}</th>
                <th className="py-2.5 px-6">{t('emp.att.recorded')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 font-medium">
              {filteredHistory.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-stone-400">
                    {isLoading
                      ? t('emp.att.loading')
                      : linkError
                      ? t('emp.att.notLinked')
                      : t('emp.att.empty')}
                  </td>
                </tr>
              )}

              {filteredHistory.map((rec) => (
                <tr key={rec.id} className="hover:bg-brand-50/30 transition-colors">
                  <td className="py-3 px-6 whitespace-nowrap">
                    <span className="font-bold text-stone-900">{rec.date}</span>
                    <span className="text-stone-400 text-3xs ms-1.5">({dayOfWeek(rec.date)})</span>
                  </td>
                  <td className="py-3 px-4 font-mono text-stone-700 whitespace-nowrap">
                    {formatTime(rec.check_in)}
                  </td>
                  <td className="py-3 px-4 font-mono text-stone-700 whitespace-nowrap">
                    {formatTime(rec.check_out)}
                  </td>
                  <td className="py-3 px-4 font-bold text-brand-700 whitespace-nowrap">
                    {rec.worked_hours !== null ? `${rec.worked_hours}h` : '—'}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    <Badge
                      variant={
                        rec.status === 'Present'
                          ? 'success'
                          : rec.status === 'Late'
                          ? 'warning'
                          : rec.status === 'On Leave'
                          ? 'purple'
                          : 'neutral'
                      }
                      dot={rec.status === 'Present' || rec.status === 'Late'}
                    >
                      {t(`status.attendance.${rec.status}`)}
                    </Badge>
                  </td>
                  <td className="py-3 px-6 text-2xs text-stone-500">
                    {rec.created_at ? rec.created_at.split('T')[0] : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
