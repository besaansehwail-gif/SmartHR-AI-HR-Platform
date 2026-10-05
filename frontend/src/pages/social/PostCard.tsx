import React, { useEffect, useState } from 'react';
import {
  Heart,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Trash2,
  Send,
  Building2,
  Clock,
} from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { Textarea } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { useT, formatRelativeTime } from '../../i18n';
import { AuthedImage } from '../../components/ui/AuthedImage';
import { SmartHRApi } from '../../services/api';
import { SocialComment, SocialPost } from '../../types';
import { SocialAvatar, PersonLine } from './SocialBits';

/**
 * One post, with its likes and its comments.
 *
 * **The counts come from the server, not from arithmetic here.** Every like,
 * unlike and comment re-reads the post from the response the API returns, so a
 * second tab, a duplicate request or a failed write can never leave a number on
 * screen that the database does not agree with. `POST /like` is idempotent -
 * UNIQUE (post_id, user_id) - so a double click is one like, not two.
 *
 * Edit and delete are offered only on your own post, and that is not what
 * enforces it: `post_for_author()` puts the caller in the query, so somebody
 * else's post is a 404 whatever this component renders.
 */

interface PostCardProps {
  post: SocialPost;
  onChanged: (post: SocialPost) => void;
  onDeleted: (postId: number) => void;
  onOpenProfile: (userId: number) => void;
}

