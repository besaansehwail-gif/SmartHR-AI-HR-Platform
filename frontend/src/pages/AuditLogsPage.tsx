import React, { useState, useEffect, useMemo } from 'react';
import {
  History,
  Search,
  Download,
  Activity,
  List,
  GitCommit,
} from 'lucide-react';
import { AuditActionType, AuditLogRecord } from '../types';
import { SmartHRApi } from '../services/api';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input, Select } from '../components/ui/Input';
import { ActionTypeBadge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';
import { EmptyState } from '../components/ui/EmptyState';
import { useT } from '../i18n';

/**
 * audit_logs stores six columns and nothing else:
 * (id, user_id, action, entity_type, entity_id, timestamp).
 *
 * The badge component renders the seven-value AuditActionType union, while the
 * database holds the finer-grained token the backend wrote. This maps one onto
 * the other so no display category has to be invented or stored.
 */
const ACTION_CATEGORY: Record<string, AuditActionType> = {
  CREATE: 'CREATE',
  ASSIGN: 'CREATE',
  UPDATE: 'UPDATE',
  STATUS_CHANGE: 'UPDATE',
  DELETE: 'DELETE',
  APPROVE: 'APPROVE',
  REJECT: 'APPROVE',
  LOGIN: 'LOGIN',
  LOGIN_FAILED: 'SECURITY',
  ACTIVATE: 'SECURITY',
  DEACTIVATE: 'SECURITY',
  EXPORT: 'EXPORT',
};

const categoryOf = (action: string): AuditActionType =>
  ACTION_CATEGORY[action] ?? 'SECURITY';

/** audit_logs.timestamp arrives as an ISO string; render it like a log line. */
const formatTimestamp = (value: string | null): string => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`
  );
};

const initials = (name: string): string =>
  name
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

/** entity_type + entity_id is the only pointer back to the affected record. */
const targetRecord = (log: AuditLogRecord): string =>
  log.entity_id === null ? '-' : `#${log.entity_id}`;

export const AuditLogsPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();
  const [logs, setLogs] = useState<AuditLogRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // View Mode: Table vs Timeline
  const [viewMode, setViewMode] = useState<'table' | 'timeline'>('table');

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [actionTypeFilter, setActionTypeFilter] = useState('all');
  const [entityFilter, setEntityFilter] = useState('all');
  const [dateRangeFilter, setDateRangeFilter] = useState('all');

  // Detail Modal
  const [selectedLog, setSelectedLog] = useState<AuditLogRecord | null>(null);

  const loadLogs = async () => {
    setIsLoading(true);
    try {
      const data = await SmartHRApi.getAuditLogs();
      setLogs(data);
    } catch (err) {
      showToast(t('audit.errorLoading'), {
        message: err instanceof Error ? err.message : t('audit.unreachable'),
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  // Filter options come from the rows actually present, so the pickers never
  // offer a category the trail has no events for.
  const actionOptions = useMemo(() => {
    const present = new Set(logs.map((log) => categoryOf(log.action)));
    return [
      { label: t('audit.allActions'), value: 'all' },
      ...Array.from(present)
        .sort()
        .map((category) => ({ label: category, value: category })),
    ];
  }, [logs]);

  const entityOptions = useMemo(() => {
    const present = new Set(
      logs.map((log) => log.entity_type).filter((value): value is string => !!value)
    );
    return [
      { label: t('audit.allEntities'), value: 'all' },
      ...Array.from(present)
        .sort()
        .map((entity) => ({ label: entity, value: entity })),
    ];
  }, [logs]);

  const filteredLogs = useMemo(() => {
    const now = Date.now();
    const windowMs: Record<string, number> = {
      today: 24 * 60 * 60 * 1000,
      '7days': 7 * 24 * 60 * 60 * 1000,
      '30days': 30 * 24 * 60 * 60 * 1000,
    };

    return logs.filter((log) => {
      const needle = searchQuery.toLowerCase();
      const matchesSearch =
        !searchQuery ||
        log.action.toLowerCase().includes(needle) ||
        log.description.toLowerCase().includes(needle) ||
        log.user.name.toLowerCase().includes(needle) ||
        (log.user.email ?? '').toLowerCase().includes(needle) ||
        (log.entity_type ?? '').toLowerCase().includes(needle) ||
        String(log.entity_id ?? '').includes(needle);

      const matchesAction =
        actionTypeFilter === 'all' || categoryOf(log.action) === actionTypeFilter;

      const matchesEntity = entityFilter === 'all' || log.entity_type === entityFilter;

      let matchesDate = true;
      if (dateRangeFilter !== 'all' && windowMs[dateRangeFilter]) {
        const stamp = log.timestamp ? new Date(log.timestamp).getTime() : NaN;
        matchesDate =
          !Number.isNaN(stamp) && now - stamp <= windowMs[dateRangeFilter];
      }

      return matchesSearch && matchesAction && matchesEntity && matchesDate;
    });
  }, [logs, searchQuery, actionTypeFilter, entityFilter, dateRangeFilter]);

  const resetFilters = () => {
    setSearchQuery('');
    setActionTypeFilter('all');
    setEntityFilter('all');
    setDateRangeFilter('all');
  };

  // Export CSV. Exporting the trail is itself an auditable event, and it is
  // the one action only the browser can observe, so it is recorded here.
  const handleExportCSV = async () => {
    const header = 'ID,Timestamp,UserID,User,Email,Role,Action,Category,EntityType,EntityID,Description';
    const rows = filteredLogs.map((l) =>
      [
        l.id,
        `"${formatTimestamp(l.timestamp)}"`,
        l.user_id ?? '',
        `"${l.user.name.replace(/"/g, '""')}"`,
        l.user.email ?? '',
        l.user.role ?? '',
        l.action,
        categoryOf(l.action),
        l.entity_type ?? '',
        l.entity_id ?? '',
        `"${l.description.replace(/"/g, '""')}"`,
      ].join(',')
    );

    const blob = new Blob([[header, ...rows].join('\n')], {
      type: 'text/csv;charset=utf-8;',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute(
      'download',
      `SmartHR_Audit_Trail_${new Date().toISOString().split('T')[0]}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showToast(t('audit.exported'), {
      message: `Downloaded ${filteredLogs.length} audit trail records.`,
      type: 'success',
    });

    try {
      await SmartHRApi.createAuditLog({ action: 'EXPORT', entity_type: 'AuditLog' });
      await loadLogs();
    } catch {
      // The download already succeeded; failing to record it must not look
      // like the export itself failed.
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('audit.title')}
        subtitle={t('audit.subtitle')}
        badge={
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-stone-100 text-stone-800 border border-stone-300">
            {logs.length} recorded events
          </span>
        }
        actions={
          <>
            <div className="flex items-center rounded-lg border border-stone-200 bg-white p-1">
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  viewMode === 'table' ? 'bg-brand-100 text-brand-700' : 'text-stone-500 hover:text-stone-900'
                }`}
                title={t('audit.tableView')}
              >
                <List className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t('audit.table')}</span>
              </button>
              <button
                onClick={() => setViewMode('timeline')}
                className={`p-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  viewMode === 'timeline' ? 'bg-brand-100 text-brand-700' : 'text-stone-500 hover:text-stone-900'
                }`}
                title={t('audit.timelineView')}
              >
                <GitCommit className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t('audit.timeline')}</span>
              </button>
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={handleExportCSV}
              leftIcon={<Download className="w-4 h-4" />}
            >
              {t('audit.export')}
            </Button>
          </>
        }
      />

      {/* Filter and Search Bar */}
      <Card padding="sm" className="bg-stone-50/60">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="w-full md:w-80">
            <Input
              type="text"
              placeholder={t('audit.search')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftIcon={<Search className="w-4 h-4" />}
            />
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <div className="w-36">
              <Select
                value={actionTypeFilter}
                onChange={(e) => setActionTypeFilter(e.target.value)}
                options={actionOptions}
              />
            </div>

            <div className="w-36">
              <Select
                value={entityFilter}
                onChange={(e) => setEntityFilter(e.target.value)}
                options={entityOptions}
              />
            </div>

            <div className="w-36">
              <Select
                value={dateRangeFilter}
                onChange={(e) => setDateRangeFilter(e.target.value)}
                options={[
                  { label: t('audit.allTime'), value: 'all' },
                  { label: t('audit.past24h'), value: 'today' },
                  { label: t('audit.past7d'), value: '7days' },
                  { label: t('audit.past30d'), value: '30days' },
                ]}
              />
            </div>

            {(searchQuery || actionTypeFilter !== 'all' || entityFilter !== 'all' || dateRangeFilter !== 'all') && (
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                {t('audit.reset')}
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Main View: Table or Timeline */}
      {isLoading ? (
        <Card padding="lg">
          <p className="text-sm text-stone-500 text-center py-8">{t('audit.loading')}</p>
        </Card>
      ) : filteredLogs.length === 0 ? (
        <EmptyState
          icon={<History className="w-6 h-6" />}
          title={logs.length === 0 ? t('audit.emptyNone') : t('audit.emptyFiltered')}
          description={
            logs.length === 0
              ? t('audit.emptyNoneHint')
              : t('audit.emptyFilteredHint')
          }
          actionLabel={logs.length === 0 ? undefined : t('audit.clearFilters')}
          onAction={logs.length === 0 ? undefined : resetFilters}
        />
      ) : viewMode === 'table' ? (
        <Card padding="none" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-start text-xs text-stone-600">
              <thead>
                <tr className="border-b border-stone-200 bg-stone-50/80 text-3xs font-bold text-stone-500 uppercase tracking-wider">
                  <th className="py-3 px-6">{t('audit.colTimestamp')}</th>
                  <th className="py-3 px-4">{t('audit.colActionType')}</th>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">{t('audit.colDescription')}</th>
                  <th className="py-3 px-4">{t('audit.colEntity')}</th>
                  <th className="py-3 px-4">{t('audit.colRecord')}</th>
                  <th className="py-3 px-6 text-end">{t('audit.colDetails')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 font-medium">
                {filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    onClick={() => setSelectedLog(log)}
                    className="hover:bg-brand-50/40 cursor-pointer transition-colors"
                  >
                    {/* Timestamp */}
                    <td className="py-3.5 px-6 font-mono text-2xs text-stone-500 whitespace-nowrap">
                      {formatTimestamp(log.timestamp)}
                    </td>

                    {/* Action Type */}
                    <td className="py-3.5 px-4">
                      <ActionTypeBadge type={categoryOf(log.action)} />
                    </td>

                    {/* User */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-brand-100 text-brand-700 font-bold text-3xs flex items-center justify-center">
                          {initials(log.user.name)}
                        </div>
                        <div>
                          <p className="font-bold text-stone-900 text-xs">{log.user.name}</p>
                          <p className="text-3xs text-stone-400">{log.user.role ?? t('audit.noRole')}</p>
                        </div>
                      </div>
                    </td>

                    {/* Activity */}
                    <td className="py-3.5 px-4">
                      <p className="font-semibold text-stone-900 text-xs">{log.action}</p>
                      <p className="text-2xs text-stone-500 truncate max-w-sm">{log.description}</p>
                    </td>

                    {/* Entity type */}
                    <td className="py-3.5 px-4">
                      <span className="font-mono text-2xs px-2 py-0.5 rounded bg-stone-100 text-stone-700 border border-stone-200">
                        {log.entity_type ?? '-'}
                      </span>
                    </td>

                    {/* Entity id */}
                    <td className="py-3.5 px-4 font-mono text-3xs text-stone-400 whitespace-nowrap">
                      {targetRecord(log)}
                    </td>

                    {/* Action button */}
                    <td className="py-3.5 px-6 text-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-brand-700 hover:text-brand-900 text-xs font-semibold"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedLog(log);
                        }}
                      >
                        {t('audit.inspect')}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        /* Timeline View */
        <div className="space-y-4">
          {filteredLogs.map((log) => (
            <div
              key={log.id}
              onClick={() => setSelectedLog(log)}
              className="bg-white p-5 rounded-xl border border-stone-200 shadow-2xs hover:shadow-md hover:border-brand-300 transition-all cursor-pointer flex items-start gap-4"
            >
              <div className="w-9 h-9 rounded-xl bg-brand-50 text-brand-700 border border-brand-100 flex items-center justify-center shrink-0 mt-0.5">
                <Activity className="w-4 h-4" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-stone-900 text-sm">{log.action}</span>
                    <ActionTypeBadge type={categoryOf(log.action)} />
                    <span className="text-2xs text-stone-400">•</span>
                    <span className="text-2xs font-semibold text-brand-700">
                      {log.user.name}
                      {log.user.role ? ` (${log.user.role})` : ''}
                    </span>
                  </div>
                  <span className="text-2xs font-mono text-stone-400 shrink-0">
                    {formatTimestamp(log.timestamp)}
                  </span>
                </div>

                <p className="text-xs text-stone-600 mt-1.5 leading-relaxed">{log.description}</p>

                <div className="mt-3 flex items-center gap-3 text-2xs text-stone-400 font-mono">
                  <span>
                    {t('audit.target')} <strong className="text-stone-700">{log.entity_type ?? '-'} {targetRecord(log)}</strong>
                  </span>
                  <span>•</span>
                  <span>Event #{log.id}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Log Detail Modal */}
      {selectedLog && (
        <Modal
          isOpen={!!selectedLog}
          onClose={() => setSelectedLog(null)}
          title={t('audit.inspection')}
          subtitle={`Event ID: ${selectedLog.id} • Registered ${formatTimestamp(selectedLog.timestamp)}`}
          size="lg"
          footer={
            <Button variant="outline" size="sm" onClick={() => setSelectedLog(null)}>
              {t('action.close')}
            </Button>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3.5 bg-stone-50 rounded-xl border border-stone-200">
              <div>
                <span className="text-3xs text-stone-400 uppercase font-bold">{t('audit.colActionType')}</span>
                <div className="mt-1"><ActionTypeBadge type={categoryOf(selectedLog.action)} /></div>
              </div>
              <div>
                <span className="text-3xs text-stone-400 uppercase font-bold">{t('audit.colEntity')}</span>
                <p className="text-xs font-bold text-stone-800 mt-1">{selectedLog.entity_type ?? '-'}</p>
              </div>
              <div>
                <span className="text-3xs text-stone-400 uppercase font-bold">{t('audit.colRecord')}</span>
                <p className="text-xs font-bold text-stone-800 mt-1">{targetRecord(selectedLog)}</p>
              </div>
              <div>
                <span className="text-3xs text-stone-400 uppercase font-bold">{t('audit.occurredAt')}</span>
                <p className="text-xs font-mono text-stone-600 mt-1 truncate">
                  {formatTimestamp(selectedLog.timestamp)}
                </p>
              </div>
            </div>

            <div>
              <span className="text-3xs text-stone-400 uppercase font-bold">{t('audit.operator')}</span>
              <div className="mt-1.5 p-3 bg-white rounded-lg border border-stone-200 flex items-center justify-between">
                <div>
                  <p className="font-bold text-stone-900">{selectedLog.user.name}</p>
                  <p className="text-2xs text-stone-500 font-mono">
                    {selectedLog.user.email ?? t('audit.noAccount')}
                  </p>
                </div>
                {selectedLog.user.role && (
                  <span className="text-2xs font-semibold px-2 py-0.5 rounded bg-brand-50 text-brand-700 border border-brand-200">
                    {selectedLog.user.role}
                  </span>
                )}
              </div>
            </div>

            <div>
              <span className="text-3xs text-stone-400 uppercase font-bold">{t('audit.summary')}</span>
              <p className="mt-1 text-sm font-semibold text-stone-900">{selectedLog.action}</p>
              <p className="text-xs text-stone-600 mt-1 leading-relaxed bg-stone-50 p-3 rounded-lg border border-stone-200">
                {selectedLog.description}
              </p>
            </div>

            <div>
              <span className="text-3xs text-stone-400 uppercase font-bold">
                {t('audit.storedRecord')}
              </span>
              <pre className="mt-1.5 p-3.5 rounded-lg bg-stone-50 text-stone-800 border border-stone-200 font-mono text-3xs overflow-x-auto leading-relaxed">
                {JSON.stringify(
                  {
                    id: selectedLog.id,
                    user_id: selectedLog.user_id,
                    action: selectedLog.action,
                    entity_type: selectedLog.entity_type,
                    entity_id: selectedLog.entity_id,
                    timestamp: selectedLog.timestamp,
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
