import React, { useCallback, useEffect, useState } from 'react';
import { FileText, Info, MessageSquareQuote, RefreshCw, ShieldCheck } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Tabs } from '../ui/Tabs';
import { Select } from '../ui/Input';
import { ErrorState, InfoPanel, InlineEmpty, LoadingState } from '../ui/States';
import { useToast } from '../ui/Toast';
import { SmartHRApi } from '../../services/api';
import { AiInterviewReport, AiReportAnswer, AiReportContext } from '../../types';
import { formatDateTime, useT } from '../../i18n';

/**
 * The AI Interview Report for HR (Phase 8).
 *
 *   GET /ai-interview/report/{interview_id}  -> read-only, built from the
 *   answers and analyses Phase 7 stored. No model is called to show it.
 *
 * Everything here is factual: counts of how answers were analysed, the job's
 * own requirement phrases, and quotes. There is no score, rating, percentage,
 * ranking or recommendation - the backend has no field for one and this panel
 * adds none. The counts are deliberately rendered in one neutral tone, so
 * "not addressed" never reads as a red mark against a person.
 *
 * An analysis that failed or is still pending is shown as exactly that - "Not
 * analysed" / "Not analysed yet" - never as a negative finding. Transcripts
 * and AI-written text are shown as stored and are not translated.
 *
 * Phase 11.4: the interview as it actually ran - `question_flow` (main
 * questions in the order heard, each follow-up nested under its main question
 * and labelled "Follow-up to question N"), `coverage` (answered, follow-ups,
 * highest reached, not reached in the current bank) and `context` (whether the
 * analyses had Job / CV / Matching context - never the context itself, never
 * a score). All derived by the backend from stored answers.
 */

export interface InterviewReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  interviewId: number;
}

type TabId = 'summary' | 'questions';

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="min-w-0">
    <p className="text-3xs font-bold uppercase tracking-wider text-stone-500">{label}</p>
    <div className="text-sm text-stone-900 mt-0.5 break-words">{children}</div>
  </div>
);

const Heading: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h4 className="text-xs font-bold text-stone-800 mb-2">{children}</h4>
);

/** Text written by the applicant or by the model: shown as stored, direction
 *  taken from the text itself, never translated. */
const Stored: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <span dir="auto" className={className}>{children}</span>
);

const Chips: React.FC<{ items: string[]; empty: string }> = ({ items, empty }) =>
  items.length ? (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item} variant="neutral"><Stored>{item}</Stored></Badge>
      ))}
    </div>
  ) : (
    <p className="text-xs text-stone-500 italic">{empty}</p>
  );

