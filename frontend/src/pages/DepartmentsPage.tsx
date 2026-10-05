import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Building,
  Plus,
  Search,
  Users,
  Briefcase,
  LayoutGrid,
  List,
  Edit2,
  Trash2,
  ChevronRight,
  TrendingUp,
  Loader2,
  XCircle,
} from 'lucide-react';
import { DepartmentPayload, DepartmentRecord } from '../types';
import { SmartHRApi } from '../services/api';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';
import { EmptyState } from '../components/ui/EmptyState';
import { useT } from '../i18n';

export const DepartmentsPage: React.FC<{
  onNavigatePositions?: () => void;
}> = ({ onNavigatePositions }) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // View mode
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  // Search
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingDept, setEditingDept] = useState<DepartmentRecord | null>(null);
  const [deletingDept, setDeletingDept] = useState<DepartmentRecord | null>(
    null
  );

  // Form state - departments store only a name.
  const [formName, setFormName] = useState('');

  const loadDepartments = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getDepartments();
      setDepartments(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('dept.loadErrorTitle');
      setLoadError(message);
      showToast(t('dept.errorLoading'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadDepartments();
  }, [loadDepartments]);

  const filteredDepts = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return departments.filter(
      (d) => !query || d.name.toLowerCase().includes(query)
    );
  }, [departments, searchQuery]);

  const totalEmployees = departments.reduce(
    (acc, d) => acc + (d.employee_count ?? 0),
    0
  );
  const totalPositions = departments.reduce(
    (acc, d) => acc + (d.position_count ?? 0),
    0
  );
  const totalOpenJobs = departments.reduce(
    (acc, d) => acc + (d.open_job_count ?? 0),
    0
  );

  const handleOpenAdd = () => {
    setFormName('');
    setIsAddModalOpen(true);
  };

  const handleOpenEdit = (dept: DepartmentRecord) => {
    setEditingDept(dept);
    setFormName(dept.name);
  };

  const handleCreateDepartment = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formName.trim()) {
      showToast(t('validation.error'), {
        message: t('dept.nameRequired'),
        type: 'warning',
      });
      return;
    }

    setIsSaving(true);

    try {
      const payload: DepartmentPayload = { name: formName.trim() };
      const created = await SmartHRApi.createDepartment(payload);

      setDepartments((prev) =>
        [...prev, created].sort((a, b) => a.name.localeCompare(b.name))
      );
      setIsAddModalOpen(false);

      showToast(t('dept.created'), {
        message: `"${created.name}" was added to the organisation.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('dept.createFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleUpdateDepartment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingDept) return;

    if (!formName.trim()) {
      showToast(t('validation.error'), {
        message: t('dept.nameRequired'),
        type: 'warning',
      });
      return;
    }

    setIsSaving(true);

    try {
      const updated = await SmartHRApi.updateDepartment(editingDept.id, {
        name: formName.trim(),
      });

      setDepartments((prev) =>
        prev
          .map((d) => (d.id === updated.id ? updated : d))
          .sort((a, b) => a.name.localeCompare(b.name))
      );
      setEditingDept(null);

      showToast(t('dept.updated'), {
        message: `Renamed to "${updated.name}".`,
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

  const handleDeleteDepartment = async () => {
    if (!deletingDept) return;

    setIsSaving(true);

    try {
      await SmartHRApi.deleteDepartment(deletingDept.id);
      setDepartments((prev) => prev.filter((d) => d.id !== deletingDept.id));

      showToast(t('dept.deleted'), {
        message: `"${deletingDept.name}" was removed.`,
        type: 'info',
      });
      setDeletingDept(null);
    } catch (error) {
      showToast(t('action.deleteFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const renderStates = () => {
    if (isLoading) {
      return (
        <Card>
          <div className="py-12 text-center text-stone-400">
            <Loader2 className="w-8 h-8 mx-auto mb-2 text-stone-300 animate-spin" />
            <p className="font-semibold text-stone-600">
              {t('dept.loading')}
            </p>
          </div>
        </Card>
      );
    }

    if (loadError) {
      return (
        <Card>
          <div className="py-12 text-center">
            <XCircle className="w-8 h-8 mx-auto mb-2 text-rose-300" />
            <p className="font-semibold text-stone-600">
              {t('dept.loadError')}
            </p>
            <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
            <div className="mt-4">
              <Button variant="outline" size="sm" onClick={loadDepartments}>
                {t('action.retry')}
              </Button>
            </div>
          </div>
        </Card>
      );
    }

    if (filteredDepts.length === 0) {
      return (
        <EmptyState
          icon={<Building className="w-8 h-8 text-stone-300" />}
          title={t('dept.empty')}
          description={
            departments.length === 0
              ? t('dept.emptyHint')
              : t('dept.searchHint')
          }
        />
      );
    }

    return null;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('dept.title')}
        subtitle={t('dept.subtitle')}
        actions={
          <div className="flex items-center gap-2">
            {onNavigatePositions && (
              <Button
                variant="outline"
                size="sm"
                rightIcon={<ChevronRight className="w-3.5 h-3.5" data-flip-rtl />}
                onClick={onNavigatePositions}
              >
                {t('dept.viewPositions')}
              </Button>
            )}
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={handleOpenAdd}
            >
              + Add Department
            </Button>
          </div>
        }
      />

      {/* Summary strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            Departments
          </span>
          <p className="text-2xl font-black text-stone-900 mt-1">
            {departments.length}
          </p>
        </Card>
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('dept.totalHeadcount')}
          </span>
          <p className="text-2xl font-black text-stone-900 mt-1">
            {totalEmployees}
          </p>
        </Card>
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('dept.definedPositions')}
          </span>
          <p className="text-2xl font-black text-stone-900 mt-1">
            {totalPositions}
          </p>
        </Card>
        <Card>
          <span className="text-3xs font-bold uppercase text-stone-400 block">
            {t('dept.openRequisitions')}
          </span>
          <p className="text-2xl font-black text-emerald-700 mt-1">
            {totalOpenJobs}
          </p>
        </Card>
      </div>

      {/* Search & view toggle */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('dept.search')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-1 bg-stone-100 rounded-lg p-1">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-2.5 py-1 rounded-md text-xs font-bold transition-colors flex items-center gap-1.5 ${
                viewMode === 'cards'
                  ? 'bg-white text-stone-900 shadow-2xs'
                  : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              {t('dept.viewCards')}
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-2.5 py-1 rounded-md text-xs font-bold transition-colors flex items-center gap-1.5 ${
                viewMode === 'table'
                  ? 'bg-white text-stone-900 shadow-2xs'
                  : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <List className="w-3.5 h-3.5" />
              {t('dept.viewTable')}
            </button>
          </div>
        </div>
      </Card>

      {renderStates()}

      {/* Cards view */}
      {!isLoading && !loadError && filteredDepts.length > 0 && viewMode === 'cards' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredDepts.map((dept) => (
            <Card key={dept.id} padding="none">
              <div className="p-5 space-y-4 hover:border-brand-200 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-brand-100 text-brand-800 flex items-center justify-center shrink-0">
                      <Building className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-extrabold text-stone-900 truncate">
                        {dept.name}
                      </h3>
                      <span className="text-3xs text-stone-400 font-mono">
                        DEPT-{String(dept.id).padStart(3, '0')}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-2 rounded-lg bg-stone-50 border border-stone-200/70">
                    <span className="block font-black text-stone-900 text-sm">
                      {dept.employee_count ?? 0}
                    </span>
                    <span className="text-3xs text-stone-400 font-medium">
                      {t('dept.colEmployees')}
                    </span>
                  </div>
                  <div className="p-2 rounded-lg bg-stone-50 border border-stone-200/70">
                    <span className="block font-black text-stone-900 text-sm">
                      {dept.position_count ?? 0}
                    </span>
                    <span className="text-3xs text-stone-400 font-medium">
                      {t('dept.colPositions')}
                    </span>
                  </div>
                  <div className="p-2 rounded-lg bg-emerald-50 border border-emerald-200/70">
                    <span className="block font-black text-emerald-800 text-sm">
                      {dept.open_job_count ?? 0}
                    </span>
                    <span className="text-3xs text-emerald-600 font-medium">
                      {t('dept.colOpenJobs')}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-stone-100">
                  <span className="text-3xs text-stone-400 flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" />
                    {dept.job_count ?? 0} total requisition
                    {(dept.job_count ?? 0) === 1 ? '' : 's'}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      className="px-2 h-7"
                      title={t('dept.editAria')}
                      onClick={() => handleOpenEdit(dept)}
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="px-2 h-7 text-rose-600 hover:bg-rose-50"
                      title={t('dept.deleteAria')}
                      onClick={() => setDeletingDept(dept)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Table view */}
      {!isLoading && !loadError && filteredDepts.length > 0 && viewMode === 'table' && (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full text-start text-xs border-collapse">
              <thead>
                <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                  <th className="py-3.5 px-4">{t('table.department')}</th>
                  <th className="py-3.5 px-4">{t('dept.colEmployees')}</th>
                  <th className="py-3.5 px-4">{t('dept.colPositions')}</th>
                  <th className="py-3.5 px-4">{t('dept.colRequisitions')}</th>
                  <th className="py-3.5 px-4">{t('dept.colOpenJobs')}</th>
                  <th className="py-3.5 px-4 text-end">{t('table.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 text-stone-700">
                {filteredDepts.map((dept) => (
                  <tr key={dept.id} className="hover:bg-stone-50/60">
                    <td className="py-3 px-4">
                      <span className="font-bold text-stone-900 flex items-center gap-2">
                        <Building className="w-3.5 h-3.5 text-stone-400" />
                        {dept.name}
                      </span>
                      <span className="text-3xs text-stone-400 font-mono block ms-5.5">
                        DEPT-{String(dept.id).padStart(3, '0')}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-semibold">
                      <span className="flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5 text-stone-400" />
                        {dept.employee_count ?? 0}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-semibold">
                      <span className="flex items-center gap-1.5">
                        <Briefcase className="w-3.5 h-3.5 text-stone-400" />
                        {dept.position_count ?? 0}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-stone-600">
                      {dept.job_count ?? 0}
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-bold text-emerald-700">
                        {dept.open_job_count ?? 0}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-end">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          className="px-2 h-7"
                          onClick={() => handleOpenEdit(dept)}
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="px-2 h-7 text-rose-600 hover:bg-rose-50"
                          onClick={() => setDeletingDept(dept)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Add Department Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t('dept.add')}
        subtitle={t('dept.addSubtitle')}
        size="sm"
      >
        <form onSubmit={handleCreateDepartment} className="space-y-4">
          <Input
            label={t('dept.name')}
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder={t('dept.namePlaceholder')}
            helperText="Must be unique. Name is the only field this table stores."
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
              {t('dept.create')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Department Modal */}
      <Modal
        isOpen={editingDept !== null}
        onClose={() => setEditingDept(null)}
        title={t('dept.edit')}
        subtitle={
          editingDept
            ? `${editingDept.employee_count ?? 0} employee(s) • ${editingDept.position_count ?? 0} position(s)`
            : ''
        }
        size="sm"
      >
        <form onSubmit={handleUpdateDepartment} className="space-y-4">
          <Input
            label={t('dept.name')}
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            helperText="Renaming updates every employee, position and job that references it."
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setEditingDept(null)}
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
        isOpen={deletingDept !== null}
        onClose={() => setDeletingDept(null)}
        title={t('dept.delete')}
        subtitle={t('dept.cannotUndo')}
        size="sm"
      >
        <div className="space-y-4 text-xs">
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-900">
            <p className="font-bold">{deletingDept?.name}</p>
            <p className="text-2xs mt-1">
              {deletingDept?.employee_count ?? 0} employee(s) •{' '}
              {deletingDept?.position_count ?? 0} position(s) •{' '}
              {deletingDept?.job_count ?? 0} job(s)
            </p>
          </div>

          <p className="text-stone-600">
            Departments referenced by positions, employees or jobs cannot be
            deleted. Reassign those records first.
          </p>

          <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeletingDept(null)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="danger"
              size="sm"
              isLoading={isSaving}
              onClick={handleDeleteDepartment}
            >
              {t('dept.delete')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
