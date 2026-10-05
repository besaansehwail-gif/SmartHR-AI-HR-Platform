import React, { useCallback, useEffect, useState } from 'react';
import {
  Bell,
  Heart,
  MessageCircle,
  MessageSquare,
  UserCheck,
  UserPlus,
} from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { ErrorState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useT, formatRelativeTime } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import { PageId } from '../../components/layout/Sidebar';
import {
  SocialHubStatus,
  SocialNotification,
  SocialNotificationType,
} from '../../types';
import { SocialEmpty, SocialHero } from './SocialShell';

/**
 * What happened while you were away.
 *
 * **This is the existing `notifications` table**, narrowed to the five types
 * whose names begin `social_`. There is no second notification system: the
 * same row appears in the top-bar bell and on the per-role notification pages,
 * and marking one read here is the same column those mark.
 *
 * The sentence itself is **stored English text**, rendered exactly as written,
 * following the rule every other database value in SmartHR follows. Only the
 * category label around it is translated - a notification that said "Sara
 * liked your post" is a record of something that happened, and re-wording it
 * in the browser would be inventing a second account of it.
 */

interface SocialNotificationsPageProps {
  onNavigate: (page: PageId) => void;
  onOpenProfile: (userId: number) => void;
  onOpenConversation: (conversationId: number) => void;
}

/**
 * The five types the backend actually emits, each with its own mark.
 *
 * A type SmartHR does not know falls back to the bell rather than being
 * hidden: an unrecognised row is still a real notification.
 */
const MARKS: Record<
  SocialNotificationType,
  { icon: React.ReactNode; tone: string }
> = {
  social_connection_request: {
    icon: <UserPlus className="w-4 h-4" />,
    tone: 'bg-brand-50 text-brand-700 border-brand-100',
  },
  social_connection_accepted: {
    icon: <UserCheck className="w-4 h-4" />,
    tone: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  },
  social_comment: {
    icon: <MessageSquare className="w-4 h-4" />,
    tone: 'bg-sky-50 text-sky-700 border-sky-100',
  },
  social_reaction: {
    icon: <Heart className="w-4 h-4" />,
    tone: 'bg-rose-50 text-rose-700 border-rose-100',
  },
  social_message: {
    icon: <MessageCircle className="w-4 h-4" />,
    tone: 'bg-stone-100 text-stone-700 border-stone-200',
  },
};

const FALLBACK = {
  icon: <Bell className="w-4 h-4" />,
  tone: 'bg-stone-100 text-stone-600 border-stone-200',
};

