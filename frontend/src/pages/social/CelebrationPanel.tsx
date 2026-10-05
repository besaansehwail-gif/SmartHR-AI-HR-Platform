import React, { useCallback, useEffect, useState } from 'react';
import { PartyPopper, RefreshCw, Check, X, Info, Send } from 'lucide-react';

import { AuthedImage } from '../../components/ui/AuthedImage';
import { Button } from '../../components/ui/Button';
import { useT } from '../../i18n/LocaleProvider';
import { SmartHRApi } from '../../services/api';
import type { CelebrationDraft, CelebrationStatus } from '../../types';

/**
 * AI Employee Celebration - HR's queue of prepared celebrations.
 *
 * **Nobody picks an employee here any more.** A daily sweep
 * (`scripts/run_daily_celebrations.py`) reads the employee dates (hire,
 * birth, promotion, graduation, wedding, new baby), finds who is celebrating
 * today, runs the three agents once per occasion and leaves a draft. This panel is where those drafts are read and decided on.
 *
 * The decision is the point of the whole design: the AI detects, writes and
 * reviews, and a person posts. Pressing Post calls
 * `social_service.create_post()` under the recruiter's own account, so the
 * celebration is moderated, audited and attributed exactly as a post they
 * typed - there is no second publishing path.
 *
 * **A draft the Review Agent rejected is shown and cannot be posted.** Hiding
 * it would make "the reviewer said no" indistinguishable from "nothing
 * happened"; offering Post anyway would make the reviewer decorative. The
 * server decides that, in `postable`, and this file reads it rather than
 * re-deriving the rule.
 */

interface CelebrationPanelProps {
  /** Puts an approved draft in the feed composer, for HR to edit before posting. */
  onUseInComposer: (message: string) => void;
  /** Called after a post is created, so the feed can re-read itself. */
  onPosted?: () => void;
}

