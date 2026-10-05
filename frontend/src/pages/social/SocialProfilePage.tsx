import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  Award,
  Building2,
  Camera,
  GraduationCap,
  MapPin,
  Pencil,
  Shield,
  Users,
} from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { Input, Textarea } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { ErrorState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useT, formatDate } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import { PageId } from '../../components/layout/Sidebar';
import { SocialHero } from './SocialShell';
import { SocialPost, SocialProfile } from '../../types';
import { PostCard } from './PostCard';
import { SocialAvatar, ConnectActions } from './SocialBits';
import { useOpenConversation, useSocialActions } from './useSocialActions';
import { pickImage } from './imagePicker';

/**
 * One person's social profile: their own, or a colleague's.
 *
 * The **same shape either way** - there is no richer variant for HR and no
 * field on this page that is not on every other profile. The only difference
 * is `is_me`, which swaps Connect / Message for Edit.
 *
 * **Achievements are completed training and time at SmartHR, and nothing
 * else.** Performance ratings, review feedback, attendance and leave are HR
 * records; this is a social profile, and the endpoint does not send them. The
 * tab says so in a line under the list rather than leaving the omission to be
 * guessed at.
 */

interface SocialProfilePageProps {
  onNavigate: (page: PageId) => void;
  /** Null means "my own profile". */
  userId: number | null;
  onBack: () => void;
  onOpenProfile: (userId: number) => void;
  onOpenConversation: (conversationId: number) => void;
}

type TabId = 'posts' | 'about' | 'achievements';

