import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Sparkles,
  X,
  Send,
  AlertTriangle,
  Info,
  Database,
  Loader2,
  RefreshCw,
  Lock,
  ChevronDown,
} from 'lucide-react';
import { SmartHRApi } from '../../services/api';
import { AiChatResponse, AiStatus, AiChatTurn } from '../../types';
import { useT } from '../../i18n';

/**
 * SmartHR AI Assistant.
 *
 * A floating launcher plus a chat panel, mounted once in the authenticated
 * shell so it is available on every page rather than only the dashboard.
 *
 * What it does not do is as important as what it does:
 *  - it holds no API key and talks to no model directly; it posts to /ai/chat
 *    and the server does the rest;
 *  - it sends only the message and the visible transcript, never a user id,
 *    employee id or role, because the server takes all three from the JWT;
 *  - it renders whatever grounding the server reports (which tool ran, and
 *    whether a model phrased the answer), so the user can see what a reply is
 *    based on instead of taking it on trust.
 *
 * It is also deliberately self-contained: any failure inside it is caught and
 * shown as a message in the panel. The assistant must never take a page down.
 */

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** Grounding shown under an assistant message. */
  meta?: {
    tool?: string | null;
    generatedBy?: 'llm' | 'tool';
    notice?: string | null;
    errorCode?: string | null;
  };
  failed?: boolean;
}

const newId = () => Math.random().toString(36).slice(2, 10);

/* Resolved inside the component so it follows the current language. */
const welcomeMessage = (text: string): ChatMessage => ({
  id: 'welcome',
  role: 'assistant',
  content: text,
});

const SUGGESTION_KEYS = ['ai.assistant.sample1', 'ai.assistant.sample2'];

/* Kept alongside the translated samples in both languages: the assistant
 * answers Arabic questions from the database regardless of UI language, and
 * offering one is how a user discovers that. */
const ARABIC_SAMPLE = 'شو وضعي بالإجازات؟';

/** A tool refusal is not a system failure; it is an answer. Label it as such. */
const ERROR_LABEL_KEYS: Record<string, string> = {
  forbidden: 'ai.error.forbidden',
  no_employee_link: 'ai.error.no_employee_record',
  database_error: 'ai.error.database_error',
  unknown_tool: 'ai.error.unknown_tool',
  inactive_account: 'ai.error.inactive_account',
};

