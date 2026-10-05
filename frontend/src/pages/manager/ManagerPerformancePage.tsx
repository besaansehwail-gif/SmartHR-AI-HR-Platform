import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Star,
  Award,
  CheckCircle2,
  Users,
  BarChart2,
  Edit3,
  Plus,
  XCircle,
  Loader2,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardHeader } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input, Select, Textarea } from '../../components/ui/Input';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import {
  EmployeeRosterEntry,
  PerformanceReviewPayload,
  PerformanceReviewRecord,
  ReviewerOption,
} from '../../types';
import { useT } from '../../i18n';

// =========================
// Rating
//
// performance_reviews.rating is an INTEGER with a database CHECK constraint
// of 1..5, so the appraisal picker offers exactly those five whole values.
// =========================

const RATING_VALUES = [5, 4, 3, 2, 1] as const;


const tierPillClass = (rating: number): string => {
  switch (rating) {
    case 5:
      return 'bg-brand-100 text-brand-800';
    case 4:
      return 'bg-brand-50 text-brand-700 border border-brand-200';
    case 3:
      return 'bg-stone-100 text-stone-700';
    case 2:
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    default:
      return 'bg-rose-50 text-rose-700 border border-rose-200';
  }
};

const ratingBarClass = (rating: number): string => {
  switch (rating) {
    case 5:
      return 'bg-brand-700';
    case 4:
      return 'bg-brand-500';
    case 3:
      return 'bg-brand-300';
    case 2:
      return 'bg-amber-400';
    default:
      return 'bg-rose-400';
  }
};

