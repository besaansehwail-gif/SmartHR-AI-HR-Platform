import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  Info,
  Clock,
  Trash2,
  Check,
  Filter,
  Calendar,
  UserCheck,
  ShieldAlert,
  ArrowRight,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import { toSystemNotification } from '../../services/notificationAdapters';
import { SystemNotification } from '../../types';
import { PageId } from '../../components/layout/Sidebar';
import { useT } from '../../i18n';

export interface HRNotificationsPageProps {
  onNavigate: (page: PageId) => void;
  onSelectEmployee?: (empId: string) => void;
}

export const HRNotificationsPage: React.FC<HRNotificationsPageProps> = ({
  onNavigate,
  onSelectEmployee,
}) => {
  const { t } = useT();
  const { showToast } = useToast();
  const [notifications, setNotifications] = useState<SystemNotification[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // HR sees the whole notifications table; the backend restricts scope=all
  // to Admin and HR roles.
  const loadNotifications = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await SmartHRApi.getNotifications('all');
      setNotifications(data.map(toSystemNotification));
    } catch (error) {
      showToast(t('notif.loadFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
      setNotifications([]);
    } finally {
      setIsLoading(false);
    }
  }, [showToast, t]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'warning' | 'info' | 'success' | 'alert'>('ALL');
  const [unreadOnly, setUnreadOnly] = useState(false);

  const filteredNotifications = useMemo(() => {
    return notifications.filter((notif) => {
      const matchesType = typeFilter === 'ALL' || notif.type === typeFilter;
      const matchesUnread = !unreadOnly || !notif.read;
      return matchesType && matchesUnread;
    });
  }, [notifications, typeFilter, unreadOnly]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleMarkAsRead = async (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );

    try {
      await SmartHRApi.setNotificationRead(Number(id), true);
    } catch {
      loadNotifications();
    }
  };

  const handleMarkAllRead = async () => {
    const unread = notifications.filter((n) => !n.read);
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));

    try {
      // scope=all can include other users' rows, so each is marked directly.
      await Promise.all(
        unread.map((n) => SmartHRApi.setNotificationRead(Number(n.id), true))
      );
      showToast(t('hr.notif.allReadTitle'), {
        message: t('hr.notif.allReadMessage'),
        type: 'info',
      });
    } catch (error) {
      loadNotifications();
      showToast(t('notif.updateFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    }
  };

  // There is no DELETE endpoint for notifications, so dismissing marks the
  // row read in PostgreSQL and hides it from this stream.
  const handleDeleteNotification = async (id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));

    try {
      await SmartHRApi.setNotificationRead(Number(id), true);
      showToast(t('hr.notif.dismissedTitle'), {
        message: t('hr.notif.dismissedMessage'),
        type: 'info',
      });
    } catch {
      loadNotifications();
    }
  };

  const handleActionClick = (notif: SystemNotification) => {
    handleMarkAsRead(notif.id);
    if (notif.linkPage) {
      if (notif.linkPage === 'hr-employee-360' && onSelectEmployee) {
        onSelectEmployee('EMP-0109');
      }
      onNavigate(notif.linkPage as PageId);
    }
  };

  const getNotificationIcon = (type: SystemNotification['type']) => {
    switch (type) {
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-amber-600" />;
      case 'alert':
        return <ShieldAlert className="w-4 h-4 text-rose-600" />;
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
      case 'info':
      default:
        return <Info className="w-4 h-4 text-sky-600" />;
    }
  };

  const getNotificationBg = (type: SystemNotification['type'], isRead: boolean) => {
    if (isRead) return 'bg-white border-stone-100 opacity-80';
    switch (type) {
      case 'warning':
        return 'bg-amber-50/40 border-amber-200/80';
      case 'alert':
        return 'bg-rose-50/40 border-rose-200/80';
      case 'success':
        return 'bg-emerald-50/40 border-emerald-200/80';
      case 'info':
      default:
        return 'bg-brand-50/30 border-brand-200/80';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('hr.notif.title')}
        subtitle={t('hr.notif.subtitle')}
        badge={
          <Badge variant={unreadCount > 0 ? 'warning' : 'neutral'} dot={unreadCount > 0}>
            {unreadCount} {t('hr.notif.unreadAlerts')}
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Check className="w-3.5 h-3.5" />}
              onClick={handleMarkAllRead}
              disabled={unreadCount === 0}
            >
              {t('hr.notif.markAllRead')}
            </Button>
          </div>
        }
      />

      {/* Filter and Switch Bar */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="flex items-center gap-1.5 flex-wrap">
            {(['ALL', 'warning', 'info', 'success', 'alert'] as const).map((kind) => (
              <button
                key={kind}
                onClick={() => setTypeFilter(kind)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-colors ${
                  typeFilter === kind
                    ? 'bg-brand-700 text-white shadow-xs'
                    : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                }`}
              >
                {kind === 'ALL' ? t('hr.notif.allAlerts') : t(`notif.type.${kind}`)}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs font-semibold text-stone-700 cursor-pointer self-end sm:self-center">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              className="rounded border-stone-300 text-brand-600 focus:ring-brand-600"
            />
            {t('hr.notif.showUnreadOnly')} ({unreadCount})
          </label>
        </div>
      </Card>

      {/* Notifications List */}
      <div className="space-y-3">
        {isLoading ? (
          <Card>
            <div className="py-12 text-center text-stone-400">
              <Bell className="w-8 h-8 mx-auto mb-2 text-stone-300 animate-pulse" />
              <p className="font-semibold text-stone-600">{t('hr.notif.loading')}</p>
            </div>
          </Card>
        ) : filteredNotifications.length === 0 ? (
          <Card>
            <div className="py-12 text-center text-stone-400">
              <Bell className="w-8 h-8 mx-auto mb-2 text-stone-300" />
              <p className="font-semibold text-stone-600">{t('notif.emptyFilter')}</p>
              <p className="text-2xs text-stone-400 mt-1">{t('hr.notif.allClear')}</p>
            </div>
          </Card>
        ) : (
          filteredNotifications.map((notif) => (
            <div
              key={notif.id}
              className={`p-4 rounded-xl border transition-all ${getNotificationBg(
                notif.type,
                notif.read
              )} flex flex-col sm:flex-row sm:items-center justify-between gap-4 group`}
            >
              <div className="flex items-start gap-3.5 min-w-0">
                <div className="p-2 rounded-xl bg-white shadow-2xs border border-stone-200/80 shrink-0 mt-0.5">
                  {getNotificationIcon(notif.type)}
                </div>

                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-bold text-stone-900 text-xs tracking-tight">
                      {notif.title}
                    </h4>
                    {!notif.read && (
                      <span className="w-2 h-2 rounded-full bg-brand-600 ring-2 ring-brand-100" />
                    )}
                  </div>
                  <p className="text-xs text-stone-600 leading-relaxed">
                    {notif.message}
                  </p>
                  <span className="text-3xs font-medium text-stone-400 flex items-center gap-1 pt-0.5">
                    <Clock className="w-3 h-3" />
                    {notif.timestamp}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                {notif.linkPage && (
                  <Button
                    variant="purple-soft"
                    size="sm"
                    className="text-xs"
                    onClick={() => handleActionClick(notif)}
                    rightIcon={<ArrowRight className="w-3.5 h-3.5" data-flip-rtl />}
                  >
                    {t('hr.notif.resolve')}
                  </Button>
                )}

                {!notif.read && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-stone-500 hover:text-stone-800"
                    title={t('hr.notif.markRead')}
                    onClick={() => handleMarkAsRead(notif.id)}
                  >
                    <Check className="w-4 h-4" />
                  </Button>
                )}

                <Button
                  variant="ghost"
                  size="sm"
                  className="text-stone-400 hover:text-rose-600"
                  title={t('hr.notif.dismiss')}
                  onClick={() => handleDeleteNotification(notif.id)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
