import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Calendar,
  Plus,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  Eye,
  Info,
  CalendarDays,
  UserCheck,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { LeaveRequestRecord, MyEmployeeIdentity } from '../../types';
import { SmartHRApi } from '../../services/api';
import { useT } from '../../i18n';

/** The leave types already present in this database. The column is free
 *  text, so the picker is seeded from what exists plus the standard set
 *  rather than from a lookup table, which does not exist. */
const FALLBACK_LEAVE_TYPES = [
  'Annual Leave',
  'Sick Leave',
  'Emergency Leave',
  'Unpaid Leave',
];

export const MyLeavePage: React.FC = () => {
  const { t } = useT();

  // leave_type is free text; translate the four known values, show the rest
  // exactly as the database holds them.
  const leaveTypeLabel = (type: string): string =>
    (FALLBACK_LEAVE_TYPES as string[]).includes(type) ? t(`leave.type.${type}`) : type;
  const { showToast } = useToast();

  // GET /leave-requests/me returns only the rows belonging to the employees
  // record linked to the signed-in account.
  const [identity, setIdentity] = useState<MyEmployeeIdentity | null>(null);
  const [requests, setRequests] = useState<LeaveRequestRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Modals
  const [isRequestModalOpen, setIsRequestModalOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<LeaveRequestRecord | null>(null);

  // Form State
  const today = new Date().toISOString().slice(0, 10);
  const [formLeaveType, setFormLeaveType] = useState(FALLBACK_LEAVE_TYPES[0]);
  const [formStartDate, setFormStartDate] = useState(today);
  const [formEndDate, setFormEndDate] = useState(today);
  const [formReason, setFormReason] = useState('');

  const loadRequests = useCallback(async () => {
    try {
      const rows = await SmartHRApi.getMyLeaveRequests();
      setRequests(rows);
      setLinkError(null);
    } catch (err) {
      setLinkError(err instanceof Error ? err.message : t('emp.leave.loadError'));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const me = await SmartHRApi.getMyEmployee();
        if (!cancelled) setIdentity(me);
        await loadRequests();
      } catch (err) {
        if (!cancelled) {
          setLinkError(err instanceof Error ? err.message : t('emp.leave.loadErrorShort'));
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [loadRequests]);

  const leaveTypes = useMemo(() => {
    const seen = new Set(requests.map((r) => r.leave_type).filter(Boolean));
    FALLBACK_LEAVE_TYPES.forEach((t) => seen.add(t));
    return Array.from(seen).sort();
  }, [requests]);

  // Counted from the caller's own rows. There is no leave-entitlement table,
  // so what is reported is days taken and pending, never a remaining balance.
  const balances = useMemo(() => {
    const byType = new Map<string, { approved: number; pending: number; requests: number }>();

    requests.forEach((r) => {
      const key = r.leave_type || t('emp.leave.unspecified');
      const bucket = byType.get(key) ?? { approved: 0, pending: 0, requests: 0 };
      bucket.requests += 1;
      if (r.status === 'Approved') bucket.approved += r.duration_days;
      if (r.status === 'Pending') bucket.pending += r.duration_days;
      byType.set(key, bucket);
    });

    return Array.from(byType.entries())
      .map(([type, v]) => ({ type, ...v }))
      .sort((a, b) => b.approved - a.approved);
  }, [requests]);

  const calculateDays = (start: string, end: string) => {
    if (!start || !end) return 0;
    const d1 = new Date(start);
    const d2 = new Date(end);
    if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return 0;
    if (d2 < d1) return 0;
    return Math.round((d2.getTime() - d1.getTime()) / 86400000) + 1;
  };

  const handleOpenRequest = () => {
    setFormLeaveType(leaveTypes[0] ?? FALLBACK_LEAVE_TYPES[0]);
    setFormStartDate(today);
    setFormEndDate(today);
    setFormReason('');
    setIsRequestModalOpen(true);
  };

  // POST /leave-requests/me. No employee_id is sent - the server takes it from
  // the JWT - and the status is always Pending, so this cannot self-approve.
  const handleSubmitRequest = async (e: React.FormEvent) => {
    e.preventDefault();

    if (calculateDays(formStartDate, formEndDate) === 0) {
      showToast(t('emp.leave.checkDates'), {
        message: t('emp.leave.endBeforeStart'),
        type: 'error',
      });
      return;
    }

    setIsSaving(true);
    try {
      await SmartHRApi.createMyLeaveRequest({
        leave_type: formLeaveType,
        start_date: formStartDate,
        end_date: formEndDate,
        reason: formReason || null,
      });

      await loadRequests();
      setIsRequestModalOpen(false);
      showToast(t('emp.leave.submitted'), {
        message: t('emp.leave.submittedMessage'),
        type: 'success',
      });
    } catch (err) {
      showToast(t('emp.leave.submitFailed'), {
        message: err instanceof Error ? err.message : t('emp.leave.rejected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.leave.title')}
        subtitle={
          identity
            ? `Leave requests filed by ${identity.full_name}`
            : t('emp.leave.subtitle')
        }
        breadcrumbs={[
          { label: t('workspace.employee'), href: '#' },
          { label: t('emp.leave.title'), active: true },
        ]}
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={handleOpenRequest}
          >
            {t('emp.leave.requestLeave')}
          </Button>
        }
      />

      {linkError && (
        <Card>
          <div className="py-6 text-center">
            <Info className="w-6 h-6 text-stone-400 mx-auto mb-2" />
            <p className="text-sm font-bold text-stone-800">{t('emp.leave.noneAvailable')}</p>
            <p className="text-xs text-stone-500 mt-1 max-w-xl mx-auto leading-relaxed">
              {linkError}
            </p>
          </div>
        </Card>
      )}

      {/* 1. Days taken per type, counted from this employee's own requests.
             There is no entitlement table, so no allowance is shown. */}
      {!linkError && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {balances.length === 0 && (
            <div className="sm:col-span-2 lg:col-span-4 p-5 rounded-2xl bg-white border border-dashed border-stone-300 text-center">
              <CalendarDays className="w-6 h-6 text-stone-300 mx-auto mb-2" />
              <p className="text-xs font-bold text-stone-700">
                {isLoading ? t('state.loading') : t('emp.leave.empty')}
              </p>
              <p className="text-2xs text-stone-500 mt-1">
                {t('emp.leave.emptyHint')}
              </p>
            </div>
          )}

          {balances.map((bal) => {
            const total = bal.approved + bal.pending;
            return (
              <div
                key={bal.type}
                className="p-5 rounded-2xl bg-white border border-stone-200 shadow-sm flex flex-col justify-between gap-4"
              >
                <div className="space-y-1">
                  <span className="text-3xs font-extrabold uppercase tracking-wider text-stone-400">
                    {bal.type}
                  </span>
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-black text-stone-900">
                      {bal.approved}{' '}
                      <span className="text-xs font-semibold text-stone-400">days taken</span>
                    </span>
                    <span className="text-2xs font-bold text-stone-500">
                      {bal.requests} request{bal.requests === 1 ? '' : 's'}
                    </span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <div className="w-full h-2.5 rounded-full bg-stone-100 overflow-hidden flex">
                    <div
                      className="h-full bg-emerald-600"
                      style={{ width: `${total ? (bal.approved / total) * 100 : 0}%` }}
                    />
                    <div
                      className="h-full bg-amber-500"
                      style={{ width: `${total ? (bal.pending / total) * 100 : 0}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-3xs font-medium text-stone-500">
                    <span>Approved: {bal.approved}d</span>
                    {bal.pending > 0 && (
                      <span className="text-amber-600 font-bold">{bal.pending}d pending</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 2. Leave History & Status Table */}
      <Card
        title={t('emp.leave.history')}
        subtitle={t('emp.leave.historyHint')}
        headerAction={
          <Button variant="outline" size="sm" className="text-xs" onClick={handleOpenRequest}>
            {t('emp.leave.newRequest')}
          </Button>
        }
      >
        <div className="overflow-x-auto -mx-6">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-y border-stone-200 bg-stone-50/70 text-stone-500 uppercase tracking-wider text-3xs font-bold">
                <th className="py-2.5 px-6">{t('emp.leave.requestId')}</th>
                <th className="py-2.5 px-4">{t('mgr.leave.type')}</th>
                <th className="py-2.5 px-4">{t('emp.leave.dateRange')}</th>
                <th className="py-2.5 px-4">{t('mgr.leave.colDuration')}</th>
                <th className="py-2.5 px-4">{t('mgr.leave.reason')}</th>
                <th className="py-2.5 px-4">{t('table.status')}</th>
                <th className="py-2.5 px-6 text-end">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 font-medium">
              {requests.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-stone-400">
                    {isLoading
                      ? t('emp.leave.loading')
                      : linkError
                      ? t('emp.leave.notLinked')
                      : t('emp.leave.emptyFull')}
                  </td>
                </tr>
              )}

              {requests.map((req) => (
                <tr key={req.id} className="hover:bg-brand-50/30 transition-colors">
                  <td className="py-3 px-6 font-mono font-bold text-stone-900 whitespace-nowrap">
                    #{req.id}
                  </td>
                  <td className="py-3 px-4 font-bold text-stone-800 whitespace-nowrap">
                    {leaveTypeLabel(req.leave_type)}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap text-stone-600">
                    {req.start_date} → {req.end_date}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap font-bold text-brand-700">
                    {req.duration_days} day{req.duration_days === 1 ? '' : 's'}
                  </td>
                  <td className="py-3 px-4 max-w-xs truncate text-stone-500">
                    {req.reason ?? '—'}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    <Badge
                      variant={
                        req.status === 'Approved'
                          ? 'success'
                          : req.status === 'Pending'
                          ? 'warning'
                          : req.status === 'Cancelled'
                          ? 'neutral'
                          : 'danger'
                      }
                      dot={req.status === 'Pending'}
                    >
                      {t(`status.leave.${req.status}`)}
                    </Badge>
                  </td>
                  <td className="py-3 px-6 text-end whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs text-brand-700 font-semibold"
                      leftIcon={<Eye className="w-3.5 h-3.5" />}
                      onClick={() => setSelectedRequest(req)}
                    >
                      {t('mgr.leave.details')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 3. Request Leave Modal */}
      <Modal
        isOpen={isRequestModalOpen}
        onClose={() => setIsRequestModalOpen(false)}
        title={t('emp.leave.requestTimeOff')}
        subtitle={t('emp.leave.requestSubtitle')}
        size="md"
        footer={
          <div className="flex justify-end gap-2.5">
            <Button variant="outline" onClick={() => setIsRequestModalOpen(false)}>
              {t('action.cancel')}
            </Button>
            <Button variant="primary" onClick={handleSubmitRequest} disabled={isSaving}>
              {isSaving ? t('emp.leave.submitting') : t('emp.leave.submit')}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSubmitRequest} className="space-y-4">
          <div>
            <label className="block text-2xs font-bold text-stone-700 mb-1">
              {t('emp.leave.category')}
            </label>
            <select
              value={formLeaveType}
              onChange={(e) => setFormLeaveType(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-xl border border-stone-300 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {leaveTypes.map((type) => (
                <option key={type} value={type}>
                  {leaveTypeLabel(type)}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-2xs font-bold text-stone-700 mb-1">{t('mgr.leave.startDate')}</label>
              <Input
                type="date"
                value={formStartDate}
                onChange={(e) => setFormStartDate(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-2xs font-bold text-stone-700 mb-1">{t('mgr.leave.endDate')}</label>
              <Input
                type="date"
                value={formEndDate}
                onChange={(e) => setFormEndDate(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="p-3 rounded-xl bg-brand-50/60 border border-brand-100 flex items-center justify-between text-xs">
            <span className="text-brand-900 font-medium">{t('emp.leave.calendarDays')}</span>
            <span className="font-extrabold text-brand-700">
              {calculateDays(formStartDate, formEndDate)} Days
            </span>
          </div>

          <div>
            <label className="block text-2xs font-bold text-stone-700 mb-1">
              {t('emp.leave.reasonCoverage')}
            </label>
            <textarea
              rows={3}
              value={formReason}
              onChange={(e) => setFormReason(e.target.value)}
              placeholder={t('emp.leave.reasonPlaceholder')}
              className="w-full p-2.5 text-xs rounded-xl border border-stone-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
              required
            />
          </div>

          <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 text-2xs text-stone-600 flex items-start gap-2">
            <Info className="w-4 h-4 text-stone-400 shrink-0 mt-0.5" />
            <span>
              {t('emp.leave.savedWithStatus')} <strong>Pending</strong> and your employee id
              is taken from your session, so it can only ever be filed for you. A manager
              or HR records the decision.
            </span>
          </div>
        </form>
      </Modal>

      {/* 4. View Request Details Modal */}
      {selectedRequest && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedRequest(null)}
          title={`Leave Request Details — #${selectedRequest.id}`}
          subtitle={
            selectedRequest.created_at
              ? `Submitted on ${selectedRequest.created_at.split('T')[0]}`
              : t('emp.leave.noSubmissionDate')
          }
          size="md"
          footer={
            <div className="flex justify-between items-center w-full">
              {/* Changing a request status is a manager/HR action
                  (PATCH /leave-requests/{id}/status is roles 1,2,3), so an
                  employee cannot withdraw or approve their own request here. */}
              <span className="text-2xs text-stone-500">
                {selectedRequest.status === 'Pending'
                  ? t('emp.leave.awaitingDecision')
                  : `Decision recorded: ${selectedRequest.status}.`}
              </span>
              <Button variant="outline" onClick={() => setSelectedRequest(null)}>
                {t('action.close')}
              </Button>
            </div>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between p-3.5 rounded-xl bg-stone-50 border border-stone-200">
              <div>
                <span className="text-3xs font-bold text-stone-400 uppercase block">{t('mgr.leave.type')}</span>
                <span className="text-sm font-black text-stone-900">
                  {leaveTypeLabel(selectedRequest.leave_type)}
                </span>
              </div>
              <Badge
                variant={
                  selectedRequest.status === 'Approved'
                    ? 'success'
                    : selectedRequest.status === 'Pending'
                    ? 'warning'
                    : selectedRequest.status === 'Cancelled'
                    ? 'neutral'
                    : 'danger'
                }
              >
                {selectedRequest.status}
              </Badge>
            </div>

            <dl className="divide-y divide-stone-100">
              <div className="py-2.5 flex justify-between">
                <dt className="text-stone-500">{t('emp.leave.dateWindow')}</dt>
                <dd className="font-bold text-stone-900">
                  {selectedRequest.start_date} → {selectedRequest.end_date}
                </dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-stone-500">{t('emp.leave.totalDuration')}</dt>
                <dd className="font-bold text-brand-700">
                  {selectedRequest.duration_days} day
                  {selectedRequest.duration_days === 1 ? '' : 's'}
                </dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-stone-500">{t('emp.leave.overlapping')}</dt>
                <dd className="font-medium text-stone-900">
                  {selectedRequest.overlapping_count}
                </dd>
              </div>
              {selectedRequest.approved_by_email && (
                <div className="py-2.5 flex justify-between">
                  <dt className="text-stone-500">{t('emp.leave.decisionBy')}</dt>
                  <dd className="font-semibold text-stone-900">
                    {selectedRequest.approved_by_email}
                  </dd>
                </div>
              )}
            </dl>

            <div className="space-y-1">
              <span className="text-3xs font-bold text-stone-400 uppercase block">{t('emp.leave.yourNotes')}</span>
              <p className="p-3 rounded-xl bg-stone-50 border border-stone-200 text-stone-700">
                {selectedRequest.reason ?? t('emp.leave.noReason')}
              </p>
            </div>

            {/* leave_requests has no supervisor-remarks column, so nothing
                beyond the decision itself can be shown here. */}
          </div>
        </Modal>
      )}
    </div>
  );
};
