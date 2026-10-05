import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Calendar as CalendarIcon,
  Clock,
  Video,
  MapPin,
  Plus,
  XCircle,
  Search,
  ExternalLink,
  Edit2,
  MessageSquare,
  Loader2,
  FileText,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input, Select, Textarea } from '../../components/ui/Input';
import { InterviewReportModal } from '../../components/ai/InterviewReportModal';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import {
  ApplicationRecord,
  InterviewPayload,
  InterviewRecord,
  InterviewStatusToken,
  InterviewerOption,
} from '../../types';
import { useT } from '../../i18n';

export interface InterviewsPageProps {
  preselectedCandidateId?: string;
}

// =========================
// Status mapping
//
// PostgreSQL stores interviews.status as one of:
// scheduled | in_progress | completed | cancelled.
// =========================

const STATUS_TOKENS: InterviewStatusToken[] = [
  'scheduled',
  'in_progress',
  'completed',
  'cancelled',
];

// The filter bar keeps the three states the original design exposed.
const FILTER_TOKENS = ['ALL', 'scheduled', 'completed', 'cancelled'] as const;
type FilterToken = (typeof FILTER_TOKENS)[number];

const interviewRef = (id: number): string =>
  `INT-${String(id).padStart(3, '0')}`;

const isMeetingLink = (location: string | null): boolean =>
  !!location && /^https?:\/\//i.test(location.trim());

const initialsOf = (name: string | null): string =>
  (name ?? '?')
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

/** `scheduled_at` arrives as a naive ISO timestamp from FastAPI. Split it
 *  into the date and time halves the form edits, without timezone shifting. */
const splitScheduledAt = (value: string): { date: string; time: string } => {
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/.exec(value ?? '');
  if (!match) return { date: '', time: '' };
  return { date: match[1], time: `${match[2]}:${match[3]}` };
};

const joinScheduledAt = (date: string, time: string): string =>
  `${date}T${time.length === 5 ? `${time}:00` : time}`;