export const SocialProfilePage: React.FC<SocialProfilePageProps> = ({
  onNavigate,
  userId,
  onBack,
  onOpenProfile,
  onOpenConversation,
}) => {
  const { t, locale } = useT();
  const { showToast } = useToast();

  const [profile, setProfile] = useState<SocialProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>('posts');

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    headline: '',
    bio: '',
    skills: '',
    interests: '',
    location: '',
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data =
        userId === null
          ? await SmartHRApi.getMySocialProfile()
          : await SmartHRApi.getSocialProfile(userId);
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('social.profile.notFound'));
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [userId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const actions = useSocialActions(load);
  const openConversation = useOpenConversation(onOpenConversation);

  const openEditor = () => {
    if (!profile) return;
    setForm({
      headline: profile.headline ?? '',
      bio: profile.bio ?? '',
      // Sent back as the comma-separated text the person typed; the server
      // splits it for display and never interprets it.
      skills: profile.skills.join(', '),
      interests: profile.interests.join(', '),
      location: profile.location ?? '',
    });
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      setProfile(await SmartHRApi.updateMySocialProfile(form));
      showToast(t('social.profile.saved'), { type: 'success' });
      setEditing(false);
    } catch (err) {
      showToast(t('social.profile.saveFailed'), {
        message: err instanceof Error ? err.message : undefined,
        type: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  const uploadAvatar = () =>
    pickImage({
      onPicked: async (file) => {
        try {
          setProfile(await SmartHRApi.uploadMySocialAvatar(file));
          showToast(t('social.profile.avatarUpdated'), { type: 'success' });
        } catch (err) {
          showToast(t('social.profile.saveFailed'), {
            message: err instanceof Error ? err.message : undefined,
            type: 'error',
          });
        }
      },
      onRejected: (reason) =>
        showToast(t(`social.compose.${reason}`), { type: 'warning' }),
    });

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-32 rounded-2xl skeleton" />
        <div className="h-48 rounded-2xl skeleton" />
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="space-y-4">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<ArrowLeft className="w-4 h-4" data-flip-rtl />}
          onClick={onBack}
        >
          {t('social.profile.backToPeople')}
        </Button>
        <ErrorState message={error ?? t('social.profile.notFound')} onRetry={load} />
      </div>
    );
  }

  const replacePost = (updated: SocialPost) =>
    setProfile((current) =>
      current
        ? {
            ...current,
            posts: (current.posts ?? []).map((p) =>
              p.id === updated.id ? updated : p
            ),
          }
        : current
    );

  const dropPost = (postId: number) =>
    setProfile((current) =>
      current
        ? { ...current, posts: (current.posts ?? []).filter((p) => p.id !== postId) }
        : current
    );

  const posts = profile.posts ?? [];

  return (
    <div className="space-y-5">
      <SocialHero
        title={
          profile.is_me
            ? t('social.profile.mineTitle')
            : t('social.profile.title')
        }
        subtitle={
          profile.is_me
            ? t('social.profile.mineSubtitle')
            : t('social.profile.subtitle')
        }
        me={profile.is_me ? profile : null}
        current="soc-profile"
        onNavigate={onNavigate}
      />

      {!profile.is_me && (
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<ArrowLeft className="w-4 h-4" data-flip-rtl />}
          onClick={onBack}
        >
          {t('social.profile.backToPeople')}
        </Button>
      )}

      {/* ----------------------------- Header --------------------------- */}
      <Card padding="none" className="overflow-hidden">
        {/* A warm brand band rather than an uploaded cover: SmartHR has the
            colour, it does not have a photograph of this person's workplace. */}
        <div className="h-24 sm:h-32 bg-gradient-to-br from-brand-400 via-brand-500 to-brand-700" />

        <div className="px-5 sm:px-6 pb-5 -mt-12 sm:-mt-14">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex items-end gap-4 min-w-0">
              <div className="relative shrink-0">
                <SocialAvatar
                  person={profile}
                  size="xl"
                  className="ring-4 ring-white shadow-pop"
                />
                {profile.is_me && (
                  <button
                    type="button"
                    onClick={uploadAvatar}
                    aria-label={t('social.profile.changeAvatar')}
                    className="absolute bottom-0 end-0 w-8 h-8 rounded-full bg-brand-600 text-white border-2 border-white flex items-center justify-center hover:bg-brand-700 transition-colors"
                  >
                    <Camera className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              <div className="min-w-0 pb-1">
                <h1 className="text-lg sm:text-xl font-black text-stone-900 tracking-tight truncate">
                  {profile.name}
                </h1>
                <p className="text-xs text-stone-600 truncate mt-0.5">
                  {profile.headline ||
                    profile.position_title ||
                    t('social.people.noPosition')}
                </p>

                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-3xs text-stone-500">
                  {profile.department_name && (
                    <span className="inline-flex items-center gap-1">
                      <Building2 className="w-3 h-3" />
                      {profile.department_name}
                    </span>
                  )}
                  {profile.location && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      {profile.location}
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    {t('social.connect.count', { count: profile.connections_count })}
                  </span>
                  {profile.role_name && (
                    <Badge variant="brand" size="sm">
                      {profile.role_name}
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="pb-1">
              {profile.is_me ? (
                <Button
                  variant="outline"
                  size="sm"
                  leftIcon={<Pencil className="w-3.5 h-3.5" />}
                  onClick={openEditor}
                >
                  {t('social.profile.edit')}
                </Button>
              ) : (
                <ConnectActions
                  person={profile}
                  connection={profile.connection}
                  busy={actions.busy}
                  onConnect={(id) => actions.connect(id, profile.name)}
                  onAccept={actions.accept}
                  onReject={actions.reject}
                  onDisconnect={actions.disconnect}
                  onMessage={openConversation}
                />
              )}
            </div>
          </div>

          {/* An account with no employees row is legitimate; say so rather
              than leaving the department line blank and unexplained. */}
          {!profile.employee_id && (
            <p className="mt-4 flex items-start gap-2 text-3xs text-stone-500 bg-sand-50 border border-sand-200 rounded-xl px-3 py-2">
              <Shield className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
              {t('social.profile.unlinkedAccount')}
            </p>
          )}
        </div>

        {/* The profile's own navigation, attached to the card rather than
            floating under it - one object on screen, which is how a social
            profile reads. Same three sections, same state. */}
        <nav
          aria-label={t('social.profile.tab.about')}
          className="px-3 sm:px-5 border-t border-stone-100 bg-sand-50/50"
        >
          <ul className="flex items-center gap-1 overflow-x-auto no-scrollbar">
            {(
              [
                { id: 'posts', label: t('social.profile.tab.posts'), count: posts.length },
                { id: 'about', label: t('social.profile.tab.about'), count: undefined },
                {
                  id: 'achievements',
                  label: t('social.profile.tab.achievements'),
                  count: profile.achievements.length,
                },
              ] as { id: TabId; label: string; count?: number }[]
            ).map((item) => {
              const active = tab === item.id;

              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setTab(item.id)}
                    aria-current={active ? 'true' : undefined}
                    className={`relative shrink-0 h-11 px-3 sm:px-4 inline-flex items-center gap-1.5 text-2xs font-bold transition-colors ${
                      active ? 'text-brand-700' : 'text-stone-500 hover:text-stone-800'
                    }`}
                  >
                    <span className="whitespace-nowrap">{item.label}</span>
                    {typeof item.count === 'number' && item.count > 0 && (
                      <span
                        className={`min-w-4 h-4 px-1 rounded-full text-[10px] font-black leading-4 text-center tabular-nums ${
                          active
                            ? 'bg-brand-100 text-brand-800'
                            : 'bg-stone-100 text-stone-500'
                        }`}
                      >
                        {item.count}
                      </span>
                    )}
                    {active && (
                      <span
                        aria-hidden="true"
                        className="absolute inset-x-2 sm:inset-x-3 bottom-0 h-0.5 rounded-t-full bg-brand-600"
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </Card>

      {tab === 'posts' && (
        <div className="space-y-4">
          {posts.length === 0 ? (
            <EmptyState
              icon={<Users className="w-6 h-6" />}
              title={t('social.profile.noPosts')}
              description={
                profile.is_me
                  ? t('social.profile.noPostsMine')
                  : t('social.profile.noPostsOther', { name: profile.name })
              }
            />
          ) : (
            posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                onChanged={replacePost}
                onDeleted={dropPost}
                onOpenProfile={onOpenProfile}
              />
            ))
          )}
        </div>
      )}

      {tab === 'about' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500 mb-2">
              {t('social.profile.bio')}
            </h2>
            {profile.bio ? (
              <p className="text-sm text-stone-700 leading-relaxed whitespace-pre-wrap">
                {profile.bio}
              </p>
            ) : (
              <p className="text-2xs text-stone-400">
                {profile.is_me
                  ? t('social.profile.noBioMine')
                  : t('social.profile.noBio')}
              </p>
            )}
          </Card>

          <div className="space-y-4">
            <Card>
              <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500 mb-2">
                {t('social.profile.skills')}
              </h2>
              {profile.skills.length === 0 ? (
                <p className="text-2xs text-stone-400">
                  {t('social.profile.noSkills')}
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {profile.skills.map((skill) => (
                    <Badge key={skill} variant="brand" size="md">
                      {skill}
                    </Badge>
                  ))}
                </div>
              )}
            </Card>

            {profile.interests.length > 0 && (
              <Card>
                <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500 mb-2">
                  {t('social.profile.interests')}
                </h2>
                <div className="flex flex-wrap gap-1.5">
                  {profile.interests.map((interest) => (
                    <Badge key={interest} variant="neutral" size="md">
                      {interest}
                    </Badge>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === 'achievements' && (
        <div className="space-y-3">
          {profile.achievements.length === 0 ? (
            <EmptyState
              icon={<Award className="w-6 h-6" />}
              title={t('social.profile.achievements.empty')}
              description={t('social.profile.achievements.emptyBody')}
            />
          ) : (
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {profile.achievements.map((item, index) => (
                <li key={`${item.kind}-${index}`}>
                  <Card variant="hover" padding="sm">
                    <div className="flex items-start gap-3">
                      <span
                        className="w-9 h-9 rounded-xl bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center shrink-0"
                        aria-hidden="true"
                      >
                        {item.kind === 'training' ? (
                          <GraduationCap className="w-4 h-4" />
                        ) : (
                          <Award className="w-4 h-4" />
                        )}
                      </span>

                      <div className="min-w-0">
                        <p className="text-xs font-bold text-stone-900">
                          {item.kind === 'training'
                            ? /* The course title, exactly as stored. */
                              item.title
                            : t('social.profile.achievement.tenure')}
                        </p>
                        <p className="text-3xs text-stone-500 mt-0.5">
                          {item.kind === 'training'
                            ? t('social.profile.achievement.training')
                            : t('social.profile.achievement.years', {
                                count: item.years ?? 0,
                              })}
                        </p>
                        {item.date && (
                          <p className="text-3xs text-stone-400 mt-0.5">
                            {formatDate(item.date, locale)}
                          </p>
                        )}
                      </div>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}

          <p className="text-3xs text-stone-400 leading-relaxed">
            {t('social.profile.achievements.note')}
          </p>
        </div>
      )}

      {/* ----------------------------- Editor --------------------------- */}
      <Modal
        isOpen={editing}
        onClose={() => setEditing(false)}
        title={t('social.profile.edit')}
        size="lg"
        footer={
          <>
            <Button variant="outline" onClick={() => setEditing(false)}>
              {t('action.cancel')}
            </Button>
            <Button variant="primary" onClick={save} isLoading={saving}>
              {t('social.profile.save')}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label={t('social.profile.headline')}
            placeholder={t('social.profile.headlinePlaceholder')}
            value={form.headline}
            maxLength={150}
            onChange={(event) =>
              setForm((f) => ({ ...f, headline: event.target.value }))
            }
          />

          <Textarea
            label={t('social.profile.bio')}
            placeholder={t('social.profile.bioPlaceholder')}
            rows={4}
            value={form.bio}
            maxLength={2000}
            onChange={(event) => setForm((f) => ({ ...f, bio: event.target.value }))}
          />

          <Input
            label={t('social.profile.skills')}
            placeholder={t('social.profile.skillsPlaceholder')}
            value={form.skills}
            onChange={(event) =>
              setForm((f) => ({ ...f, skills: event.target.value }))
            }
          />

          <Input
            label={t('social.profile.interests')}
            placeholder={t('social.profile.interestsPlaceholder')}
            value={form.interests}
            onChange={(event) =>
              setForm((f) => ({ ...f, interests: event.target.value }))
            }
          />

          <Input
            label={t('social.profile.location')}
            placeholder={t('social.profile.locationPlaceholder')}
            value={form.location}
            maxLength={150}
            onChange={(event) =>
              setForm((f) => ({ ...f, location: event.target.value }))
            }
          />
        </div>
      </Modal>
    </div>
  );
};
