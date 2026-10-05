import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Briefcase,
  Search,
  Plus,
  Edit2,
  CheckCircle2,
  PauseCircle,
  XCircle,
  ArrowRight,
  Calendar,
  UserCircle2,
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
  DepartmentRecord,
  JobPayload,
  JobRecord,
  JobStatusToken,
} from '../../types';
import { useT } from '../../i18n';
import { documentLocale } from '../../i18n/format';

export interface RecruitmentJobsPageProps {
  /** Passed by App.tsx when navigating through to the candidates pipeline. */
  onViewCandidatesForJob?: (jobId: number) => void;
  onSelectJobCandidates?: (jobId: number) => void;
}

// =========================
// Status mapping
//
// PostgreSQL stores jobs.status as one of: open | on_hold | closed | draft.
// The UI shows the human labels; these helpers are the only place the two
// representations meet.
// =========================

const STATUS_TOKENS: JobStatusToken[] = ['open', 'on_hold', 'closed', 'draft'];

const jobRef = (id: number): string => `JOB-${String(id).padStart(3, '0')}`;

const formatPostedDate = (value: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleDateString(documentLocale() === 'ar' ? 'ar-u-nu-latn' : 'en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

interface JobFormState {
  title: string;
  department_id: string;
  status: JobStatusToken;
  description: string;
  requirements: string;
}

const EMPTY_FORM: JobFormState = {
  title: '',
  department_id: '',
  status: 'open',
  description: '',
  requirements: '',
};

export const RecruitmentJobsPage: React.FC<RecruitmentJobsPageProps> = ({
  onViewCandidatesForJob,
  onSelectJobCandidates,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingStatusId, setPendingStatusId] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDept, setSelectedDept] = useState('ALL');
  const [selectedStatus, setSelectedStatus] = useState('ALL');

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [currentJob, setCurrentJob] = useState<JobRecord | null>(null);

  // Form State
  const [formData, setFormData] = useState<JobFormState>(EMPTY_FORM);

  const openCandidates = (jobId: number) => {
    if (onViewCandidatesForJob) onViewCandidatesForJob(jobId);
    else if (onSelectJobCandidates) onSelectJobCandidates(jobId);
  };

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getJobs();
      setJobs(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('hr.jobs.loadErrorTitle');
      setLoadError(message);
      showToast(t('hr.jobs.loadFailed'), {
        message,
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadDepartments = useCallback(async () => {
    try {
      const data = (await SmartHRApi.getDepartments()) as DepartmentRecord[];
      setDepartments(data);
    } catch {
      // Non-fatal: the listing still renders, only the pickers stay empty.
      showToast(t('hr.jobs.deptLoadFailed'), {
        message: t('hr.jobs.deptIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadJobs();
    loadDepartments();
  }, [loadJobs, loadDepartments]);

  const departmentOptions = useMemo(
    () =>
      departments.map((d) => ({
        label: d.name,
        value: String(d.id),
      })),
    [departments]
  );

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        query === '' ||
        job.title.toLowerCase().includes(query) ||
        (job.department_name ?? '').toLowerCase().includes(query) ||
        (job.description ?? '').toLowerCase().includes(query) ||
        (job.requirements ?? '').toLowerCase().includes(query);

      const matchesDept =
        selectedDept === 'ALL' || String(job.department_id) === selectedDept;

      const matchesStatus =
        selectedStatus === 'ALL' || job.status === selectedStatus;

      return matchesSearch && matchesDept && matchesStatus;
    });
  }, [jobs, searchQuery, selectedDept, selectedStatus]);

  const handleOpenCreate = () => {
    setFormData({
      ...EMPTY_FORM,
      department_id: departments.length ? String(departments[0].id) : '',
    });
    setIsCreateModalOpen(true);
  };

  const handleOpenEdit = (job: JobRecord) => {
    setCurrentJob(job);
    setFormData({
      title: job.title,
      department_id: String(job.department_id),
      status: job.status,
      description: job.description ?? '',
      requirements: job.requirements ?? '',
    });
    setIsEditModalOpen(true);
  };

  const buildPayload = (): JobPayload | null => {
    if (!formData.title.trim()) {
      showToast(t('validation.error'), {
        message: t('hr.jobs.titleRequired'),
        type: 'error',
      });
      return null;
    }

    const departmentId = Number(formData.department_id);

    if (!departmentId) {
      showToast(t('validation.error'), {
        message: t('hr.jobs.deptRequired'),
        type: 'error',
      });
      return null;
    }

    return {
      title: formData.title.trim(),
      department_id: departmentId,
      description: formData.description.trim() || null,
      requirements: formData.requirements.trim() || null,
      status: formData.status,
    };
  };

  const handleSaveCreate = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      const created = await SmartHRApi.createJob(payload);
      setJobs((prev) => [created, ...prev]);
      setIsCreateModalOpen(false);

      showToast(t('hr.jobs.created'), {
        message: `Requisition ${jobRef(created.id)} (${created.title}) saved to the database.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('hr.jobs.createFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentJob) return;

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      const updated = await SmartHRApi.updateJob(currentJob.id, payload);

      setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));

      setIsEditModalOpen(false);

      showToast(t('hr.jobs.updated'), {
        message: `Updated requisition ${jobRef(updated.id)} successfully.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('hr.jobs.updateFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggleStatus = async (
    jobId: number,
    newStatus: JobStatusToken
  ) => {
    setPendingStatusId(jobId);

    try {
      const updated = await SmartHRApi.updateJobStatus(jobId, newStatus);

      setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));

      showToast(t('hr.jobs.statusUpdated'), {
        message: t('hr.jobs.statusSetTo', {
          ref: jobRef(updated.id),
          status: t(`status.job.${updated.status}`),
        }),
        type: 'info',
      });
    } catch (error) {
      showToast(t('hr.jobs.statusFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setPendingStatusId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('hr.jobs.title')}
        subtitle={t('hr.jobs.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {jobs.filter((j) => j.status === 'open').length} Active Requisitions
          </Badge>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={handleOpenCreate}
          >
            + Create Job Opening
          </Button>
        }
      />

      {/* Filter and Search Bar */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('hr.jobs.search')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <select
              value={selectedDept}
              onChange={(e) => setSelectedDept(e.target.value)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:ring-2 focus:ring-brand-600 focus:outline-none"
            >
              <option value="ALL">{t('hr.employees.allDepartments')}</option>
              {departments.map((d) => (
                <option key={d.id} value={String(d.id)}>
                  {d.name}
                </option>
              ))}
            </select>

            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:ring-2 focus:ring-brand-600 focus:outline-none"
            >
              <option value="ALL">{t('filter.allStatusesLabel')}</option>
              {STATUS_TOKENS.map((token) => (
                <option key={token} value={token}>
                  {t(`status.job.${token}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Jobs Grid */}
      <div className="grid grid-cols-1 gap-4">
        {isLoading ? (
          <Card>
            <div className="py-12 text-center text-stone-400">
              <Loader2 className="w-8 h-8 mx-auto mb-2 text-stone-300 animate-spin" />
              <p className="font-semibold text-stone-600">
                {t('hr.jobs.loading')}
              </p>
            </div>
          </Card>
        ) : loadError ? (
          <Card>
            <div className="py-12 text-center">
              <XCircle className="w-8 h-8 mx-auto mb-2 text-rose-300" />
              <p className="font-semibold text-stone-600">
                {t('hr.jobs.loadError')}
              </p>
              <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
              <div className="mt-4">
                <Button variant="outline" size="sm" onClick={loadJobs}>
                  {t('action.retry')}
                </Button>
              </div>
            </div>
          </Card>
        ) : filteredJobs.length === 0 ? (
          <Card>
            <div className="py-12 text-center text-stone-400">
              <Briefcase className="w-8 h-8 mx-auto mb-2 text-stone-300" />
              <p className="font-semibold text-stone-600">
                {t('hr.jobs.empty')}
              </p>
              <p className="text-2xs text-stone-400 mt-1">
                {jobs.length === 0
                  ? t('hr.jobs.emptyHint')
                  : t('hr.jobs.searchHint')}
              </p>
            </div>
          </Card>
        ) : (
          filteredJobs.map((job) => (
            <Card key={job.id} padding="none">
              <div className="p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-6 hover:bg-stone-50/40 transition-colors">
                {/* Left details */}
                <div className="space-y-2 min-w-0 flex-1">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="font-mono text-3xs font-bold px-2 py-0.5 rounded bg-stone-100 text-stone-600 border border-stone-200">
                      {jobRef(job.id)}
                    </span>
                    <h3 className="text-base font-extrabold text-stone-900 tracking-tight">
                      {job.title}
                    </h3>
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-3xs font-bold ${
                        job.status === 'open'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : job.status === 'on_hold'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : 'bg-stone-100 text-stone-600 border border-stone-200'
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          job.status === 'open'
                            ? 'bg-emerald-500'
                            : job.status === 'on_hold'
                            ? 'bg-amber-500'
                            : 'bg-stone-400'
                        }`}
                      />
                      {t(`status.job.${job.status}`)}
                    </span>
                  </div>

                  <p className="text-xs text-stone-500 line-clamp-1">
                    {job.description || t('hr.jobs.noOverview')}
                  </p>

                  <div className="flex items-center gap-4 text-xs text-stone-500 pt-1 flex-wrap">
                    <span className="font-medium text-brand-700">
                      {job.department_name ?? t('hr.jobs.unassigned')}
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5 text-stone-400" />
                      {t('hr.jobs.posted')} {formatPostedDate(job.created_at)}
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <UserCircle2 className="w-3.5 h-3.5 text-stone-400" />
                      Created by{' '}
                      <strong className="text-stone-800">
                        {job.created_by_email ?? t('hr.jobs.system')}
                      </strong>
                    </span>
                    {job.requirements ? (
                      <>
                        <span>•</span>
                        <span className="truncate max-w-xs">
                          Requirements:{' '}
                          <strong className="text-stone-800">
                            {job.requirements}
                          </strong>
                        </span>
                      </>
                    ) : null}
                  </div>
                </div>

                {/* Right: Pipeline Mini Bar & Actions */}
                <div className="flex flex-col sm:flex-row lg:flex-col items-start lg:items-end justify-between gap-4 shrink-0 border-t lg:border-t-0 pt-4 lg:pt-0">
                  {/* Pipeline Quick Count Pills */}
                  <div className="flex items-center gap-1 text-center">
                    <div className="px-2 py-1 bg-stone-100 rounded text-3xs">
                      <span className="font-bold block text-stone-800">
                        {job.pipeline_counts.applied}
                      </span>
                      <span className="text-stone-400 font-medium">{t('hr.jobs.stageApplied')}</span>
                    </div>
                    <div className="px-2 py-1 bg-sky-50 rounded text-3xs">
                      <span className="font-bold block text-sky-700">
                        {job.pipeline_counts.screening}
                      </span>
                      <span className="text-sky-500 font-medium">{t('hr.jobs.stageScreen')}</span>
                    </div>
                    <div className="px-2 py-1 bg-brand-50 rounded text-3xs">
                      <span className="font-bold block text-brand-700">
                        {job.pipeline_counts.interview}
                      </span>
                      <span className="text-brand-500 font-medium">
                        {t('hr.jobs.stageInterview')}
                      </span>
                    </div>
                    <div className="px-2 py-1 bg-emerald-50 rounded text-3xs">
                      <span className="font-bold block text-emerald-700">
                        {job.pipeline_counts.offer}
                      </span>
                      <span className="text-emerald-500 font-medium">{t('hr.jobs.stageOffer')}</span>
                    </div>
                  </div>

                  {/* Buttons */}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="purple-soft"
                      size="sm"
                      onClick={() => openCandidates(job.id)}
                      rightIcon={<ArrowRight className="w-3.5 h-3.5" data-flip-rtl />}
                    >
                      Candidates ({job.applications_count})
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      title={t('hr.jobs.edit')}
                      onClick={() => handleOpenEdit(job)}
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>

                    {job.status === 'open' ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-amber-600 hover:bg-amber-50"
                        title={t('hr.jobs.hold')}
                        disabled={pendingStatusId === job.id}
                        onClick={() => handleToggleStatus(job.id, 'on_hold')}
                      >
                        <PauseCircle className="w-4 h-4" />
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-emerald-600 hover:bg-emerald-50"
                        title={t('hr.jobs.reopen')}
                        disabled={pendingStatusId === job.id}
                        onClick={() => handleToggleStatus(job.id, 'open')}
                      >
                        <CheckCircle2 className="w-4 h-4" />
                      </Button>
                    )}

                    {job.status !== 'closed' ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-stone-500 hover:bg-stone-100"
                        title={t('hr.jobs.close')}
                        disabled={pendingStatusId === job.id}
                        onClick={() => handleToggleStatus(job.id, 'closed')}
                      >
                        <XCircle className="w-4 h-4" />
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Create Job Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title={t('hr.jobs.new')}
        subtitle={t('hr.jobs.newSubtitle')}
        size="lg"
      >
        <form onSubmit={handleSaveCreate} className="space-y-4">
          <Input
            label={t('hr.jobs.titleField')}
            required
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            placeholder={t('hr.jobs.titlePlaceholder')}
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('table.department')}
              required
              options={departmentOptions}
              value={formData.department_id}
              onChange={(e) =>
                setFormData({ ...formData, department_id: e.target.value })
              }
            />

            <Select
              label={t('table.status')}
              options={STATUS_TOKENS.map((token) => ({
                label: t(`status.job.${token}`),
                value: token,
              }))}
              value={formData.status}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  status: e.target.value as JobStatusToken,
                })
              }
            />
          </div>

          <Textarea
            label={t('hr.jobs.overview')}
            rows={3}
            value={formData.description}
            onChange={(e) =>
              setFormData({ ...formData, description: e.target.value })
            }
            placeholder={t('hr.jobs.overviewPlaceholder')}
          />

          <Textarea
            label={t('hr.jobs.requirements')}
            rows={3}
            value={formData.requirements}
            onChange={(e) =>
              setFormData({ ...formData, requirements: e.target.value })
            }
            placeholder={t('hr.jobs.requirementsPlaceholder')}
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setIsCreateModalOpen(false)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
            >
              {t('hr.jobs.publish')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Job Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title={t('hr.jobs.editTitle')}
        subtitle={
          currentJob
            ? `Editing ${jobRef(currentJob.id)} • ${currentJob.title}`
            : ''
        }
        size="lg"
      >
        <form onSubmit={handleSaveEdit} className="space-y-4">
          <Input
            label={t('hr.jobs.titleField')}
            required
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('table.department')}
              required
              options={departmentOptions}
              value={formData.department_id}
              onChange={(e) =>
                setFormData({ ...formData, department_id: e.target.value })
              }
            />

            <Select
              label={t('table.status')}
              options={STATUS_TOKENS.map((token) => ({
                label: t(`status.job.${token}`),
                value: token,
              }))}
              value={formData.status}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  status: e.target.value as JobStatusToken,
                })
              }
            />
          </div>

          <Textarea
            label={t('hr.jobs.overview')}
            rows={3}
            value={formData.description}
            onChange={(e) =>
              setFormData({ ...formData, description: e.target.value })
            }
          />

          <Textarea
            label={t('hr.jobs.requirements')}
            rows={3}
            value={formData.requirements}
            onChange={(e) =>
              setFormData({ ...formData, requirements: e.target.value })
            }
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setIsEditModalOpen(false)}
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
    </div>
  );
};