export const AiAssistant: React.FC = () => {
  const { t } = useT();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    welcomeMessage(t('ai.assistant.greeting')),
  ]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [transportError, setTransportError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // What this caller may ask, and whether a model is wired up. Failing this
  // call is not fatal - the panel still works, it just shows less context.
  useEffect(() => {
    if (!isOpen || status) return;

    let cancelled = false;
    SmartHRApi.getAiStatus()
      .then((value) => {
        if (!cancelled) setStatus(value);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, status]);

  useEffect(() => {
    if (isOpen) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages, isOpen, isSending]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  const send = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || isSending) return;

      const userMessage: ChatMessage = { id: newId(), role: 'user', content: question };

      // The transcript sent as history is the one the user can see, so the
      // model is never given context the user is unaware of.
      const history: AiChatTurn[] = messages
        .filter((m) => m.id !== 'welcome' && !m.failed)
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content }));

      setMessages((prev) => [...prev, userMessage]);
      setInput('');
      setIsSending(true);
      setTransportError(null);

      try {
        const response: AiChatResponse = await SmartHRApi.aiChat({
          message: question,
          history,
        });

        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: 'assistant',
            content: response.reply,
            meta: {
              tool: response.tool_used,
              generatedBy: response.generated_by,
              notice: response.notice,
              errorCode: response.tool_ok === false ? response.tool_error_code : null,
            },
          },
        ]);
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : t('ai.assistant.unreachable');
        setTransportError(detail);
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: 'assistant',
            content: detail,
            failed: true,
          },
        ]);
      } finally {
        setIsSending(false);
      }
    },
    [isSending, messages]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    send(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const reset = () => {
    setMessages([welcomeMessage(t('ai.assistant.greeting'))]);
    setTransportError(null);
    inputRef.current?.focus();
  };

  return (
    <>
      {/* Launcher */}
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-label={isOpen ? t('ai.assistant.ariaClose') : t('ai.assistant.ariaOpen')}
        aria-expanded={isOpen}
        className={`fixed bottom-5 end-5 z-40 inline-flex items-center gap-2 h-12 rounded-full shadow-pop
          transition-[background-color,transform,box-shadow] duration-200
          focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2
          ${isOpen
            ? 'w-12 justify-center bg-stone-800 hover:bg-stone-900 text-white'
            : 'px-4 bg-brand-600 hover:bg-brand-700 text-white'}`}
      >
        {isOpen ? (
          <ChevronDown className="w-5 h-5" aria-hidden="true" />
        ) : (
          <>
            <Sparkles className="w-[18px] h-[18px] shrink-0" aria-hidden="true" />
            <span className="text-xs font-bold hidden sm:inline">{t('ai.assistant.askSmartHR')}</span>
          </>
        )}
      </button>

      {/* Panel */}
      {isOpen && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label={t('ai.assistant.fullTitle')}
          className="fixed z-40 bg-white border border-stone-200 shadow-pop flex flex-col overflow-hidden
            inset-x-0 bottom-0 top-16 rounded-t-2xl
            sm:inset-x-auto sm:top-auto sm:end-5 sm:bottom-20 sm:w-[26rem] sm:h-[min(34rem,calc(100vh-8rem))] sm:rounded-2xl
            animate-in fade-in slide-in-from-bottom-3"
        >
          {/* Header */}
          <div className="shrink-0 bg-brand-950 text-white px-4 py-3 flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="w-9 h-9 rounded-xl bg-brand-500 text-brand-950 flex items-center justify-center shrink-0">
                <Sparkles className="w-4 h-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h2 className="text-sm font-extrabold tracking-tight leading-none">
                  {t('ai.assistant.fullTitle')}
                </h2>
                <p className="text-3xs text-brand-200/70 mt-1 truncate">
                  {status
                    ? `${status.mcp.available ? 'MCP tools' : 'MCP unavailable'} · ${
                        status.llm_configured ? status.provider : 'no model configured'
                      }`
                    : t('ai.assistant.grounded')}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                onClick={reset}
                aria-label={t('ai.assistant.newConversation')}
                title={t('ai.assistant.newConversation')}
                className="p-1.5 rounded-lg text-brand-200/70 hover:text-white hover:bg-white/10 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                aria-label={t('ai.assistant.close')}
                className="p-1.5 rounded-lg text-brand-200/70 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Configuration notice */}
          {status && !status.llm_configured && (
            <div className="shrink-0 px-3 py-2 bg-amber-50 border-b border-amber-200 flex items-start gap-2">
              <Info className="w-3.5 h-3.5 text-amber-600 mt-0.5 shrink-0" aria-hidden="true" />
              <p className="text-3xs text-amber-900 leading-relaxed">
                No language model is configured, so answers are the tool results
                themselves rather than generated prose. The figures are still read
                live from the database.
              </p>
            </div>
          )}

          {status && !status.employee_linked && (
            <div className="shrink-0 px-3 py-2 bg-sand-100 border-b border-sand-300 flex items-start gap-2">
              <Info className="w-3.5 h-3.5 text-stone-500 mt-0.5 shrink-0" aria-hidden="true" />
              <p className="text-3xs text-stone-600 leading-relaxed">
                This account is not linked to an employee record, so there is no
                personal leave, attendance or training to report.
              </p>
            </div>
          )}

          {/* Transcript */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3.5 py-4 space-y-3.5 bg-sand-50">
            {messages.map((message) =>
              message.role === 'user' ? (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-ee-sm bg-brand-600 text-white px-3.5 py-2.5">
                    <p className="text-xs leading-relaxed whitespace-pre-wrap break-words">
                      {message.content}
                    </p>
                  </div>
                </div>
              ) : (
                <div key={message.id} className="flex justify-start">
                  <div
                    className={`max-w-[90%] rounded-2xl rounded-es-sm px-3.5 py-2.5 border ${
                      message.failed
                        ? 'bg-red-50 border-red-200'
                        : 'bg-white border-stone-200'
                    }`}
                  >
                    {message.failed && (
                      <span className="inline-flex items-center gap-1.5 text-3xs font-extrabold text-red-700 mb-1.5">
                        <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                        {t('ai.assistant.unavailable')}
                      </span>
                    )}

                    <p className="text-xs leading-relaxed text-stone-800 whitespace-pre-wrap break-words">
                      {message.content}
                    </p>

                    {/* Grounding: what this answer was based on. */}
                    {(message.meta?.tool || message.meta?.errorCode) && (
                      <div className="mt-2 pt-2 border-t border-stone-100 flex flex-wrap items-center gap-1.5">
                        {message.meta.errorCode ? (
                          <span className="inline-flex items-center gap-1 text-3xs font-bold px-1.5 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200">
                            <Lock className="w-2.5 h-2.5" aria-hidden="true" />
                            {ERROR_LABEL_KEYS[message.meta.errorCode]
                              ? t(ERROR_LABEL_KEYS[message.meta.errorCode])
                              : message.meta.errorCode}
                          </span>
                        ) : (
                          message.meta.tool && (
                            <span
                              title={t('ai.assistant.fromToolResult')}
                              className="inline-flex items-center gap-1 text-3xs font-bold px-1.5 py-0.5 rounded border bg-brand-50 text-brand-700 border-brand-200"
                            >
                              <Database className="w-2.5 h-2.5" aria-hidden="true" />
                              mcp · {message.meta.tool}
                            </span>
                          )
                        )}
                        {message.meta.generatedBy === 'tool' && !message.meta.errorCode && (
                          <span className="text-3xs font-semibold text-stone-400">
                            direct tool result
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            )}

            {isSending && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-es-sm bg-white border border-stone-200 px-3.5 py-2.5 inline-flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-600" aria-hidden="true" />
                  <span className="text-3xs font-semibold text-stone-500">
                    {t('ai.assistant.reading')}
                  </span>
                </div>
              </div>
            )}

            {/* Starters, shown only on a fresh conversation. */}
            {messages.length === 1 && !isSending && (
              <div className="pt-1 space-y-1.5">
                <p className="text-3xs font-extrabold uppercase tracking-wider text-stone-400 px-1">
                  {t('ai.assistant.tryAsking')}
                </p>
                {[...SUGGESTION_KEYS.map((key) => t(key)), ARABIC_SAMPLE].map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => send(suggestion)}
                    className="w-full text-start text-2xs font-semibold text-stone-700 bg-white border border-stone-200 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800 rounded-xl px-3 py-2 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Composer */}
          <form
            onSubmit={handleSubmit}
            className="shrink-0 border-t border-stone-200 bg-white p-3"
          >
            {transportError && (
              <p role="alert" className="text-3xs font-semibold text-red-600 mb-2 px-1">
                {transportError}
              </p>
            )}

            <div className="flex items-end gap-2">
              <label htmlFor="smarthr-ai-input" className="sr-only">
                {t('ai.assistant.askTitle')}
              </label>
              <textarea
                id="smarthr-ai-input"
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('ai.assistant.inputPlaceholder')}
                maxLength={4000}
                className="flex-1 resize-none rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 max-h-28"
              />
              <button
                type="submit"
                disabled={!input.trim() || isSending}
                aria-label={t('ai.assistant.sendMessage')}
                className="w-10 h-10 shrink-0 inline-flex items-center justify-center rounded-xl bg-brand-600 hover:bg-brand-700 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2"
              >
                {isSending ? (
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Send className="w-4 h-4" aria-hidden="true" />
                )}
              </button>
            </div>

            <p className="text-3xs text-stone-400 mt-1.5 px-1">
              Answers come from your own SmartHR records. Enter sends, Shift+Enter
              adds a line.
            </p>
          </form>
        </div>
      )}
    </>
  );
};
