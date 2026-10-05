import React from 'react';
import { MessageSquare, UserPlus, Check, Clock, X } from 'lucide-react';

import { Button } from '../../components/ui/Button';
import { useT } from '../../i18n';
import { SocialConnectionInfo, SocialPerson } from '../../types';

/**
 * The small pieces every Social Hub screen shares: the avatar, the person
 * line, and the Connect / Message pair.
 *
 * They live in one file because they are used by all four pages and are a few
 * lines each; splitting them into four modules would be more imports than
 * code. Everything here is presentational - no fetching, no state that
 * outlives a render - so a page owns its data and these only draw it.
 */

// ---------------------------------------------------------------------------
// Avatar
// ---------------------------------------------------------------------------

const AVATAR_SIZES = {
  xs: 'w-7 h-7 text-3xs',
  sm: 'w-9 h-9 text-2xs',
  md: 'w-11 h-11 text-xs',
  lg: 'w-16 h-16 text-base',
  xl: 'w-24 h-24 sm:w-28 sm:h-28 text-2xl',
} as const;

export interface SocialAvatarProps {
  person: SocialPerson | null;
  size?: keyof typeof AVATAR_SIZES;
  /** A warm ring, used for an unseen story and for the profile header. */
  ring?: 'none' | 'brand' | 'muted';
  className?: string;
}

/**
 * Somebody's photograph, or their initials.
 *
 * Initials are the honest fallback rather than a generated cartoon: SmartHR
 * knows this person's name and does not know what they look like, and the rest
 * of the app (the sidebar, the account menu) already draws them this way.
 */
export const SocialAvatar: React.FC<SocialAvatarProps> = ({
  person,
  size = 'md',
  ring = 'none',
  className = '',
}) => {
  const { t } = useT();

  const ringClass =
    ring === 'brand'
      ? 'ring-2 ring-brand-400 ring-offset-2 ring-offset-white'
      : ring === 'muted'
        ? 'ring-2 ring-stone-200 ring-offset-2 ring-offset-white'
        : '';

  const base = `${AVATAR_SIZES[size]} ${ringClass} rounded-full shrink-0 object-cover ${className}`;

  if (person?.avatar_url) {
    return (
      <img
        src={person.avatar_url}
        alt={t('social.profile.avatarAlt', { name: person.name })}
        loading="lazy"
        decoding="async"
        className={`${base} bg-sand-100`}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className={`${base} bg-brand-100 text-brand-800 font-extrabold flex items-center justify-center`}
    >
      {person?.initials ?? '--'}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Person line
// ---------------------------------------------------------------------------

export interface PersonLineProps {
  person: SocialPerson | null;
  /** A timestamp or any other meta, rendered after the role line. */
  meta?: React.ReactNode;
  onOpen?: (userId: number) => void;
  size?: 'sm' | 'md';
}

/**
 * Name, then what they do.
 *
 * The second line prefers the person's own headline, falls back to their
 * position and department, and says so plainly when SmartHR has neither -
 * an account with no `employees` row is a legitimate state, not a blank.
 */
export const PersonLine: React.FC<PersonLineProps> = ({
  person,
  meta,
  onOpen,
  size = 'md',
}) => {
  const { t } = useT();

  if (!person) return null;

  const role =
    person.headline ||
    [person.position_title, person.department_name].filter(Boolean).join(' · ') ||
    t('social.people.noPosition');

  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <button
        type="button"
        onClick={onOpen ? () => onOpen(person.user_id) : undefined}
        disabled={!onOpen}
        className={`rounded-full ${onOpen ? '' : 'cursor-default'}`}
      >
        <SocialAvatar person={person} size={size === 'sm' ? 'sm' : 'md'} />
      </button>

      <div className="min-w-0">
        <button
          type="button"
          onClick={onOpen ? () => onOpen(person.user_id) : undefined}
          disabled={!onOpen}
          className={`block max-w-full text-start text-xs font-bold text-stone-900 truncate rounded ${
            onOpen ? 'hover:text-brand-700 hover:underline' : 'cursor-default'
          }`}
        >
          {/* A database value: shown exactly as stored, never translated. */}
          {person.name}
        </button>
        <p className="text-3xs text-stone-500 truncate">{role}</p>
        {meta && <div className="text-3xs text-stone-400 mt-0.5">{meta}</div>}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Connect / Message
// ---------------------------------------------------------------------------

export interface ConnectActionsProps {
  person: SocialPerson;
  connection: SocialConnectionInfo;
  busy?: boolean;
  size?: 'xs' | 'sm';
  onConnect: (userId: number) => void;
  onAccept: (connectionId: number) => void;
  onReject: (connectionId: number) => void;
  onDisconnect: (connectionId: number, name: string) => void;
  onMessage: (userId: number) => void;
}

/**
 * What you can do about a colleague, given where you stand with them.
 *
 * Every state renders a different control rather than one button with a
 * changing label, because "Connect", "Request sent" and "Accept / Decline" are
 * three genuinely different affordances. The direction matters: an incoming
 * request is answerable, an outgoing one is only waiting.
 */
export const ConnectActions: React.FC<ConnectActionsProps> = ({
  person,
  connection,
  busy = false,
  size = 'sm',
  onConnect,
  onAccept,
  onReject,
  onDisconnect,
  onMessage,
}) => {
  const { t } = useT();

  if (connection.state === 'self') return null;

  const message = (
    <Button
      variant="outline"
      size={size}
      leftIcon={<MessageSquare className="w-3.5 h-3.5" />}
      onClick={() => onMessage(person.user_id)}
      disabled={busy}
    >
      {t('social.connect.message')}
    </Button>
  );

  if (connection.state === 'connected') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {message}
        <Button
          variant="ghost"
          size={size}
          onClick={() =>
            connection.connection_id &&
            onDisconnect(connection.connection_id, person.name)
          }
          disabled={busy}
        >
          {t('social.connect.disconnect')}
        </Button>
      </div>
    );
  }

  if (connection.state === 'pending_incoming') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size={size}
          leftIcon={<Check className="w-3.5 h-3.5" />}
          onClick={() =>
            connection.connection_id && onAccept(connection.connection_id)
          }
          disabled={busy}
        >
          {t('social.connect.accept')}
        </Button>
        <Button
          variant="ghost"
          size={size}
          leftIcon={<X className="w-3.5 h-3.5" />}
          onClick={() =>
            connection.connection_id && onReject(connection.connection_id)
          }
          disabled={busy}
        >
          {t('social.connect.reject')}
        </Button>
      </div>
    );
  }

  if (connection.state === 'pending_outgoing') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size={size}
          leftIcon={<Clock className="w-3.5 h-3.5" />}
          disabled
        >
          {t('social.connect.pending')}
        </Button>
        {message}
      </div>
    );
  }

  // 'none' and 'rejected' both offer Connect: a declined request is not a
  // permanent block, and the other person is never told it was declined.
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="primary"
        size={size}
        leftIcon={<UserPlus className="w-3.5 h-3.5" />}
        onClick={() => onConnect(person.user_id)}
        disabled={busy}
      >
        {t('social.connect.connect')}
      </Button>
      {message}
    </div>
  );
};
