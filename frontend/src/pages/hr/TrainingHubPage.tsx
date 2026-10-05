import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  BookOpen,
  Clock,
  Users,
  Search,
  Plus,
  Award,
  Edit2,
  XCircle,
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
  AssignmentStatus,
  EmployeeRosterEntry,
  EmployeeTrainingRecord,
  TrainingPayload,
  TrainingRecord,
} from '../../types';
import { useT } from '../../i18n';

// =========================
// Assignment status
//
// Stored in employee_trainings.status as lowercase tokens, matching that
// column's default.
// =========================

const STATUS_VALUES: AssignmentStatus[] = [
  'assigned',
  'in_progress',
  'completed',
  'cancelled',
];


const statusPillClass = (status: AssignmentStatus): string => {
  switch (status) {
    case 'completed':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    case 'in_progress':
      return 'bg-brand-50 text-brand-700 border border-brand-200';
    case 'cancelled':
      return 'bg-rose-50 text-rose-700 border border-rose-200';
    default:
      return 'bg-stone-100 text-stone-600 border border-stone-200';
  }
};

const formatDateTime = (value: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

interface TrainingFormState {
  title: string;
  provider: string;
  duration_hours: string;
  description: string;
}

const EMPTY_TRAINING_FORM: TrainingFormState = {
  title: '',
  provider: '',
  duration_hours: '',
  description: '',
};

interface AssignFormState {
  employee_id: string;
  training_id: string;
  status: AssignmentStatus;
}

export const TrainingHubPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [trainings, setTrainings] = useState<TrainingRecord[]>([]);
  const [assignments, setAssignments] = useState<EmployeeTrainingRecord[]>([]);
  const [roster, setRoster] = useState<EmployeeRosterEntry[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const [activeTab, setActiveTab] = useState<'catalog' | 'tracking'>('catalog');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('ALL');

  // Modals
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false);
  const [isCourseModalOpen, setIsCourseModalOpen] = useState(false);
  const [editingTraining, setEditingTraining] = useState<TrainingRecord | null>(
    null
  );

  const [courseForm, setCourseForm] = useState<TrainingFormState>(
    EMPTY_TRAINING_FORM
  );
  const [assignForm, setAssignForm] = useState<AssignFormState>({
    employee_id: '',
    training_id: '',
    status: 'assigned',
  });

  const loadAll = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const [courseData, assignmentData] = await Promise.all([
        SmartHRApi.getTrainings(),
        SmartHRApi.getEmployeeTrainings(),
      ]);
      setTrainings(courseData);
      setAssignments(assignmentData);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('hr.training.loadErrorTitle');
      setLoadError(message);
      showToast(t('hr.training.loadFailed'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadRoster = useCallback(async () => {
    try {
      const data = await SmartHRApi.getEmployeeRoster();
      setRoster(data);
    } catch {
      // Non-fatal: the catalog and tracking tabs still render.
      showToast(t('hr.training.rosterFailed'), {
        message: t('hr.training.rosterIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadAll();
    loadRoster();
  }, [loadAll, loadRoster]);

  const providers = useMemo(() => {
    const unique = new Set<string>();
    trainings.forEach((t) => {
      if (t.provider) unique.add(t.provider);
    });
    return Array.from(unique).sort();
  }, [trainings]);

  const rosterOptions = useMemo(
    () =>
      roster.map((e) => ({
        label: `${e.name}${e.department_name ? ` (${e.department_name})` : ''}`,
        value: String(e.id),
      })),
    [roster]
  );

  const trainingOptions = useMemo(
    () =>
      trainings.map((t) => ({
        label: `${t.title}${t.provider ? ` — ${t.provider}` : ''}`,
        value: String(t.id),
      })),
    [trainings]
  );

  const filteredTrainings = useMemo(() => {
    return trainings.filter((t) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        query === '' ||
        t.title.toLowerCase().includes(query) ||
        (t.description ?? '').toLowerCase().includes(query) ||
        (t.provider ?? '').toLowerCase().includes(query);

      const matchesProvider =
        selectedProvider === 'ALL' || t.provider === selectedProvider;

      return matchesSearch && matchesProvider;
    });
  }, [trainings, searchQuery, selectedProvider]);

  const filteredAssignments = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return assignments.filter(
      (a) =>
        query === '' ||
        (a.employee_name ?? '').toLowerCase().includes(query) ||
        (a.training_title ?? '').toLowerCase().includes(query) ||
        (a.department_name ?? '').toLowerCase().includes(query)
    );
  }, [assignments, searchQuery]);

  // ---------- Course catalog ----------

  const handleOpenCreateCourse = () => {
    setEditingTraining(null);
    setCourseForm(EMPTY_TRAINING_FORM);
    setIsCourseModalOpen(true);
  };

  const handleOpenEditCourse = (training: TrainingRecord) => {
    setEditingTraining(training);
    setCourseForm({
      title: training.title,
      provider: training.provider ?? '',
      duration_hours:
        training.duration_hours === null ? '' : String(training.duration_hours),
      description: training.description ?? '',
    });
    setIsCourseModalOpen(true);
  };

  const buildTrainingPayload = (): TrainingPayload | null => {
    if (!courseForm.title.trim()) {
      showToast(t('validation.error'), {
        message: t('hr.training.titleRequired'),
        type: 'error',
      });
      return null;
    }

    const hours = courseForm.duration_hours.trim();

    if (hours !== '' && (Number.isNaN(Number(hours)) || Number(hours) < 0)) {
      showToast(t('validation.error'), {
        message: t('hr.training.durationInvalid'),
        type: 'error',
      });
      return null;
    }

    return {
      title: courseForm.title.trim(),
      provider: courseForm.provider.trim() || null,
      duration_hours: hours === '' ? null : Number(hours),
      description: courseForm.description.trim() || null,
    };
  };

  const handleSaveCourse = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildTrainingPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      if (editingTraining) {
        const updated = await SmartHRApi.updateTraining(
          editingTraining.id,
          payload
        );
        setTrainings((prev) =>
          prev.map((t) => (t.id === updated.id ? updated : t))
        );
        showToast(t('hr.training.courseUpdated'), {
          message: `Curriculum "${updated.title}" saved.`,
          type: 'success',
        });
      } else {
        const created = await SmartHRApi.createTraining(payload);
        setTrainings((prev) => [created, ...prev]);
        showToast(t('hr.training.courseCreated'), {
          message: `New curriculum "${created.title}" published to catalog.`,
          type: 'success',
        });
      }

      setIsCourseModalOpen(false);
      setEditingTraining(null);
    } catch (error) {
      showToast(
        editingTraining ? t('hr.training.updateCourseFailed') : t('hr.training.createCourseFailed'),
        {
          message: error instanceof Error ? error.message : t('error.unexpected'),
          type: 'error',
        }
      );
    } finally {
      setIsSaving(false);
    }
  };

  // ---------- Assignments ----------

  const handleOpenAssign = (training?: TrainingRecord) => {
    setAssignForm({
      employee_id: roster.length ? String(roster[0].id) : '',
      training_id: training
        ? String(training.id)
        : trainings.length
        ? String(trainings[0].id)
        : '',
      status: 'assigned',
    });
    setIsAssignModalOpen(true);
  };

  const handleAssign = async (e: React.FormEvent) => {
    e.preventDefault();

    const employeeId = Number(assignForm.employee_id);
    const trainingId = Number(assignForm.training_id);

    if (!employeeId || !trainingId) {
      showToast(t('validation.error'), {
        message: t('hr.training.selectBoth'),
        type: 'error',
      });
      return;
    }

    setIsSaving(true);

    try {
      const created = await SmartHRApi.createEmployeeTraining({
        employee_id: employeeId,
        training_id: trainingId,
        status: assignForm.status,
      });

      setAssignments((prev) => [created, ...prev]);

      // Enrollment counters live on the training payload, so re-read them.
      const refreshed = await SmartHRApi.getTrainings();
      setTrainings(refreshed);

      setIsAssignModalOpen(false);

      showToast(t('hr.training.assigned'), {
        message: `Enrolled ${created.employee_name ?? 'employee'} into "${created.training_title ?? 'course'}".`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('hr.training.assignFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleChangeAssignmentStatus = async (
    assignment: EmployeeTrainingRecord,
    status: AssignmentStatus
  ) => {
    setPendingId(assignment.id);

    try {
      const updated = await SmartHRApi.updateEmployeeTrainingStatus(
        assignment.id,
        status
      );

      setAssignments((prev) =>
        prev.map((a) => (a.id === updated.id ? updated : a))
      );

      const refreshed = await SmartHRApi.getTrainings();
      setTrainings(refreshed);

      showToast(t('hr.training.assignmentUpdated'), {
        message: t('hr.training.statusSetTo', {
          name: updated.employee_name ?? t('table.employee'),
          status: t(`status.training.${updated.status}`),
        }),
        type: 'success',
      });
    } catch (error) {
      showToast(t('hr.training.assignmentFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('hr.training.title')}
        subtitle={t('hr.training.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {trainings.length} Active Courses
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={handleOpenCreateCourse}
            >
              + {t('hr.training.createCourseAction')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Award className="w-3.5 h-3.5" />}
              disabled={trainings.length === 0}
              onClick={() => handleOpenAssign()}
            >
              {t('hr.training.assignCourse')}
            </Button>
          </div>
        }
      />

      {/* Tabs & Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-stone-200/80 pb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('catalog')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
              activeTab === 'catalog'
                ? 'bg-brand-700 text-white shadow-xs'
                : 'text-stone-600 hover:bg-stone-100'
            }`}
          >
            Course Catalog ({trainings.length})
          </button>
          <button
            onClick={() => setActiveTab('tracking')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
              activeTab === 'tracking'
                ? 'bg-brand-700 text-white shadow-xs'
                : 'text-stone-600 hover:bg-stone-100'
            }`}
          >
            Employee Progress Tracking ({assignments.length})
          </button>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-stone-400 absolute start-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('hr.training.search')}
              className="ps-8 pe-3 py-1 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          {activeTab === 'catalog' && (
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              className="px-2.5 py-1 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="ALL">{t('hr.training.allProviders')}</option>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Loading / error states shared by both tabs */}
      {isLoading ? (
        <Card>
          <div className="py-12 text-center text-stone-400">
            <Loader2 className="w-8 h-8 mx-auto mb-2 text-stone-300 animate-spin" />
            <p className="font-semibold text-stone-600">
              {t('hr.training.loading')}
            </p>
          </div>
        </Card>
      ) : loadError ? (
        <Card>
          <div className="py-12 text-center">
            <XCircle className="w-8 h-8 mx-auto mb-2 text-rose-300" />
            <p className="font-semibold text-stone-600">
              {t('hr.training.loadError')}
            </p>
            <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
            <div className="mt-4">
              <Button variant="outline" size="sm" onClick={loadAll}>
                {t('action.retry')}
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <>
          {/* TAB 1: COURSE CATALOG */}
          {activeTab === 'catalog' &&
            (filteredTrainings.length === 0 ? (
              <Card>
                <div className="py-12 text-center text-stone-400">
                  <BookOpen className="w-8 h-8 mx-auto mb-2 text-stone-300" />
                  <p className="font-semibold text-stone-600">
                    {t('hr.training.emptyCatalog')}
                  </p>
                  <p className="text-2xs text-stone-400 mt-1">
                    {trainings.length === 0
                      ? t('hr.training.emptyCatalogHint')
                      : t('hr.training.searchHint')}
                  </p>
                </div>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {filteredTrainings.map((crs) => (
                  <Card key={crs.id} padding="none">
                    <div className="p-5 flex flex-col justify-between h-full space-y-4 hover:border-brand-200 transition-colors">
                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-3xs font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-stone-100 text-stone-600 truncate max-w-[60%]">
                            {crs.provider ?? t('hr.training.internal')}
                          </span>
                          <span className="text-3xs font-bold px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-200">
                            {crs.enrolled_count} enrolled
                          </span>
                        </div>

                        <h3 className="text-sm font-extrabold text-stone-900 tracking-tight leading-snug">
                          {crs.title}
                        </h3>

                        <p className="text-xs text-stone-500 line-clamp-2 leading-relaxed">
                          {crs.description ?? t('hr.training.noSummary')}
                        </p>
                      </div>

                      <div className="space-y-3 pt-3 border-t border-stone-100">
                        <div className="flex items-center justify-between text-2xs text-stone-500">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5 text-stone-400" />
                            {crs.duration_hours === null || crs.duration_hours === undefined
                              ? t('hr.training.notSpecified')
                              : t('hr.training.hours', { hours: crs.duration_hours })}
                          </span>
                          <span className="flex items-center gap-1">
                            <Users className="w-3.5 h-3.5 text-stone-400" />
                            {crs.enrolled_count} Enrolled
                          </span>
                          <span className="font-bold text-emerald-600">
                            {crs.completion_rate}% Done
                          </span>
                        </div>

                        {/* Completion bar - derived from assignment rows */}
                        <div className="w-full h-1.5 rounded-full bg-stone-100 overflow-hidden">
                          <div
                            className="h-full bg-brand-600 rounded-full"
                            style={{ width: `${crs.completion_rate}%` }}
                          />
                        </div>

                        <div className="flex items-center justify-between pt-1 gap-2">
                          <span className="text-3xs text-stone-400 truncate">
                            {crs.completed_count} of {crs.enrolled_count}{' '}
                            completed
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <Button
                              variant="outline"
                              size="sm"
                              title={t('hr.training.editCourse')}
                              onClick={() => handleOpenEditCourse(crs)}
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="purple-soft"
                              size="sm"
                              onClick={() => handleOpenAssign(crs)}
                            >
                              {t('hr.training.assign')}
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            ))}

          {/* TAB 2: EMPLOYEE PROGRESS TRACKING */}
          {activeTab === 'tracking' && (
            <Card padding="none">
              <div className="overflow-x-auto">
                <table className="w-full text-start text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                      <th className="py-3 px-4">{t('table.employee')}</th>
                      <th className="py-3 px-4">{t('table.department')}</th>
                      <th className="py-3 px-4">{t('hr.training.colCourse')}</th>
                      <th className="py-3 px-4">{t('hr.training.colStarted')}</th>
                      <th className="py-3 px-4">{t('hr.training.colCompleted')}</th>
                      <th className="py-3 px-4">{t('table.status')}</th>
                      <th className="py-3 px-4 text-end">{t('hr.training.updateStatus')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100 text-stone-700">
                    {filteredAssignments.length === 0 ? (
                      <tr>
                        <td
                          colSpan={7}
                          className="py-12 text-center text-stone-400"
                        >
                          <Award className="w-8 h-8 mx-auto mb-2 text-stone-300" />
                          <p className="font-semibold text-stone-600">
                            {t('hr.training.noAssignments')}
                          </p>
                          <p className="text-2xs text-stone-400 mt-1">
                            {t('hr.training.noAssignmentsHint')}
                          </p>
                        </td>
                      </tr>
                    ) : (
                      filteredAssignments.map((asg) => (
                        <tr key={asg.id} className="hover:bg-stone-50/60">
                          <td className="py-3.5 px-4 font-bold text-stone-900">
                            {asg.employee_name ?? t('hr.training.unknown')}
                            <span className="block text-3xs font-medium text-stone-400">
                              {asg.position_title ?? t('hr.training.noPosition')}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-stone-600 font-medium">
                            {asg.department_name ?? t('hr.training.unassigned')}
                          </td>
                          <td className="py-3.5 px-4 font-semibold text-brand-800">
                            {asg.training_title ?? t('hr.training.unknownCourse')}
                            <span className="block text-3xs font-medium text-stone-400">
                              {asg.training_provider ?? t('hr.training.internal')}
                              {asg.training_duration_hours !== null
                                ? ` • ${asg.training_duration_hours}h`
                                : ''}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-stone-500">
                            {formatDateTime(asg.started_at)}
                          </td>
                          <td className="py-3.5 px-4 text-stone-500">
                            {formatDateTime(asg.completed_at)}
                          </td>
                          <td className="py-3.5 px-4">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-bold ${statusPillClass(
                                asg.status
                              )}`}
                            >
                              {t(`status.training.${asg.status}`)}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-end">
                            <select
                              value={asg.status}
                              disabled={pendingId === asg.id}
                              onChange={(e) =>
                                handleChangeAssignmentStatus(
                                  asg,
                                  e.target.value as AssignmentStatus
                                )
                              }
                              className="px-2 py-1 text-3xs font-bold rounded border border-stone-200 bg-white text-stone-700 hover:border-brand-600 focus:outline-none disabled:opacity-50"
                            >
                              {STATUS_VALUES.map((st) => (
                                <option key={st} value={st}>
                                  {t(`status.training.${st}`)}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      {/* Assign Course Modal */}
      <Modal
        isOpen={isAssignModalOpen}
        onClose={() => setIsAssignModalOpen(false)}
        title={t('hr.training.assignTitle')}
        subtitle={t('hr.training.assignSubtitle')}
        size="md"
      >
        <form onSubmit={handleAssign} className="space-y-4">
          <Select
            label={t('hr.training.selectEmployee')}
            required
            options={rosterOptions}
            value={assignForm.employee_id}
            onChange={(e) =>
              setAssignForm({ ...assignForm, employee_id: e.target.value })
            }
          />

          <Select
            label={t('hr.training.curriculum')}
            required
            options={trainingOptions}
            value={assignForm.training_id}
            onChange={(e) =>
              setAssignForm({ ...assignForm, training_id: e.target.value })
            }
          />

          <Select
            label={t('hr.training.initialStatus')}
            options={STATUS_VALUES.map((s) => ({
              label: t(`status.training.${s}`),
              value: s,
            }))}
            value={assignForm.status}
            onChange={(e) =>
              setAssignForm({
                ...assignForm,
                status: e.target.value as AssignmentStatus,
              })
            }
            helperText="Start and completion timestamps are set from this status."
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setIsAssignModalOpen(false)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
            >
              {t('hr.training.confirmAssignment')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Create / Edit Course Modal */}
      <Modal
        isOpen={isCourseModalOpen}
        onClose={() => {
          setIsCourseModalOpen(false);
          setEditingTraining(null);
        }}
        title={
          editingTraining
            ? t('hr.training.editTitle')
            : t('hr.training.createTitle')
        }
        subtitle={
          editingTraining
            ? `Editing "${editingTraining.title}"`
            : t('hr.training.createSubtitle')
        }
        size="lg"
      >
        <form onSubmit={handleSaveCourse} className="space-y-4">
          <Input
            label={t('hr.training.curriculumTitle')}
            required
            value={courseForm.title}
            onChange={(e) =>
              setCourseForm({ ...courseForm, title: e.target.value })
            }
            placeholder={t('hr.training.curriculumPlaceholder')}
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('hr.training.provider')}
              value={courseForm.provider}
              onChange={(e) =>
                setCourseForm({ ...courseForm, provider: e.target.value })
              }
              placeholder={t('hr.training.providerPlaceholder')}
            />

            <Input
              label={t('hr.training.duration')}
              type="number"
              min="0"
              value={courseForm.duration_hours}
              onChange={(e) =>
                setCourseForm({ ...courseForm, duration_hours: e.target.value })
              }
              placeholder={t('hr.training.durationPlaceholder')}
            />
          </div>

          <Textarea
            label={t('hr.training.objectives')}
            rows={3}
            value={courseForm.description}
            onChange={(e) =>
              setCourseForm({ ...courseForm, description: e.target.value })
            }
            placeholder={t('hr.training.objectivesPlaceholder')}
          />

          <p className="text-3xs text-stone-400">
            Enrolment and completion figures are derived from assignment
            records, not stored on the course.
          </p>

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => {
                setIsCourseModalOpen(false);
                setEditingTraining(null);
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
              {editingTraining ? t('action.saveChanges') : t('hr.training.publish')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
