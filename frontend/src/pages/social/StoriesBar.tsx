import React, { useEffect, useState } from 'react';
import { Plus, X, ChevronLeft, ChevronRight, Eye, Trash2, ImagePlus } from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Textarea } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { useT, formatRelativeTime } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import { SocialStoriesResponse, SocialStoryGroup } from '../../types';
import { SocialAvatar } from './SocialBits';
import { pickImage } from './imagePicker';

/**
 * The stories strip, plus the two things you can do with it: post one and
 * watch one.
 *
 * **Expiry is the server's answer, not a timer here.** `GET /social/stories`
 * returns only stories whose `expires_at` is still in the future, so nothing in
 * this component hides an expired story - it never receives one. The countdown
 * shown on a card is presentation of a timestamp the server sent.
 *
 * Opening a story marks it seen through `POST /social/stories/{id}/view`, and
 * the ring around the avatar follows the server's `has_unseen`, so the seen
 * state survives a reload rather than living in this component.
 */

interface StoriesBarProps {
  onOpenProfile: (userId: number) => void;
}

const hoursLeft = (expiresAt: string): number =>
  Math.max(0, Math.round((new Date(expiresAt).getTime() - Date.now()) / 3600000));

export const StoriesBar: React.FC<StoriesBarProps> = ({ onOpenProfile }) => {
  const { t, locale } = useT();
  const { showToast } = useToast();

  const [data, setData] = useState<SocialStoriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [composing, setComposing] = useState(false);
  const [caption, setCaption] = useState('');
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Which group is open, and how far into it. Null is "nothing open".
  const [viewing, setViewing] = useState<{ group: number; index: number } | null>(
    null
  );

  const load = async () => {
    try {
      setData(await SmartHRApi.getSocialStories());
    } catch {
      // A failed strip must not take the feed down with it: the page below is
      // the point of the screen, so this degrades to "no active stories".
      setData({ groups: [], total: 0 });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Revoke the object URL rather than leaking one per picked image.
  useEffect(() => {
    if (!image) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const groups = data?.groups ?? [];
  const openGroup: SocialStoryGroup | undefined =
    viewing === null ? undefined : groups[viewing.group];
  const openStory =
    openGroup && viewing ? openGroup.stories[viewing.index] : undefined;

  useEffect(() => {
    if (!openStory || openStory.seen || openStory.is_mine) return;

    SmartHRApi.viewSocialStory(openStory.id)
      .then(() => load())
      .catch(() => {
        // Seen state is a nicety; failing to record it must not interrupt
        // watching the story.
      });
  }, [openStory?.id]);

  const close = () => setViewing(null);

  const step = (delta: number) => {
    if (!viewing || !openGroup) return;

    const next = viewing.index + delta;

    if (next >= 0 && next < openGroup.stories.length) {
      setViewing({ ...viewing, index: next });
      return;
    }

    const nextGroup = viewing.group + (delta > 0 ? 1 : -1);

    if (nextGroup < 0 || nextGroup >= groups.length) {
      close();
      return;
    }

    setViewing({
      group: nextGroup,
      index: delta > 0 ? 0 : groups[nextGroup].stories.length - 1,
    });
  };

  const submit = async () => {
    if (!caption.trim() && !image) {
      showToast(t('social.stories.needSomething'), { type: 'warning' });
      return;
    }

    setSaving(true);
    try {
      const shared = await SmartHRApi.createSocialStory({ caption, image });

      if (shared.pending_review) {
        showToast(t('social.pending.storyToast'), {
          message: t('social.pending.notice'),
          type: 'info',
        });
      } else {
        showToast(t('social.stories.shared'), {
          message: t('social.stories.sharedBody'),
          type: 'success',
        });
      }
      setComposing(false);
      setCaption('');
      setImage(null);
      await load();
    } catch (error) {
      showToast(t('social.compose.failed'), {
        message: error instanceof Error ? error.message : undefined,
        type: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  const remove = async (storyId: number) => {
    try {
      await SmartHRApi.deleteSocialStory(storyId);
      showToast(t('social.stories.deleted'), { type: 'success' });
      close();
      await load();
    } catch (error) {
      showToast(t('social.post.actionFailed'), {
        message: error instanceof Error ? error.message : undefined,
        type: 'error',
      });
    }
  };

  return (
    <section
      aria-label={t('social.stories.title')}
      className="bg-white rounded-2xl border border-stone-200/80 shadow-card p-4"
    >
      <div className="flex items-center justify-between gap-3 mb-3.5">
        <h2 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500">
          {t('social.stories.title')}
        </h2>
        {groups.length > 0 && (
          <p className="text-3xs text-stone-400 truncate">
            {t('social.stories.expiryNote')}
          </p>
        )}
      </div>

      <div className="flex gap-3.5 overflow-x-auto no-scrollbar pb-1">
        {/* Add story is always first, so the affordance never moves. */}
        <button
          type="button"
          onClick={() => setComposing(true)}
          className="shrink-0 w-[76px] flex flex-col items-center gap-1.5 group"
        >
          <span className="w-16 h-16 rounded-full border-2 border-dashed border-brand-300 bg-brand-50 text-brand-600 flex items-center justify-center transition-colors group-hover:bg-brand-100 group-hover:border-brand-400">
            <Plus className="w-5 h-5" />
          </span>
          <span className="text-3xs font-semibold text-stone-600 text-center leading-tight">
            {t('social.stories.add')}
          </span>
        </button>

        {loading &&
          [0, 1, 2].map((i) => (
            <div key={i} className="shrink-0 w-[76px] flex flex-col items-center gap-1.5">
              <span className="w-16 h-16 rounded-full skeleton" />
              <span className="w-12 h-2.5 rounded skeleton" />
            </div>
          ))}

        {!loading && groups.length === 0 && (
          <div className="flex-1 flex items-center ps-2">
            <p className="text-2xs text-stone-400">{t('social.stories.empty')}</p>
          </div>
        )}

        {groups.map((group, index) => (
          <button
            key={group.author?.user_id ?? index}
            type="button"
            onClick={() => setViewing({ group: index, index: 0 })}
            className="shrink-0 w-[76px] flex flex-col items-center gap-1.5 group"
            title={group.is_mine ? t('social.stories.yours') : group.author?.name}
          >
            {/* The ring is the unseen mark, and it follows the server's
                `has_unseen` - it is not a local guess about what has been
                opened in this tab. A seen story keeps a ring so the row stays
                even, but a plain one. */}
            <span
              className={`w-16 h-16 rounded-full p-[2.5px] flex items-center justify-center transition-transform group-hover:scale-105 ${
                group.has_unseen
                  ? 'bg-gradient-to-tr from-brand-600 via-brand-400 to-brand-200'
                  : 'bg-stone-200'
              }`}
            >
              <span className="w-full h-full rounded-full p-[2px] bg-white flex items-center justify-center">
                <SocialAvatar
                  person={group.author}
                  size="lg"
                  className={`w-full h-full ${
                    group.has_unseen ? '' : 'opacity-80'
                  }`}
                />
              </span>
            </span>

            <span
              className={`text-3xs text-center leading-tight truncate w-full ${
                group.has_unseen
                  ? 'font-bold text-stone-800'
                  : 'font-semibold text-stone-500'
              }`}
            >
              {group.is_mine ? t('social.stories.yours') : group.author?.name}
            </span>
          </button>
        ))}
      </div>

      {/* --- Compose ------------------------------------------------------ */}
      <Modal
        isOpen={composing}
        onClose={() => setComposing(false)}
        title={t('social.stories.create')}
        subtitle={t('social.stories.sharedBody')}
        size="md"
        footer={
          <>
            <Button variant="outline" onClick={() => setComposing(false)}>
              {t('action.cancel')}
            </Button>
            <Button variant="primary" onClick={submit} isLoading={saving}>
              {t('social.stories.add')}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {preview ? (
            <div className="relative">
              <img
                src={preview}
                alt=""
                className="w-full max-h-64 object-contain rounded-xl bg-sand-100"
              />
              <button
                type="button"
                onClick={() => setImage(null)}
                aria-label={t('social.compose.removePhoto')}
                className="absolute top-2 end-2 w-8 h-8 rounded-full bg-stone-900/70 text-white flex items-center justify-center"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <Button
              variant="outline"
              fullWidth
              leftIcon={<ImagePlus className="w-4 h-4" />}
              onClick={() =>
                pickImage({
                  onPicked: setImage,
                  onRejected: (reason) =>
                    showToast(t(`social.compose.${reason}`), { type: 'warning' }),
                })
              }
            >
              {t('social.compose.photo')}
            </Button>
          )}

          <Textarea
            label={t('social.stories.caption')}
            placeholder={t('social.stories.captionPlaceholder')}
            rows={3}
            value={caption}
            maxLength={300}
            onChange={(event) => setCaption(event.target.value)}
          />
        </div>
      </Modal>

      {/* --- Viewer ------------------------------------------------------- */}
      <Modal
        isOpen={Boolean(openStory)}
        onClose={close}
        title={openGroup?.author?.name ?? t('social.stories.title')}
        subtitle={
          openStory ? formatRelativeTime(openStory.created_at, locale) : undefined
        }
        size="lg"
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => step(-1)}
                aria-label={t('social.stories.previous')}
              >
                <ChevronLeft className="w-4 h-4" data-flip-rtl />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => step(1)}
                aria-label={t('social.stories.next')}
              >
                <ChevronRight className="w-4 h-4" data-flip-rtl />
              </Button>
            </div>

            {openStory?.is_mine && (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                onClick={() => remove(openStory.id)}
              >
                {t('social.stories.delete')}
              </Button>
            )}
          </div>
        }
      >
        {openStory && (
          <div className="space-y-3">
            {openStory.image_url && (
              <img
                src={openStory.image_url}
                alt={t('social.stories.imageAlt', {
                  name: openGroup?.author?.name ?? '',
                })}
                className="w-full max-h-[60vh] object-contain rounded-xl bg-stone-900"
              />
            )}

            {/* The author's own words - a database value, never translated. */}
            {openStory.caption && (
              <p className="text-sm text-stone-800 leading-relaxed whitespace-pre-wrap">
                {openStory.caption}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-3 text-3xs text-stone-500">
              <span>
                {hoursLeft(openStory.expires_at) < 1
                  ? t('social.stories.expiringSoon')
                  : t('social.stories.expiresIn', {
                      hours: hoursLeft(openStory.expires_at),
                    })}
              </span>

              {/* Only the author is sent a view count, so this is absent - not
                  zero - for everybody else. */}
              {openStory.is_mine && (
                <ViewCount storyId={openStory.id} />
              )}

              <button
                type="button"
                onClick={() => {
                  const id = openGroup?.author?.user_id;
                  close();
                  if (id) onOpenProfile(id);
                }}
                className="text-brand-700 font-semibold hover:underline"
              >
                {t('social.profile.title')}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
};

/**
 * How many colleagues watched this story.
 *
 * Fetched rather than taken from the strip, because the grouped list
 * deliberately does not carry a view count: `GET /social/stories/{id}` is where
 * the server decides whether the caller is the author and may be told.
 */
const ViewCount: React.FC<{ storyId: number }> = ({ storyId }) => {
  const { t } = useT();
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    SmartHRApi.getSocialStory(storyId)
      .then((story) => {
        if (!cancelled) setCount(story.view_count);
      })
      .catch(() => {
        if (!cancelled) setCount(null);
      });

    return () => {
      cancelled = true;
    };
  }, [storyId]);

  if (count === null) return null;

  return (
    <span className="inline-flex items-center gap-1">
      <Eye className="w-3 h-3" />
      {t('social.stories.viewCount', { count })}
    </span>
  );
};
