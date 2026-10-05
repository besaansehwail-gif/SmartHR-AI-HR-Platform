import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  UserCheck,
  Search,
  FileText,
  XCircle,
  Plus,
  Edit2,
  MapPin,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input, Select } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import { CvAnalysisModal } from '../../components/ai/CvAnalysisModal';
import {
  CandidateRecord,
  CandidateStageToken,
  JobRecord,
} from '../../types';
import { useT } from '../../i18n';

export interface CandidatesPageProps {
  initialJobFilter?: string;
  onScheduleInterview?: (candidateId: string) => void;
}

// =========================
// Stage mapping
//
// The pipeline stage lives in applications.status (varchar), not on the
// candidate row. These are the tokens the backend accepts; the UI shows
// the human labels.
// =========================

const STAGE_TOKENS: CandidateStageToken[] = [
  'applied',
  'screening',
  'shortlisted',
  'interview',
  'assessment',
  'offer',
  'hired',
  'rejected',
];

/*
 * Stage labels come from `status.stage.<token>` in the dictionary - the same
 * eight tokens `applications.status` stores. The tokens themselves never
 * change; only how they are shown does.
 */

const candidateRef = (id: number): string => `CAN-${String(id).padStart(3, '0')}`;

const formatDate = (value: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

const formatDateTime = (value: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const initialsOf = (fullName: string): string =>
  fullName
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

const getStageBadgeColor = (stage: CandidateStageToken | null) => {
  switch (stage) {
    case 'applied':
      return 'bg-stone-100 text-stone-700 border-stone-200';
    case 'screening':
      return 'bg-sky-50 text-sky-700 border-sky-200';
    case 'shortlisted':
      return 'bg-brand-50 text-brand-700 border-brand-200';
    case 'interview':
      return 'bg-brand-50 text-brand-700 border-brand-200';
    case 'assessment':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'offer':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'hired':
      return 'bg-emerald-100 text-emerald-800 border-emerald-300 font-bold';
    case 'rejected':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    default:
      return 'bg-stone-100 text-stone-500 border-stone-200';
  }
};

interface CandidateFormState {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  location: string;
  job_id: string;
  stage: CandidateStageToken;
}

const EMPTY_FORM: CandidateFormState = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  location: '',
  job_id: '',
  stage: 'applied',
};

export const CandidatesPage: React.FC<CandidatesPageProps> = ({
  initialJobFilter = 'ALL',
  onScheduleInterview,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingStageId, setPendingStageId] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedJob, setSelectedJob] = useState(initialJobFilter);
  const [selectedStage, setSelectedStage] = useState('ALL');

  // Modals
  const [selectedCandidate, setSelectedCandidate] =
    useState<CandidateRecord | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingCandidate, setEditingCandidate] =
    useState<CandidateRecord | null>(null);

  const [formData, setFormData] = useState<CandidateFormState>(EMPTY_FORM);

  // AI CV analysis. cvs.candidate_id is NOT NULL, so a CV is always uploaded
  // against a candidate that already exists - this opens for one row at a time.
  const [cvCandidate, setCvCandidate] = useState<CandidateRecord | null>(null);

  const loadCandidates = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getCandidates();
      setCandidates(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('hr.candidates.unableToLoad');
      setLoadError(message);
      showToast(t('hr.candidates.loadFailedToast'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadJobs = useCallback(async () => {
    try {
      const data = await SmartHRApi.getJobs();
      setJobs(data);
    } catch {
      // Non-fatal: the funnel still renders, only the pickers stay empty.
      showToast(t('hr.candidates.jobsFailed'), {
        message: t('hr.candidates.jobsIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadCandidates();
    loadJobs();
  }, [loadCandidates, loadJobs]);

  const jobOptions = useMemo(
    () =>
      jobs.map((j) => ({
        label: `${j.title}${j.department_name ? ` (${j.department_name})` : ''}`,
        value: String(j.id),
      })),
    [jobs]
  );

  const stageOptions = useMemo(
    () =>
      STAGE_TOKENS.map((token) => ({
        label: t(`status.stage.${token}`),
        value: token,
      })),
    []
  );

  const filteredCandidates = useMemo(() => {
    return candidates.filter((c) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        query === '' ||
        c.full_name.toLowerCase().includes(query) ||
        c.email.toLowerCase().includes(query) ||
        (c.job_title ?? '').toLowerCase().includes(query) ||
        (c.location ?? '').toLowerCase().includes(query) ||
        (c.phone ?? '').toLowerCase().includes(query);

      const matchesJob =
        selectedJob === 'ALL' || String(c.job_id ?? '') === selectedJob;

      const matchesStage =
        selectedStage === 'ALL' || c.stage === selectedStage;

      return matchesSearch && matchesJob && matchesStage;
    });
  }, [candidates, searchQuery, selectedJob, selectedStage]);

  const applyUpdated = (updated: CandidateRecord) => {
    setCandidates((prev) =>
      prev.map((c) => (c.id === updated.id ? updated : c))
    );

    setSelectedCandidate((prev) =>
      prev && prev.id === updated.id ? updated : prev
    );
  };

  const handleMoveStage = async (
    candidate: CandidateRecord,
    nextStage: CandidateStageToken
  ) => {
    if (!candidate.application_id) {
      showToast(t('hr.candidates.noApplicationOnFile'), {
        message: `${candidate.full_name} is not linked to a job requisition yet.`,
        type: 'error',
      });
      return;
    }

    setPendingStageId(candidate.id);

    try {
      await SmartHRApi.updateApplicationStage(
        candidate.application_id,
        nextStage
      );

      // Re-read the candidate so the stage, timeline and interview status
      // all come back from the database rather than being patched locally.
      const refreshed = await SmartHRApi.getCandidate(candidate.id);
      applyUpdated(refreshed);

      // Moving the stage writes applications.status and nothing else. Landing
      // on `interview` with no interviews row is the state that looks like a
      // broken feature, so the toast names the action that is still missing.
      const stageOnly =
        nextStage === 'interview' && !refreshed.interview_status;

      showToast(t('hr.candidates.stageUpdated'), {
        message: stageOnly
          ? t('hr.candidates.stageOnlyHint')
          : `${candidate.full_name} → ${t(`status.stage.${nextStage}`)}`,
        type: stageOnly ? 'warning' : 'success',
      });
    } catch (error) {
      showToast(t('hr.candidates.stageUpdateFailed'), {
        message: error instanceof Error ? error.message : t('hr.candidates.unexpectedError'),
        type: 'error',
      });
    } finally {
      setPendingStageId(null);
    }
  };

  const handleOpenAdd = () => {
    setFormData({
      ...EMPTY_FORM,
      job_id: jobs.length ? String(jobs[0].id) : '',
    });
    setIsAddModalOpen(true);
  };

  const handleOpenEdit = (candidate: CandidateRecord) => {
    setEditingCandidate(candidate);
    setFormData({
      first_name: candidate.first_name,
      last_name: candidate.last_name,
      email: candidate.email,
      phone: candidate.phone ?? '',
      location: candidate.location ?? '',
      job_id: candidate.job_id ? String(candidate.job_id) : '',
      stage: candidate.stage ?? 'applied',
    });
    setIsEditModalOpen(true);
  };

  const validateForm = (): boolean => {
    if (!formData.first_name.trim() || !formData.last_name.trim()) {
      showToast(t('hr.candidates.validationError'), {
        message: t('hr.candidates.namesRequired'),
        type: 'error',
      });
      return false;
    }

    if (!formData.email.trim()) {
      showToast(t('hr.candidates.validationError'), {
        message: t('hr.candidates.emailRequired'),
        type: 'error',
      });
      return false;
    }

    return true;
  };

  const handleAddCandidate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsSaving(true);

    try {
      const created = await SmartHRApi.createCandidate({
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        email: formData.email.trim(),
        phone: formData.phone.trim() || null,
        location: formData.location.trim() || null,
        job_id: formData.job_id ? Number(formData.job_id) : null,
        stage: formData.stage,
      });

      setCandidates((prev) => [created, ...prev]);
      setIsAddModalOpen(false);

      showToast(t('hr.candidates.registered'), {
        message: created.job_title
          ? `${created.full_name} added to pipeline for ${created.job_title}.`
          : `${created.full_name} saved to the database.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('hr.candidates.registerFailed'), {
        message: error instanceof Error ? error.message : t('hr.candidates.unexpectedError'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleEditCandidate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCandidate) return;
    if (!validateForm()) return;

    setIsSaving(true);

    try {
      const updated = await SmartHRApi.updateCandidate(editingCandidate.id, {
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        email: formData.email.trim(),
        phone: formData.phone.trim() || null,
        location: formData.location.trim() || null,
      });

      applyUpdated(updated);
      setIsEditModalOpen(false);

      showToast(t('hr.candidates.updatedToast'), {
        message: `${candidateRef(updated.id)} — ${updated.full_name} saved successfully.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('hr.candidates.updateFailed'), {
        message: error instanceof Error ? error.message : t('hr.candidates.unexpectedError'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title={t('hr.candidates.title')}
        subtitle={t('hr.candidates.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {candidates.length} In Active Funnel
          </Badge>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={handleOpenAdd}
          >
            + Add Candidate
          </Button>
        }
      />

      {/* Filter and Search Bar */}
      <Card>
        <div className="flex flex-col lg:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('hr.candidates.searchAll')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-2 w-full lg:w-auto flex-wrap sm:flex-nowrap">
            <select
              value={selectedJob}
              onChange={(e) => setSelectedJob(e.target.value)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:ring-2 focus:ring-brand-600 focus:outline-none max-w-[220px] truncate"
            >
              <option value="ALL">
                All Requisitions ({candidates.length})
              </option>
              {jobs.map((j) => (
                <option key={j.id} value={String(j.id)}>
                  {j.title}
                </option>
              ))}
            </select>

            <select
              value={selectedStage}
              onChange={(e) => setSelectedStage(e.target.value)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:ring-2 focus:ring-brand-600 focus:outline-none"
            >
              <option value="ALL">{t('hr.candidates.allStages')}</option>
              {STAGE_TOKENS.map((s) => (
                <option key={s} value={s}>
                  {t(`status.stage.${s}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Candidates Table */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50/80 text-stone-500 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3 px-4">{t('hr.candidates.colCandidate')}</th>
                <th className="py-3 px-4">{t('hr.candidates.appliedPosition')}</th>
                <th className="py-3 px-4">{t('table.location')}</th>
                <th className="py-3 px-4">{t('hr.candidates.currentStage')}</th>
                <th className="py-3 px-4">{t('hr.candidates.interviewStatus')}</th>
                <th className="py-3 px-4">{t('hr.candidates.resume')}</th>
                <th className="py-3 px-4 text-end">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    <Loader2 className="w-8 h-8 mx-auto mb-2 text-stone-300 animate-spin" />
                    <p className="font-semibold text-stone-600">
                      {t('hr.candidates.loading')}
                    </p>
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center">
                    <XCircle className="w-8 h-8 mx-auto mb-2 text-rose-300" />
                    <p className="font-semibold text-stone-600">
                      {t('hr.candidates.loadFailed')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                    <div className="mt-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={loadCandidates}
                      >
                        {t('admin.users.retry')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : filteredCandidates.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    <UserCheck className="w-8 h-8 mx-auto mb-2 text-stone-300" />
                    <p className="font-semibold text-stone-600">
                      {t('hr.candidates.noneMatch')}
                    </p>
                  </td>
                </tr>
              ) : (
                filteredCandidates.map((cand) => (
                  <tr
                    key={cand.id}
                    className="hover:bg-stone-50/80 transition-colors group cursor-pointer"
                    onClick={() => {
                      setSelectedCandidate(cand);
                      setIsDetailModalOpen(true);
                    }}
                  >
                    {/* Candidate Identity */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-brand-700 to-brand-600 text-white font-bold text-xs flex items-center justify-center shrink-0 shadow-2xs">
                          {initialsOf(cand.full_name)}
                        </div>
                        <div className="min-w-0">
                          <span className="font-bold text-stone-900 group-hover:text-brand-700 transition-colors block truncate">
                            {cand.full_name}
                          </span>
                          <span className="text-stone-400 text-3xs truncate block">
                            {candidateRef(cand.id)} • {cand.email}
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* Applied Job */}
                    <td className="py-3.5 px-4">
                      <div className="min-w-0 max-w-[200px]">
                        <span className="font-semibold text-stone-900 block truncate">
                          {cand.job_title ?? t('hr.candidates.noApplicationYet')}
                        </span>
                        <span className="text-stone-400 text-3xs truncate block">
                          {cand.department_name ?? t('hr.candidates.unassigned')} • Applied{' '}
                          {formatDate(cand.applied_at)}
                        </span>
                      </div>
                    </td>

                    {/* Location */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 text-stone-600 font-medium text-2xs">
                        <MapPin className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                        <span className="truncate">
                          {cand.location ?? '—'}
                        </span>
                      </div>
                      <span className="text-stone-400 text-3xs block mt-0.5">
                        {cand.phone ?? t('hr.candidates.noPhoneOnFile')}
                      </span>
                    </td>

                    {/* Stage Pill */}
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-3xs font-bold border ${getStageBadgeColor(
                          cand.stage
                        )}`}
                      >
                        {cand.stage ? t(`status.stage.${cand.stage}`) : t('hr.candidates.noApplication')}
                      </span>
                    </td>

                    {/* Interview Status */}
                    <td className="py-3.5 px-4 text-stone-600 font-medium text-2xs">
                      {cand.interview_status ? (
                        <>
                          <span className="capitalize block">
                            {cand.interview_status}
                          </span>
                          <span className="text-stone-400 text-3xs">
                            {formatDateTime(cand.interview_scheduled_at)}
                          </span>
                        </>
                      ) : cand.stage === 'interview' ? (
                        // The application says Interview but no interviews row
                        // exists: the stage was moved by hand. Saying so is the
                        // difference between a recruiter seeing a bug and
                        // seeing the button they still have to press.
                        <span className="text-amber-700 font-semibold">
                          {t('hr.candidates.stageWithoutInterview')}
                        </span>
                      ) : (
                        <span className="text-stone-400">
                          {t('hr.candidates.noInterviewScheduled')}
                        </span>
                      )}
                    </td>

                    {/* Resume / CV */}
                    <td
                      className="py-3.5 px-4"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex flex-col items-start gap-1">
                        {cand.cv_file_name ? (
                          <span
                            title={cand.cv_file_name}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-stone-100 text-stone-600 text-3xs font-bold max-w-[11rem] truncate"
                          >
                            <FileText className="w-3 h-3 shrink-0" />
                            <span className="truncate">{cand.cv_file_name}</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-stone-50 text-stone-400 text-3xs font-bold">
                            <FileText className="w-3 h-3" />
                            {t('hr.candidates.noCv')}
                          </span>
                        )}

                        <button
                          onClick={() => setCvCandidate(cand)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-brand-50 hover:bg-brand-100 text-brand-700 border border-brand-200 text-3xs font-bold transition-colors"
                        >
                          <Sparkles className="w-3 h-3" />
                          {cand.cv_file_name ? t('hr.candidates.analyseNewCv') : t('hr.candidates.uploadAnalyse')}
                        </button>
                      </div>
                    </td>

                    {/* Actions */}
                    <td
                      className="py-3.5 px-4 text-end"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-end gap-1.5">
                        {/* Quick Move Select */}
                        <select
                          value={cand.stage ?? ''}
                          disabled={
                            !cand.application_id || pendingStageId === cand.id
                          }
                          onChange={(e) =>
                            handleMoveStage(
                              cand,
                              e.target.value as CandidateStageToken
                            )
                          }
                          title={
                            cand.application_id
                              ? t('hr.candidates.moveStage')
                              : t('hr.candidates.noApplicationOnFile')
                          }
                          className="px-2 py-1 text-3xs font-bold rounded border border-stone-200 bg-white text-stone-700 hover:border-brand-600 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {!cand.stage && <option value="">{t('hr.candidates.noStage')}</option>}
                          {STAGE_TOKENS.map((st) => (
                            <option key={st} value={st}>
                              {t('hr.candidates.moveStage')}: {t(`status.stage.${st}`)}
                            </option>
                          ))}
                        </select>

                        <Button
                          variant="outline"
                          size="sm"
                          className="px-2 h-6"
                          title={t('hr.candidates.editTitle')}
                          onClick={() => handleOpenEdit(cand)}
                        >
                          <Edit2 className="w-3 h-3" />
                        </Button>

                        {onScheduleInterview && (
                          <Button
                            variant="purple-soft"
                            size="sm"
                            className="px-2 h-6 text-3xs"
                            onClick={() =>
                              onScheduleInterview(String(cand.id))
                            }
                          >
                            {t('hr.candidates.colInterview')}
                          </Button>
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

      {/* Candidate Dossier Modal */}
      {selectedCandidate && (
        <Modal
          isOpen={isDetailModalOpen}
          onClose={() => setIsDetailModalOpen(false)}
          title={selectedCandidate.full_name}
          subtitle={
            selectedCandidate.job_title
              ? `Applied for ${selectedCandidate.job_title}`
              : t('hr.candidates.noApplicationOnFile')
          }
          size="lg"
          footer={
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-stone-500">
                  {t('hr.candidates.transitionStage')}
                </span>
                <div className="flex items-center gap-1 flex-wrap">
                  {STAGE_TOKENS.map((st) => (
                    <button
                      key={st}
                      disabled={
                        !selectedCandidate.application_id ||
                        pendingStageId === selectedCandidate.id
                      }
                      onClick={() => handleMoveStage(selectedCandidate, st)}
                      className={`px-2 py-0.5 rounded text-3xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                        selectedCandidate.stage === st
                          ? 'bg-brand-700 text-white shadow-xs'
                          : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                      }`}
                    >
                      {t(`status.stage.${st}`)}
                    </button>
                  ))}
                </div>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsDetailModalOpen(false)}
              >
                {t('hr.candidates.closeDossier')}
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            {/* Quick stats grid */}
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200/70">
                <span className="text-stone-400 font-medium">
                  {t('hr.candidates.pipelineStage')}
                </span>
                <p className="text-xl font-black text-brand-700 mt-0.5">
                  {selectedCandidate.stage
                    ? t(`status.stage.${selectedCandidate.stage}`)
                    : t('hr.candidates.noApplication')}
                </p>
                <span className="text-3xs text-stone-500 font-semibold">
                  {selectedCandidate.applications_count} application
                  {selectedCandidate.applications_count === 1 ? '' : 's'} on file
                </span>
              </div>

              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200/70">
                <span className="text-stone-400 font-medium">
                  {t('hr.candidates.appliedPosition')}
                </span>
                <p className="text-sm font-bold text-stone-900 mt-0.5 truncate">
                  {selectedCandidate.job_title ?? '—'}
                </p>
                <span className="text-3xs text-stone-500 truncate block">
                  {selectedCandidate.department_name ?? t('hr.candidates.unassigned')} • Applied{' '}
                  {formatDate(selectedCandidate.applied_at)}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200/70">
                <span className="text-stone-400 font-medium">
                  {t('hr.candidates.contactLocation')}
                </span>
                <p className="text-xs font-bold text-stone-900 mt-0.5 truncate">
                  {selectedCandidate.email}
                </p>
                <span className="text-3xs text-stone-500 truncate block">
                  {selectedCandidate.phone ?? t('hr.candidates.noPhone')} •{' '}
                  {selectedCandidate.location ?? t('hr.candidates.noLocation')}
                </span>
              </div>
            </div>

            {/* Interview status, read from the recruitment `interviews`
                table by GET /candidates/. The dossier writes nothing. */}
            <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-stone-50 border border-stone-200/70">
              <div className="min-w-0">
                <span className="text-stone-400 font-medium text-xs">
                  {t('hr.candidates.interviewStatus')}
                </span>
                {selectedCandidate.interview_status ? (
                  <p className="text-xs font-bold text-stone-900 mt-0.5">
                    <span className="capitalize">
                      {selectedCandidate.interview_status}
                    </span>
                    <span className="text-3xs text-stone-500 font-medium ms-2">
                      {formatDateTime(selectedCandidate.interview_scheduled_at)}
                    </span>
                  </p>
                ) : (
                  <p
                    className={`text-xs font-bold mt-0.5 ${
                      selectedCandidate.stage === 'interview'
                        ? 'text-amber-700'
                        : 'text-stone-500'
                    }`}
                  >
                    {selectedCandidate.stage === 'interview'
                      ? t('hr.candidates.stageWithoutInterview')
                      : t('hr.candidates.noInterviewScheduled')}
                  </p>
                )}
              </div>
            </div>

            {/* Application History Timeline */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-stone-800 uppercase tracking-wider">
                {t('hr.candidates.auditTitle')}
              </h4>
              <div className="space-y-2 relative border-s-2 border-stone-200 ms-3 ps-4">
                {selectedCandidate.timeline.length === 0 ? (
                  <p className="text-2xs text-stone-400">
                    {t('hr.candidates.noActivity')}
                  </p>
                ) : (
                  selectedCandidate.timeline.map((item, idx) => (
                    <div key={idx} className="relative text-xs">
                      <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-brand-600 ring-2 ring-white" />
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-stone-900">
                          {item.label}
                        </span>
                        <span className="text-3xs text-stone-400">
                          {formatDate(item.date)}
                        </span>
                      </div>
                      <p className="text-stone-600 text-2xs mt-0.5">
                        {item.note}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </Modal>
      )}

      {/* Add Candidate Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t('hr.candidates.registerTitle')}
        subtitle={t('hr.candidates.registerSubtitle')}
        size="lg"
      >
        <form onSubmit={handleAddCandidate} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('hr.candidates.firstName')}
              required
              value={formData.first_name}
              onChange={(e) =>
                setFormData({ ...formData, first_name: e.target.value })
              }
              placeholder={t('hr.candidates.firstNamePlaceholder')}
            />
            <Input
              label={t('hr.candidates.lastName')}
              required
              value={formData.last_name}
              onChange={(e) =>
                setFormData({ ...formData, last_name: e.target.value })
              }
              placeholder={t('hr.candidates.lastNamePlaceholder')}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('hr.candidates.emailAddress')}
              type="email"
              required
              value={formData.email}
              onChange={(e) =>
                setFormData({ ...formData, email: e.target.value })
              }
              placeholder={t('hr.candidates.emailPlaceholder')}
            />
            <Input
              label={t('hr.candidates.contactPhone')}
              value={formData.phone}
              onChange={(e) =>
                setFormData({ ...formData, phone: e.target.value })
              }
              placeholder={t('hr.candidates.phonePlaceholder')}
            />
          </div>

          <Input
            label={t('hr.candidates.candidateLocation')}
            value={formData.location}
            onChange={(e) =>
              setFormData({ ...formData, location: e.target.value })
            }
            placeholder={t('hr.candidates.locationPlaceholder')}
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('hr.candidates.targetJob')}
              options={jobOptions}
              value={formData.job_id}
              onChange={(e) =>
                setFormData({ ...formData, job_id: e.target.value })
              }
              helperText="Creates the application row linking candidate to job."
            />

            <Select
              label={t('hr.candidates.initialStage')}
              options={stageOptions}
              value={formData.stage}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  stage: e.target.value as CandidateStageToken,
                })
              }
            />
          </div>

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
              {t('hr.candidates.registerButton')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Candidate Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title={t('hr.candidates.editProfileTitle')}
        subtitle={
          editingCandidate
            ? `Editing ${candidateRef(editingCandidate.id)} • ${editingCandidate.full_name}`
            : ''
        }
        size="lg"
      >
        <form onSubmit={handleEditCandidate} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('hr.candidates.firstName')}
              required
              value={formData.first_name}
              onChange={(e) =>
                setFormData({ ...formData, first_name: e.target.value })
              }
            />
            <Input
              label={t('hr.candidates.lastName')}
              required
              value={formData.last_name}
              onChange={(e) =>
                setFormData({ ...formData, last_name: e.target.value })
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('hr.candidates.emailAddress')}
              type="email"
              required
              value={formData.email}
              onChange={(e) =>
                setFormData({ ...formData, email: e.target.value })
              }
            />
            <Input
              label={t('hr.candidates.contactPhone')}
              value={formData.phone}
              onChange={(e) =>
                setFormData({ ...formData, phone: e.target.value })
              }
            />
          </div>

          <Input
            label={t('hr.candidates.candidateLocation')}
            value={formData.location}
            onChange={(e) =>
              setFormData({ ...formData, location: e.target.value })
            }
          />

          <p className="text-3xs text-stone-400">
            Pipeline stage and job requisition are managed from the funnel
            actions, not this form.
          </p>

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
              {t('admin.users.saveChanges')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* AI CV analysis, opened per candidate from the Resume / CV column. */}
      {cvCandidate && (
        <CvAnalysisModal
          isOpen={!!cvCandidate}
          onClose={() => setCvCandidate(null)}
          candidateId={cvCandidate.id}
          candidateName={cvCandidate.full_name}
          onUploaded={() => {
            // The candidate dossier reports the most recent CV on file, so the
            // list is re-read to pick the new one up.
            loadCandidates();
          }}
        />
      )}
    </div>
  );
};