const formatDate = (value: string | null): string => {
  if (!value) return '—';
  const { date } = splitScheduledAt(value);
  if (!date) return '—';
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return date;
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

const formatTime = (value: string | null): string => {
  if (!value) return '—';
  const { time } = splitScheduledAt(value);
  return time || '—';
};

const statusPillClass = (status: InterviewStatusToken): string => {
  switch (status) {
    case 'scheduled':
      return 'bg-sky-50 text-sky-700 border border-sky-200';
    case 'in_progress':
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    case 'completed':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    default:
      return 'bg-rose-50 text-rose-700 border border-rose-200';
  }
};

interface InterviewFormState {
  application_id: string;
  interviewer_id: string;
  date: string;
  time: string;
  location: string;
  status: InterviewStatusToken;
  notes: string;
}

const EMPTY_FORM: InterviewFormState = {
  application_id: '',
  interviewer_id: '',
  date: '',
  time: '10:00',
  location: '',
  status: 'scheduled',
  notes: '',
};

export const InterviewsPage: React.FC<InterviewsPageProps> = ({
  preselectedCandidateId,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [interviews, setInterviews] = useState<InterviewRecord[]>([]);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [interviewers, setInterviewers] = useState<InterviewerOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<FilterToken>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [editingInterview, setEditingInterview] =
    useState<InterviewRecord | null>(null);
  const [selectedInterview, setSelectedInterview] =
    useState<InterviewRecord | null>(null);

  // AI Interview Report (Phase 8): which interview's report is open, if any.
  const [reportInterviewId, setReportInterviewId] = useState<number | null>(null);

  const [formData, setFormData] = useState<InterviewFormState>(EMPTY_FORM);
  const [outcomeNotes, setOutcomeNotes] = useState('');

  const loadInterviews = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getInterviews();
      setInterviews(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('hr.interviews.loadErrorTitle');
      setLoadError(message);
      showToast(t('hr.interviews.loadFailed'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadPickers = useCallback(async () => {
    try {
      const [apps, users] = await Promise.all([
        SmartHRApi.getApplications(),
        SmartHRApi.getInterviewers(),
      ]);
      setApplications(apps);
      setInterviewers(users);
    } catch {
      // Non-fatal: the board still renders, only the pickers stay empty.
      showToast(t('hr.interviews.optionsFailed'), {
        message: t('hr.interviews.optionsIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadInterviews();
    loadPickers();
  }, [loadInterviews, loadPickers]);

  const applicationOptions = useMemo(
    () =>
      applications.map((a) => ({
        label: `${a.candidate_name ?? t('hr.interviews.unknown')} — ${a.job_title ?? t('hr.interviews.unknownRole')}`,
        value: String(a.id),
      })),
    [applications]
  );

  const interviewerOptions = useMemo(
    () => [
      { label: t('hr.interviews.unassigned'), value: '' },
      ...interviewers.map((u) => ({
        label: `${u.name ?? u.email}${u.role ? ` (${u.role})` : ''}`,
        value: String(u.id),
      })),
    ],
    [interviewers]
  );

  const filteredInterviews = useMemo(() => {
    return interviews.filter((item) => {
      const matchesStatus =
        statusFilter === 'ALL' || item.status === statusFilter;

      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        query === '' ||
        (item.candidate_name ?? '').toLowerCase().includes(query) ||
        (item.job_title ?? '').toLowerCase().includes(query) ||
        (item.interviewer_name ?? '').toLowerCase().includes(query) ||
        (item.location ?? '').toLowerCase().includes(query);

      return matchesStatus && matchesSearch;
    });
  }, [interviews, statusFilter, searchQuery]);

  const applyUpdated = (updated: InterviewRecord) => {
    setInterviews((prev) =>
      prev.map((i) => (i.id === updated.id ? updated : i))
    );
    setSelectedInterview((prev) =>
      prev && prev.id === updated.id ? updated : prev
    );
  };

  const handleOpenSchedule = () => {
    // When navigated here from the Candidates funnel, preselect that
    // candidate's most recent application.
    const preselected = preselectedCandidateId
      ? applications.find(
          (a) => a.candidate_id === Number(preselectedCandidateId)
        )
      : undefined;

    const fallback = applications.length ? applications[0] : undefined;
    const chosen = preselected ?? fallback;

    setEditingInterview(null);
    setFormData({
      ...EMPTY_FORM,
      application_id: chosen ? String(chosen.id) : '',
      interviewer_id: interviewers.length ? String(interviewers[0].id) : '',
      date: new Date().toISOString().slice(0, 10),
    });
    setIsScheduleModalOpen(true);
  };

  const handleOpenEdit = (interview: InterviewRecord) => {
    const { date, time } = splitScheduledAt(interview.scheduled_at);

    setEditingInterview(interview);
    setFormData({
      application_id: String(interview.application_id),
      interviewer_id: interview.interviewer_id
        ? String(interview.interviewer_id)
        : '',
      date,
      time,
      location: interview.location ?? '',
      status: interview.status,
      notes: interview.notes ?? '',
    });
    setIsScheduleModalOpen(true);
  };

  const buildPayload = (): InterviewPayload | null => {
    const applicationId = Number(formData.application_id);

    if (!applicationId) {
      showToast(t('validation.error'), {
        message: t('hr.interviews.selectApplication'),
        type: 'error',
      });
      return null;
    }

    if (!formData.date || !formData.time) {
      showToast(t('validation.error'), {
        message: t('hr.interviews.dateRequired'),
        type: 'error',
      });
      return null;
    }

    return {
      application_id: applicationId,
      interviewer_id: formData.interviewer_id
        ? Number(formData.interviewer_id)
        : null,
      scheduled_at: joinScheduledAt(formData.date, formData.time),
      location: formData.location.trim() || null,
      status: formData.status,
      notes: formData.notes.trim() || null,
    };
  };

  const handleSubmitInterview = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      if (editingInterview) {
        const updated = await SmartHRApi.updateInterview(
          editingInterview.id,
          payload
        );
        applyUpdated(updated);

        showToast(t('hr.interviews.updated'), {
          message: `${interviewRef(updated.id)} saved successfully.`,
          type: 'success',
        });
      } else {
        const created = await SmartHRApi.createInterview(payload);
        setInterviews((prev) => [created, ...prev]);

        showToast(t('hr.interviews.scheduled'), {
          message: `Interview with ${created.candidate_name ?? 'candidate'} scheduled for ${formatDate(created.scheduled_at)}.`,
          type: 'success',
        });
      }

      setIsScheduleModalOpen(false);
      setEditingInterview(null);
    } catch (error) {
      showToast(
        editingInterview
          ? t('hr.interviews.updateFailed')
          : t('hr.interviews.scheduleFailed'),
        {
          message: error instanceof Error ? error.message : t('error.unexpected'),
          type: 'error',
        }
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleChangeStatus = async (
    interview: InterviewRecord,
    status: InterviewStatusToken,
    notes?: string | null
  ) => {
    setPendingId(interview.id);

    try {
      const updated = await SmartHRApi.updateInterviewStatus(
        interview.id,
        status,
        notes
      );
      applyUpdated(updated);

      showToast(t('hr.interviews.updated'), {
        message: t('hr.interviews.statusSetTo', {
          ref: interviewRef(updated.id),
          status: t(`status.interview.${updated.status}`),
        }),
        type: status === 'cancelled' ? 'info' : 'success',
      });

      return true;
    } catch (error) {
      showToast(t('hr.interviews.updateFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
      return false;
    } finally {
      setPendingId(null);
    }
  };

  const handleOpenFeedback = (interview: InterviewRecord) => {
    setSelectedInterview(interview);
    setOutcomeNotes(interview.notes ?? '');
    setIsFeedbackModalOpen(true);
  };

  const handleSubmitFeedback = async () => {
    if (!selectedInterview) return;

    setIsSaving(true);

    const ok = await handleChangeStatus(
      selectedInterview,
      'completed',
      outcomeNotes.trim() || null
    );

    setIsSaving(false);

    if (ok) setIsFeedbackModalOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('hr.interviews.title')}
        subtitle={t('hr.interviews.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {interviews.filter((i) => i.status === 'scheduled').length} Upcoming
          </Badge>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={handleOpenSchedule}
          >
            + Schedule Interview
          </Button>
        }
      />

      {/* Filter and Stats Bar */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('hr.interviews.search')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-1.5 w-full sm:w-auto">
            {FILTER_TOKENS.map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  statusFilter === st
                    ? 'bg-brand-700 text-white shadow-xs'
                    : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                }`}
              >
                {st === 'ALL' ? t('hr.interviews.filterAll') : t(`status.interview.${st}`)}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Interviews Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {isLoading ? (
          <div className="col-span-2">
            <Card>
              <div className="py-12 text-center text-stone-400">
                <Loader2 className="w-8 h-8 mx-auto mb-2 text-stone-300 animate-spin" />
                <p className="font-semibold text-stone-600">
                  {t('hr.interviews.loading')}
                </p>
              </div>
            </Card>
          </div>
        ) : loadError ? (
          <div className="col-span-2">
            <Card>
              <div className="py-12 text-center">
                <XCircle className="w-8 h-8 mx-auto mb-2 text-rose-300" />
                <p className="font-semibold text-stone-600">
                  {t('hr.interviews.loadError')}
                </p>
                <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                <div className="mt-4">
                  <Button variant="outline" size="sm" onClick={loadInterviews}>
                    {t('action.retry')}
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        ) : filteredInterviews.length === 0 ? (
          <div className="col-span-2">
            <Card>
              <div className="py-12 text-center text-stone-400">
                <CalendarIcon className="w-8 h-8 mx-auto mb-2 text-stone-300" />
                <p className="font-semibold text-stone-600">
                  {t('hr.interviews.empty')}
                </p>
              </div>
            </Card>
          </div>
        ) : (
          filteredInterviews.map((item) => (
            <Card key={item.id} padding="none">
              <div className="p-5 space-y-4 hover:bg-stone-50/40 transition-colors">
                {/* Header row */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-brand-100 text-brand-800 font-extrabold text-sm flex items-center justify-center shrink-0">
                      {initialsOf(item.candidate_name)}
                    </div>
                    <div>
                      <h4 className="font-bold text-stone-900 text-sm">
                        {item.candidate_name ?? t('hr.interviews.unknownCandidate')}
                      </h4>
                      <p className="text-2xs text-stone-500">
                        {item.job_title ?? t('hr.interviews.unknownRole')}
                      </p>
                    </div>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-3xs font-bold ${statusPillClass(
                      item.status
                    )}`}
                  >
                    {t(`status.interview.${item.status}`)}
                  </span>
                </div>

                {/* Details box */}
                <div className="p-3 bg-stone-50 rounded-xl border border-stone-200/70 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500 font-medium flex items-center gap-1">
                      <CalendarIcon className="w-3.5 h-3.5 text-stone-400" />
                      {formatDate(item.scheduled_at)}
                    </span>
                    <span className="font-semibold text-stone-800 flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-stone-400" />
                      {formatTime(item.scheduled_at)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-stone-200/60 text-2xs">
                    <span className="text-stone-500 font-medium">
                      {t('hr.interviews.interviewerLabel')}
                    </span>
                    <span className="font-bold text-brand-700">
                      {item.interviewer_name ?? t('hr.interviews.unassigned')}
                      {item.interviewer_role
                        ? ` (${item.interviewer_role})`
                        : ''}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-2xs gap-2">
                    <span className="text-stone-500 font-medium flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-stone-400" />
                      {t('hr.interviews.locationLabel')}
                    </span>
                    <span className="font-medium text-stone-700 truncate max-w-[220px]">
                      {item.location ?? t('hr.interviews.notSpecified')}
                    </span>
                  </div>
                </div>

                {/* Recorded outcome notes */}
                {item.status === 'completed' && item.notes && (
                  <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-100 flex items-start gap-1.5 text-xs">
                    <MessageSquare className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <span className="text-3xs text-emerald-800 font-medium italic">
                      {item.notes}
                    </span>
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex items-center justify-between pt-2 border-t border-stone-100">
                  {isMeetingLink(item.location) ? (
                    <a
                      href={item.location ?? '#'}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs font-semibold text-brand-700 hover:text-brand-900 flex items-center gap-1"
                    >
                      <Video className="w-3.5 h-3.5" />
                      {t('hr.interviews.joinRoom')} <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : (
                    <span className="text-3xs text-stone-400 font-mono">
                      {interviewRef(item.id)}
                    </span>
                  )}

                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-brand-700"
                      leftIcon={<FileText className="w-3.5 h-3.5" />}
                      onClick={() => setReportInterviewId(item.id)}
                    >
                      {t('hr.aiReport.open')}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      title={t('hr.interviews.edit')}
                      onClick={() => handleOpenEdit(item)}
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>

                    {item.status === 'scheduled' && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-rose-600 hover:bg-rose-50"
                          disabled={pendingId === item.id}
                          onClick={() => handleChangeStatus(item, 'cancelled')}
                        >
                          {t('action.cancel')}
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={pendingId === item.id}
                          onClick={() => handleOpenFeedback(item)}
                        >
                          {t('hr.interviews.complete')}
                        </Button>
                      </>
                    )}

                    {item.status === 'completed' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-brand-700"
                        onClick={() => handleOpenFeedback(item)}
                      >
                        {t('hr.interviews.editOutcome')}
                      </Button>
                    )}

                    {item.status === 'cancelled' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-emerald-600 hover:bg-emerald-50"
                        disabled={pendingId === item.id}
                        onClick={() => handleChangeStatus(item, 'scheduled')}
                      >
                        {t('hr.interviews.reinstate')}
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Schedule / Edit Interview Modal */}
      <Modal
        isOpen={isScheduleModalOpen}
        onClose={() => {
          setIsScheduleModalOpen(false);
          setEditingInterview(null);
        }}
        title={
          editingInterview
            ? t('hr.interviews.editTitle')
            : t('hr.interviews.scheduleTitle')
        }
        subtitle={
          editingInterview
            ? `Editing ${interviewRef(editingInterview.id)} • ${editingInterview.candidate_name ?? 'candidate'}`
            : t('hr.interviews.scheduleSubtitle')
        }
        size="lg"
      >
        <form onSubmit={handleSubmitInterview} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('hr.interviews.application')}
              required
              options={applicationOptions}
              value={formData.application_id}
              onChange={(e) =>
                setFormData({ ...formData, application_id: e.target.value })
              }
              helperText="Interviews attach to an application, not directly to a candidate."
            />

            <Select
              label={t('hr.interviews.lead')}
              options={interviewerOptions}
              value={formData.interviewer_id}
              onChange={(e) =>
                setFormData({ ...formData, interviewer_id: e.target.value })
              }
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Input
              label={t('hr.interviews.date')}
              type="date"
              required
              value={formData.date}
              onChange={(e) =>
                setFormData({ ...formData, date: e.target.value })
              }
            />

            <Input
              label={t('hr.interviews.slot')}
              type="time"
              required
              value={formData.time}
              onChange={(e) =>
                setFormData({ ...formData, time: e.target.value })
              }
            />

            <Select
              label={t('table.status')}
              options={STATUS_TOKENS.map((token) => ({
                label: t(`status.interview.${token}`),
                value: token,
              }))}
              value={formData.status}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  status: e.target.value as InterviewStatusToken,
                })
              }
            />
          </div>

          <Input
            label={t('hr.interviews.location')}
            value={formData.location}
            onChange={(e) =>
              setFormData({ ...formData, location: e.target.value })
            }
            placeholder={t('hr.interviews.locationPlaceholder')}
            helperText="A link starting with http shows a Join Room button on the card."
          />

          <Textarea
            label={t('hr.interviews.brief')}
            rows={2}
            value={formData.notes}
            onChange={(e) =>
              setFormData({ ...formData, notes: e.target.value })
            }
            placeholder={t('hr.interviews.briefPlaceholder')}
          />

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => {
                setIsScheduleModalOpen(false);
                setEditingInterview(null);
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
              {editingInterview ? t('action.saveChanges') : t('hr.interviews.confirm')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Complete Interview & Outcome Modal */}
      {selectedInterview && (
        <Modal
          isOpen={isFeedbackModalOpen}
          onClose={() => setIsFeedbackModalOpen(false)}
          title={t('hr.interviews.outcome')}
          subtitle={`Candidate: ${selectedInterview.candidate_name ?? t('hr.interviews.unknown')} • ${selectedInterview.job_title ?? t('hr.interviews.unknownRole')}`}
          footer={
            <div className="flex items-center justify-end gap-2 w-full">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsFeedbackModalOpen(false)}
              >
                {t('action.cancel')}
              </Button>
              <Button
                variant="primary"
                size="sm"
                isLoading={isSaving}
                onClick={handleSubmitFeedback}
              >
                {t('hr.interviews.saveCompleted')}
              </Button>
            </div>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="p-3 rounded-xl bg-brand-50/60 border border-brand-100">
              <p className="font-bold text-brand-900">
                {selectedInterview.candidate_name ?? t('hr.interviews.unknownCandidate')}
              </p>
              <p className="text-brand-700 text-2xs">
                Role: {selectedInterview.job_title ?? '—'} • Interviewed by{' '}
                {selectedInterview.interviewer_name ?? t('hr.interviews.unassigned')}
              </p>
              <p className="text-brand-600 text-3xs mt-1">
                {formatDate(selectedInterview.scheduled_at)} at{' '}
                {formatTime(selectedInterview.scheduled_at)}
                {selectedInterview.location
                  ? ` • ${selectedInterview.location}`
                  : ''}
              </p>
            </div>

            <Textarea
              label={t('hr.interviews.evaluation')}
              rows={5}
              value={outcomeNotes}
              onChange={(e) => setOutcomeNotes(e.target.value)}
              placeholder={t('hr.interviews.evaluationPlaceholder')}
              helperText="Saved to interviews.notes and marks the interview completed."
            />
          </div>
        </Modal>
      )}

      {/* AI Interview Report (Phase 8) - read-only, Admin/HR, from stored analyses */}
      {reportInterviewId !== null && (
        <InterviewReportModal
          isOpen
          interviewId={reportInterviewId}
          onClose={() => setReportInterviewId(null)}
        />
      )}
    </div>
  );
};