export const CelebrationPanel: React.FC<CelebrationPanelProps> = ({
  onUseInComposer,
  onPosted,
}) => {
  const { t } = useT();

  const [drafts, setDrafts] = useState<CelebrationDraft[]>([]);
  const [status, setStatus] = useState<CelebrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [sweeping, setSweeping] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDrafts = useCallback(async () => {
    try {
      const response = await SmartHRApi.getCelebrationDrafts();
      setDrafts(response.drafts);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('social.celebration.failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    let live = true;

    const load = async () => {
      await loadDrafts();
      try {
        const config = await SmartHRApi.getCelebrationStatus();
        if (live) setStatus(config);
      } catch {
        // The panel is an extra on somebody else's page; if its own status
        // call fails it says nothing rather than putting a banner over a
        // working feed.
        if (live) setStatus(null);
      }
    };

    void load();
    return () => {
      live = false;
    };
  }, [loadDrafts]);

  const runSweep = useCallback(async () => {
    setSweeping(true);
    setError(null);
    setNote(null);

    try {
      const summary = await SmartHRApi.runCelebrationSweep();
      // Idempotent by design, so "nothing new" is a normal, reportable
      // outcome rather than a failure.
      setNote(
        summary.prepared > 0
          ? t('social.celebration.sweepPrepared', {
              count: String(summary.prepared),
            })
          : summary.skipped_existing > 0
            ? t('social.celebration.sweepAlready')
            : t('social.celebration.sweepNone')
      );
      await loadDrafts();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('social.celebration.failed'));
    } finally {
      setSweeping(false);
    }
  }, [loadDrafts, t]);

  const post = useCallback(
    async (draft: CelebrationDraft) => {
      setBusyId(draft.id);
      setError(null);
      setNote(null);

      try {
        await SmartHRApi.approveCelebrationDraft(draft.id);
        setNote(t('social.celebration.posted'));
        await loadDrafts();
        onPosted?.();
      } catch (err) {
        setError(err instanceof Error ? err.message : t('social.celebration.failed'));
      } finally {
        setBusyId(null);
      }
    },
    [loadDrafts, onPosted, t]
  );

  const dismiss = useCallback(
    async (draft: CelebrationDraft) => {
      setBusyId(draft.id);
      setError(null);

      try {
        await SmartHRApi.dismissCelebrationDraft(draft.id);
        await loadDrafts();
      } catch (err) {
        setError(err instanceof Error ? err.message : t('social.celebration.failed'));
      } finally {
        setBusyId(null);
      }
    },
    [loadDrafts, t]
  );

  return (
    <div className="bg-white rounded-2xl border border-stone-200/80 shadow-card p-4">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <PartyPopper className="w-4 h-4 text-brand-600 shrink-0" aria-hidden="true" />
          <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500 truncate">
            {t('social.celebration.title')}
          </h2>
        </div>

        <button
          type="button"
          onClick={runSweep}
          disabled={sweeping}
          title={t('social.celebration.checkNow')}
          className="shrink-0 h-7 px-2 rounded-lg inline-flex items-center gap-1.5 text-3xs font-bold text-stone-600 hover:text-brand-700 hover:bg-brand-50 transition-colors disabled:opacity-50"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${sweeping ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          {t('social.celebration.checkNow')}
        </button>
      </div>

      <p className="text-3xs text-stone-500 leading-relaxed mb-3">
        {t('social.celebration.subtitleAuto')}
      </p>

      {note && (
        <p className="mb-2.5 text-3xs text-stone-600 bg-sand-50 border border-stone-200 rounded-lg p-2 leading-relaxed">
          {note}
        </p>
      )}

      {error && (
        <p className="mb-2.5 text-3xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2 leading-relaxed">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-3xs text-stone-400 py-2">{t('state.loading')}</p>
      ) : drafts.length === 0 ? (
        <p className="text-3xs text-stone-500 py-2 leading-relaxed">
          {t('social.celebration.queueEmpty')}
        </p>
      ) : (
        <ul className="space-y-3 -mx-1">
          {drafts.map((draft) => {
            const busy = busyId === draft.id;

            return (
              <li
                key={draft.id}
                className="px-1 pb-3 border-b border-stone-100 last:border-0 last:pb-0"
              >
                {/* Who, and what for - both from the employees row. */}
                <p className="text-2xs font-extrabold text-stone-900 truncate">
                  {draft.employee_name ?? `#${draft.employee_id}`}
                </p>
                <p className="text-3xs text-stone-500 mb-2">
                  {t(`social.celebration.occasion.${draft.occasion}`)}
                  {draft.years !== null ? ` · ${draft.years}` : ''}
                </p>

                {draft.message && (
                  <div className="rounded-lg border border-stone-200 overflow-hidden mb-2">
                    {/* The image the post would carry, shown BEFORE the
                        decision - so HR approves what they actually saw. */}
                    {draft.image_url && (
                      <AuthedImage
                        src={draft.image_url}
                        alt={t('social.celebration.imageAlt')}
                        className="w-full h-24 object-cover bg-sand-100"
                        fallback={<div className="w-full h-24 bg-sand-100" />}
                      />
                    )}
                    <p className="text-2xs text-stone-800 leading-relaxed bg-sand-50 p-2.5 whitespace-pre-wrap">
                      {draft.message}
                    </p>
                  </div>
                )}

                {/* The Review Agent's verdict, always shown. */}
                <div
                  className={`text-3xs leading-relaxed rounded-lg p-2 border flex gap-1.5 mb-2 ${
                    draft.review.approved
                      ? 'text-emerald-800 bg-emerald-50 border-emerald-200'
                      : 'text-amber-900 bg-amber-50 border-amber-200'
                  }`}
                >
                  {draft.review.approved ? (
                    <Check className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
                  ) : (
                    <X className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
                  )}
                  <span>
                    <span className="font-bold">
                      {draft.review.approved
                        ? t('social.celebration.approved')
                        : t('social.celebration.rejected')}
                    </span>
                    {draft.review.reason ? ` ${draft.review.reason}` : ''}
                    {draft.retry_count > 0 && (
                      <span className="block mt-1 opacity-80">
                        {t('social.celebration.retries', {
                          count: String(draft.retry_count),
                          max: String(status?.max_retries ?? 2),
                        })}
                      </span>
                    )}
                  </span>
                </div>

                {/* Post is offered only for a draft the server says is
                    postable - approved, pending and not empty. */}
                {draft.postable ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Button
                      onClick={() => post(draft)}
                      disabled={busy}
                      variant="primary"
                      className="!h-8 !text-3xs"
                    >
                      <Send className="w-3 h-3 me-1.5" aria-hidden="true" />
                      {busy
                        ? t('social.celebration.posting')
                        : t('social.celebration.post')}
                    </Button>

                    <button
                      type="button"
                      onClick={() => onUseInComposer(draft.message ?? '')}
                      disabled={busy}
                      className="h-8 px-2.5 rounded-lg text-3xs font-bold text-stone-600 hover:text-brand-700 hover:bg-brand-50 transition-colors disabled:opacity-50"
                    >
                      {t('social.celebration.edit')}
                    </button>

                    <button
                      type="button"
                      onClick={() => dismiss(draft)}
                      disabled={busy}
                      className="h-8 px-2.5 rounded-lg text-3xs font-bold text-stone-500 hover:text-rose-700 hover:bg-rose-50 transition-colors disabled:opacity-50"
                    >
                      {t('social.celebration.dismiss')}
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <p className="text-3xs text-stone-500 leading-relaxed flex-1 min-w-0">
                      {t('social.celebration.notPostable')}
                    </p>
                    <button
                      type="button"
                      onClick={() => dismiss(draft)}
                      disabled={busy}
                      className="h-8 px-2.5 rounded-lg text-3xs font-bold text-stone-500 hover:text-rose-700 hover:bg-rose-50 transition-colors disabled:opacity-50"
                    >
                      {t('social.celebration.dismiss')}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* Said plainly, once: an occasion is found only from a date recorded
          on the employee, so nobody waits for a post that has no date
          behind it. */}
      {status && (
        <p className="mt-3 pt-3 border-t border-stone-100 text-3xs text-stone-400 leading-relaxed flex gap-1.5">
          <Info className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
          {t('social.celebration.dataLimit')}
        </p>
      )}
    </div>
  );
};
