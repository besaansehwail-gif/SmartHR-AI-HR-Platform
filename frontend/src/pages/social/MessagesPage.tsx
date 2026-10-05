import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquare, Send, ArrowLeft, Lock } from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { Textarea } from '../../components/ui/Input';
import { ErrorState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useT, formatRelativeTime } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import {
  SocialConversationSummary,
  SocialHubStatus,
  SocialConversationsResponse,
  SocialMessagesResponse,
  SocialPerson,
} from '../../types';
import { PageId } from '../../components/layout/Sidebar';
import { SocialAvatar } from './SocialBits';
import { SocialHero } from './SocialShell';

/**
 * Two-column messaging: the thread list, and the open conversation.
 *
 * On a phone it is one column at a time - the list, then the thread with a
 * back control - rather than two squeezed side by side, which is what the rest
 * of SmartHR does with master/detail screens.
 *
 * **Membership is what authorises a read, and it is the server's job.** A
 * thread the caller is not in returns 404 from
 * `GET /social/conversations/{id}/messages`, because the query joins through
 * `social_conversation_members` filtered on the caller. Nothing in this
 * component decides who may read what.
 *
 * REST, not a socket: `POST` then re-read. The conversation list also refreshes
 * when the window regains focus, which is the cheap version of realtime and is
 * honest about being that. There is no polling loop pretending to be live.
 */

interface MessagesPageProps {
  /** Set when arriving from a Message button elsewhere. */
  initialConversationId: number | null;
  onNavigate: (page: PageId) => void;
  onOpenProfile: (userId: number) => void;
}

const otherPerson = (
  conversation: SocialConversationSummary
): SocialPerson | null => conversation.participants[0] ?? null;

