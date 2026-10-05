import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  FileText,
  Lock,
  Send,
  Sparkles,
  UserCheck,
  Wrench,
  X,
} from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import { InfoPanel, Spinner } from '../../components/ui/States';
import { PageId } from '../../components/layout/Sidebar';
import { SmartHRApi } from '../../services/api';
import { AgentStep, HrAgentResponse, HrAgentStatus, ScreeningRow } from '../../types';
import { useT } from '../../i18n';

/**
 * The SmartHR Internal AI Agent - the recruiter's screening agent.
 *
 * Two things on this page are deliberate and worth keeping.
 *
 * **The candidate cards are not parsed out of the model's prose.** They come
 * from `response.candidates`, which the backend lifts straight out of the tool
 * results the model was given. So whatever the model wrote above them, the
 * cards show what SmartHR actually returned - and a reply with no tool calls
 * behind it renders no cards at all, visibly.
 *
 * **A null score renders as "Not scored", never as 0%.** Null means SmartHR
 * holds no CV and no profile skills for that person. A 0% beside somebody's
 * name reads as a verdict on them; "no evidence on file" reads as the task it
 * actually is, which is to go and ask them for a CV.
 */

type Turn = { role: 'user' | 'assistant'; content: string; meta?: HrAgentResponse };

/*
 * Example prompts. These are suggestions SmartHR offers, so they are
 * translated - unlike anything the agent returns, which is left exactly as
 * the backend produced it.
 */
const EXAMPLE_KEYS = [
  'ai.hr.example1',
  'ai.hr.example2',
  'ai.hr.example3',
  'ai.hr.example4',
];

const RELEVANCE_VARIANT: Record<string, 'success' | 'info' | 'neutral' | 'warning'> = {
  strong: 'success',
  some: 'info',
  none_evidenced: 'neutral',
  none_stated: 'neutral',
  unknown: 'neutral',
};

const scoreTone = (score: number | null): string => {
  if (score === null) return 'bg-stone-100 text-stone-500 border-stone-200';
  if (score >= 75) return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (score >= 50) return 'bg-brand-50 text-brand-700 border-brand-200';
  return 'bg-amber-50 text-amber-700 border-amber-200';
};

