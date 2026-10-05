import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bell,
  Calendar,
  ImagePlus,
  MessageSquare,
  Rss,
  UserPlus,
  Users,
  X,
} from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { Pagination } from '../../components/ui/Pagination';
import { Textarea } from '../../components/ui/Input';
import { ErrorState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useT } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import { PageId } from '../../components/layout/Sidebar';
import {
  SocialDirectoryPerson,
  SocialFeedResponse,
  SocialFeedScope,
  SocialHubStatus,
  SocialPost,
} from '../../types';
import { PostCard } from './PostCard';
import { StoriesBar } from './StoriesBar';
import { SocialAvatar, ConnectActions } from './SocialBits';
import { CelebrationPanel } from './CelebrationPanel';
import { PostSkeleton, SocialEmpty, SocialHero } from './SocialShell';
import { useOpenConversation, useSocialActions } from './useSocialActions';
import { pickImage } from './imagePicker';

/**
 * The Social Hub's front page: stories, a composer, the feed, and a rail.
 *
 * Three columns on a wide screen, one on a phone - the rail moves below the
 * feed rather than disappearing, because "people you may know" is how an empty
 * network stops being empty.
 *
 * **Nothing here is invented to fill space.** There is no events table in
 * SmartHR, so the rail says so in one line instead of showing a plausible
 * calendar; an empty feed is an empty state naming the filter that produced it;
 * and the directory count is the real number of colleagues with an account.
 */

interface SocialFeedPageProps {
  onNavigate: (page: PageId) => void;
  onOpenProfile: (userId: number) => void;
  onOpenConversation: (conversationId: number) => void;
}

const SCOPES: { id: SocialFeedScope; key: string }[] = [
  { id: 'all', key: 'social.feed.scope.all' },
  { id: 'department', key: 'social.feed.scope.department' },
  { id: 'following', key: 'social.feed.scope.following' },
  { id: 'company', key: 'social.feed.scope.company' },
];

const PAGE_SIZE = 10;

/** Admin and HR, the same pair POST /social/celebration is guarded with. */
const CELEBRATION_ROLES = [1, 2];

