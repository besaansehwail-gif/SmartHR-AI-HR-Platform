import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Image as ImageIcon,
  MessageSquare,
  Shield,
  ShieldOff,
  Trash2,
} from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState, InfoPanel, SkeletonCard } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import {
  SocialModerationReview,
  SocialModerationStatus,
  SocialModerationSummary,
} from '../../types';
import { useT } from '../../i18n';
import { formatDateTime } from '../../i18n/format';

/**
 * Social Moderation - the HR review workspace.
 *
 * This page lives in the **HR** workspace and its PageId starts `hr-`, which
 * is not cosmetic: `workspaceOf()` maps every `soc-` page to the social
 * workspace, and roles 1-4 all have that. Naming it `soc-moderation` would
 * have put a nav entry to it in front of Managers and Employees. The real
 * boundary is `require_roles(1, 2)` on the five `/social/moderation*` routes,
 * and `scripts/test_social_moderation.py` proves it - but a nav entry a
 * Manager can see is still a bug.
 *
 * **It is an HR workspace, not a security console.** Warm palette, the same
 * Card and Badge as every other HR screen, the content shown as the words a
 * colleague actually wrote rather than as a payload to be analysed.
 *
 * **Everything on a card is the server's answer.** The flag, the categories,
 * the severity and the confidence come from `/social/moderation`; nothing is
 * inferred in the browser, and a decision re-reads the row it changed rather
 * than patching a number locally.
 *
 * Two rules the UI holds to:
 *
 *   * A null `confidence` renders as **"Not scored"**, never as 0%. Null
 *     means no model ran - the same rule `screening_service` and the
 *     interview report already follow, for the same reason: 0% beside
 *     somebody's post reads as a verdict that was never reached.
 *
 *   * An `unavailable` decision is labelled as *the check not having
 *     happened*, not as a finding. A reviewer opening this queue needs to
 *     know instantly whether the AI found something or never ran.
 */

const TABS: SocialModerationStatus[] = ['pending', 'approved', 'removed'];

const TYPE_ICON: Record<string, React.ReactNode> = {
  post: <MessageSquare className="w-3.5 h-3.5" aria-hidden="true" />,
  comment: <MessageSquare className="w-3.5 h-3.5" aria-hidden="true" />,
  story: <ImageIcon className="w-3.5 h-3.5" aria-hidden="true" />,
};

const SEVERITY_VARIANT: Record<string, 'warning' | 'danger' | 'neutral'> = {
  low: 'neutral',
  medium: 'warning',
  high: 'danger',
};

