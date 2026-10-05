import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Briefcase,
  Plus,
  Search,
  Edit2,
  Trash2,
  Building,
  Download,
  Users,
  Loader2,
  XCircle,
} from 'lucide-react';
import {
  DepartmentRecord,
  PositionPayload,
  PositionRecord,
} from '../types';
import { SmartHRApi } from '../services/api';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input, Select } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';
import { EmptyState } from '../components/ui/EmptyState';
import { useT } from '../i18n';

interface PositionFormState {
  title: string;
  department_id: string;
}

const EMPTY_FORM: PositionFormState = {
  title: '',
  department_id: '',
};

export const PositionsPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [positions, setPositions] = useState<PositionRecord[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDept, setSelectedDept] = useState('all');

  // Modals
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingPos, setEditingPos] = useState<PositionRecord | null>(null);
  const [deletingPos, setDeletingPos] = useState<PositionRecord | null>(null);

  const [formData, setFormData] = useState<PositionFormState>(EMPTY_FORM);

  const loadPositions = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getPositions();
      setPositions(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('pos.loadErrorTitle');
      setLoadError(message);
      showToast(t('pos.errorLoading'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadDepartments = useCallback(async () => {
    try {
      const data = await SmartHRApi.getDepartments();
      setDepartments(data);
    } catch {
      // Non-fatal: the listing still renders, only the picker stays empty.
      showToast(t('pos.deptLoadFailed'), {
        message: t('pos.deptPickerIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadPositions();
    loadDepartments();
  }, [loadPositions, loadDepartments]);

  const departmentOptions = useMemo(
    () =>
      departments.map((d) => ({ label: d.name, value: String(d.id) })),
    [departments]
  );

  const filteredPositions = useMemo(() => {
    return positions.filter((p) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        !query ||
        p.title.toLowerCase().includes(query) ||
        (p.department_name ?? '').toLowerCase().includes(query);

      const matchesDept =
        selectedDept === 'all' || String(p.department_id) === selectedDept;

      return matchesSearch && matchesDept;
    });
  }, [positions, searchQuery, selectedDept]);

  const totalEmployees = positions.reduce(
    (acc, p) => acc + p.employee_count,
    0
  );
  const vacantPositions = positions.filter((p) => p.employee_count === 0).length;

  const handleOpenAdd = () => {
    setFormData({
      ...EMPTY_FORM,
      department_id: departments.length ? String(departments[0].id) : '',
    });
    setIsAddModalOpen(true);
  };

  const handleOpenEdit = (position: PositionRecord) => {
    setEditingPos(position);
    setFormData({
      title: position.title,
      department_id: String(position.department_id),
    });
  };

  const buildPayload = (): PositionPayload | null => {
    if (!formData.title.trim()) {
      showToast(t('validation.error'), {
        message: t('pos.titleRequired'),
        type: 'warning',
      });
      return null;
    }

    const departmentId = Number(formData.department_id);

    if (!departmentId) {
      showToast(t('validation.error'), {
        message: t('pos.selectDepartment'),
        type: 'warning',
      });
      return null;
    }

    return {
      title: formData.title.trim(),
      department_id: departmentId,
    };
  };

  const handleCreatePosition = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      const created = await SmartHRApi.createPosition(payload);
      setPositions((prev) => [...prev, created]);
      setIsAddModalOpen(false);

      showToast(t('pos.created'), {
        message: `"${created.title}" added to ${created.department_name}.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('pos.createFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleUpdatePosition = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPos) return;

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      const updated = await SmartHRApi.updatePosition(editingPos.id, payload);
      setPositions((prev) =>
        prev.map((p) => (p.id === updated.id ? updated : p))
      );
      setEditingPos(null);

      showToast(t('pos.updated'), {
        message: `"${updated.title}" now sits in ${updated.department_name}.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('action.updateFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeletePosition = async () => {
    if (!deletingPos) return;

    setIsSaving(true);

    try {
      await SmartHRApi.deletePosition(deletingPos.id);
      setPositions((prev) => prev.filter((p) => p.id !== deletingPos.id));

      showToast(t('pos.deleted'), {
        message: `"${deletingPos.title}" was removed.`,
        type: 'info',
      });
      setDeletingPos(null);
    } catch (error) {
      showToast(t('action.deleteFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleExportCSV = () => {
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      ['ID,Title,Department,Employees']
        .concat(
          filteredPositions.map(
            (p) =>
              `${p.id},"${p.title}",${p.department_name ?? ''},${p.employee_count}`
          )
        )
        .join('\n');

    const link = document.createElement('a');
    link.setAttribute('href', encodeURI(csvContent));
    link.setAttribute('download', 'smarthr_positions.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast(t('pos.exportStarted'), {
      message: `${filteredPositions.length} position(s) exported to CSV.`,
      type: 'info',
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('pos.title')}
        subtitle={t('pos.subtitle')}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Download className="w-3.5 h-3.5" />}
              onClick={handleExportCSV}
            >
              {t('pos.exportCsv')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={handleOpenAdd}
            >
              + Add Position
            </Button>
          </div>
        }
      />

      {/* Summary strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('pos.total')}
          </span>
          <p className="text-2xl font-black text-stone-900 mt-1">
            {positions.length}
          </p>
        </Card>
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('pos.departmentsCovered')}
          </span>
          <p className="text-2xl font-black text-stone-900 mt-1">
            {new Set(positions.map((p) => p.department_id)).size}
          </p>
        </Card>
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('pos.assignedHeadcount')}
          </span>
          <p className="text-2xl font-black text-stone-900 mt-1">
            {totalEmployees}
          </p>
        </Card>
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('pos.unstaffedRoles')}
          </span>
          <p className="text-2xl font-black text-amber-600 mt-1">
            {vacantPositions}
          </p>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('pos.search')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <select
            value={selectedDept}
            onChange={(e) => setSelectedDept(e.target.value)}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
          >
            <option value="all">{t('pos.allDepartments')}</option>
            {departments.map((d) => (
              <option key={d.id} value={String(d.id)}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {/* Positions Table */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3.5 px-4">{t('pos.colPosition')}</th>
                <th className="py-3.5 px-4">{t('table.department')}</th>
                <th className="py-3.5 px-4">{t('pos.colAssigned')}</th>
                <th className="py-3.5 px-4">{t('pos.colStaffing')}</th>
                <th className="py-3.5 px-4 text-end">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-stone-400">
                    <Loader2 className="w-7 h-7 mx-auto mb-2 text-stone-300 animate-spin" />
                    {t('pos.loading')}
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center">
                    <XCircle className="w-7 h-7 mx-auto mb-2 text-rose-300" />
                    <p className="font-semibold text-stone-600">
                      {t('pos.loadError')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                    <div className="mt-3">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={loadPositions}
                      >
                        {t('action.retry')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : filteredPositions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-4">
                    <EmptyState
                      icon={<Briefcase className="w-8 h-8 text-stone-300" />}
                      title={t('pos.empty')}
                      description={
                        positions.length === 0
                          ? t('pos.emptyHint')
                          : t('pos.searchHint')
                      }
                    />
                  </td>
                </tr>
              ) : (
                filteredPositions.map((pos) => (
                  <tr key={pos.id} className="hover:bg-stone-50/60">
                    <td className="py-3 px-4">
                      <span className="font-bold text-stone-900 flex items-center gap-2">
                        <Briefcase className="w-3.5 h-3.5 text-stone-400" />
                        {pos.title}
                      </span>
                      <span className="text-3xs text-stone-400 font-mono block ms-5.5">
                        POS-{String(pos.id).padStart(3, '0')}
                      </span>
                    </td>

                    <td className="py-3 px-4">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-3xs font-bold bg-brand-50 text-brand-700 border border-brand-200">
                        <Building className="w-3 h-3" />
                        {pos.department_name ?? t('pos.unassigned')}
                      </span>
                    </td>

                    <td className="py-3 px-4 font-semibold">
                      <span className="flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5 text-stone-400" />
                        {pos.employee_count}
                      </span>
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-3xs font-bold ${
                          pos.employee_count > 0
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            pos.employee_count > 0
                              ? 'bg-emerald-500'
                              : 'bg-amber-500'
                          }`}
                        />
                        {pos.employee_count > 0 ? t('pos.staffed') : t('pos.unstaffed')}
                      </span>
                    </td>

                    <td className="py-3 px-4 text-end">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          className="px-2 h-7"
                          title={t('pos.editAria')}
                          onClick={() => handleOpenEdit(pos)}
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="px-2 h-7 text-rose-600 hover:bg-rose-50"
                          title={t('pos.deleteAria')}
                          onClick={() => setDeletingPos(pos)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Add Position Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t('pos.add')}
        subtitle={t('pos.addSubtitle')}
        size="sm"
      >
        <form onSubmit={handleCreatePosition} className="space-y-4">
          <Input
            label={t('pos.titleField')}
            required
            value={formData.title}
            onChange={(e) =>
              setFormData({ ...formData, title: e.target.value })
            }
            placeholder={t('pos.titlePlaceholder')}
          />

          <Select
            label={t('table.department')}
            required
            options={departmentOptions}
            value={formData.department_id}
            onChange={(e) =>
              setFormData({ ...formData, department_id: e.target.value })
            }
            helperText="positions.department_id is required and must reference a real department."
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setIsAddModalOpen(false)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
            >
              {t('pos.create')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Position Modal */}
      <Modal
        isOpen={editingPos !== null}
        onClose={() => setEditingPos(null)}
        title={t('pos.edit')}
        subtitle={
          editingPos
            ? `${editingPos.employee_count} employee(s) currently assigned`
            : ''
        }
        size="sm"
      >
        <form onSubmit={handleUpdatePosition} className="space-y-4">
          <Input
            label={t('pos.titleField')}
            required
            value={formData.title}
            onChange={(e) =>
              setFormData({ ...formData, title: e.target.value })
            }
          />

          <Select
            label={t('table.department')}
            required
            options={departmentOptions}
            value={formData.department_id}
            onChange={(e) =>
              setFormData({ ...formData, department_id: e.target.value })
            }
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setEditingPos(null)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
            >
              {t('action.saveChanges')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={deletingPos !== null}
        onClose={() => setDeletingPos(null)}
        title={t('pos.delete')}
        subtitle={t('pos.cannotUndo')}
        size="sm"
      >
        <div className="space-y-4 text-xs">
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-900">
            <p className="font-bold">{deletingPos?.title}</p>
            <p className="text-2xs mt-1">
              {deletingPos?.department_name} •{' '}
              {deletingPos?.employee_count ?? 0} employee(s) assigned
            </p>
          </div>

          <p className="text-stone-600">
            Positions still assigned to employees cannot be deleted. Reassign
            those employees first.
          </p>

          <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeletingPos(null)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="danger"
              size="sm"
              isLoading={isSaving}
              onClick={handleDeletePosition}
            >
              {t('pos.delete')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
