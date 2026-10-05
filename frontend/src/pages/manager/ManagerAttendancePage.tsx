import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Clock,
  CheckCircle2,
  Calendar,
  Search,
  Users,
  ShieldCheck,
  Edit2,
  Plus,
  XCircle,
  Loader2,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input, Select } from '../../components/ui/Input';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import {
  AttendancePayload,
  AttendanceRecord,
  AttendanceStatus,
  EmployeeRosterEntry,
} from '../../types';
import { useT } from '../../i18n';
import { documentLocale } from '../../i18n/format';

// =========================
// Attendance status
//
// Stored in attendance.status as Title Case, matching the existing rows.
// =========================

const STATUS_VALUES: AttendanceStatus[] = [
  'Present',
  'Late',
  'Absent',
  'On Leave',
  'Half Day',
];

/** `check_in` / `check_out` arrive as HH:MM:SS; the table and the time
 *  inputs both want HH:MM. */
const toHhMm = (value: string | null): string => {
  if (!value) return '';
  const match = /^(\d{2}):(\d{2})/.exec(value);
  return match ? `${match[1]}:${match[2]}` : value;
};

const displayTime = (value: string | null): string => toHhMm(value) || '—';

const formatDate = (value: string): string => {
  if (!value) return '—';
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(
    documentLocale() === 'ar' ? 'ar-u-nu-latn' : 'en-GB',
    {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }
  );
};

const statusPillClass = (status: AttendanceStatus): string => {
  switch (status) {
    case 'Present':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    case 'Late':
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    case 'On Leave':
      return 'bg-sky-50 text-sky-700 border border-sky-200';
    case 'Half Day':
      return 'bg-brand-50 text-brand-700 border border-brand-200';
    default:
      return 'bg-rose-50 text-rose-700 border border-rose-200';
  }
};

interface AttendanceFormState {
  employee_id: string;
  date: string;
  check_in: string;
  check_out: string;
  status: AttendanceStatus;
}

const EMPTY_FORM: AttendanceFormState = {
  employee_id: '',
  date: '',
  check_in: '',
  check_out: '',
  status: 'Present',
};

