import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Info, Inbox, Search, UserCheck } from 'lucide-react';

import { Select } from '../../components/ui/Input';
import { ErrorState } from '../../components/ui/States';
import { useT } from '../../i18n';
import { SmartHRApi } from '../../services/api';
import { PageId } from '../../components/layout/Sidebar';
import {
  DepartmentRecord,
  SocialConnectionsResponse,
  SocialDirectoryPerson,
  SocialHubStatus,
  SocialPeopleResponse,
} from '../../types';
import { SocialAvatar, ConnectActions, PersonLine } from './SocialBits';
import { SocialEmpty, SocialHero, SocialSection } from './SocialShell';
import { useOpenConversation, useSocialActions } from './useSocialActions';

/**
 * People discovery: who else is here, and who is waiting on an answer.
 *
 * **It lists colleagues who have a SmartHR account**, which is a narrowing the
 * page states rather than hides. A connection request or a message needs
 * somebody who can sign in and answer it, so an `employees` row with no account
 * would be two buttons that can never complete - the same reasoning that makes
 * a training listing say `can_apply: false` instead of offering a button that
 * would fail.
 *
 * Nothing on a card is HR data. Name, position, department and headline are
 * all the server sends, and the endpoint has nothing else in it to leak. It is
 * deliberately **not** the HR Employees screen: no table, no row actions, no
 * record ids - this is a place to find a colleague, not to administer one.
 */

interface PeoplePageProps {
  onNavigate: (page: PageId) => void;
  onOpenProfile: (userId: number) => void;
  onOpenConversation: (conversationId: number) => void;
}