const StepTrace: React.FC<{ steps: AgentStep[] }> = ({ steps }) => {
  const { t } = useT();

  if (steps.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-stone-200/70">
      <p className="text-3xs font-bold uppercase tracking-wider text-stone-400 mb-2">
        {t('ai.toolsUsed', { count: steps.length })}
      </p>
      <ol className="space-y-1">
        {steps.map((step) => (
          <li key={`${step.step}-${step.tool}`} className="flex items-center gap-2 text-3xs">
            <span
              className={`w-4 h-4 rounded-full flex items-center justify-center shrink-0 ${
                step.ok ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
              }`}
            >
              {step.ok ? <Check className="w-2.5 h-2.5" /> : <X className="w-2.5 h-2.5" />}
            </span>
            <code className="font-mono text-stone-700">{step.tool}</code>
            {step.arguments.length > 0 && (
              <span className="text-stone-400">({step.arguments.join(', ')})</span>
            )}
            {!step.ok && step.error_code && (
              <span className="text-amber-700 font-semibold">{step.error_code}</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
};

const SkillPills: React.FC<{ items: string[]; tone: 'match' | 'gap' | 'extra' }> = ({
  items,
  tone,
}) => {
  if (items.length === 0) return null;

  const cls =
    tone === 'match'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : tone === 'gap'
      ? 'bg-amber-50 text-amber-800 border-amber-200'
      : 'bg-sand-100 text-stone-600 border-sand-300';

  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className={`px-2 py-0.5 rounded-md border text-3xs font-semibold ${cls}`}
        >
          {item}
        </span>
      ))}
    </div>
  );
};

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div>
    <p className="text-3xs font-bold uppercase tracking-wider text-stone-400 mb-1">
      {label}
    </p>
    {children}
  </div>
);

/** One screened candidate, rendered from the tool result rather than the prose. */
const CandidateCard: React.FC<{
  row: ScreeningRow;
  rank: number;
  onOpenCandidates: () => void;
}> = ({ row, rank, onOpenCandidates }) => {
  const { t } = useT();
  const [open, setOpen] = useState(rank === 1);
  const { candidate, match, evidence, relevant_experience: experience } = row;
  const scored = match.score !== null;

  return (
    <Card padding="none" className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 p-4 text-start hover:bg-sand-50/70 transition-colors"
      >
        <span className="w-6 h-6 rounded-lg bg-stone-100 text-stone-600 text-2xs font-bold flex items-center justify-center shrink-0">
          {rank}
        </span>

        <span className="flex-1 min-w-0">
          <span className="block text-xs font-bold text-stone-900 truncate">
            {candidate.full_name}
          </span>
          <span className="block text-3xs text-stone-500 truncate">
            {candidate.email}
            {candidate.location ? ` • ${candidate.location}` : ''}
          </span>
        </span>

        <span
          className={`px-2.5 py-1 rounded-lg border text-2xs font-bold shrink-0 ${scoreTone(
            match.score
          )}`}
        >
          {scored ? `${match.score}%` : t('ai.match.notScored')}
        </span>

        <ChevronDown
          className={`w-4 h-4 text-stone-400 shrink-0 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 space-y-3 border-t border-stone-200/70">
          {!scored ? (
            /* No evidence is a task, not a verdict - so it is stated as one. */
            <InfoPanel title={t('ai.hr.noEvidenceTitle')} tone="warning">
              {/* score_basis comes from the backend and is shown as it wrote it. */}
              <p>{match.score_basis}</p>
              {(match.unevidenced_requirements || []).length > 0 && (
                <p className="mt-2">
                  {t('ai.hr.noEvidenceGaps', {
                    requirements: (match.unevidenced_requirements || []).join(', '),
                  })}
                </p>
              )}
            </InfoPanel>
          ) : (
            <>
              <Field label={t('ai.match.score')}>
                <p className="text-2xs text-stone-600 leading-relaxed">
                  {match.score_basis}
                </p>
              </Field>

              <Field label={t('ai.match.matchingSkills')}>
                {match.matching_skills.length > 0 ? (
                  <SkillPills items={match.matching_skills} tone="match" />
                ) : (
                  <p className="text-2xs text-stone-500">{t('ai.hr.noneMatched')}</p>
                )}
              </Field>

              <Field label={t('ai.match.skillGaps')}>
                {match.skill_gaps.length > 0 ? (
                  <SkillPills items={match.skill_gaps} tone="gap" />
                ) : (
                  <p className="text-2xs text-stone-500">{t('ai.hr.everyRequirementMet')}</p>
                )}
              </Field>

              {match.additional_skills.length > 0 && (
                <Field label={t('ai.match.additionalSkills')}>
                  <SkillPills items={match.additional_skills} tone="extra" />
                </Field>
              )}
            </>
          )}

          <Field label={t('ai.hr.relevantExperience')}>
            <div className="flex items-start gap-2">
              <Badge variant={RELEVANCE_VARIANT[experience.relevance] || 'neutral'} size="sm">
                {t(`ai.hr.relevance.${experience.relevance}`)}
              </Badge>
              <p className="text-2xs text-stone-600 leading-relaxed flex-1">
                {experience.basis}
              </p>
            </div>
            {experience.matching_roles.length > 0 && (
              <ul className="mt-2 space-y-1">
                {experience.matching_roles.map((role, i) => (
                  <li key={i} className="text-2xs text-stone-700">
                    • <strong>{role.title || 'Role'}</strong>
                    {role.company ? ` — ${role.company}` : ''}
                    <span className="text-stone-500">
                      {' '}
                      (mentions {role.requirements_mentioned.join(', ')})
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Field>

          {row.education?.available && (
            <Field label={t('ai.cv.education')}>
              <p className="text-2xs text-stone-600">{row.education.basis}</p>
            </Field>
          )}

          {row.certifications?.available && (
            <Field label={t('ai.cv.certifications')}>
              <p className="text-2xs text-stone-600">{row.certifications.basis}</p>
            </Field>
          )}

          <Field label={t('ai.hr.evidence')}>
            <p className="text-2xs text-stone-600 leading-relaxed">
              {evidence.evidence_note}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant={candidate.has_cv ? 'success' : 'neutral'} size="sm">
                {candidate.has_cv ? (
                  <span className="inline-flex items-center gap-1">
                    <FileText className="w-2.5 h-2.5" />
                    {candidate.cv_file_name || t('ai.hr.cvOnFile')}
                  </span>
                ) : (
                  t('ai.hr.noCvOnFile')
                )}
              </Badge>
              {candidate.profile_skills.length > 0 && (
                <Badge variant="info" size="sm">
                  {t('ai.hr.skillsOnProfile', { count: candidate.profile_skills.length })}
                </Badge>
              )}
              <Badge variant="neutral" size="sm">
                {t('ai.hr.applicationCount', { count: candidate.applications_count })}
              </Badge>
            </div>
          </Field>

          <div className="pt-2 border-t border-stone-200/70 flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenCandidates}
              leftIcon={<UserCheck className="w-3.5 h-3.5" />}
            >
              {t('ai.hr.openInCandidates')}
            </Button>
            <p className="text-3xs text-stone-400 leading-relaxed flex-1">
              {t('ai.hr.decisionIsYours')}
            </p>
          </div>
        </div>
      )}
    </Card>
  );
};

export const HrAgentPage: React.FC<{ onNavigate: (page: PageId) => void }> = ({
  onNavigate,
}) => {
  const { t } = useT();
  const [status, setStatus] = useState<HrAgentStatus | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    SmartHRApi.getHrAgentStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns, busy]);

  const ask = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text || busy) return;

      setInput('');
      setTurns((prev) => [...prev, { role: 'user', content: text }]);
      setBusy(true);

      try {
        const history = turns.slice(-10).map((t) => ({ role: t.role, content: t.content }));
        const result = await SmartHRApi.hrAgentChat({ message: text, history });
        setTurns((prev) => [
          ...prev,
          { role: 'assistant', content: result.reply, meta: result },
        ]);
      } catch (err) {
        setTurns((prev) => [
          ...prev,
          {
            role: 'assistant',
            content:
              err instanceof Error
                ? t('ai.failed', { error: err.message })
                : t('ai.failedGeneric'),
          },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [busy, turns]
  );

  /** The most recent turn that produced screening rows. */
  const latest = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      const meta = turns[i].meta;
      if (meta && meta.candidates.length > 0) return meta;
    }
    return null;
  }, [turns]);

  // SmartHR's own suggestions, translated. The backend also returns examples,
  // but those are English strings from the API and would read oddly beside an
  // Arabic UI, so the translated set is used in both languages.
  const examples = EXAMPLE_KEYS.map((key) => t(key));

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('ai.hr.title')}
        subtitle={t('ai.hr.subtitle')}
        icon={<Sparkles className="w-5 h-5" />}
        badge={
          status ? (
            <Badge variant={status.llm_configured ? 'success' : 'warning'}>
              {status.llm_configured
                ? t('ai.poweredBy', {
                    provider: status.provider,
                    model: status.model ?? '',
                  })
                : t('ai.noModel')}
            </Badge>
          ) : undefined
        }
      />

      {status && !status.llm_configured && (
        <InfoPanel title={t('ai.noModelTitle')} tone="warning">
          <p>{t('ai.noModelBody')}</p>
        </InfoPanel>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-6">
          <Card padding="none" className="flex flex-col h-[34rem]">
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {turns.length === 0 && (
                <div className="text-center py-10">
                  <span className="inline-flex w-12 h-12 rounded-2xl bg-brand-50 border border-brand-100 text-brand-600 items-center justify-center">
                    <Sparkles className="w-5 h-5" />
                  </span>
                  <h3 className="mt-3 text-sm font-bold text-stone-900">
                    {t('ai.hr.emptyTitle')}
                  </h3>
                  <p className="mt-1 text-xs text-stone-500 max-w-md mx-auto leading-relaxed">
                    {t('ai.hr.emptyHint')}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2 justify-center">
                    {examples.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => ask(example)}
                        className="px-3 py-1.5 rounded-lg bg-sand-100 hover:bg-sand-200 border border-sand-300 text-2xs font-semibold text-stone-700 transition-colors"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {turns.map((turn, index) => (
                <div
                  key={index}
                  className={`flex ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[88%] rounded-2xl px-4 py-3 ${
                      turn.role === 'user'
                        ? 'bg-brand-600 text-white'
                        : 'bg-sand-50 border border-stone-200 text-stone-800'
                    }`}
                  >
                    <p className="text-xs leading-relaxed whitespace-pre-line">
                      {turn.content}
                    </p>

                    {turn.meta && (
                      <>
                        <StepTrace steps={turn.meta.steps} />

                        <div className="mt-2 flex items-center gap-2 flex-wrap">
                          <Badge
                            variant={turn.meta.generated_by === 'llm' ? 'info' : 'neutral'}
                            size="sm"
                          >
                            {turn.meta.generated_by === 'llm'
                              ? t('ai.writtenByModel')
                              : t('ai.assembledFromTools')}
                          </Badge>
                          <Badge variant="neutral" size="sm">
                            {t('ai.viaTransport', {
                              transport: turn.meta.tool_transport.toUpperCase(),
                            })}
                          </Badge>
                          {turn.meta.read_only && (
                            <Badge variant="success" size="sm">
                              <span className="inline-flex items-center gap-1">
                                <Lock className="w-2.5 h-2.5" />
                                {t('ai.readOnly')}
                              </span>
                            </Badge>
                          )}
                        </div>

                        {turn.meta.notice && (
                          <p className="mt-2 text-3xs text-stone-500 leading-relaxed">
                            {turn.meta.notice}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}

              {busy && (
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-sand-50 border border-stone-200 px-4 py-3">
                    <Spinner label={t('ai.hr.thinking')} />
                  </div>
                </div>
              )}

              <div ref={endRef} />
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                ask(input);
              }}
              className="p-3 border-t border-stone-200 flex items-center gap-2"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t('ai.hr.placeholder')}
                className="flex-1 h-10 px-3.5 rounded-lg border border-stone-200 text-xs outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                disabled={busy}
              />
              <Button
                type="submit"
                variant="primary"
                size="md"
                disabled={busy || !input.trim()}
                leftIcon={<Send className="w-4 h-4" />}
              >
                {t('ai.ask')}
              </Button>
            </form>
          </Card>

          {latest && (
            <div className="space-y-3">
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="text-sm font-bold text-stone-900">
                    {latest.job
                      ? t('ai.hr.candidatesFor', { title: latest.job.title })
                      : t('ai.hr.screeningResults')}
                  </h3>
                  <p className="text-2xs text-stone-500 mt-0.5">
                    {latest.job && latest.job.requirements.length > 0
                      ? t('ai.hr.scoredAgainst', {
                          requirements: latest.job.requirements.join(', '),
                        })
                      : t('ai.hr.fromTools')}
                  </p>
                </div>
                <Badge variant="warning" size="sm">
                  {t('ai.match.label')} — {t('ai.match.notADecision')}
                </Badge>
              </div>

              {latest.candidates.map((row, index) => (
                <CandidateCard
                  key={row.candidate.candidate_id}
                  row={row}
                  rank={index + 1}
                  onOpenCandidates={() => onNavigate('hr-candidates')}
                />
              ))}

              <p className="text-3xs text-stone-400 leading-relaxed">
                {latest.candidates[0]?.match.disclaimer}
              </p>
            </div>
          )}
        </div>

        <div className="space-y-6">
          {status && (
            <>
              <Card padding="md" variant="attention">
                <CardHeader
                  title={t('ai.hr.cannotChangeTitle')}
                  icon={<Lock className="w-4 h-4" />}
                />
                <p className="text-xs text-stone-700 leading-relaxed">
                  {status.guarantees.read_only}
                </p>
                <p className="mt-3 text-xs text-stone-700 leading-relaxed">
                  {status.guarantees.decision_owner}
                </p>
              </Card>

              <Card padding="md">
                <CardHeader
                  title={t('ai.hr.whatItCanDo')}
                  subtitle={t('ai.hr.toolCount', {
                    count: status.tools.length,
                    server: status.mcp.server.name,
                    steps: status.max_steps,
                  })}
                  icon={<Wrench className="w-4 h-4" />}
                />
                <ul className="space-y-1.5">
                  {status.tools.map((tool) => (
                    <li key={tool.name} className="flex items-center gap-2">
                      <code className="text-3xs font-mono text-stone-700 bg-sand-100 border border-sand-300 rounded px-1.5 py-0.5 shrink-0">
                        {tool.name}
                      </code>
                      <Badge variant="neutral" size="sm">
                        {t('ai.hr.read')}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </Card>

              <InfoPanel title={t('ai.hr.whereNumbersComeFrom')} tone="neutral">
                <p>{status.guarantees.no_invention}</p>
              </InfoPanel>
            </>
          )}

          <Card padding="md">
            <CardHeader
              title={t('ai.hr.readingResult')}
              icon={<AlertTriangle className="w-4 h-4" />}
            />
            <dl className="space-y-2.5">
              <div>
                <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                  {t('ai.hr.readingPercentTerm')}
                </dt>
                <dd className="text-2xs text-stone-700 mt-0.5 leading-relaxed">
                  {t('ai.hr.readingPercentBody')}
                </dd>
              </div>
              <div>
                <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                  {t('ai.hr.readingNotScoredTerm')}
                </dt>
                <dd className="text-2xs text-stone-700 mt-0.5 leading-relaxed">
                  {t('ai.hr.readingNotScoredBody')}
                </dd>
              </div>
              <div>
                <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                  {t('ai.hr.readingGapTerm')}
                </dt>
                <dd className="text-2xs text-stone-700 mt-0.5 leading-relaxed">
                  {t('ai.hr.readingGapBody')}
                </dd>
              </div>
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
};
