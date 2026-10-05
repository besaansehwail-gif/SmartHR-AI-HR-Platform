import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, Send, Sparkles, Wrench, X } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import { InfoPanel, Spinner } from '../../components/ui/States';
import { PageId } from '../../components/layout/Sidebar';
import { SmartHRApi } from '../../services/api';
import { AgentStep, CareerAgentResponse, CareerAgentStatus } from '../../types';
import { useT } from '../../i18n';

/**
 * The AI Career Agent.
 *
 * The panel shows the agent's **tool trace** under every answer: which SmartHR
 * tools it called, in what order, and whether each succeeded. That is the point
 * of showing it - an answer about your own applications should be checkable
 * rather than taken on trust, and a reply with no tool calls behind it is
 * visibly a reply with nothing behind it.
 *
 * The apply gate is stated in the UI too, because an applicant needs to know
 * that browsing cannot accidentally submit an application.
 */

/* SmartHR's own suggestions, so they are translated; nothing the agent
 * returns is. */
const SUGGESTION_KEYS = [
  'ai.career.suggestion1',
  'ai.career.suggestion2',
  'ai.career.suggestion3',
  'ai.career.suggestion4',
];

type Turn = { role: 'user' | 'assistant'; content: string; meta?: CareerAgentResponse };

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

export const CareerAgentPage: React.FC<{ onNavigate: (page: PageId) => void }> = ({
  onNavigate,
}) => {
  const { t } = useT();
  const [status, setStatus] = useState<CareerAgentStatus | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    SmartHRApi.getCareerAgentStatus()
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
        const result = await SmartHRApi.careerAgentChat({ message: text, history });
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

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('ai.career.title')}
        subtitle={t('ai.career.subtitle')}
        icon={<Sparkles className="w-5 h-5" />}
        badge={
          status ? (
            <Badge variant={status.llm_configured ? 'success' : 'warning'}>
              {status.llm_configured
                ? t('ai.poweredBy', { provider: status.provider, model: status.model ?? '' })
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card padding="none" className="flex flex-col h-[36rem]">
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {turns.length === 0 && (
                <div className="text-center py-10">
                  <span className="inline-flex w-12 h-12 rounded-2xl bg-brand-50 border border-brand-100 text-brand-600 items-center justify-center">
                    <Sparkles className="w-5 h-5" />
                  </span>
                  <h3 className="mt-3 text-sm font-bold text-stone-900">
                    {t('ai.career.emptyTitle')}
                  </h3>
                  <p className="mt-1 text-xs text-stone-500 max-w-md mx-auto leading-relaxed">
                    {t('ai.career.emptyHint')}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2 justify-center">
                    {SUGGESTION_KEYS.map((key) => t(key)).map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => ask(suggestion)}
                        className="px-3 py-1.5 rounded-lg bg-sand-100 hover:bg-sand-200 border border-sand-300 text-2xs font-semibold text-stone-700 transition-colors"
                      >
                        {suggestion}
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
                    className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                      turn.role === 'user'
                        ? 'bg-brand-600 text-white'
                        : 'bg-sand-50 border border-stone-200 text-stone-800'
                    }`}
                  >
                    <p className="text-xs leading-relaxed whitespace-pre-line">{turn.content}</p>

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
                          {turn.meta.apply_intent_detected && (
                            <Badge variant="warning" size="sm">
                              {t('ai.career.applyToolAvailable')}
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
                    <Spinner label={t('ai.thinking')} />
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
                placeholder={t('ai.career.placeholder')}
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
        </div>

        <div className="space-y-6">
          {status && (
            <>
              <Card padding="md">
                <CardHeader
                  title={t('ai.career.whatItCanDo')}
                  subtitle={t('ai.career.toolCount', {
                    count: status.tools.length,
                    server: status.mcp.server.name,
                  })}
                  icon={<Wrench className="w-4 h-4" />}
                />
                <ul className="space-y-2">
                  {status.tools.map((tool) => (
                    <li key={tool.name} className="flex items-start gap-2">
                      <code className="text-3xs font-mono text-stone-700 bg-sand-100 border border-sand-300 rounded px-1.5 py-0.5 shrink-0">
                        {tool.name}
                      </code>
                      {tool.requires_explicit_request && (
                        <Badge variant="warning" size="sm">
                          {t('ai.career.needsSayso')}
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              </Card>

              <Card padding="md" variant="attention">
                <CardHeader
                  title={t('ai.career.applyGateTitle')}
                  icon={<AlertTriangle className="w-4 h-4" />}
                />
                <p className="text-xs text-stone-700 leading-relaxed">
                  {status.apply_gate.description}
                </p>
                <dl className="mt-3 space-y-2">
                  <div>
                    <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                      {t('ai.career.applyGateSubmits')}
                    </dt>
                    <dd className="text-2xs text-stone-700 mt-0.5">
                      “{status.apply_gate.example_that_applies}”
                    </dd>
                  </div>
                  <div>
                    <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                      {t('ai.career.applyGateDoesNot')}
                    </dt>
                    <dd className="text-2xs text-stone-700 mt-0.5">
                      “{status.apply_gate.example_that_does_not}”
                    </dd>
                  </div>
                </dl>
              </Card>
            </>
          )}

          <InfoPanel title={t('ai.career.cannotTitle')} tone="neutral">
            <p>{t('ai.career.cannotBody')}</p>
          </InfoPanel>
        </div>
      </div>
    </div>
  );
};