export const SocialNotificationsPage: React.FC<SocialNotificationsPageProps> = ({
  onNavigate,
}) => {
  const { t, locale } = useT();
  const { showToast } = useToast();

  const [items, setItems] = useState<SocialNotification[]>([]);
  const [status, setStatus] = useState<SocialHubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await SmartHRApi.getSocialNotifications();
      setItems(response.notifications);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('social.notifications.loadError'));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [t]);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await SmartHRApi.getSocialStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    load();
    loadStatus();
  }, [load, loadStatus]);

  const markRead = async (notification: SocialNotification) => {
    if (notification.is_read) return;

    setBusy(notification.id);
    try {
      await SmartHRApi.readSocialNotification(notification.id);
      // Re-read rather than flipping the flag locally, so the badge in the
      // header and the row agree with the database rather than with an
      // optimistic guess.
      await Promise.all([load(), loadStatus()]);
    } catch (err) {
      showToast(t('social.notifications.markFailed'), {
        message: err instanceof Error ? err.message : undefined,
        type: 'error',
      });
    } finally {
      setBusy(null);
    }
  };

  const markAll = async () => {
    const unread = items.filter((item) => !item.is_read);
    if (unread.length === 0) return;

    setBusy(-1);
    try {
      // There is no bulk endpoint on the social surface, so this is the real
      // per-row call repeated - not a single request that pretends to be one.
      await Promise.all(
        unread.map((item) => SmartHRApi.readSocialNotification(item.id))
      );
      await Promise.all([load(), loadStatus()]);
    } catch (err) {
      showToast(t('social.notifications.markFailed'), {
        message: err instanceof Error ? err.message : undefined,
        type: 'error',
      });
    } finally {
      setBusy(null);
    }
  };

  const unreadCount = items.filter((item) => !item.is_read).length;
  const shown = filter === 'unread' ? items.filter((i) => !i.is_read) : items;

  return (
    <div className="space-y-5">
      <SocialHero
        title={t('social.notifications.title')}
        subtitle={t('social.notifications.subtitle')}
        me={status?.me ?? null}
        unread={status?.unread_notifications ?? 0}
        current="soc-notifications"
        onNavigate={onNavigate}
        actions={
          unreadCount > 0 ? (
            <Button
              variant="outline"
              size="sm"
              onClick={markAll}
              isLoading={busy === -1}
            >
              {t('social.notifications.markAll')}
            </Button>
          ) : undefined
        }
      />

      <div className="max-w-3xl">
        {/* Two states, not a filter bar: a notification is read or it is not. */}
        <div className="inline-flex rounded-xl border border-stone-200 bg-white p-1 mb-4">
          {(['all', 'unread'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              aria-pressed={filter === value}
              className={`h-8 px-3.5 rounded-lg text-2xs font-bold transition-colors ${
                filter === value
                  ? 'bg-brand-600 text-white'
                  : 'text-stone-500 hover:text-stone-800'
              }`}
            >
              {t(`social.notifications.filter.${value}`)}
              {value === 'unread' && unreadCount > 0 && (
                <span className="ms-1.5 tabular-nums">{unreadCount}</span>
              )}
            </button>
          ))}
        </div>

        {error ? (
          <ErrorState message={error} onRetry={load} />
        ) : loading ? (
          <ul className="space-y-2.5">
            {[0, 1, 2].map((i) => (
              <li
                key={i}
                className="bg-white rounded-2xl border border-stone-200/80 p-4 flex items-center gap-3"
              >
                <span className="w-9 h-9 rounded-xl skeleton shrink-0" />
                <span className="flex-1 space-y-2">
                  <span className="block h-3 w-1/3 rounded skeleton" />
                  <span className="block h-2.5 w-2/3 rounded skeleton" />
                </span>
              </li>
            ))}
          </ul>
        ) : shown.length === 0 ? (
          <SocialEmpty
            icon={<Bell className="w-5 h-5" />}
            title={
              filter === 'unread'
                ? t('social.notifications.empty.unreadTitle')
                : t('social.notifications.empty.title')
            }
            body={
              filter === 'unread'
                ? t('social.notifications.empty.unreadBody')
                : t('social.notifications.empty.body')
            }
            actionLabel={
              filter === 'all' ? t('social.empty.findPeople') : undefined
            }
            onAction={filter === 'all' ? () => onNavigate('soc-people') : undefined}
          />
        ) : (
          <ul className="space-y-2.5">
            {shown.map((item) => {
              const mark = MARKS[item.type as SocialNotificationType] ?? FALLBACK;
              const categoryKey = `social.notifications.type.${item.type}`;
              const category = t(categoryKey);

              return (
                <li key={item.id}>
                  <div
                    className={`rounded-2xl border p-4 flex items-start gap-3 transition-colors ${
                      item.is_read
                        ? 'bg-white border-stone-200/80'
                        : 'bg-brand-50/40 border-brand-100'
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${mark.tone}`}
                    >
                      {mark.icon}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Translated: this is our label for the row. */}
                        <span className="text-3xs font-extrabold uppercase tracking-wider text-stone-500">
                          {category === categoryKey
                            ? t('social.notifications.type.other')
                            : category}
                        </span>
                        {!item.is_read && (
                          <span
                            className="w-1.5 h-1.5 rounded-full bg-brand-500"
                            aria-label={t('social.notifications.filter.unread')}
                          />
                        )}
                      </div>

                      {/* Stored text, shown as written. */}
                      <p className="mt-1 text-xs font-bold text-stone-900 break-words">
                        {item.title}
                      </p>
                      {item.message && (
                        <p className="mt-0.5 text-2xs text-stone-600 leading-relaxed break-words">
                          {item.message}
                        </p>
                      )}

                      <p className="mt-1.5 text-3xs text-stone-400">
                        {formatRelativeTime(item.created_at, locale)}
                      </p>
                    </div>

                    {!item.is_read && (
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => markRead(item)}
                        isLoading={busy === item.id}
                      >
                        {t('social.notifications.markRead')}
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};