export const PostCard: React.FC<PostCardProps> = ({
  post,
  onChanged,
  onDeleted,
  onOpenProfile,
}) => {
  const { t, locale } = useT();
  const { showToast } = useToast();

  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.content);

  const [showComments, setShowComments] = useState(false);
  const [comments, setComments] = useState<SocialComment[] | null>(null);
  const [commentDraft, setCommentDraft] = useState('');
  const [commentBusy, setCommentBusy] = useState(false);

  const fail = (error: unknown) =>
    showToast(t('social.post.actionFailed'), {
      message: error instanceof Error ? error.message : undefined,
      type: 'error',
    });

  const toggleLike = async () => {
    setBusy(true);
    try {
      const updated = post.liked_by_me
        ? await SmartHRApi.unlikeSocialPost(post.id)
        : await SmartHRApi.likeSocialPost(post.id);
      onChanged(updated);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  const loadComments = async () => {
    try {
      const data = await SmartHRApi.getSocialComments(post.id);
      setComments(data.comments);
    } catch {
      setComments([]);
      showToast(t('social.comments.loadError'), { type: 'error' });
    }
  };

  useEffect(() => {
    if (showComments && comments === null) loadComments();
  }, [showComments]);

  const submitComment = async () => {
    if (!commentDraft.trim()) return;

    setCommentBusy(true);
    try {
      const added = await SmartHRApi.addSocialComment(post.id, commentDraft);

      // Held comments are visible to their author only, so say so rather
      // than letting them wonder why nobody replied.
      if (added.pending_review) {
        showToast(t('social.pending.commentToast'), {
          message: t('social.pending.notice'),
          type: 'info',
        });
      }

      setCommentDraft('');
      await loadComments();
      // Re-read the post so the comment count is the server's, not ours + 1.
      onChanged(await SmartHRApi.getSocialPost(post.id));
    } catch (error) {
      fail(error);
    } finally {
      setCommentBusy(false);
    }
  };

  const removeComment = async (commentId: number) => {
    try {
      await SmartHRApi.deleteSocialComment(commentId);
      showToast(t('social.comments.deleted'), { type: 'success' });
      await loadComments();
      onChanged(await SmartHRApi.getSocialPost(post.id));
    } catch (error) {
      fail(error);
    }
  };

  const saveEdit = async () => {
    if (!draft.trim()) return;

    setBusy(true);
    try {
      onChanged(await SmartHRApi.updateSocialPost(post.id, draft));
      setEditing(false);
      showToast(t('social.post.updated'), { type: 'success' });
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(t('social.post.deleteConfirm'))) return;

    setBusy(true);
    try {
      await SmartHRApi.deleteSocialPost(post.id);
      showToast(t('social.post.deleted'), { type: 'success' });
      onDeleted(post.id);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="bg-white rounded-2xl border border-stone-200/80 shadow-card hover:shadow-card-hover transition-shadow duration-200 overflow-hidden">
      {/* --- Author ------------------------------------------------------- */}
      {/* Only ever true on the viewer's own content - the backend sets
          `pending_review` from the author's own id, so a colleague's payload
          cannot carry it. The author is told the status and nothing else. */}
      {post.pending_review && (
        <div className="flex items-start gap-2 px-4 pt-3.5 pb-0.5">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-1 text-3xs font-bold text-amber-800">
            <Clock className="w-3 h-3" aria-hidden="true" />
            {t('social.pending.badge')}
          </span>
          <p className="text-3xs text-stone-500 leading-relaxed pt-1">
            {t('social.pending.notice')}
          </p>
        </div>
      )}

      <header className="flex items-start justify-between gap-3 p-4 pb-3">
        <PersonLine
          person={post.author}
          onOpen={onOpenProfile}
          meta={
            <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <time dateTime={post.created_at}>
                {formatRelativeTime(post.created_at, locale)}
              </time>
              {post.edited_at && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{t('social.post.edited')}</span>
                </>
              )}
              {post.audience === 'department' && post.author?.department_name && (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="inline-flex items-center gap-1">
                    <Building2 className="w-3 h-3" />
                    {t('social.post.toDepartment', {
                      department: post.author.department_name,
                    })}
                  </span>
                </>
              )}
            </span>
          }
        />

        {post.is_mine && (
          <div className="relative shrink-0">
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              aria-label={t('social.post.edit')}
              aria-expanded={menuOpen}
              className="w-8 h-8 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-sand-100 flex items-center justify-center transition-colors"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>

            {menuOpen && (
              <>
                {/* Click-away layer rather than a document listener: it is one
                    element and it disappears with the menu. */}
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setMenuOpen(false)}
                  aria-hidden="true"
                />
                <div className="absolute end-0 top-9 z-20 w-44 rounded-xl border border-stone-200 bg-white shadow-pop py-1 animate-in fade-in slide-in-from-top-2">
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setDraft(post.content);
                      setEditing(true);
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-2xs font-semibold text-stone-700 hover:bg-sand-50 text-start"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                    {t('social.post.edit')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      remove();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-2xs font-semibold text-red-700 hover:bg-red-50 text-start"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {t('social.post.delete')}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </header>

      {/* --- Content ------------------------------------------------------ */}
      <div className="px-4 pb-3">
        {editing ? (
          <div className="space-y-2">
            <Textarea
              rows={4}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                size="sm"
                onClick={saveEdit}
                isLoading={busy}
              >
                {t('social.post.saveEdit')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing(false);
                  setDraft(post.content);
                }}
              >
                {t('action.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          /* The author's own words, in the language they chose. A database
             value: shown exactly as written, never translated. */
          <p className="text-sm text-stone-800 leading-relaxed whitespace-pre-wrap break-words">
            {post.content}
          </p>
        )}
      </div>

      {/* Through AuthedImage, because /social/media is behind require_staff
          and a bare <img src> sends no token - the tag's own request comes
          back 401, which is why post images never appeared. The guard is
          unchanged; only the transport is. */}
      {post.image_url && !editing && (
        <AuthedImage
          src={post.image_url}
          alt={t('social.post.imageAlt', { name: post.author?.name ?? '' })}
          className="w-full max-h-[28rem] object-cover bg-sand-100 border-y border-stone-100"
          fallback={
            <div className="w-full h-40 bg-sand-100 border-y border-stone-100" />
          }
        />
      )}

      {/* --- Counts ------------------------------------------------------- */}
      {(post.like_count > 0 || post.comment_count > 0) && (
        <div className="px-4 pt-3 pb-1 flex items-center gap-3 text-3xs text-stone-500">
          {post.like_count > 0 && (
            <span className="inline-flex items-center gap-1">
              <Heart className="w-3 h-3 fill-brand-400 text-brand-400" />
              {t('social.post.likeCount', { count: post.like_count })}
            </span>
          )}
          {post.comment_count > 0 && (
            <button
              type="button"
              onClick={() => setShowComments(true)}
              className="hover:text-stone-800 hover:underline"
            >
              {t('social.post.commentCount', { count: post.comment_count })}
            </button>
          )}
        </div>
      )}

      {/* --- Actions ------------------------------------------------------ */}
      <div className="px-2 py-1.5 mt-2 border-t border-stone-100 flex items-center gap-1">
        <button
          type="button"
          onClick={toggleLike}
          disabled={busy}
          aria-pressed={post.liked_by_me}
          className={`flex-1 h-10 rounded-xl text-2xs font-bold inline-flex items-center justify-center gap-1.5 transition-colors disabled:opacity-60 ${
            post.liked_by_me
              ? 'text-brand-700 bg-brand-50 hover:bg-brand-100'
              : 'text-stone-600 hover:bg-sand-100'
          }`}
        >
          <Heart
            className={`w-4 h-4 ${post.liked_by_me ? 'fill-brand-500 text-brand-500' : ''}`}
          />
          {post.liked_by_me ? t('social.post.liked') : t('social.post.like')}
        </button>

        <button
          type="button"
          onClick={() => setShowComments((open) => !open)}
          aria-expanded={showComments}
          className="flex-1 h-10 rounded-xl text-2xs font-bold text-stone-600 hover:bg-sand-100 inline-flex items-center justify-center gap-1.5 transition-colors"
        >
          <MessageCircle className="w-4 h-4" />
          {t('social.post.comment')}
        </button>
      </div>

      {/* --- Comments ----------------------------------------------------- */}
      {showComments && (
        <div className="px-4 pb-4 pt-1 border-t border-stone-100 bg-sand-50/60 space-y-3">
          {comments === null ? (
            <div className="space-y-2 pt-3">
              <span className="block h-3 w-1/3 rounded skeleton" />
              <span className="block h-3 w-2/3 rounded skeleton" />
            </div>
          ) : comments.length === 0 ? (
            <p className="pt-3 text-2xs text-stone-400">{t('social.comments.empty')}</p>
          ) : (
            <ul className="pt-3 space-y-3">
              {comments.map((comment) => (
                <li key={comment.id} className="flex items-start gap-2.5">
                  <button
                    type="button"
                    onClick={() =>
                      comment.author && onOpenProfile(comment.author.user_id)
                    }
                    className="rounded-full shrink-0"
                  >
                    <SocialAvatar person={comment.author} size="xs" />
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="rounded-xl rounded-ss-sm bg-white border border-stone-200/80 px-3 py-2">
                      <p className="text-3xs font-bold text-stone-800 truncate">
                        {comment.author?.name}
                        {comment.pending_review && (
                          <span className="ms-2 inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-3xs font-bold text-amber-800 align-middle">
                            <Clock className="w-2.5 h-2.5" aria-hidden="true" />
                            {t('social.pending.badge')}
                          </span>
                        )}
                      </p>
                      <p className="text-2xs text-stone-700 leading-relaxed whitespace-pre-wrap break-words mt-0.5">
                        {comment.content}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 mt-1 px-1">
                      <time
                        dateTime={comment.created_at}
                        className="text-3xs text-stone-400"
                      >
                        {formatRelativeTime(comment.created_at, locale)}
                      </time>
                      {comment.is_mine && (
                        <button
                          type="button"
                          onClick={() => removeComment(comment.id)}
                          className="text-3xs font-semibold text-stone-400 hover:text-red-600"
                        >
                          {t('social.comments.delete')}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-start gap-2 pt-1">
            <Textarea
              rows={1}
              value={commentDraft}
              placeholder={t('social.comments.placeholder')}
              onChange={(event) => setCommentDraft(event.target.value)}
              onKeyDown={(event) => {
                // Enter sends, Shift+Enter makes a new line - what a comment
                // box is expected to do.
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  submitComment();
                }
              }}
              className="flex-1"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={submitComment}
              isLoading={commentBusy}
              disabled={!commentDraft.trim()}
              aria-label={t('social.comments.send')}
            >
              <Send className="w-3.5 h-3.5" data-flip-rtl />
            </Button>
          </div>
        </div>
      )}
    </article>
  );
};