export const SocialModerationPage: React.FC = () => {
  const { t, locale } = useT();
  const { showToast } = useToast();

  const [tab, setTab] = useState<SocialModerationStatus>('pending');
  const [reviews, setReviews] = useState<SocialModerationReview[]>([]);
  const [summary, setSummary] = useState<SocialModerationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [queue, head] = await Promise.all([
        SmartHRApi.getSocialModeration({ status: tab }),
        SmartHRApi.getSocialModerationSummary(),
      ]);

      setReviews(queue.reviews);
      setSummary(head);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('social.moderation.loadError'));
    } finally {
      setLoading(false);
    }
  }, [tab, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (review: SocialModerationReview, approve: boolean) => {
    setBusyId(review.id);

    try {
      const note = notes[review.id]?.trim() || undefined;

      if (approve) {
        await SmartHRApi.approveSocialModeration(review.id, note);
        showToast(t('social.moderation.approved'), { type: 'success' });
      } else {
        await SmartHRApi.removeSocialModeration(review.id, note);
        showToast(t('social.moderation.removed'), { type: 'success' });
      }

      // Re-read rather than splicing the row out locally: the counts in the
      // header come from the server too, and the two must not disagree.
      await load();
    } catch (err) {
      showToast(t('social.moderation.actionFailed'), {
        type: 'error',
        message: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusyId(null);
    }
  };

  const counts = summary?.counts;

  return (
    <div>
      <PageHeader
        title={t('social.moderation.title')}
        subtitle={t('social.moderation.subtitle')}
        icon={<Shield className="w-5 h-5" aria-hidden="true" />}
        badge={
          counts?.pending ? (
            <Badge variant="warning" dot>
              {counts.pending}
            </Badge>
          ) : undefined
        }
        toolbar={
          <div className="flex flex-wrap items-center gap-2">
            {TABS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setTab(value)}
                className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-colors border ${
                  tab === value
                    ? 'bg-brand-500 border-brand-500 text-white'
                    : 'bg-white border-stone-200 text-stone-600 hover:bg-sand-100'
                }`}
              >
                {t(`social.moderation.tab.${value}`)}
                {counts && counts[value] > 0 && (
                  <span
                    className={`ms-2 text-3xs font-extrabold ${
                      tab === value ? 'text-white/80' : 'text-stone-400'
                    }`}
                  >
                    {counts[value]}
                  </span>
                )}
              </button>
            ))}
          </div>
        }
      />

      {/* What this page is and is not. Stated once, at the top, because a
          reviewer arriving here for the first time needs to know that the
          model advised and they decide. */}
      <InfoPanel
        title={t('social.moderation.aiNote')}
        icon={<Shield className="w-4 h-4" aria-hidden="true" />}
        tone="brand"
        className="mb-5"
      >
        {summary && !summary.enabled && (
          <p className="mt-2 font-semibold">{t('social.moderation.disabled')}</p>
        )}
        {summary && summary.enabled && !summary.model_configured && (
          <p className="mt-2 font-semibold">{t('social.moderation.modelMissing')}</p>
        )}
        {summary?.model_configured && (
          <p className="mt-2 text-2xs text-brand-800/80">
            {t('social.moderation.modelLabel')}{' '}
            {/* Provider and model are configuration values, shown as stored. */}
            <span className="font-semibold">
              {summary.provider} / {summary.model}
            </span>
          </p>
        )}
      </InfoPanel>

      {loading && (
        <div className="space-y-4">
          <SkeletonCard rows={3} />
          <SkeletonCard rows={3} />
        </div>
      )}

      {!loading && error && (
        <ErrorState
          title={t('social.moderation.loadError')}
          message={error}
          onRetry={() => void load()}
        />
      )}

      {!loading && !error && reviews.length === 0 && (
        <EmptyState
          icon={<Shield className="w-6 h-6" aria-hidden="true" />}
          title={t(`social.moderation.empty.${tab}.title`)}
          description={t(`social.moderation.empty.${tab}.body`)}
        />
      )}

      {!loading && !error && reviews.length > 0 && (
        <div className="space-y-4">
          {reviews.map((review) => {
            const unavailable = review.ai_decision === 'unavailable';

            return (
              <Card key={review.id} className="p-5">
                {/* --- who and what ------------------------------------- */}
                <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* A person's name is a database value, never translated. */}
                      <span className="text-sm font-extrabold text-stone-900 truncate">
                        {review.author?.name ?? review.author?.email}
                      </span>

                      <Badge variant="outline" size="sm">
                        <span className="flex items-center gap-1.5">
                          {TYPE_ICON[review.content_type]}
                          {t(`social.moderation.type.${review.content_type}`)}
                        </span>
                      </Badge>
                    </div>

                    {(review.author?.position || review.author?.department) && (
                      <p className="text-3xs text-stone-500 mt-0.5 truncate">
                        {[review.author?.position, review.author?.department]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    )}
                  </div>

                  <p className="text-3xs text-stone-400 shrink-0">
                    {t('social.moderation.submitted')}:{' '}
                    {formatDateTime(review.created_at, locale)}
                  </p>
                </div>

                {/* --- the content being judged ------------------------- */}
                {review.content_exists ? (
                  <blockquote className="border-s-2 border-sand-300 bg-sand-50 rounded-e-xl ps-4 pe-3 py-3 mb-4">
                    <p className="text-sm text-stone-800 whitespace-pre-wrap break-words">
                      {review.content}
                    </p>
                  </blockquote>
                ) : (
                  <p className="text-xs text-stone-500 italic mb-4">
                    {t('social.moderation.contentGone')}
                  </p>
                )}

                {/* --- what the model said ------------------------------ */}
                {unavailable ? (
                  <div className="flex items-start gap-2.5 mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200">
                    <AlertTriangle
                      className="w-4 h-4 text-amber-600 shrink-0 mt-0.5"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-xs font-bold text-amber-900">
                        {t('social.moderation.unavailable')}
                      </p>
                      <p className="text-2xs text-amber-800 mt-0.5">
                        {t(
                          `social.moderation.unavailable.${review.error_code ?? 'llm_error'}`
                        )}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-4">
                    {review.categories.length > 0 && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                          {t('social.moderation.flaggedFor')}
                        </span>
                        {review.categories.map((category) => (
                          <Badge key={category} variant="danger" size="sm">
                            {t(`social.moderation.category.${category}`)}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {review.severity && (
                      <div className="flex items-center gap-2">
                        <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                          {t('social.moderation.severity')}
                        </span>
                        <Badge variant={SEVERITY_VARIANT[review.severity]} size="sm">
                          {t(`social.moderation.severity.${review.severity}`)}
                        </Badge>
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                        {t('social.moderation.confidence')}
                      </span>
                      {/* Null is "no model ran", which is not 0%. */}
                      <span className="text-xs font-bold text-stone-700">
                        {review.confidence === null
                          ? t('social.moderation.notScored')
                          : `${Math.round(review.confidence * 100)}%`}
                      </span>
                    </div>
                  </div>
                )}

                {review.reason && !unavailable && (
                  <p className="text-xs text-stone-600 mb-4">
                    <span className="font-bold text-stone-500">
                      {t('social.moderation.reason')}:
                    </span>{' '}
                    {/* Model output about this specific post, rendered as
                        written - the rule the assistant and the interview
                        report already follow. */}
                    {review.reason}
                  </p>
                )}

                {/* --- the decision ------------------------------------- */}
                {review.status === 'pending' ? (
                  <div className="pt-4 border-t border-stone-200/80">
                    <label className="block">
                      <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                        {t('social.moderation.note')}
                      </span>
                      <input
                        type="text"
                        value={notes[review.id] ?? ''}
                        onChange={(event) =>
                          setNotes((current) => ({
                            ...current,
                            [review.id]: event.target.value,
                          }))
                        }
                        placeholder={t('social.moderation.notePlaceholder')}
                        className="mt-1.5 w-full rounded-xl border border-stone-200 bg-white px-3.5 py-2 text-xs text-stone-800 placeholder:text-stone-400 focus:border-brand-400 focus:outline-none"
                      />
                    </label>

                    <div className="flex flex-wrap gap-2.5 mt-3.5">
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={busyId === review.id || !review.content_exists}
                        onClick={() => void decide(review, true)}
                      >
                        <Check className="w-3.5 h-3.5 me-1.5" aria-hidden="true" />
                        {t('social.moderation.approve')}
                      </Button>

                      <Button
                        size="sm"
                        variant="danger"
                        disabled={busyId === review.id || !review.content_exists}
                        onClick={() => void decide(review, false)}
                      >
                        <Trash2 className="w-3.5 h-3.5 me-1.5" aria-hidden="true" />
                        {t('social.moderation.remove')}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="pt-3.5 border-t border-stone-200/80 flex flex-wrap items-center gap-2 text-3xs text-stone-500">
                    <Badge
                      variant={review.status === 'approved' ? 'success' : 'neutral'}
                      size="sm"
                    >
                      <span className="flex items-center gap-1.5">
                        {review.status === 'approved' ? (
                          <Check className="w-3 h-3" aria-hidden="true" />
                        ) : (
                          <ShieldOff className="w-3 h-3" aria-hidden="true" />
                        )}
                        {t(`social.moderation.tab.${review.status}`)}
                      </span>
                    </Badge>

                    {review.reviewer && (
                      <span>
                        {t('social.moderation.reviewedBy')}{' '}
                        <span className="font-semibold text-stone-700">
                          {review.reviewer.name ?? review.reviewer.email}
                        </span>
                        {review.reviewed_at &&
                          ` · ${formatDateTime(review.reviewed_at, locale)}`}
                      </span>
                    )}

                    {review.reviewer_note && (
                      <span className="italic">“{review.reviewer_note}”</span>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