const formatDate = (value: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

interface ReviewFormState {
  employee_id: string;
  reviewer_id: string;
  rating: string;
  review_date: string;
  feedback: string;
}

const EMPTY_FORM: ReviewFormState = {
  employee_id: '',
  reviewer_id: '',
  rating: '4',
  review_date: '',
  feedback: '',
};

export const ManagerPerformancePage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [reviews, setReviews] = useState<PerformanceReviewRecord[]>([]);
  const [roster, setRoster] = useState<EmployeeRosterEntry[]>([]);
  const [reviewers, setReviewers] = useState<ReviewerOption[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [editingReview, setEditingReview] =
    useState<PerformanceReviewRecord | null>(null);
  const [formData, setFormData] = useState<ReviewFormState>(EMPTY_FORM);

  const loadReviews = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getPerformanceReviews();
      setReviews(data);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t('mgr.perf.loadErrorTitle');
      setLoadError(message);
      showToast(t('mgr.perf.loadFailed'), {
        message,
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadPickers = useCallback(async () => {
    try {
      const [rosterData, reviewerData] = await Promise.all([
        SmartHRApi.getEmployeeRoster(),
        SmartHRApi.getReviewers(),
      ]);
      setRoster(rosterData);
      setReviewers(reviewerData);
    } catch {
      // Non-fatal: the appraisal table still renders.
      showToast(t('mgr.perf.optionsFailed'), {
        message: t('mgr.perf.optionsIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadReviews();
    loadPickers();
  }, [loadReviews, loadPickers]);

  const rosterOptions = useMemo(
    () =>
      roster.map((e) => ({
        label: `${e.name}${e.department_name ? ` (${e.department_name})` : ''}`,
        value: String(e.id),
      })),
    [roster]
  );

  const reviewerOptions = useMemo(
    () =>
      reviewers.map((u) => ({
        label: `${u.name ?? u.email}${u.role ? ` (${u.role})` : ''}`,
        value: String(u.id),
      })),
    [reviewers]
  );

  // ---------- Metrics, all derived from the real rows ----------

  const totalReviews = reviews.length;

  const averageRating = useMemo(() => {
    if (!reviews.length) return '0.00';
    const sum = reviews.reduce((acc, r) => acc + r.rating, 0);
    return (sum / reviews.length).toFixed(2);
  }, [reviews]);

  const reviewedEmployeeCount = useMemo(
    () => new Set(reviews.map((r) => r.employee_id)).size,
    [reviews]
  );

  const topRatedCount = useMemo(
    () => reviews.filter((r) => r.rating === 5).length,
    [reviews]
  );

  const needsAttentionCount = useMemo(
    () => reviews.filter((r) => r.rating <= 2).length,
    [reviews]
  );

  const distribution = useMemo(
    () =>
      RATING_VALUES.map((rating) => {
        const count = reviews.filter((r) => r.rating === rating).length;
        return {
          rating,
          count,
          percent: totalReviews ? (count / totalReviews) * 100 : 0,
        };
      }),
    [reviews, totalReviews]
  );

  const latestReviewDate = useMemo(() => {
    if (!reviews.length) return null;
    return reviews
      .map((r) => r.review_date)
      .sort()
      .slice(-1)[0];
  }, [reviews]);

  // ---------- Modal handling ----------

  const handleOpenCreate = () => {
    setEditingReview(null);
    setFormData({
      ...EMPTY_FORM,
      employee_id: roster.length ? String(roster[0].id) : '',
      reviewer_id: reviewers.length ? String(reviewers[0].id) : '',
      review_date: new Date().toISOString().slice(0, 10),
    });
    setIsReviewModalOpen(true);
  };

  const handleOpenEdit = (review: PerformanceReviewRecord) => {
    setEditingReview(review);
    setFormData({
      employee_id: String(review.employee_id),
      reviewer_id: String(review.reviewer_id),
      rating: String(review.rating),
      review_date: review.review_date.slice(0, 10),
      feedback: review.feedback ?? '',
    });
    setIsReviewModalOpen(true);
  };

  const buildPayload = (): PerformanceReviewPayload | null => {
    const employeeId = Number(formData.employee_id);

    if (!employeeId) {
      showToast(t('validation.error'), {
        message: t('mgr.perf.selectEmployee'),
        type: 'error',
      });
      return null;
    }

    const rating = Number(formData.rating);

    if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
      showToast(t('validation.error'), {
        message: t('mgr.perf.ratingRange'),
        type: 'error',
      });
      return null;
    }

    if (!formData.review_date) {
      showToast(t('validation.error'), {
        message: t('mgr.perf.dateRequired'),
        type: 'error',
      });
      return null;
    }

    return {
      employee_id: employeeId,
      reviewer_id: formData.reviewer_id
        ? Number(formData.reviewer_id)
        : null,
      rating,
      review_date: formData.review_date,
      feedback: formData.feedback.trim() || null,
    };
  };

  const handleSaveReview = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = buildPayload();
    if (!payload) return;

    setIsSaving(true);

    try {
      if (editingReview) {
        const updated = await SmartHRApi.updatePerformanceReview(
          editingReview.id,
          payload
        );
        setReviews((prev) =>
          prev.map((r) => (r.id === updated.id ? updated : r))
        );
        showToast(t('mgr.perf.updated'), {
          message: `Appraisal for ${updated.employee_name ?? 'employee'} saved (Rating: ${updated.rating}/5).`,
          type: 'success',
        });
      } else {
        const created = await SmartHRApi.createPerformanceReview(payload);
        setReviews((prev) => [created, ...prev]);
        showToast(t('mgr.perf.saved'), {
          message: `Formal appraisal for ${created.employee_name ?? 'employee'} recorded (Rating: ${created.rating}/5).`,
          type: 'success',
        });
      }

      setIsReviewModalOpen(false);
      setEditingReview(null);
    } catch (error) {
      showToast(
        editingReview ? t('mgr.perf.updateFailed') : t('mgr.perf.saveFailed'),
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
        title={t('mgr.perf.title')}
        subtitle={t('mgr.perf.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {totalReviews} Recorded Appraisal{totalReviews === 1 ? '' : 's'}
          </Badge>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={handleOpenCreate}
          >
            {t('mgr.perf.newReview')}
          </Button>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <KpiCard
          title={t('mgr.perf.teamAverage')}
          value={`${averageRating} / 5.0`}
          change={totalReviews ? `${totalReviews} review(s)` : t('mgr.perf.noData')}
          changeType={Number(averageRating) >= 3.5 ? 'positive' : 'neutral'}
          comparison="Scale: 1 to 5"
          icon={<Star className="w-5 h-5 text-amber-500 fill-amber-500" />}
          description={t('mgr.perf.meanRecorded')}
        />
        <KpiCard
          title={t('mgr.perf.reviewsRecorded')}
          value={totalReviews}
          change={`${reviewedEmployeeCount} employee(s)`}
          changeType="positive"
          comparison={
            latestReviewDate
              ? `Latest: ${formatDate(latestReviewDate)}`
              : t('mgr.perf.noReviewsYet')
          }
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
          description={t('mgr.perf.rowsIn')}
        />
        <KpiCard
          title={t('mgr.perf.topRated')}
          value={topRatedCount}
          change={
            totalReviews
              ? `${((topRatedCount / totalReviews) * 100).toFixed(0)}% of reviews`
              : t('mgr.perf.noData')
          }
          changeType="positive"
          comparison="Exceptional tier"
          icon={<Award className="w-5 h-5 text-brand-600" />}
          description={t('mgr.perf.ratingOf5')}
        />
        <KpiCard
          title={t('mgr.perf.needsAttention')}
          value={needsAttentionCount}
          change={needsAttentionCount > 0 ? t('mgr.perf.actionRequired') : t('mgr.perf.noneFlagged')}
          changeType={needsAttentionCount > 0 ? 'negative' : 'positive'}
          comparison="Rating of 1 or 2"
          icon={<BarChart2 className="w-5 h-5 text-brand-600" />}
          description={t('mgr.perf.belowExpectations')}
        />
      </div>

      {/* Rating Distribution & Review Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader
              title={t('mgr.perf.distribution')}
              subtitle={t('mgr.perf.distributionHint')}
              action={
                <Badge variant="purple" dot>
                  {totalReviews} total
                </Badge>
              }
            />
            <div className="space-y-3 pt-1">
              {distribution.map((row) => (
                <div key={row.rating}>
                  <div className="flex justify-between text-xs font-bold mb-1">
                    <span className="text-brand-950 flex items-center gap-1.5">
                      <span
                        className={`w-2.5 h-2.5 rounded-full ${ratingBarClass(
                          row.rating
                        )}`}
                      />
                      {row.rating} - {t(`mgr.perf.rating${row.rating}`)}
                    </span>
                    <span className="text-brand-900 font-extrabold">
                      {row.count} ({row.percent.toFixed(0)}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-stone-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${ratingBarClass(
                        row.rating
                      )}`}
                      style={{ width: `${row.percent}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div>
          <Card>
            <CardHeader
              title={t('mgr.perf.summary')}
              subtitle={t('mgr.perf.summaryHint')}
            />
            <div className="space-y-3 pt-1 text-xs">
              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 flex items-center justify-between">
                <span className="text-stone-500 font-medium">
                  {t('mgr.perf.totalReviews')}
                </span>
                <span className="font-black text-stone-900 text-base">
                  {totalReviews}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 flex items-center justify-between">
                <span className="text-stone-500 font-medium">
                  {t('mgr.perf.employeesReviewed')}
                </span>
                <span className="font-black text-stone-900 text-base">
                  {reviewedEmployeeCount}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-brand-50/80 border border-brand-200 flex items-center justify-between">
                <span className="text-brand-800 font-medium">
                  {t('mgr.perf.averageRating')}
                </span>
                <span className="font-black text-brand-950 text-base">
                  {averageRating}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 flex items-center justify-between">
                <span className="text-stone-500 font-medium">
                  {t('mgr.perf.latestReview')}
                </span>
                <span className="font-bold text-stone-800">
                  {latestReviewDate ? formatDate(latestReviewDate) : '—'}
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Performance Reviews Table */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3.5 px-4">{t('table.employee')}</th>
                <th className="py-3.5 px-4">{t('table.rating')}</th>
                <th className="py-3.5 px-4">Tier</th>
                <th className="py-3.5 px-4">{t('mgr.perf.reviewDate')}</th>
                <th className="py-3.5 px-4">{t('mgr.perf.reviewer')}</th>
                <th className="py-3.5 px-4">{t('mgr.perf.supervisorFeedback')}</th>
                <th className="py-3.5 px-4 text-end">{t('mgr.perf.appraisalAction')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    <Loader2 className="w-7 h-7 mx-auto mb-2 text-stone-300 animate-spin" />
                    {t('mgr.perf.loading')}
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center">
                    <XCircle className="w-7 h-7 mx-auto mb-2 text-rose-300" />
                    <p className="font-semibold text-stone-600">
                      {t('mgr.perf.loadError')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                    <div className="mt-3">
                      <Button variant="outline" size="sm" onClick={loadReviews}>
                        {t('action.retry')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : reviews.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    <Users className="w-8 h-8 mx-auto mb-2 text-stone-300" />
                    <p className="font-semibold text-stone-600">
                      {t('mgr.perf.empty')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">
                      {t('mgr.perf.emptyHint')}
                    </p>
                  </td>
                </tr>
              ) : (
                reviews.map((review) => (
                  <tr
                    key={review.id}
                    className="hover:bg-stone-50/60 transition-colors"
                  >
                    {/* Employee */}
                    <td className="py-3 px-4">
                      <p className="font-bold text-stone-900 text-xs">
                        {review.employee_name ?? t('mgr.perf.unknown')}
                      </p>
                      <p className="text-3xs text-stone-400">
                        {review.position_title ?? t('mgr.perf.noPosition')} •{' '}
                        {review.department_name ?? t('mgr.perf.unassigned')}
                      </p>
                    </td>

                    {/* Rating */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                        <span className="font-extrabold text-stone-900 text-xs">
                          {review.rating} / 5
                        </span>
                      </div>
                    </td>

                    {/* Tier */}
                    <td className="py-3 px-4">
                      <span
                        className={`text-3xs font-bold px-2 py-0.5 rounded-full ${tierPillClass(
                          review.rating
                        )}`}
                      >
                        {t(`mgr.perf.rating${review.rating}`)}
                      </span>
                    </td>

                    {/* Review Date */}
                    <td className="py-3 px-4 text-stone-600 font-mono text-2xs">
                      {formatDate(review.review_date)}
                    </td>

                    {/* Reviewer */}
                    <td className="py-3 px-4">
                      <p className="font-semibold text-brand-800 text-2xs">
                        {review.reviewer_name ?? review.reviewer_email ?? '—'}
                      </p>
                      <p className="text-3xs text-stone-400">
                        {review.reviewer_role ?? ''}
                      </p>
                    </td>

                    {/* Feedback */}
                    <td className="py-3 px-4 max-w-[220px]">
                      <p className="text-2xs text-stone-500 italic truncate">
                        {review.feedback ?? t('mgr.perf.noFeedback')}
                      </p>
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-end">
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-2xs"
                        leftIcon={<Edit3 className="w-3 h-3" />}
                        onClick={() => handleOpenEdit(review)}
                      >
                        {t('mgr.perf.updateReview')}
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Create / Edit Review Modal */}
      <Modal
        isOpen={isReviewModalOpen}
        onClose={() => {
          setIsReviewModalOpen(false);
          setEditingReview(null);
        }}
        title={
          editingReview
            ? `Performance Review: ${editingReview.employee_name ?? t('table.employee')}`
            : t('mgr.perf.newTitle')
        }
        subtitle={
          editingReview
            ? `${editingReview.position_title ?? t('mgr.perf.noPosition')} • Recorded ${formatDate(editingReview.review_date)}`
            : t('mgr.perf.newSubtitle')
        }
        size="lg"
      >
        <form onSubmit={handleSaveReview} className="space-y-4 text-xs">
          {editingReview && (
            <div className="p-3.5 rounded-xl bg-brand-50/60 border border-brand-100 flex justify-between items-center gap-3">
              <div className="min-w-0">
                <p className="font-bold text-stone-900 text-sm">
                  {editingReview.employee_name ?? t('mgr.perf.unknown')}
                </p>
                <p className="text-2xs text-brand-800 truncate">
                  {editingReview.position_title ?? t('mgr.perf.noPosition')} •{' '}
                  {editingReview.department_name ?? t('mgr.perf.unassigned')}
                </p>
              </div>
              <div className="text-end shrink-0">
                <span className="text-3xs text-stone-400 uppercase font-bold block">
                  {t('mgr.perf.currentRating')}
                </span>
                <span className="text-base font-extrabold text-brand-900">
                  {editingReview.rating} / 5
                </span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
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
              label={t('mgr.perf.reviewer')}
              options={reviewerOptions}
              value={formData.reviewer_id}
              onChange={(e) =>
                setFormData({ ...formData, reviewer_id: e.target.value })
              }
              helperText="Reviewers are system users, not employees."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Select
              label={t('mgr.perf.appraisalRating')}
              required
              options={RATING_VALUES.map((r) => ({
                label: `${r} - ${t(`mgr.perf.rating${r}`)}`,
                value: String(r),
              }))}
              value={formData.rating}
              onChange={(e) =>
                setFormData({ ...formData, rating: e.target.value })
              }
              helperText="Whole numbers 1-5 (database constraint)."
            />

            <Input
              label={t('mgr.perf.reviewDate')}
              type="date"
              required
              value={formData.review_date}
              onChange={(e) =>
                setFormData({ ...formData, review_date: e.target.value })
              }
            />
          </div>

          <Textarea
            label={t('mgr.perf.evaluationSummary')}
            rows={4}
            value={formData.feedback}
            onChange={(e) =>
              setFormData({ ...formData, feedback: e.target.value })
            }
            placeholder={t('mgr.perf.evaluationPlaceholder')}
          />

          <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => {
                setIsReviewModalOpen(false);
                setEditingReview(null);
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
              {editingReview ? t('action.saveChanges') : t('mgr.perf.complete')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
