import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  Eye,
  Check,
  X,
  Plus,
  ShieldAlert,
  Loader2,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input, Select, Textarea } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import {
  EmployeeRosterEntry,
  LeaveRequestPayload,
  LeaveRequestRecord,
  LeaveStatus,
} from '../../types';
import { useT } from '../../i18n';
import { documentLocale } from '../../i18n/format';

// =========================
// Leave status
//
// Stored in leave_requests.status as Title Case, matching existing rows.
// =========================

const STATUS_VALUES: LeaveStatus[] = [
  'Pending',
  'Approved',
  'Rejected',
  'Cancelled',
];

/** leave_type is free text in the database. These are the values already in
 *  use, plus the common remainder; anything unseen in the data is merged in
 *  at render time so no existing value is ever lost from the picker. */
const BASE_LEAVE_TYPES = [
  'Annual Leave',
  'Sick Leave',
  'Emergency Leave',
  'Unpaid Leave',
];

const formatDate = (value: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(
    documentLocale() === 'ar' ? 'ar-u-nu-latn' : 'en-GB',
    {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

const statusPillClass = (status: LeaveStatus): string => {
  switch (status) {
    case 'Approved':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    case 'Rejected':
      return 'bg-rose-50 text-rose-700 border border-rose-200';
    case 'Cancelled':
      return 'bg-stone-100 text-stone-600 border border-stone-200';
    default:
      return 'bg-amber-50 text-amber-700 border border-amber-200';
  }
};

interface LeaveFormState {
  employee_id: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: LeaveStatus;
}

const EMPTY_FORM: LeaveFormState = {
  employee_id: '',
  leave_type: 'Annual Leave',
  start_date: '',
  end_date: '',
  reason: '',
  status: 'Pending',
};

export const ManagerLeavePage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [leaves, setLeaves] = useState<LeaveRequestRecord[]>([]);
  const [roster, setRoster] = useState<EmployeeRosterEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [activeTab, setActiveTab] = useState<
    'Pending' | 'Approved' | 'Rejected' | 'ALL'
  >('Pending');

  // Modals
  const [selectedLeave, setSelectedLeave] = useState<LeaveRequestRecord | null>(
    null
  );
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isFormModalOpen, setIsFormModalOpen] = useState(false);
  const [editingLeave, setEditingLeave] = useState<LeaveRequestRecord | null>(
    null
  );
  const [formData, setFormData] = useState<LeaveFormState>(EMPTY_FORM);

  const loadLeaves = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getLeaveRequests();
      setLeaves(data);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t('mgr.leave.loadErrorTitle');
      setLoadError(message);
      showToast(t('mgr.leave.loadFailed'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadRoster = useCallback(async () => {
    try {
      const data = await SmartHRApi.getEmployeeRoster();
      setRoster(data);
    } catch {
      // Non-fatal: the queue still renders from the leave payload itself.
      showToast(t('mgr.leave.rosterFailed'), {
        message: t('mgr.leave.rosterIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadLeaves();
    loadRoster();
  }, [loadLeaves, loadRoster]);

  const pendingCount = leaves.filter((l) => l.status === 'Pending').length;
  const approvedCount = leaves.filter((l) => l.status === 'Approved').length;
  const rejectedCount = leaves.filter((l) => l.status === 'Rejected').length;

  const filteredLeaves = useMemo(
    () =>
      leaves.filter((l) => (activeTab === 'ALL' ? true : l.status === activeTab)),
    [leaves, activeTab]
  );

  const rosterOptions = useMemo(
    () =>
      roster.map((e) => ({
        label: `${e.name}${e.department_name ? ` (${e.department_name})` : ''}`,
        value: String(e.id),
      })),
    [roster]
  );

  // leave_type is free text. The four known values get a translation; a value
  // the database already holds but the dictionary does not is shown as stored,
  // never as a missing-key placeholder.
  const leaveTypeLabel = useCallback(
    (type: string): string =>
      (BASE_LEAVE_TYPES as string[]).includes(type) ? t(`leave.type.${type}`) : type,
    [t]
  );

  const leaveTypeOptions = useMemo(() => {
    const seen = new Set(BASE_LEAVE_TYPES);
    leaves.forEach((l) => {
      if (l.leave_type) seen.add(l.leave_type);
    });
    return Array.from(seen).map((type) => ({
      label: leaveTypeLabel(type),
      value: type,
    }));
  }, [leaves, leaveTypeLabel]);

  const applyUpdated = (updated: LeaveRequestRecord) => {
    setLeaves((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
    setSelectedLeave((prev) =>
      prev && prev.id === updated.id ? updated : prev
    );
  };

  const handleDecision = async (
    leave: LeaveRequestRecord,
    status: LeaveStatus
  ) => {
    setPendingId(leave.id);

    try {
      const updated = await SmartHRApi.updateLeaveStatus(leave.id, status);
      applyUpdated(updated);

      showToast(`Leave ${status}`, {
        message:
          status === 'Approved'
            ? `Time-off for ${updated.employee_name ?? 'employee'} signed off and recorded.`
            : `Request for ${updated.employee_name ?? 'employee'} set to ${status}.`,
        type: status === 'Approved' ? 'success' : 'warning',
      });

      return true;
    } catch (error) {
      showToast(t('mgr.leave.updateFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
      return false;
    } finally {
      setPendingId(null);
    }
  };

  const handleApproveAllPending = async () => {
    const pending = leaves.filter((l) => l.status === 'Pending');

    for (const leave of pending) {
      // Sequential so each decision is written and reflected in order.
      // eslint-disable-next-line no-await-in-loop
      await handleDecision(leave, 'Approved');
    }
  };

  const handleOpenDetails = (leave: LeaveRequestRecord) => {
    setSelectedLeave(leave);
    setIsDetailModalOpen(true);
  };

  const handleOpenCreate = () => {
    const today = new Date().toISOString().slice(0, 10);
    setEditingLeave(null);
    setFormData({
      ...EMPTY_FORM,
      employee_id: roster.length ? String(roster[0].id) : '',
      start_date: today,
      end_date: today,
    });
    setIsFormModalOpen(true);
  };

  const handleOpenEdit = (leave: LeaveRequestRecord) => {
    setEditingLeave(leave);
    setFormData({
      employee_id: String(leave.employee_id),
      leave_type: leave.leave_type,
      start_date: leave.start_date.slice(0, 10),
      end_date: leave.end_date.slice(0, 10),
      reason: leave.reason ?? '',
      status: leave.status,
    });
    setIsDetailModalOpen(false);
    setIsFormModalOpen(true);
  };

  const buildPayload = (): LeaveRequestPayload | null => {
    const employeeId = Number(formData.employee_id);

    if (!employeeId) {
      showToast(t('validation.error'), {
        message: t('mgr.leave.selectEmployee'),
        type: 'error',
      });
      return null;
    }

    if (!formData.leave_type.trim()) {
      showToast(t('validation.error'), {
        message: t('mgr.leave.typeRequired'),
        type: 'error',
      });
      return null;
    }

    if (!formData.start_date || !formData.end_date) {
      showToast(t('validation.error'), {
        message: t('mgr.leave.datesRequired'),
        type: 'error',
      });
      return null;
    }

    if (formData.end_date < formData.start_date) {
      showToast(t('validation.error'), {
        message: t('mgr.leave.endBeforeStart'),
        type: 'error',
      });
      return null;
    }

    return {
      employee_id: employeeId,
      leave_type: formData.leave_type,
      start_date: formData.start_date,
      end_date: formData.end_date,
      reason: formData.reason.trim() || null,
      status: formData.status,
    };
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      if (editingLeave) {
        const updated = await SmartHRApi.updateLeaveRequest(
          editingLeave.id,
          payload
        );
        applyUpdated(updated);
        showToast(t('mgr.leave.updated'), {
          message: `Request for ${updated.employee_name ?? 'employee'} saved.`,
          type: 'success',
        });
      } else {
        const created = await SmartHRApi.createLeaveRequest(payload);
        setLeaves((prev) => [created, ...prev]);
        showToast(t('mgr.leave.created'), {
          message: t('mgr.leave.createdMessage', {
            days: created.duration_days,
            type: leaveTypeLabel(created.leave_type),
            name: created.employee_name ?? t('table.employee'),
          }),
          type: 'success',
        });
      }

      setIsFormModalOpen(false);
      setEditingLeave(null);
    } catch (error) {
      showToast(
        editingLeave
          ? t('mgr.leave.updateFailed')
          : t('mgr.leave.createFailed'),
        {
          message: error instanceof Error ? error.message : t('error.unexpected'),
          type: 'error',
        }
      );
    } finally {
      setIsSaving(false);
    }
  };

  const tabButton = (
    tab: 'Pending' | 'Approved' | 'Rejected' | 'ALL',
    icon: React.ReactNode,
    label: React.ReactNode
  ) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`pb-3 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
        activeTab === tab
          ? 'border-brand-600 text-brand-700'
          : 'border-transparent text-stone-500 hover:text-stone-700'
      }`}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('mgr.leave.title')}
        subtitle={t('mgr.leave.subtitle')}
        badge={
          <Badge variant={pendingCount > 0 ? 'warning' : 'success'} dot>
            {pendingCount} Pending Decisions
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            {pendingCount > 0 && (
              <Button
                variant="outline"
                size="sm"
                leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                disabled={pendingId !== null}
                onClick={handleApproveAllPending}
              >
                Approve All Pending ({pendingCount})
              </Button>
            )}
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={handleOpenCreate}
            >
              {t('mgr.leave.newRequest')}
            </Button>
          </div>
        }
      />

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-stone-200">
        {tabButton(
          'Pending',
          <Clock className="w-3.5 h-3.5" />,
          <>
            {t('mgr.leave.tabPending')}
            {pendingCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-3xs font-extrabold bg-amber-100 text-amber-800">
                {pendingCount}
              </span>
            )}
          </>
        )}
        {tabButton(
          'Approved',
          <CheckCircle2 className="w-3.5 h-3.5" />,
          t('mgr.leave.tabApproved', { count: approvedCount })
        )}
        {tabButton(
          'Rejected',
          <XCircle className="w-3.5 h-3.5" />,
          t('mgr.leave.tabRejected', { count: rejectedCount })
        )}
        {tabButton('ALL', null, t('mgr.leave.tabAll', { count: leaves.length }))}
      </div>

      {/* Requests Table */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3.5 px-4">{t('table.employee')}</th>
                <th className="py-3.5 px-4">{t('mgr.leave.type')}</th>
                <th className="py-3.5 px-4">{t('mgr.leave.colDates')}</th>
                <th className="py-3.5 px-4">{t('mgr.leave.colDuration')}</th>
                <th className="py-3.5 px-4">{t('mgr.leave.colReason')}</th>
                <th className="py-3.5 px-4">{t('mgr.leave.colDecisionBy')}</th>
                <th className="py-3.5 px-4">{t('table.status')}</th>
                <th className="py-3.5 px-4 text-end">{t('mgr.leave.colActions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-stone-400">
                    <Loader2 className="w-7 h-7 mx-auto mb-2 text-stone-300 animate-spin" />
                    {t('mgr.leave.loading')}
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center">
                    <XCircle className="w-7 h-7 mx-auto mb-2 text-rose-300" />
                    <p className="font-semibold text-stone-600">
                      {t('mgr.leave.loadError')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                    <div className="mt-3">
                      <Button variant="outline" size="sm" onClick={loadLeaves}>
                        {t('action.retry')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : filteredLeaves.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-stone-400">
                    <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                    <p className="font-semibold text-stone-600">
                      {t('mgr.leave.empty')}
                    </p>
                  </td>
                </tr>
              ) : (
                filteredLeaves.map((leave) => (
                  <tr
                    key={leave.id}
                    className="hover:bg-stone-50/60 transition-colors"
                  >
                    {/* Employee */}
                    <td className="py-3 px-4">
                      <p className="font-bold text-stone-900 text-xs">
                        {leave.employee_name ?? t('mgr.leave.unknown')}
                      </p>
                      <p className="text-3xs text-stone-400">
                        {leave.position_title ?? t('mgr.leave.noPosition')} •{' '}
                        {leave.department_name ?? t('mgr.leave.unassigned')}
                      </p>
                    </td>

                    {/* Leave Type */}
                    <td className="py-3 px-4">
                      <span className="font-semibold text-stone-800">
                        {leaveTypeLabel(leave.leave_type)}
                      </span>
                      <span className="block text-3xs text-stone-400">
                        Applied: {formatDate(leave.created_at)}
                      </span>
                    </td>

                    {/* Dates */}
                    <td className="py-3 px-4 font-mono text-2xs text-stone-700">
                      {leave.start_date}{' '}
                      <span className="text-stone-400">&rarr;</span>{' '}
                      {leave.end_date}
                    </td>

                    {/* Duration */}
                    <td className="py-3 px-4">
                      <span className="font-extrabold text-stone-900">
                        {leave.duration_days} days
                      </span>
                      {leave.overlapping_count > 0 && (
                        <span className="block text-3xs text-amber-700 font-bold">
                          {leave.overlapping_count} overlap
                        </span>
                      )}
                    </td>

                    {/* Reason */}
                    <td className="py-3 px-4 max-w-[220px]">
                      <p className="text-2xs text-stone-600 truncate">
                        {leave.reason ?? '—'}
                      </p>
                    </td>

                    {/* Decision By */}
                    <td className="py-3 px-4 text-2xs text-stone-500">
                      {leave.approved_by_email ?? '—'}
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-3xs font-bold ${statusPillClass(
                          leave.status
                        )}`}
                      >
                        {t(`status.leave.${leave.status}`)}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-end">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs text-brand-700"
                          onClick={() => handleOpenDetails(leave)}
                        >
                          <Eye className="w-3.5 h-3.5 me-1" /> {t('mgr.leave.details')}
                        </Button>
                        {leave.status === 'Pending' && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-emerald-700 border-emerald-300 hover:bg-emerald-50 px-2"
                              disabled={pendingId === leave.id}
                              onClick={() => handleDecision(leave, 'Approved')}
                            >
                              <Check className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-rose-700 border-rose-300 hover:bg-rose-50 px-2"
                              disabled={pendingId === leave.id}
                              onClick={() => handleDecision(leave, 'Rejected')}
                            >
                              <X className="w-3.5 h-3.5" />
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Leave Details Modal */}
      {selectedLeave && (
        <Modal
          isOpen={isDetailModalOpen}
          onClose={() => setIsDetailModalOpen(false)}
          title={`Leave Request: ${selectedLeave.employee_name ?? t('table.employee')}`}
          subtitle={t('mgr.leave.detailSubtitle', {
            type: leaveTypeLabel(selectedLeave.leave_type),
            days: selectedLeave.duration_days,
          })}
          size="md"
        >
          <div className="space-y-4 text-xs">
            <div className="p-3 rounded-xl bg-brand-50/60 border border-brand-100 flex justify-between items-center gap-3">
              <div className="min-w-0">
                <p className="font-bold text-stone-900 text-sm">
                  {selectedLeave.employee_name ?? t('mgr.leave.unknown')}
                </p>
                <p className="text-2xs text-brand-800 truncate">
                  {selectedLeave.position_title ?? t('mgr.leave.noPosition')} •{' '}
                  {selectedLeave.department_name ?? t('mgr.leave.unassigned')}
                </p>
              </div>
              <span
                className={`px-2.5 py-1 rounded-full text-3xs font-extrabold shrink-0 ${statusPillClass(
                  selectedLeave.status
                )}`}
              >
                {selectedLeave.status}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-stone-50 border border-stone-200">
              <div>
                <span className="text-3xs text-stone-400 font-bold uppercase block">
                  {t('mgr.leave.colDates')}
                </span>
                <span className="font-mono font-bold text-stone-800">
                  {selectedLeave.start_date} to {selectedLeave.end_date}
                </span>
              </div>
              <div>
                <span className="text-3xs text-stone-400 font-bold uppercase block">
                  {t('mgr.leave.colDuration')}
                </span>
                <span className="font-bold text-stone-800">
                  {selectedLeave.duration_days} Calendar Days
                </span>
              </div>
              <div>
                <span className="text-3xs text-stone-400 font-bold uppercase block">
                  {t('mgr.leave.colDecisionBy')}
                </span>
                <span className="font-bold text-emerald-700">
                  {selectedLeave.approved_by_email ?? t('mgr.leave.notActioned')}
                </span>
              </div>
              <div>
                <span className="text-3xs text-stone-400 font-bold uppercase block">
                  {t('mgr.leave.appliedOn')}
                </span>
                <span className="font-mono text-stone-600">
                  {formatDate(selectedLeave.created_at)}
                </span>
              </div>
            </div>

            {selectedLeave.overlapping_count > 0 && (
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-2 text-2xs">
                <ShieldAlert className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                <div>
                  <strong className="font-bold block">
                    {t('mgr.leave.overlapWarning')}
                  </strong>
                  {selectedLeave.overlapping_count} other request
                  {selectedLeave.overlapping_count === 1 ? ' is' : 's are'} also
                  scheduled during this period. Ensure hand-off coverage.
                </div>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-2xs font-bold text-stone-700 block">
                {t('mgr.leave.employeeReason')}
              </label>
              <p className="p-3 rounded-lg bg-stone-50 border border-stone-200 text-stone-700 text-2xs leading-relaxed">
                {selectedLeave.reason ?? t('mgr.leave.noReason')}
              </p>
            </div>

            <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsDetailModalOpen(false)}
              >
                {t('action.close')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleOpenEdit(selectedLeave)}
              >
                {t('mgr.leave.editRequest')}
              </Button>
              {selectedLeave.status === 'Pending' && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-rose-700 border-rose-300 hover:bg-rose-50"
                    disabled={pendingId === selectedLeave.id}
                    onClick={async () => {
                      const ok = await handleDecision(
                        selectedLeave,
                        'Rejected'
                      );
                      if (ok) setIsDetailModalOpen(false);
                    }}
                  >
                    {t('mgr.leave.rejectRequest')}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={pendingId === selectedLeave.id}
                    onClick={async () => {
                      const ok = await handleDecision(
                        selectedLeave,
                        'Approved'
                      );
                      if (ok) setIsDetailModalOpen(false);
                    }}
                  >
                    {t('mgr.leave.approveRequest')}
                  </Button>
                </>
              )}
            </div>
          </div>
        </Modal>
      )}

      {/* Create / Edit Leave Request Modal */}
      <Modal
        isOpen={isFormModalOpen}
        onClose={() => {
          setIsFormModalOpen(false);
          setEditingLeave(null);
        }}
        title={editingLeave ? t('mgr.leave.editTitle') : t('mgr.leave.newTitle')}
        subtitle={
          editingLeave
            ? `Editing request #${editingLeave.id} • ${editingLeave.employee_name ?? t('table.employee')}`
            : t('mgr.leave.newSubtitle')
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

            <Select
              label={t('mgr.leave.type')}
              required
              options={leaveTypeOptions}
              value={formData.leave_type}
              onChange={(e) =>
                setFormData({ ...formData, leave_type: e.target.value })
              }
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Input
              label={t('mgr.leave.startDate')}
              type="date"
              required
              value={formData.start_date}
              onChange={(e) =>
                setFormData({ ...formData, start_date: e.target.value })
              }
            />

            <Input
              label={t('mgr.leave.endDate')}
              type="date"
              required
              value={formData.end_date}
              onChange={(e) =>
                setFormData({ ...formData, end_date: e.target.value })
              }
            />

            <Select
              label={t('table.status')}
              options={STATUS_VALUES.map((s) => ({
                label: t(`status.leave.${s}`),
                value: s,
              }))}
              value={formData.status}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  status: e.target.value as LeaveStatus,
                })
              }
            />
          </div>

          <Textarea
            label={t('mgr.leave.reason')}
            rows={3}
            value={formData.reason}
            onChange={(e) =>
              setFormData({ ...formData, reason: e.target.value })
            }
            placeholder={t('mgr.leave.reasonPlaceholder')}
          />

          <p className="text-3xs text-stone-400">
            Approving or rejecting records the acting user in approved_by.
            Duration is derived from the date range.
          </p>

          <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => {
                setIsFormModalOpen(false);
                setEditingLeave(null);
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
              {editingLeave ? t('action.saveChanges') : t('mgr.leave.createRequest')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