export const MessagesPage: React.FC<MessagesPageProps> = ({
  initialConversationId,
  onNavigate,
  onOpenProfile,
}) => {
  const { t, locale } = useT();
  const { showToast } = useToast();

  const [list, setList] = useState<SocialConversationsResponse | null>(null);
  // Only for the header's "signed in as" mark; the thread list does not
  // carry the caller, and inventing a field on it for a header would be a
  // worse trade than one small extra read.
  const [status, setStatus] = useState<SocialHubStatus | null>(null);
  const [activeId, setActiveId] = useState<number | null>(initialConversationId);
  const [thread, setThread] = useState<SocialMessagesResponse | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadList = useCallback(async () => {
    try {
      const data = await SmartHRApi.getSocialConversations();
      setList(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : undefined);
      setList(null);
      return null;
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadThread = useCallback(
    async (conversationId: number) => {
      setLoadingThread(true);
      try {
        setThread(await SmartHRApi.getSocialMessages(conversationId));
      } catch {
        setThread(null);
        showToast(t('social.messages.loadError'), { type: 'error' });
      } finally {
        setLoadingThread(false);
      }
    },
    [showToast, t]
  );

  useEffect(() => {
    SmartHRApi.getSocialStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (activeId === null) {
      setThread(null);
      return;
    }
    loadThread(activeId);
  }, [activeId, loadThread]);

  // Reading a thread clears its unread count server-side, so the list has to
  // be re-read afterwards or the badge lies until the next navigation.
  useEffect(() => {
    if (thread) loadList();
  }, [thread?.conversation.id, thread?.total]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [thread?.messages.length]);

  // Cheap freshness, honestly scoped: when the tab comes back, re-read. No
  // interval, because a timer that fires every few seconds is a polling loop
  // dressed up as realtime.
  useEffect(() => {
    const onFocus = () => {
      loadList();
      if (activeId !== null) loadThread(activeId);
    };

    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [activeId, loadList, loadThread]);

  const send = async () => {
    if (!draft.trim() || activeId === null) return;

    setSending(true);
    try {
      await SmartHRApi.sendSocialMessage(activeId, draft);
      setDraft('');
      await loadThread(activeId);
      await loadList();
    } catch (err) {
      showToast(t('social.messages.failed'), {
        message: err instanceof Error ? err.message : undefined,
        type: 'error',
      });
    } finally {
      setSending(false);
    }
  };

  const conversations = list?.conversations ?? [];
  const active = conversations.find((c) => c.id === activeId) ?? null;
  const partner = thread?.conversation.participants[0] ?? (active ? otherPerson(active) : null);

  return (
    <div className="space-y-5">
      <SocialHero
        title={t('social.messages.title')}
        subtitle={t('social.messages.subtitle')}
        me={status?.me ?? null}
        unread={status?.unread_notifications ?? 0}
        current="soc-messages"
        onNavigate={onNavigate}
      />

      {error ? (
        <ErrorState message={error} onRetry={loadList} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-4 items-stretch lg:h-[calc(100vh-19rem)] lg:min-h-[28rem]">
          {/* ------------------------- Thread list ------------------------ */}
          <section
            aria-label={t('social.messages.conversations')}
            className={`bg-white rounded-2xl border border-stone-200/80 shadow-card overflow-hidden ${
              activeId !== null ? 'hidden lg:block' : ''
            }`}
          >
            <header className="px-4 py-3 border-b border-stone-100 flex items-center justify-between">
              <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500">
                {t('social.messages.conversations')}
              </h2>
              {(list?.unread_total ?? 0) > 0 && (
                <span className="min-w-5 h-5 px-1.5 rounded-full bg-brand-600 text-white text-3xs font-extrabold tabular-nums flex items-center justify-center">
                  {list?.unread_total}
                </span>
              )}
            </header>

            {loadingList ? (
              <div className="p-4 space-y-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-9 h-9 rounded-full skeleton" />
                    <span className="flex-1 h-3 rounded skeleton" />
                  </div>
                ))}
              </div>
            ) : conversations.length === 0 ? (
              <div className="p-5">
                <p className="text-xs font-bold text-stone-800">
                  {t('social.messages.empty.title')}
                </p>
                <p className="text-2xs text-stone-500 mt-1 leading-relaxed">
                  {t('social.messages.empty.body')}
                </p>
              </div>
            ) : (
              <ul className="max-h-[32rem] overflow-y-auto divide-y divide-stone-100">
                {conversations.map((conversation) => {
                  const person = otherPerson(conversation);
                  const isActive = conversation.id === activeId;

                  return (
                    <li key={conversation.id}>
                      <button
                        type="button"
                        onClick={() => setActiveId(conversation.id)}
                        aria-current={isActive ? 'true' : undefined}
                        className={`w-full flex items-center gap-3 px-4 py-3 text-start transition-colors ${
                          isActive ? 'bg-brand-50' : 'hover:bg-sand-50'
                        }`}
                      >
                        <SocialAvatar person={person} size="sm" />

                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline justify-between gap-2">
                            <span className="text-2xs font-bold text-stone-900 truncate">
                              {person?.name ?? '—'}
                            </span>
                            {conversation.last_message_at && (
                              <span className="text-3xs text-stone-400 shrink-0">
                                {formatRelativeTime(conversation.last_message_at, locale)}
                              </span>
                            )}
                          </span>

                          <span className="flex items-center justify-between gap-2 mt-0.5">
                            <span
                              className={`text-3xs truncate ${
                                conversation.unread_count > 0
                                  ? 'text-stone-800 font-semibold'
                                  : 'text-stone-500'
                              }`}
                            >
                              {conversation.last_message?.body ??
                                t('social.messages.noMessages')}
                            </span>
                            {conversation.unread_count > 0 && (
                              <span className="min-w-4 h-4 px-1 rounded-full bg-brand-600 text-white text-3xs font-extrabold tabular-nums flex items-center justify-center shrink-0">
                                {conversation.unread_count}
                              </span>
                            )}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* -------------------------- Thread ---------------------------- */}
          <section
            className={`bg-white rounded-2xl border border-stone-200/80 shadow-card flex flex-col min-h-[28rem] ${
              activeId === null ? 'hidden lg:flex' : ''
            }`}
          >
            {activeId === null ? (
              <div className="flex-1 flex items-center justify-center p-6">
                <EmptyState
                  icon={<MessageSquare className="w-6 h-6" />}
                  title={t('social.messages.pickOne')}
                  description={t('social.messages.pickOneBody')}
                  className="border-0 bg-transparent"
                />
              </div>
            ) : (
              <>
                <header className="px-4 py-3 border-b border-stone-100 flex items-center gap-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="lg:hidden"
                    onClick={() => setActiveId(null)}
                    aria-label={t('social.messages.backToList')}
                  >
                    <ArrowLeft className="w-4 h-4" data-flip-rtl />
                  </Button>

                  <button
                    type="button"
                    onClick={() => partner && onOpenProfile(partner.user_id)}
                    className="flex items-center gap-2.5 min-w-0 rounded-lg"
                  >
                    <SocialAvatar person={partner} size="sm" />
                    <span className="min-w-0 text-start">
                      <span className="block text-xs font-bold text-stone-900 truncate">
                        {partner?.name ?? '—'}
                      </span>
                      <span className="block text-3xs text-stone-500 truncate">
                        {partner?.headline ||
                          partner?.position_title ||
                          partner?.department_name ||
                          ''}
                      </span>
                    </span>
                  </button>
                </header>

                <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-sand-50/50">
                  {loadingThread ? (
                    <div className="space-y-3">
                      <span className="block h-8 w-2/3 rounded-xl skeleton" />
                      <span className="block h-8 w-1/2 rounded-xl skeleton ms-auto" />
                    </div>
                  ) : (thread?.messages.length ?? 0) === 0 ? (
                    <p className="text-2xs text-stone-400 text-center py-8">
                      {t('social.messages.noMessages')}
                    </p>
                  ) : (
                    thread?.messages.map((message) => (
                      <div
                        key={message.id}
                        className={`flex ${message.from_me ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[80%] sm:max-w-[70%] rounded-2xl px-3.5 py-2 ${
                            message.from_me
                              ? 'bg-brand-600 text-white rounded-ee-sm'
                              : 'bg-white border border-stone-200 text-stone-800 rounded-es-sm'
                          }`}
                        >
                          {/* What a colleague actually wrote - never translated. */}
                          <p className="text-2xs leading-relaxed whitespace-pre-wrap break-words">
                            {message.body}
                          </p>
                          <time
                            dateTime={message.created_at}
                            className={`block text-3xs mt-1 ${
                              message.from_me ? 'text-white/70' : 'text-stone-400'
                            }`}
                          >
                            {formatRelativeTime(message.created_at, locale)}
                          </time>
                        </div>
                      </div>
                    ))
                  )}
                  <div ref={bottomRef} />
                </div>

                <footer className="p-3 border-t border-stone-100 space-y-2">
                  <div className="flex items-end gap-2">
                    <Textarea
                      rows={1}
                      value={draft}
                      placeholder={t('social.messages.placeholder')}
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          send();
                        }
                      }}
                      maxLength={4000}
                      className="flex-1"
                    />
                    <Button
                      variant="primary"
                      onClick={send}
                      isLoading={sending}
                      disabled={!draft.trim()}
                      aria-label={t('social.messages.send')}
                    >
                      <Send className="w-4 h-4" data-flip-rtl />
                    </Button>
                  </div>

                  <p className="flex items-center gap-1.5 text-3xs text-stone-400">
                    <Lock className="w-3 h-3" aria-hidden="true" />
                    {t('social.messages.privateNote')}
                  </p>
                </footer>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
};