export const PeoplePage: React.FC<PeoplePageProps> = ({
  onNavigate,
  onOpenProfile,
  onOpenConversation,
}) => {
  const { t } = useT();

  const [query, setQuery] = useState('');
  const [departmentId, setDepartmentId] = useState<string>('');
  const [position, setPosition] = useState<string>('');
  const [people, setPeople] = useState<SocialPeopleResponse | null>(null);
  const [connections, setConnections] = useState<SocialConnectionsResponse | null>(
    null
  );
  const [status, setStatus] = useState<SocialHubStatus | null>(null);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [directory, mine] = await Promise.all([
        SmartHRApi.getSocialPeople({
          q: query,
          departmentId: departmentId ? Number(departmentId) : null,
        }),
        SmartHRApi.getSocialConnections(),
      ]);
      setPeople(directory);
      setConnections(mine);
    } catch (err) {
      setError(err instanceof Error ? err.message : undefined);
      setPeople(null);
    } finally {
      setLoading(false);
    }
  }, [query, departmentId]);

  useEffect(() => {
    // Debounced so typing a name is not one request per keystroke.
    const timer = window.setTimeout(load, 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    // The department filter needs the real list; /departments/ is open to all
    // staff roles, which is exactly this page's audience.
    SmartHRApi.getDepartments()
      .then(setDepartments)
      .catch(() => setDepartments([]));

    SmartHRApi.getSocialStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  const actions = useSocialActions(load);
  const openConversation = useOpenConversation(onOpenConversation);

  const incoming = connections?.incoming_requests ?? [];
  const connected = connections?.connections ?? [];
  const found = people?.people ?? [];

  /**
   * Job titles, taken from the people the directory returned.
   *
   * There is no positions parameter on `/social/people` and no endpoint that
   * answers "which titles exist among people with accounts", so this offers
   * exactly the titles present in the result and filters within it. A list
   * built from the `positions` table would offer choices that match nobody.
   */
  const positions = useMemo(() => {
    const titles = new Set<string>();
    found.forEach((p) => p.position_title && titles.add(p.position_title));
    return Array.from(titles).sort((a, b) => a.localeCompare(b));
  }, [found]);

  const results = useMemo(
    () => (position ? found.filter((p) => p.position_title === position) : found),
    [found, position]
  );

  const filtering = Boolean(query || departmentId || position);

  const card = (person: SocialDirectoryPerson) => (
    <li
      key={person.user_id}
      className="group bg-white rounded-2xl border border-stone-200/80 shadow-card hover:border-brand-200 hover:shadow-card-hover transition-all overflow-hidden flex flex-col"
    >
      {/* A warm band, not a photograph: SmartHR stores no cover image, and a
          stock picture would be decoration pretending to be somebody's. */}
      <div className="h-12 bg-gradient-to-r from-brand-100 via-brand-50 to-sand-100" />

      <div className="px-4 pb-4 -mt-7 flex flex-col flex-1">
        <button
          type="button"
          onClick={() => onOpenProfile(person.user_id)}
          className="flex flex-col items-center text-center gap-2 rounded-xl"
        >
          <SocialAvatar person={person} size="lg" ring="muted" />

          <span className="min-w-0 w-full">
            <span className="block text-xs font-extrabold text-stone-900 truncate group-hover:text-brand-700 transition-colors">
              {person.name}
            </span>
            <span className="block text-3xs text-stone-500 truncate mt-0.5">
              {person.headline ||
                person.position_title ||
                t('social.people.noPosition')}
            </span>
          </span>
        </button>

        <p className="mt-2 text-center">
          <span className="inline-block max-w-full truncate px-2.5 py-1 rounded-full bg-sand-100 border border-sand-200 text-[10px] font-bold text-brand-800">
            {person.department_name || t('social.people.noDepartment')}
          </span>
        </p>

        <div className="mt-auto pt-3.5 flex justify-center">
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
        </div>
      </div>
    </li>
  );

  return (
    <div className="space-y-5">
      <SocialHero
        title={t('social.people.title')}
        subtitle={t('social.people.subtitle')}
        me={status?.me ?? null}
        unread={status?.unread_notifications ?? 0}
        current="soc-people"
        onNavigate={onNavigate}
        toolbar={
          <div className="flex flex-col sm:flex-row sm:items-center gap-2.5">
            <div className="relative flex-1 min-w-0">
              <Search
                className="w-4 h-4 text-stone-400 absolute top-1/2 -translate-y-1/2 start-3"
                aria-hidden="true"
              />
              <input
                type="search"
                value={query}
                placeholder={t('social.people.search')}
                onChange={(event) => setQuery(event.target.value)}
                className="w-full h-10 ps-9 pe-3 rounded-xl border border-stone-200 bg-sand-50 text-xs text-stone-800 placeholder:text-stone-400 focus:bg-white focus:border-brand-300 focus:outline-none transition-colors"
              />
            </div>

            <Select
              value={departmentId}
              onChange={(event) => setDepartmentId(event.target.value)}
              className="sm:w-48"
              options={[
                { label: t('social.people.allDepartments'), value: '' },
                ...departments.map((d) => ({ label: d.name, value: String(d.id) })),
              ]}
            />

            <Select
              value={position}
              onChange={(event) => setPosition(event.target.value)}
              className="sm:w-48"
              options={[
                { label: t('social.people.allPositions'), value: '' },
                ...positions.map((title) => ({ label: title, value: title })),
              ]}
            />
          </div>
        }
      />

      {/* --- Requests waiting on me ------------------------------------- */}
      {incoming.length > 0 && (
        <SocialSection title={t('social.connect.requests')}>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {incoming.map((request) => (
              <li
                key={request.id}
                className="bg-white rounded-2xl border border-brand-100 bg-gradient-to-r from-brand-50/50 to-white p-4 flex flex-wrap items-center justify-between gap-3"
              >
                <PersonLine person={request.person} onOpen={onOpenProfile} />

                {request.person && (
                  <ConnectActions
                    person={request.person}
                    connection={{ state: 'pending_incoming', connection_id: request.id }}
                    busy={actions.busy}
                    size="xs"
                    onConnect={(id) => actions.connect(id)}
                    onAccept={actions.accept}
                    onReject={actions.reject}
                    onDisconnect={actions.disconnect}
                    onMessage={openConversation}
                  />
                )}
              </li>
            ))}
          </ul>
        </SocialSection>
      )}

      {/* --- My connections ---------------------------------------------- */}
      {connected.length > 0 && (
        <SocialSection
          title={t('social.connect.myConnections')}
          action={
            <span className="text-3xs text-stone-400 tabular-nums">
              {t('social.people.count', { count: connected.length })}
            </span>
          }
        >
          <ul className="flex gap-2.5 overflow-x-auto no-scrollbar pb-1">
            {connected.map((connection) => (
              <li
                key={connection.id}
                className="shrink-0 w-44 bg-white rounded-2xl border border-stone-200/80 p-3.5 text-center"
              >
                <button
                  type="button"
                  onClick={() =>
                    connection.person && onOpenProfile(connection.person.user_id)
                  }
                  className="flex flex-col items-center gap-2 w-full rounded-xl"
                >
                  <SocialAvatar person={connection.person} size="md" />
                  <span className="min-w-0 w-full">
                    <span className="block text-2xs font-bold text-stone-900 truncate">
                      {connection.person?.name ?? '—'}
                    </span>
                    <span className="block text-3xs text-stone-500 truncate">
                      {connection.person?.position_title ||
                        connection.person?.department_name ||
                        t('social.people.noPosition')}
                    </span>
                  </span>
                </button>

                <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700">
                  <UserCheck className="w-3 h-3" aria-hidden="true" />
                  {t('social.connect.connected')}
                </span>
              </li>
            ))}
          </ul>
        </SocialSection>
      )}

      {/* --- Directory --------------------------------------------------- */}
      <SocialSection
        title={t('social.people.directory')}
        action={
          people ? (
            <span className="text-3xs text-stone-400 tabular-nums">
              {t('social.people.count', { count: results.length })}
            </span>
          ) : undefined
        }
      >
        {error ? (
          <ErrorState message={error} onRetry={load} />
        ) : loading ? (
          <ul className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <li
                key={i}
                className="bg-white rounded-2xl border border-stone-200/80 overflow-hidden"
              >
                <span className="block h-12 skeleton" />
                <span className="flex flex-col items-center gap-2 px-4 pb-4 -mt-7">
                  <span className="w-16 h-16 rounded-full skeleton border-4 border-white" />
                  <span className="h-3 w-24 rounded skeleton" />
                  <span className="h-2.5 w-16 rounded skeleton" />
                </span>
              </li>
            ))}
          </ul>
        ) : results.length === 0 ? (
          <SocialEmpty
            icon={filtering ? <Search className="w-5 h-5" /> : <Inbox className="w-5 h-5" />}
            title={
              filtering
                ? t('social.people.empty.title')
                : t('social.people.none.title')
            }
            body={
              filtering ? t('social.people.empty.body') : t('social.people.none.body')
            }
            actionLabel={filtering ? t('social.people.clearFilters') : undefined}
            onAction={
              filtering
                ? () => {
                    setQuery('');
                    setDepartmentId('');
                    setPosition('');
                  }
                : undefined
            }
          />
        ) : (
          <ul className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4">
            {results.map(card)}
          </ul>
        )}
      </SocialSection>

      {/* Why the directory looks the way it does, said once at the bottom
          rather than implied by a short list. */}
      <p className="flex items-start gap-2 text-3xs text-stone-500 leading-relaxed">
        <Info className="w-3.5 h-3.5 shrink-0 mt-px" aria-hidden="true" />
        {t('social.people.accountsOnly')}
      </p>
    </div>
  );
};