export const ManagerAttendancePage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [roster, setRoster] = useState<EmployeeRosterEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Filters
  const [selectedDate, setSelectedDate] = useState('ALL');
  const [employeeFilter, setEmployeeFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [targetRecord, setTargetRecord] = useState<AttendanceRecord | null>(
    null
  );
  const [formData, setFormData] = useState<AttendanceFormState>(EMPTY_FORM);

  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getAttendance();
      setRecords(data);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t('mgr.att.loadErrorTitle');
      setLoadError(message);
      showToast(t('mgr.att.loadFailed'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadRoster = useCallback(async () => {
    try {
      const data = await SmartHRApi.getEmployeeRoster();
      setRoster(data);
    } catch {
      // Non-fatal: the roster table still renders from the records payload.
      showToast(t('mgr.att.rosterFailed'), {
        message: t('mgr.att.rosterIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadRecords();
    loadRoster();
  }, [loadRecords, loadRoster]);

  const availableDates = useMemo(() => {
    const unique = Array.from(new Set(records.map((r) => r.date)));
    unique.sort((a, b) => (a < b ? 1 : -1));
    return unique;
  }, [records]);

  const rosterOptions = useMemo(
    () =>
      roster.map((e) => ({
        label: `${e.name}${e.department_name ? ` (${e.department_name})` : ''}`,
        value: String(e.id),
      })),
    [roster]
  );

  const filteredRecords = useMemo(() => {
    return records.filter((rec) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        query === '' ||
        (rec.employee_name ?? '').toLowerCase().includes(query) ||
        (rec.department_name ?? '').toLowerCase().includes(query) ||
        (rec.position_title ?? '').toLowerCase().includes(query);

      const matchesEmployee =
        employeeFilter === 'ALL' || String(rec.employee_id) === employeeFilter;

      const matchesStatus =
        statusFilter === 'ALL' || rec.status === statusFilter;

      const matchesDate = selectedDate === 'ALL' || rec.date === selectedDate;

      return matchesSearch && matchesEmployee && matchesStatus && matchesDate;
    });
  }, [records, searchQuery, employeeFilter, statusFilter, selectedDate]);

  // Metrics are computed over the visible (date-filtered) roster.
  const scopedRecords = useMemo(
    () =>
      selectedDate === 'ALL'
        ? records
        : records.filter((r) => r.date === selectedDate),
    [records, selectedDate]
  );

  const totalRecords = scopedRecords.length;
  const presentCount = scopedRecords.filter((r) => r.status === 'Present').length;
  const lateCount = scopedRecords.filter((r) => r.status === 'Late').length;
  const onLeaveCount = scopedRecords.filter((r) => r.status === 'On Leave').length;
  const absentCount = scopedRecords.filter((r) => r.status === 'Absent').length;

  const punctualityBase = totalRecords - onLeaveCount;
  const punctualityRate =
    punctualityBase > 0
      ? ((presentCount / punctualityBase) * 100).toFixed(1)
      : '0.0';

  const lateNames = scopedRecords
    .filter((r) => r.status === 'Late')
    .map((r) => r.employee_name ?? t('mgr.att.unknown'));

  const onLeaveNames = scopedRecords
    .filter((r) => r.status === 'On Leave')
    .map((r) => r.employee_name ?? t('mgr.att.unknown'));

  const handleOpenCreate = () => {
    setTargetRecord(null);
    setFormData({
      ...EMPTY_FORM,
      employee_id: roster.length ? String(roster[0].id) : '',
      date: new Date().toISOString().slice(0, 10),
    });
    setIsModalOpen(true);
  };

  const handleOpenAdjust = (rec: AttendanceRecord) => {
    setTargetRecord(rec);
    setFormData({
      employee_id: String(rec.employee_id),
      date: rec.date,
      check_in: toHhMm(rec.check_in),
      check_out: toHhMm(rec.check_out),
      status: rec.status,
    });
    setIsModalOpen(true);
  };

  const buildPayload = (): AttendancePayload | null => {
    const employeeId = Number(formData.employee_id);

    if (!employeeId) {
      showToast(t('validation.error'), {
        message: t('mgr.att.selectEmployee'),
        type: 'error',
      });
      return null;
    }

    if (!formData.date) {
      showToast(t('validation.error'), {
        message: t('mgr.att.dateRequired'),
        type: 'error',
      });
      return null;
    }

    return {
      employee_id: employeeId,
      date: formData.date,
      check_in: formData.check_in ? `${formData.check_in}:00` : null,
      check_out: formData.check_out ? `${formData.check_out}:00` : null,
      status: formData.status,
    };
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      if (targetRecord) {
        const updated = await SmartHRApi.updateAttendance(
          targetRecord.id,
          payload
        );
        setRecords((prev) =>
          prev.map((r) => (r.id === updated.id ? updated : r))
        );
        showToast(t('mgr.att.adjusted'), {
          message: `Clock record for ${updated.employee_name ?? 'employee'} updated.`,
          type: 'success',
        });
      } else {
        const created = await SmartHRApi.createAttendance(payload);
        setRecords((prev) => [created, ...prev]);
        showToast(t('mgr.att.logged'), {
          message: `Record saved for ${created.employee_name ?? 'employee'} on ${formatDate(created.date)}.`,
          type: 'success',
        });
      }

      setIsModalOpen(false);
      setTargetRecord(null);
    } catch (error) {
      showToast(
        targetRecord ? t('mgr.att.adjustFailed') : t('mgr.att.logFailed'),
        {
          message: error instanceof Error ? error.message : t('error.unexpected'),
          type: 'error',
        }
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('mgr.att.title')}
        subtitle={t('mgr.att.subtitle')}
        badge={
          <Badge variant="purple" dot>
            Daily Roster •{' '}
            {selectedDate === 'ALL' ? t('mgr.att.allDates') : formatDate(selectedDate)}
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="text-xs font-semibold px-3 py-2 rounded-lg border border-stone-200 bg-white text-stone-700 shadow-2xs focus:outline-none"
            >
              <option value="ALL">{t('mgr.att.allDates')}</option>
              {availableDates.map((d) => (
                <option key={d} value={d}>
                  {formatDate(d)}
                </option>
              ))}
            </select>

            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={handleOpenCreate}
            >
              {t('mgr.att.logAttendance')}
            </Button>
          </div>
        }
      />

      {/* Attendance Summary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        <KpiCard
          title={t('mgr.att.scheduledRoster')}
          value={totalRecords}
          change="Logged records"
          changeType="neutral"
          comparison={
            selectedDate === 'ALL' ? t('mgr.att.allDatesLower') : formatDate(selectedDate)
          }
          icon={<Users className="w-5 h-5 text-brand-600" />}
          description={`${roster.length} employees on file`}
        />
        <KpiCard
          title={t('mgr.att.presentActive')}
          value={presentCount}
          change="On-schedule"
          changeType="positive"
          comparison="Checked-in"
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
          description={`${presentCount} of ${totalRecords} records`}
        />
        <KpiCard
          title={t('mgr.att.lateCheckins')}
          value={lateCount}
          change={lateCount > 0 ? `${lateCount} report(s)` : 'None'}
          changeType={lateCount > 0 ? 'negative' : 'positive'}
          comparison={lateNames.slice(0, 2).join(', ') || t('mgr.att.noLate')}
          icon={<Clock className="w-5 h-5 text-amber-500" />}
          description={t('mgr.att.lateHint')}
        />
        <KpiCard
          title={t('mgr.att.onLeaveToday')}
          value={onLeaveCount}
          change="Approved time-off"
          changeType="neutral"
          comparison={onLeaveNames.slice(0, 2).join(', ') || t('mgr.att.nobodyAway')}
          icon={<Calendar className="w-5 h-5 text-sky-600" />}
          description={t('mgr.att.excused')}
        />
        <KpiCard
          title={t('mgr.att.punctuality')}
          value={`${punctualityRate}%`}
          change={`${absentCount} absent`}
          changeType={Number(punctualityRate) >= 90 ? 'positive' : 'negative'}
          comparison="Target > 90%"
          icon={<ShieldCheck className="w-5 h-5 text-brand-600" />}
          description={t('mgr.att.presentExpected')}
        />
      </div>

      {/* Highlights / Alert Banners */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-3.5 rounded-xl border border-amber-200/80 bg-amber-50/40 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-lg bg-amber-100 text-amber-800 shrink-0">
              <Clock className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="font-bold text-xs text-amber-950">
                {lateCount} Late Arrival{lateCount === 1 ? '' : 's'} Logged
              </p>
              <p className="text-2xs text-amber-800 truncate">
                {lateNames.length
                  ? lateNames.join(', ')
                  : t('mgr.att.noLateRecorded')}
              </p>
            </div>
          </div>
          {lateCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="text-xs bg-white shrink-0"
              onClick={() => {
                const lateRec = scopedRecords.find((r) => r.status === 'Late');
                if (lateRec) handleOpenAdjust(lateRec);
              }}
            >
              {t('mgr.att.adjustExcuse')}
            </Button>
          )}
        </div>

        <div className="p-3.5 rounded-xl border border-sky-200/80 bg-sky-50/40 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-lg bg-sky-100 text-sky-800 shrink-0">
              <Calendar className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="font-bold text-xs text-sky-950">
                {onLeaveCount} Excused Team Leave
                {onLeaveCount === 1 ? '' : 's'}
              </p>
              <p className="text-2xs text-sky-800 truncate">
                {onLeaveNames.length
                  ? onLeaveNames.join(', ')
                  : t('mgr.att.nobodyOnLeave')}
              </p>
            </div>
          </div>
          <Badge variant={absentCount > 0 ? 'warning' : 'info'}>
            {absentCount} Unexcused Absence{absentCount === 1 ? '' : 's'}
          </Badge>
        </div>
      </div>

      {/* Filter Toolbar */}
      <Card>
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('mgr.att.search')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto flex-wrap">
            <select
              value={employeeFilter}
              onChange={(e) => setEmployeeFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="ALL">{t('mgr.att.allTeamMembers')}</option>
              {roster.map((m) => (
                <option key={m.id} value={String(m.id)}>
                  {m.name}
                </option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="ALL">{t('filter.allStatusesLabel')}</option>
              {STATUS_VALUES.map((s) => (
                <option key={s} value={s}>
                  {t(`status.attendance.${s}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Daily Attendance Table */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3.5 px-4">{t('table.employee')}</th>
                <th className="py-3.5 px-4">{t('table.date')}</th>
                <th className="py-3.5 px-4">{t('mgr.att.colCheckIn')}</th>
                <th className="py-3.5 px-4">{t('mgr.att.colCheckOut')}</th>
                <th className="py-3.5 px-4">{t('mgr.att.hoursLogged')}</th>
                <th className="py-3.5 px-4">{t('mgr.att.attendanceStatus')}</th>
                <th className="py-3.5 px-4 text-end">{t('mgr.att.adjustment')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-stone-400">
                    <Loader2 className="w-7 h-7 mx-auto mb-2 text-stone-300 animate-spin" />
                    {t('mgr.att.loading')}
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center">
                    <XCircle className="w-7 h-7 mx-auto mb-2 text-rose-300" />
                    <p className="font-semibold text-stone-600">
                      {t('mgr.att.loadError')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                    <div className="mt-3">
                      <Button variant="outline" size="sm" onClick={loadRecords}>
                        {t('action.retry')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-stone-400">
                    {t('mgr.att.empty')}
                  </td>
                </tr>
              ) : (
                filteredRecords.map((rec) => (
                  <tr
                    key={rec.id}
                    className="hover:bg-stone-50/60 transition-colors"
                  >
                    <td className="py-3 px-4 font-bold text-stone-900">
                      {rec.employee_name ?? t('mgr.att.unknown')}
                      <span className="block text-3xs font-medium text-stone-400">
                        {rec.department_name ?? t('mgr.att.unassigned')}
                        {rec.position_title ? ` • ${rec.position_title}` : ''}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-stone-600 font-mono text-2xs">
                      {rec.date}
                    </td>
                    <td className="py-3 px-4 font-bold">
                      <span
                        className={
                          rec.status === 'Late'
                            ? 'text-amber-700 font-black'
                            : 'text-stone-900'
                        }
                      >
                        {displayTime(rec.check_in)}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-stone-500">
                      {displayTime(rec.check_out)}
                    </td>
                    <td className="py-3 px-4 font-semibold text-stone-700">
                      {rec.worked_hours !== null ? `${rec.worked_hours} h` : '—'}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-3xs font-bold ${statusPillClass(
                          rec.status
                        )}`}
                      >
                        {t(`status.attendance.${rec.status}`)}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-brand-700 hover:bg-brand-50"
                        onClick={() => handleOpenAdjust(rec)}
                      >
                        <Edit2 className="w-3.5 h-3.5 me-1" /> {t('mgr.att.adjust')}
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Log / Adjust Clock Record Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setTargetRecord(null);
        }}
        title={
          targetRecord
            ? `Adjust Clock Record: ${targetRecord.employee_name ?? t('table.employee')}`
            : t('mgr.att.logTitle')
        }
        subtitle={
          targetRecord
            ? t('mgr.att.currentCheckIn', {
                time: displayTime(targetRecord.check_in),
                status: t(`status.attendance.${targetRecord.status}`),
              })
            : t('mgr.att.logSubtitle')
        }
        size="md"
      >
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('table.employee')}
              required
              options={rosterOptions}
              value={formData.employee_id}
              onChange={(e) =>
                setFormData({ ...formData, employee_id: e.target.value })
              }
            />

            <Input
              label={t('table.date')}
              type="date"
              required
              value={formData.date}
              onChange={(e) =>
                setFormData({ ...formData, date: e.target.value })
              }
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Input
              label={t('mgr.att.colCheckIn')}
              type="time"
              value={formData.check_in}
              onChange={(e) =>
                setFormData({ ...formData, check_in: e.target.value })
              }
            />

            <Input
              label={t('mgr.att.colCheckOut')}
              type="time"
              value={formData.check_out}
              onChange={(e) =>
                setFormData({ ...formData, check_out: e.target.value })
              }
            />

            <Select
              label={t('table.status')}
              options={STATUS_VALUES.map((s) => ({
                label: t(`status.attendance.${s}`),
                value: s,
              }))}
              value={formData.status}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  status: e.target.value as AttendanceStatus,
                })
              }
            />
          </div>

          <p className="text-3xs text-stone-400">
            Hours logged are derived from check-in and check-out; they are not
            stored separately.
          </p>

          <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => {
                setIsModalOpen(false);
                setTargetRecord(null);
              }}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
            >
              {targetRecord ? t('mgr.att.saveAdjustment') : t('mgr.att.logRecord')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