export const SocialFeedPage: React.FC<SocialFeedPageProps> = ({
  onNavigate,
  onOpenProfile,
  onOpenConversation,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [scope, setScope] = useState<SocialFeedScope>('all');
  const [page, setPage] = useState(1);
  const [feed, setFeed] = useState<SocialFeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState<SocialHubStatus | null>(null);
  const [suggested, setSuggested] = useState<SocialDirectoryPerson[]>([]);

  const [draft, setDraft] = useState('');
  const [audience, setAudience] = useState<'company' | 'department'>('company');
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setFeed(await SmartHRApi.getSocialFeed({ scope, page, pageSize: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('social.feed.loadError'));
      setFeed(null);
    } finally {
      setLoading(false);
    }
  }, [scope, page, t]);

  const loadRail = useCallback(async () => {
    // The rail is secondary: if either call fails the feed still renders, so
    // these are settled independently rather than in one await chain.
    try {
      setStatus(await SmartHRApi.getSocialStatus());
    } catch {
      setStatus(null);
    }
    try {
      setSuggested((await SmartHRApi.getSocialSuggestions(4)).people);
    } catch {
      setSuggested([]);
    }
  }, []);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  useEffect(() => {
    loadRail();
  }, [loadRail]);

  useEffect(() => {
    if (!image) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const actions = useSocialActions(async () => {
    await Promise.all([loadRail(), loadFeed()]);
  });

  const openConversation = useOpenConversation(onOpenConversation);

  const submit = async () => {
    if (!draft.trim()) return;

    setPosting(true);
    try {
      const created = await SmartHRApi.createSocialPost({
        content: draft,
        audience,
        image,
      });

      // "Posted" and "posted, and held for review" are different events, and
      // saying the first when the second happened is how somebody ends up
      // posting the same thing twice.
      if (created.pending_review) {
        showToast(t('social.pending.postToast'), {
          message: t('social.pending.notice'),
          type: 'info',
        });
      } else {
        showToast(t('social.compose.posted'), {
          message: t('social.compose.postedBody'),
          type: 'success',
        });
      }
      setDraft('');
      setImage(null);
      setAudience('company');
      setPage(1);
      await loadFeed();
      await loadRail();
    } catch (err) {
      showToast(t('social.compose.failed'), {
        message: err instanceof Error ? err.message : undefined,
        type: 'error',
      });
    } finally {
      setPosting(false);
    }
  };

  const replacePost = (updated: SocialPost) =>
    setFeed((current) =>
      current
        ? {
            ...current,
            posts: current.posts.map((p) => (p.id === updated.id ? updated : p)),
          }
        : current
    );

  const dropPost = (postId: number) =>
    setFeed((current) =>
      current
        ? {
            ...current,
            posts: current.posts.filter((p) => p.id !== postId),
            total: Math.max(current.total - 1, 0),
          }
        : current
    );

  const emptyBody = useMemo(() => {
    switch (scope) {
      case 'department':
        return t('social.feed.empty.department');
      case 'following':
        return t('social.feed.empty.following');
      case 'company':
        return t('social.feed.empty.company');
      default:
        return t('social.feed.empty.body');
    }
  }, [scope, t]);

  const posts = feed?.posts ?? [];

  // "What's on your mind, Sara?" - the name is a database value, dropped into
  // a translated sentence through the placeholder rather than concatenated,
  // so Arabic can put it where Arabic puts it.
  const firstName = (status?.me?.name ?? '').trim().split(/\s+/)[0] ?? '';

  return (
    <div className="space-y-5">
      <SocialHero
        title={t('social.feed.title')}
        subtitle={t('social.feed.subtitle')}
        me={status?.me ?? null}
        unread={status?.unread_notifications ?? 0}
        current="soc-feed"
        onNavigate={onNavigate}
      />

      {/* Two columns on a wide screen. The rail moves *below* the feed on a
          phone rather than disappearing, because "people you may know" is how
          an empty network stops being empty. */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_340px] gap-5 xl:gap-6">
        {/* ============================ CENTRE ========================== */}
        <div className="space-y-5 min-w-0">
          <StoriesBar onOpenProfile={onOpenProfile} />

          {/* --- Composer ------------------------------------------------ */}
          <div className="bg-white rounded-2xl border border-stone-200/80 shadow-card overflow-hidden">
            <div className="p-4 sm:p-5">
              <div className="flex items-start gap-3">
                <SocialAvatar person={status?.me ?? null} size="md" />

                <div className="flex-1 min-w-0">
                  <Textarea
                    rows={draft || image ? 3 : 2}
                    value={draft}
                    placeholder={t('social.compose.placeholder', {
                      name: firstName,
                    })}
                    onChange={(event) => setDraft(event.target.value)}
                    maxLength={5000}
                    className="!border-0 !bg-transparent !px-0 !py-1.5 !text-sm placeholder:text-stone-400 focus:!ring-0"
                  />

                  {preview && (
                    <div className="relative inline-block mt-2">
                      <img
                        src={preview}
                        alt=""
                        className="max-h-56 rounded-xl border border-stone-200 bg-sand-100"
                      />
                      <button
                        type="button"
                        onClick={() => setImage(null)}
                        aria-label={t('social.compose.removePhoto')}
                        className="absolute top-2 end-2 w-7 h-7 rounded-full bg-stone-900/70 hover:bg-stone-900 text-white flex items-center justify-center transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* The action rail. Separated by a hairline rather than boxed, so
                the composer reads as one surface. */}
            <div className="px-3 sm:px-4 py-2.5 border-t border-stone-100 bg-sand-50/60 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1">
                <button
                  type="button"
                  onClick={() =>
                    pickImage({
                      onPicked: setImage,
                      onRejected: (reason) =>
                        showToast(t(`social.compose.${reason}`), {
                          type: 'warning',
                        }),
                    })
                  }
                  className="h-9 px-3 rounded-lg inline-flex items-center gap-2 text-2xs font-bold text-stone-600 hover:text-brand-700 hover:bg-brand-50 transition-colors"
                >
                  <ImagePlus className="w-4 h-4" aria-hidden="true" />
                  {t('social.compose.photo')}
                </button>

                {/* Offered only when SmartHR knows the poster's department - an
                    account with no employees row has none, and the server
                    refuses that post rather than guessing. And only Admin and
                    HR posts count as Company Updates, which is derived from
                    who posted rather than from a box anybody can tick. */}
                {status?.me?.department_name && (
                  <div className="inline-flex rounded-lg border border-stone-200 bg-white p-0.5 ms-1">
                    {(['company', 'department'] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setAudience(value)}
                        aria-pressed={audience === value}
                        className={`h-7 px-2.5 rounded-md text-3xs font-bold transition-colors ${
                          audience === value
                            ? 'bg-brand-600 text-white'
                            : 'text-stone-500 hover:text-stone-800'
                        }`}
                      >
                        {t(`social.compose.audience.${value}`)}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <Button
                variant="primary"
                size="sm"
                onClick={submit}
                isLoading={posting}
                disabled={!draft.trim()}
              >
                {t('social.compose.post')}
              </Button>
            </div>
          </div>

          {/* --- Filters ------------------------------------------------- */}
          <div className="flex items-center justify-between gap-3">
            <div
              role="tablist"
              aria-label={t('social.feed.title')}
              className="inline-flex items-center gap-0.5 p-1 rounded-xl bg-white border border-stone-200/80 shadow-card overflow-x-auto no-scrollbar max-w-full"
            >
              {SCOPES.map((item) => (
                <button
                  key={item.id}
                  role="tab"
                  type="button"
                  aria-selected={scope === item.id}
                  onClick={() => {
                    setScope(item.id);
                    setPage(1);
                  }}
                  className={`shrink-0 h-8 px-3.5 rounded-lg text-2xs font-bold transition-colors ${
                    scope === item.id
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'text-stone-500 hover:text-stone-900 hover:bg-sand-100'
                  }`}
                >
                  {t(item.key)}
                </button>
              ))}
            </div>

            {feed && feed.total > 0 && (
              <span className="hidden sm:block text-3xs text-stone-400 tabular-nums shrink-0">
                {t('social.feed.count', { count: feed.total })}
              </span>
            )}
          </div>

          {scope === 'company' && (
            <p className="text-3xs text-stone-500 -mt-2.5 ps-1">
              {t('social.feed.scope.companyHint')}
            </p>
          )}

          {scope === 'department' && feed && !feed.department_available && (
            <p className="text-2xs text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5">
              {t('social.feed.noDepartment')}
            </p>
          )}

          {/* --- Feed ---------------------------------------------------- */}
          {error ? (
            <ErrorState message={error} onRetry={loadFeed} />
          ) : loading ? (
            <div className="space-y-4">
              <PostSkeleton />
              <PostSkeleton />
            </div>
          ) : posts.length === 0 ? (
            <SocialEmpty
              icon={<Rss className="w-5 h-5" />}
              title={t('social.feed.empty.title')}
              body={emptyBody}
              actionLabel={t('social.empty.findPeople')}
              onAction={() => onNavigate('soc-people')}
            />
          ) : (
            <div className="space-y-4">
              {posts.map((post) => (
                <PostCard
                  key={post.id}
                  post={post}
                  onChanged={replacePost}
                  onDeleted={dropPost}
                  onOpenProfile={onOpenProfile}
                />
              ))}
            </div>
          )}

          {feed && feed.pages > 1 && (
            <Pagination
              page={feed.page}
              pageCount={feed.pages}
              total={feed.total}
              pageSize={feed.page_size}
              onPageChange={setPage}
            />
          )}
        </div>

        {/* ============================= RAIL ========================== */}
        <aside className="space-y-4 min-w-0">
          {/* --- Who you are -------------------------------------------- */}
          <div className="bg-white rounded-2xl border border-stone-200/80 shadow-card overflow-hidden">
            {/* A warm band rather than a photograph: SmartHR has no cover
                image column, and a stock picture would be decoration
                pretending to be somebody's. */}
            <div className="h-16 bg-gradient-to-r from-brand-100 via-brand-50 to-sand-100" />

            <div className="px-4 pb-4 -mt-8">
              <button
                type="button"
                onClick={() => onNavigate('soc-profile')}
                className="block rounded-full"
              >
                <SocialAvatar person={status?.me ?? null} size="lg" ring="muted" />
              </button>

              <h2 className="mt-2.5 text-sm font-extrabold text-stone-900 truncate">
                {status?.me?.name ?? '—'}
              </h2>
              <p className="text-3xs text-stone-500 truncate">
                {status?.me?.headline ||
                  [status?.me?.position_title, status?.me?.department_name]
                    .filter(Boolean)
                    .join(' · ') ||
                  t('social.people.noPosition')}
              </p>

              <dl className="mt-3.5 grid grid-cols-3 gap-1 pt-3.5 border-t border-stone-100">
                {[
                  {
                    label: t('social.rail.connections'),
                    value: status?.connections ?? 0,
                    page: 'soc-people' as PageId,
                  },
                  {
                    label: t('social.rail.requests'),
                    value: status?.pending_requests ?? 0,
                    page: 'soc-people' as PageId,
                  },
                  {
                    label: t('social.rail.unread'),
                    value: status?.unread_messages ?? 0,
                    page: 'soc-messages' as PageId,
                  },
                ].map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => onNavigate(item.page)}
                    className="rounded-lg px-1 py-1.5 text-center hover:bg-sand-100 transition-colors"
                  >
                    <dd className="text-base font-black text-stone-900 tabular-nums leading-none">
                      {item.value}
                    </dd>
                    <dt className="mt-1 text-[10px] text-stone-500 truncate">
                      {item.label}
                    </dt>
                  </button>
                ))}
              </dl>
            </div>
          </div>

          {/* --- People you may know ------------------------------------ */}
          <div className="bg-white rounded-2xl border border-stone-200/80 shadow-card p-4">
            <div className="flex items-center justify-between gap-2 mb-3">
              <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500">
                {t('social.people.suggested')}
              </h2>
              <button
                type="button"
                onClick={() => onNavigate('soc-people')}
                className="text-3xs font-bold text-brand-700 hover:underline shrink-0"
              >
                {t('social.rail.viewAll')}
              </button>
            </div>

            {suggested.length === 0 ? (
              <p className="text-2xs text-stone-400 py-2 leading-relaxed">
                {t('social.people.suggestedEmpty')}
              </p>
            ) : (
              <ul className="divide-y divide-stone-100 -my-3">
                {suggested.map((person) => (
                  <li key={person.user_id} className="py-3 space-y-2.5">
                    <button
                      type="button"
                      onClick={() => onOpenProfile(person.user_id)}
                      className="flex items-center gap-2.5 w-full text-start rounded-lg group"
                    >
                      <SocialAvatar person={person} size="md" />
                      <span className="min-w-0">
                        <span className="block text-2xs font-bold text-stone-900 truncate group-hover:text-brand-700">
                          {person.name}
                        </span>
                        <span className="block text-3xs text-stone-500 truncate">
                          {person.headline ||
                            person.position_title ||
                            person.department_name ||
                            t('social.people.noDepartment')}
                        </span>
                      </span>
                    </button>

                    <ConnectActions
                      person={person}
                      connection={person.connection}
                      busy={actions.busy}
                      size="xs"
                      onConnect={(id) => actions.connect(id, person.name)}
                      onAccept={actions.accept}
                      onReject={actions.reject}
                      onDisconnect={actions.disconnect}
                      onMessage={openConversation}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* --- AI Employee Celebration -------------------------------- */}
          {/* Admin and HR only, matching the endpoint's own guard. The role
              comes from `status.me`, which the hub status already carries -
              this is convenience, not security: require_roles(1, 2) on the
              router is the boundary, and hiding the panel grants nobody
              anything. */}
          {CELEBRATION_ROLES.includes(status?.me?.role_id ?? 0) && (
            <CelebrationPanel
              onPosted={() => {
                // The celebration went through POST /social/posts like any
                // other post, so the feed re-reads itself rather than being
                // told what to show.
                setPage(1);
                void loadFeed();
                void loadRail();
              }}
              onUseInComposer={(message) => {
                // Into the draft, never onto the feed. The person reads it,
                // edits it and presses Post, so it travels the ordinary
                // /social/posts path with its moderation and its audit row.
                setDraft(message);
                showToast(t('social.celebration.inComposer'), { type: 'info' });
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
            />
          )}

          {/* --- Shortcuts ---------------------------------------------- */}
          <div className="bg-white rounded-2xl border border-stone-200/80 shadow-card p-4">
            <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500 mb-2.5">
              {t('social.rail.shortcuts')}
            </h2>

            <div className="space-y-0.5">
              {[
                { page: 'soc-people' as PageId, icon: <Users className="w-4 h-4" />, key: 'nav.soc-people' },
                { page: 'soc-messages' as PageId, icon: <MessageSquare className="w-4 h-4" />, key: 'nav.soc-messages' },
                { page: 'soc-notifications' as PageId, icon: <Bell className="w-4 h-4" />, key: 'nav.soc-notifications' },
                { page: 'soc-profile' as PageId, icon: <UserPlus className="w-4 h-4" />, key: 'nav.soc-profile' },
              ].map((item) => (
                <button
                  key={item.page}
                  type="button"
                  onClick={() => onNavigate(item.page)}
                  className="w-full h-9 px-2.5 rounded-lg flex items-center gap-2.5 text-2xs font-semibold text-stone-700 hover:bg-sand-100 transition-colors"
                >
                  <span className="text-brand-600" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className="truncate">{t(item.key)}</span>
                </button>
              ))}
            </div>

            {/* Said plainly rather than filled with a plausible calendar:
                SmartHR has no events table, so there is nothing real to show. */}
            <p className="mt-3 pt-3 border-t border-stone-100 text-3xs text-stone-400 leading-relaxed flex gap-1.5">
              <Calendar className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
              {t('social.rail.noEvents')}
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
};