export const InterviewReportModal: React.FC<InterviewReportModalProps> = ({ isOpen, onClose, interviewId }) => {
  const { t, locale } = useT();
  const { showToast } = useToast();
  const [report, setReport] = useState<AiInterviewReport | null>(null);
  const [sessionId, setSessionId] = useState<number | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isRerunning, setIsRerunning] = useState(false);
  const [tab, setTab] = useState<TabId>('summary');

  const load = useCallback(async (session?: number) => {
    setIsLoading(true);
    setError(null);
    try {
      setReport(await SmartHRApi.getAiInterviewReport(interviewId, session));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('hr.aiReport.loadFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [interviewId, t]);

  useEffect(() => {
    if (!isOpen) return;
    setReport(null);
    setSessionId(undefined);
    setTab('summary');
    void load();
  }, [isOpen, interviewId, load]);

  const chooseSession = (value: string) => {
    const id = Number(value);
    setSessionId(id);
    void load(id);
  };

  const unanalysed = report
    ? report.summary.analysis_status_counts.failed + report.summary.analysis_status_counts.pending
    : 0;

  const rerun = async () => {
    setIsRerunning(true);
    try {
      const result = await SmartHRApi.reanalyseAiInterview(interviewId);
      showToast(t('hr.aiReport.rerunDone', { count: result.attempted }), { type: 'success' });
      await load(sessionId ?? report?.session?.session_id);
    } catch (err) {
      showToast(t('hr.aiReport.rerunFailed'), {
        message: err instanceof Error ? err.message : undefined,
        type: 'error',
      });
    } finally {
      setIsRerunning(false);
    }
  };

  const addressesLabel = (value: string) => t(`hr.aiReport.addresses.${value}`);

  const renderAnalysis = (answer: AiReportAnswer) => {
    if (answer.analysis_status === 'pending') {
      return <p className="text-xs text-stone-500 italic">{t('hr.aiReport.notAnalysedYet')}</p>;
    }
    if (answer.analysis_status === 'failed' || !answer.analysis) {
      return (
        <p className="text-xs text-stone-500 italic">
          {t('hr.aiReport.notAnalysed')}
          {answer.error_code && (
            <span className="ms-1 font-mono not-italic text-3xs text-stone-400">({answer.error_code})</span>
          )}
        </p>
      );
    }
    const a = answer.analysis;
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="neutral">{t('hr.aiReport.addressesLabel')}: {addressesLabel(a.addresses_question)}</Badge>
          <Badge variant="neutral">{t('hr.aiReport.specificityLabel')}: {t(`hr.aiReport.specificity.${a.specificity}`)}</Badge>
          <Badge variant="neutral">{t('hr.aiReport.clarityLabel')}: {t(`hr.aiReport.clarity.${a.clarity}`)}</Badge>
        </div>
        {a.summary && (
          <Field label={t('hr.aiReport.summaryLabel')}><Stored>{a.summary}</Stored></Field>
        )}
        <div>
          <Heading>{t('hr.aiReport.evidence')}</Heading>
          {a.evidence.length ? (
            <ul className="space-y-2">
              {a.evidence.map((e, i) => (
                <li key={i} className="text-xs">
                  <Stored className="text-stone-800">{e.point}</Stored>
                  <blockquote className="mt-1 border-s-2 border-sand-300 ps-2 text-stone-600 italic">
                    <Stored>“{e.quote}”</Stored>
                  </blockquote>
                  <span className="text-3xs text-stone-400">{t(`hr.aiReport.evidenceType.${e.type}`)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-stone-500 italic">{t('hr.aiReport.none')}</p>
          )}
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <Heading>{t('hr.aiReport.skillsMentioned')}</Heading>
            <Chips items={a.skills_mentioned.map((s) => s.skill)} empty={t('hr.aiReport.none')} />
          </div>
          <div>
            <Heading>{t('hr.aiReport.requirementsReferenced')}</Heading>
            <Chips items={a.job_requirements_referenced} empty={t('hr.aiReport.none')} />
          </div>
        </div>
        <div>
          <Heading>{t('hr.aiReport.cvRelation')}</Heading>
          {a.cv_relation.length ? (
            <ul className="space-y-1">
              {a.cv_relation.map((c, i) => (
                <li key={i} className="text-xs text-stone-700">
                  <Stored>“{c.statement}”</Stored>
                  <span className="ms-2 text-3xs text-stone-500">— {t(`hr.aiReport.cv.${c.relation}`)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-stone-500 italic">{t('hr.aiReport.none')}</p>
          )}
        </div>
        <div>
          <Heading>{t('hr.aiReport.notCovered')}</Heading>
          <Chips items={a.not_covered} empty={t('hr.aiReport.none')} />
        </div>
      </div>
    );
  };

  /** Phase 11.4: what was asked, in what order, and what was not reached. */
  const renderCoverage = (r: AiInterviewReport) => {
    const c = r.coverage!;
    const order =
      c.order_matches_current_bank === null ? 'unknown' : c.order_matches_current_bank ? 'bank' : 'adaptive';
    return (
      <section data-testid="ai-report-coverage">
        <Heading>{t('hr.aiReport.sectionCoverage')}</Heading>
        <div className="flex flex-wrap gap-2 mb-3">
          <Badge variant="outline" size="md">{t('hr.aiReport.mainAnswered')}: {c.main_questions_answered_count}</Badge>
          <Badge variant="outline" size="md">{t('hr.aiReport.followUpsAnswered')}: {c.follow_ups_answered_count}</Badge>
          <Badge variant="outline" size="md">{t('hr.aiReport.highestMain')}: {c.highest_main_question_reached ?? '—'}</Badge>
        </div>
        <p className="text-xs text-stone-600 mb-2">{t(`hr.aiReport.order.${order}`)}</p>
        <Heading>{t('hr.aiReport.askedOrder')}</Heading>
        <ol className="space-y-1 mb-3">
          {r.question_flow.map((e) => (
            <li key={e.number} className="text-xs text-stone-700 flex gap-2">
              <span className="shrink-0 font-bold text-stone-500">{t('hr.aiReport.questionShort', { number: e.number })}</span>
              <span className="min-w-0">
                <Stored>{e.main?.question_text ?? '—'}</Stored>
                {e.follow_up && <span className="ms-2 text-3xs text-brand-700">{t('hr.aiReport.withFollowUp')}</span>}
              </span>
            </li>
          ))}
        </ol>
        <Heading>{t('hr.aiReport.notReached')}</Heading>
        {c.not_reached.length ? (
          <ul className="space-y-1">
            {c.not_reached.map((q) => (
              <li key={q.question_id} className="text-xs text-stone-600"><Stored>{q.question_text}</Stored></li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-stone-500 italic">{t('hr.aiReport.none')}</p>
        )}
        <p className="text-3xs text-stone-500 mt-1">{t('hr.aiReport.notReachedNote')}</p>
      </section>
    );
  };

  /** Phase 11.4: which contexts the analyses had - never the context itself. */
  const renderContext = (c: AiReportContext) => (
    <section data-testid="ai-report-context">
      <Heading>{t('hr.aiReport.sectionContext')}</Heading>
      {c.basis === 'no_completed_analyses' ? (
        <p className="text-xs text-stone-500 italic">{t('hr.aiReport.noAnalysesYet')}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {(['job', 'cv', 'matching'] as const).map((k) => (
            <Badge key={k} variant="neutral">
              {t(`hr.aiReport.context.${k}`)}: {t(c[k] ? 'hr.aiReport.context.available' : 'hr.aiReport.context.notAvailable')}
            </Badge>
          ))}
        </div>
      )}
      <p className="text-3xs text-stone-500 mt-1">{t('hr.aiReport.contextNote')}</p>
    </section>
  );

  const renderSummary = (r: AiInterviewReport) => {
    const s = r.summary;
    const counts: [string, number][] = [
      ['hr.aiReport.addresses.fully', s.addresses_question_counts.addressed],
      ['hr.aiReport.addresses.partially', s.addresses_question_counts.partially_addressed],
      ['hr.aiReport.addresses.not_addressed', s.addresses_question_counts.not_addressed],
      ['hr.aiReport.addresses.unclear', s.addresses_question_counts.unclear],
    ];
    return (
      <div className="space-y-5">
        <section>
          <Heading>{t('hr.aiReport.sectionInterview')}</Heading>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 rounded-xl border border-stone-200 p-4">
            <Field label={t('hr.aiReport.job')}><Stored>{r.interview.job_title ?? '—'}</Stored></Field>
            <Field label={t('hr.aiReport.department')}><Stored>{r.interview.department ?? '—'}</Stored></Field>
            <Field label={t('hr.aiReport.scheduledAt')}>{formatDateTime(r.interview.scheduled_at, locale)}</Field>
            <Field label={t('hr.aiReport.interviewStatus')}>{t(`status.interview.${r.interview.status}`)}</Field>
            <Field label={t('hr.aiReport.answeredCount')}>{r.interview.answered_count}</Field>
            <Field label={t('hr.aiReport.highestQuestion')}>{r.interview.highest_question_reached ?? '—'}</Field>
            {r.session && (
              <>
                <Field label={t('hr.aiReport.sessionStarted')}>{formatDateTime(r.session.started_at, locale)}</Field>
                <Field label={t('hr.aiReport.firstAnswer')}>{formatDateTime(r.session.first_answer_at ?? null, locale)}</Field>
                <Field label={t('hr.aiReport.lastAnswer')}>{formatDateTime(r.session.last_answer_at ?? null, locale)}</Field>
              </>
            )}
          </div>
          <p className="text-3xs text-stone-500 mt-2">{t('hr.aiReport.plannedNotRecorded')}</p>
          <p className="text-3xs text-stone-500 mt-0.5">{t('hr.aiReport.durationNotRecorded')}</p>
        </section>

        {r.coverage && renderCoverage(r)}
        {r.context && renderContext(r.context)}

        <section>
          <Heading>{t('hr.aiReport.sectionSummary')}</Heading>
          {!s.complete && s.answered_count > 0 && (
            <InfoPanel tone="neutral" icon={<Info className="w-4 h-4" />} title={t('hr.aiReport.incompleteTitle')} className="mb-3">
              {t('hr.aiReport.incompleteBody', {
                completed: s.analysis_status_counts.completed,
                total: s.answered_count,
              })}
            </InfoPanel>
          )}
          <div className="flex flex-wrap gap-2 mb-4">
            {counts.map(([key, value]) => (
              <Badge key={key} variant="outline" size="md">{t(key)}: {value}</Badge>
            ))}
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Heading>{t('hr.aiReport.requirementsReferenced')}</Heading>
              <Chips items={s.requirements_referenced} empty={t('hr.aiReport.none')} />
            </div>
            <div>
              <Heading>{t('hr.aiReport.requirementsNotReferenced')}</Heading>
              {s.requirements_basis === 'no_completed_analyses' ? (
                <p className="text-xs text-stone-500 italic">{t('hr.aiReport.noAnalysesYet')}</p>
              ) : (
                <Chips items={s.requirements_not_referenced} empty={t('hr.aiReport.none')} />
              )}
              <p className="text-3xs text-stone-500 mt-1">{t('hr.aiReport.notReferencedNote')}</p>
            </div>
          </div>
          <div className="mt-4">
            <Heading>{t('hr.aiReport.skillsMentioned')}</Heading>
            <Chips items={s.skills_mentioned.map((k) => k.skill)} empty={t('hr.aiReport.none')} />
            <p className="text-3xs text-stone-500 mt-1">{t('hr.aiReport.skillsNote')}</p>
          </div>
          <div className="mt-4">
            <Heading>{t('hr.aiReport.keyEvidence')}</Heading>
            {s.key_evidence.length ? (
              <ul className="space-y-2">
                {s.key_evidence.map((e, i) => (
                  <li key={i} className="text-xs flex gap-2">
                    <span className="shrink-0 font-bold text-stone-500">{t('hr.aiReport.questionShort', { number: e.question_number })}</span>
                    <blockquote className="border-s-2 border-sand-300 ps-2 text-stone-700 italic">
                      <Stored>“{e.quote}”</Stored>
                    </blockquote>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-stone-500 italic">{t('hr.aiReport.none')}</p>
            )}
            {s.key_evidence_total > s.key_evidence.length && (
              <p className="text-3xs text-stone-500 mt-1">
                {t('hr.aiReport.moreEvidence', { shown: s.key_evidence.length, total: s.key_evidence_total })}
              </p>
            )}
          </div>
          <div className="mt-4">
            <Heading>{t('hr.aiReport.notCovered')}</Heading>
            {s.not_covered.length ? (
              <ul className="space-y-1">
                {s.not_covered.map((n) => (
                  <li key={n.sequence} className="text-xs text-stone-700">
                    <span className="font-bold text-stone-500 me-2">{t('hr.aiReport.questionShort', { number: n.question_number })}</span>
                    <Stored>{n.items.join(' · ')}</Stored>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-stone-500 italic">{t('hr.aiReport.none')}</p>
            )}
          </div>
        </section>
      </div>
    );
  };

  /** One stored answer: its analysis status, exact transcript and analysis. */
  const renderAnswer = (answer: AiReportAnswer) => (
    <div key={answer.sequence} className="mt-3" data-testid="ai-report-answer">
      <div className="flex items-center justify-between gap-3">
        <p className="text-3xs font-bold uppercase tracking-wider text-stone-500">{t('hr.aiReport.candidateAnswer')}</p>
        <Badge variant="neutral">{t(`hr.aiReport.status.${answer.analysis_status}`)}</Badge>
      </div>
      <blockquote className="mt-1 rounded-lg bg-sand-50 border border-sand-200 p-3 text-sm text-stone-800 whitespace-pre-wrap">
        <Stored>{answer.transcript}</Stored>
      </blockquote>
      <div className="mt-3">{renderAnalysis(answer)}</div>
    </div>
  );

  /** Phase 11.4: main questions in the order heard, each follow-up nested
   *  under its main question - separate answers, separate analyses. */
  const renderQuestions = (r: AiInterviewReport) => {
    const bySequence = new Map(r.answers.map((a) => [a.sequence, a]));
    const answersOf = (sequences: number[]) =>
      sequences.map((s) => bySequence.get(s)).filter((a): a is AiReportAnswer => Boolean(a));
    return (
      <div className="space-y-4">
        {r.question_flow.map((e) => (
          <article key={e.number} className="rounded-xl border border-stone-200 p-4" data-testid="ai-report-flow-entry">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-3xs font-bold uppercase tracking-wider text-brand-700">
                  {t('hr.aiReport.questionN', { number: e.number })}
                </p>
                <p className="text-sm font-semibold text-stone-900 mt-0.5"><Stored>{e.main?.question_text ?? '—'}</Stored></p>
              </div>
              {e.main?.bank_position != null && (
                <Badge variant="outline">{t('hr.aiReport.bankPosition', { position: e.main.bank_position })}</Badge>
              )}
            </div>
            {e.main && e.main.answered ? (
              answersOf(e.main.answer_sequences).map(renderAnswer)
            ) : (
              <p className="mt-3 text-xs text-stone-500 italic">{t('hr.aiReport.noMainAnswer')}</p>
            )}
            {e.follow_up && (
              <div className="mt-4 border-s-2 border-brand-200 ps-3" data-testid="ai-report-follow-up">
                <p className="text-3xs font-bold uppercase tracking-wider text-brand-700">
                  {t('hr.aiReport.followUpN', { number: e.number })}
                </p>
                <p className="text-sm font-semibold text-stone-900 mt-0.5"><Stored>{e.follow_up.question_text}</Stored></p>
                {answersOf(e.follow_up.answer_sequences).map(renderAnswer)}
              </div>
            )}
          </article>
        ))}
      </div>
    );
  };

  const disclaimer = (
    <InfoPanel tone="brand" icon={<ShieldCheck className="w-4 h-4" />} title={t('hr.aiReport.disclaimerTitle')}>
      {t('hr.aiReport.disclaimerBody')}
    </InfoPanel>
  );

  let body: React.ReactNode;
  if (isLoading && !report) {
    body = <LoadingState title={t('hr.aiReport.loading')} />;
  } else if (error) {
    body = <ErrorState message={error} onRetry={() => void load(sessionId)} />;
  } else if (!report) {
    body = null;
  } else if (report.meta.state === 'no_answers') {
    body = (
      <InlineEmpty
        icon={<MessageSquareQuote className="w-5 h-5" />}
        title={t('hr.aiReport.noAnswersTitle')}
        description={t('hr.aiReport.noAnswersBody')}
      />
    );
  } else {
    body = (
      <div className="space-y-4">
        {report.sessions.length > 1 && (
          <Select
            label={t('hr.aiReport.session')}
            value={String(report.session?.session_id ?? '')}
            onChange={(e) => chooseSession(e.target.value)}
            options={report.sessions.map((s) => ({
              value: s.session_id,
              label: t('hr.aiReport.sessionOption', {
                date: formatDateTime(s.started_at, locale),
                count: s.answered_count ?? 0,
              }),
            }))}
          />
        )}
        <Tabs
          tabs={[
            { id: 'summary', label: t('hr.aiReport.tabSummary') },
            { id: 'questions', label: t('hr.aiReport.tabQuestions'), count: report.answers.length },
          ]}
          activeTab={tab}
          onChange={(id) => setTab(id as TabId)}
        />
        {tab === 'summary' ? renderSummary(report) : renderQuestions(report)}
      </div>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="2xl"
      title={t('hr.aiReport.title')}
      subtitle={report?.interview.job_title ?? undefined}
      footer={
        <div className="flex items-center justify-end gap-2">
          {report && unanalysed > 0 && (
            <Button
              variant="outline"
              size="sm"
              isLoading={isRerunning}
              leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
              onClick={() => void rerun()}
            >
              {t('hr.aiReport.rerun')}
            </Button>
          )}
          <Button variant="primary" size="sm" leftIcon={<FileText className="w-3.5 h-3.5" />} onClick={onClose}>
            {t('action.close')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {disclaimer}
        {body}
      </div>
    </Modal>
  );
};
