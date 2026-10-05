import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  CheckCircle2,
  Clock,
  Calendar,
  AlertTriangle,
  Star,
  GraduationCap,
  ArrowRight,
  Filter,
  Eye,
  Check,
  ShieldAlert,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import { ManagerNotificationItem } from '../../mock/managerData';
import { SmartHRApi } from '../../services/api';
import { toManagerNotification } from '../../services/notificationAdapters';
import { useT } from '../../i18n';

export interface ManagerNotificationsPageProps {
  onNavigate: (page: PageId) => void;
}

export const ManagerNotificationsPage: React.FC<ManagerNotificationsPageProps> = ({
  onNavigate,
}) => {
  const { t } = useT();
  const { showToast } = useToast();
  const [notifications, setNotifications] = useState<ManagerNotificationItem[]>(
    []
  );

  const loadNotifications = useCallback(async () => {
    try {
      const data = await SmartHRApi.getNotifications();
      setNotifications(data.map(toManagerNotification));
    } catch (error) {
      showToast(t('notif.loadFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
      setNotifications([]);
    }
  }, [showToast, t]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);
  const [activeFilter, setActiveFilter] = useState<
    'ALL' | 'UNREAD' | 'approval' | 'attendance' | 'leave' | 'performance' | 'training'
  >('ALL');

  const unreadCount = notifications.filter((n) => !n.read).length;

  const filteredNotifications = notifications.filter((item) => {
    if (activeFilter === 'ALL') return true;
    if (activeFilter === 'UNREAD') return !item.read;
    return item.type === activeFilter;
  });

  const handleToggleRead = async (id: string) => {
    const current = notifications.find((n) => n.id === id);
    const nextRead = current ? !current.read : true;

    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: nextRead } : n))
    );

    try {
      await SmartHRApi.setNotificationRead(Number(id), nextRead);
    } catch {
      loadNotifications();
    }
  };

  const handleMarkAllRead = async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));

    try {
      await SmartHRApi.markAllNotificationsRead();
      showToast(t('notif.updated'), {
        message: t('mgr.notif.allRead'),
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

  const handleAction = (item: ManagerNotificationItem) => {
    // Mark as read (persisted) and route to the corresponding page
    setNotifications((prev) =>
      prev.map((n) => (n.id === item.id ? { ...n, read: true } : n))
    );

    SmartHRApi.setNotificationRead(Number(item.id), true).catch(() => {
      loadNotifications();
    });

    if (item.linkPage) {
      onNavigate(item.linkPage as PageId);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('mgr.notif.title')}
        subtitle={t('mgr.notif.subtitle')}
        badge={
          <Badge variant={unreadCount > 0 ? 'warning' : 'neutral'} dot={unreadCount > 0}>
            {unreadCount} {t('mgr.notif.unreadAlerts')}
          </Badge>
        }
        actions={
          unreadCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
              onClick={handleMarkAllRead}
            >
              {t('notif.markAllRead')}
            </Button>
          )
        }
      />

      {/* Filter Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        <button
          onClick={() => setActiveFilter('ALL')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
            activeFilter === 'ALL'
              ? 'bg-brand-700 text-white'
              : 'bg-white text-stone-600 border border-stone-200 hover:bg-stone-50'
          }`}
        >
          {t('mgr.notif.filterAll')} ({notifications.length})
        </button>
        <button
          onClick={() => setActiveFilter('UNREAD')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
            activeFilter === 'UNREAD'
              ? 'bg-brand-700 text-white'
              : 'bg-white text-stone-600 border border-stone-200 hover:bg-stone-50'
          }`}
        >
          {t('mgr.notif.filterUnread')} ({unreadCount})
        </button>
        <button
          onClick={() => setActiveFilter('leave')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
            activeFilter === 'leave'
              ? 'bg-brand-700 text-white'
              : 'bg-white text-stone-600 border border-stone-200 hover:bg-stone-50'
          }`}
        >
          {t('mgr.notif.cat.approval')}
        </button>
        <button
          onClick={() => setActiveFilter('attendance')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
            activeFilter === 'attendance'
              ? 'bg-brand-700 text-white'
              : 'bg-white text-stone-600 border border-stone-200 hover:bg-stone-50'
          }`}
        >
          {t('mgr.notif.cat.attendance')}
        </button>
        <button
          onClick={() => setActiveFilter('performance')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
            activeFilter === 'performance'
              ? 'bg-brand-700 text-white'
              : 'bg-white text-stone-600 border border-stone-200 hover:bg-stone-50'
          }`}
        >
          {t('mgr.notif.cat.performance')}
        </button>
        <button
          onClick={() => setActiveFilter('training')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
            activeFilter === 'training'
              ? 'bg-brand-700 text-white'
              : 'bg-white text-stone-600 border border-stone-200 hover:bg-stone-50'
          }`}
        >
          {t('mgr.notif.cat.training')}
        </button>
      </div>

      {/* Notifications List */}
      <Card noPadding>
        <div className="divide-y divide-stone-100">
          {filteredNotifications.length === 0 ? (
            <div className="py-12 text-center text-stone-400">
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
              <p className="font-semibold text-stone-600">{t('notif.emptyFilter')}</p>
            </div>
          ) : (
            filteredNotifications.map((notif) => {
              const isLeave = notif.type === 'leave' || notif.type === 'approval';
              const isAttendance = notif.type === 'attendance';
              const isPerformance = notif.type === 'performance';
              const isTraining = notif.type === 'training';

              return (
                <div
                  key={notif.id}
                  className={`p-4 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                    notif.read ? 'bg-white opacity-85' : 'bg-brand-50/25 font-semibold'
                  }`}
                >
                  <div className="flex items-start gap-3.5">
                    <div
                      className={`p-2.5 rounded-xl shrink-0 mt-0.5 ${
                        isLeave
                          ? 'bg-amber-100 text-amber-800'
                          : isAttendance
                          ? 'bg-rose-100 text-rose-800'
                          : isPerformance
                          ? 'bg-brand-100 text-brand-800'
                          : 'bg-emerald-100 text-emerald-800'
                      }`}
                    >
                      {isLeave ? (
                        <Calendar className="w-4 h-4" />
                      ) : isAttendance ? (
                        <Clock className="w-4 h-4" />
                      ) : isPerformance ? (
                        <Star className="w-4 h-4" />
                      ) : (
                        <GraduationCap className="w-4 h-4" />
                      )}
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <h4 className="text-xs font-bold text-stone-900">{notif.title}</h4>
                        {!notif.read && (
                          <span className="w-2 h-2 rounded-full bg-brand-600 shrink-0" />
                        )}
                        <span className="text-3xs uppercase font-bold text-stone-400 px-1.5 py-0.2 rounded bg-stone-100">
                          {t(`notif.type.${notif.type}`)}
                        </span>
                      </div>
                      <p className="text-2xs text-stone-600 leading-relaxed font-normal">
                        {notif.message}
                      </p>
                      <span className="text-3xs text-stone-400 block">{notif.timestamp}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-3xs text-stone-500 hover:text-stone-700"
                      onClick={() => handleToggleRead(notif.id)}
                    >
                      {notif.read ? t('notif.markUnread') : t('notif.markRead')}
                    </Button>

                    {notif.linkPage && (
                      <Button
                        variant="primary"
                        size="sm"
                        className="text-xs"
                        rightIcon={<ArrowRight className="w-3.5 h-3.5" data-flip-rtl />}
                        onClick={() => handleAction(notif)}
                      >
                        {t('mgr.notif.takeAction')}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>
    </div>
  );
};
