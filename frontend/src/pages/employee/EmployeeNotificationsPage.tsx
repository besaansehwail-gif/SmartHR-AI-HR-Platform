import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  CheckCircle2,
  Clock,
  BookOpen,
  Calendar,
  Building2,
  Star,
  CheckCheck,
  Filter,
  ArrowRight,
  Trash2,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import { EmployeeNotificationItem } from '../../mock/employeeData';
import { SmartHRApi } from '../../services/api';
import { toEmployeeNotification } from '../../services/notificationAdapters';
import { useT } from '../../i18n';

export interface EmployeeNotificationsPageProps {
  onNavigate?: (page: PageId) => void;
}

export const EmployeeNotificationsPage: React.FC<EmployeeNotificationsPageProps> = ({
  onNavigate,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [notifications, setNotifications] = useState<EmployeeNotificationItem[]>(
    []
  );

  const loadNotifications = useCallback(async () => {
    try {
      const data = await SmartHRApi.getNotifications();
      setNotifications(data.map(toEmployeeNotification));
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
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const categories = [
    { id: 'all', label: t('notif.type.all'), count: notifications.length },
    { id: 'leave', label: t('notif.type.leave'), count: notifications.filter((n) => n.type === 'leave').length },
    { id: 'attendance', label: t('notif.type.attendance'), count: notifications.filter((n) => n.type === 'attendance').length },
    { id: 'training', label: t('notif.type.training'), count: notifications.filter((n) => n.type === 'training').length },
    { id: 'performance', label: t('notif.type.performance'), count: notifications.filter((n) => n.type === 'performance').length },
    { id: 'company', label: t('notif.type.company'), count: notifications.filter((n) => n.type === 'company').length },
  ];

  const handleMarkAllRead = async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));

    try {
      await SmartHRApi.markAllNotificationsRead();
      showToast(t('notif.updated'), {
        message: t('emp.notif.allRead'),
        type: 'success',
      });
    } catch (error) {
      loadNotifications();
      showToast(t('notif.updateFailed'), {
        message: error instanceof Error ? error.message : t('error.unexpected'),
        type: 'error',
      });
    }
  };

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

  const filteredNotifications = notifications.filter((n) => {
    const matchesCategory = activeCategory === 'all' || n.type === activeCategory;
    const matchesUnread = !showUnreadOnly || !n.read;
    return matchesCategory && matchesUnread;
  });

  const getCategoryIcon = (type: string) => {
    switch (type) {
      case 'leave':
        return <Calendar className="w-4 h-4 text-brand-600" />;
      case 'attendance':
        return <Clock className="w-4 h-4 text-emerald-600" />;
      case 'training':
        return <BookOpen className="w-4 h-4 text-amber-500" />;
      case 'performance':
        return <Star className="w-4 h-4 text-brand-600" />;
      case 'company':
        return <Building2 className="w-4 h-4 text-sky-600" />;
      default:
        return <Bell className="w-4 h-4 text-stone-500" />;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.notif.title')}
        subtitle={t('emp.notif.subtitle')}
        breadcrumbs={[
          { label: t('workspace.employee'), href: '#' },
          { label: t('nav.emp-notifications'), active: true },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<CheckCheck className="w-4 h-4" />}
              onClick={handleMarkAllRead}
              disabled={unreadCount === 0}
            >
              {t('notif.markAllRead')}
            </Button>
          </div>
        }
      />

      {/* 1. Category Filter Pills */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5 p-1 bg-stone-100 rounded-xl">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                activeCategory === cat.id
                  ? 'bg-white text-brand-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              {cat.label} ({cat.count})
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-xs font-semibold text-stone-700 cursor-pointer">
          <input
            type="checkbox"
            checked={showUnreadOnly}
            onChange={(e) => setShowUnreadOnly(e.target.checked)}
            className="rounded text-brand-600 focus:ring-brand-500"
          />
          {t('emp.notif.showUnreadOnly')} ({unreadCount})
        </label>
      </div>

      {/* 2. Notifications List Card */}
      <Card
        title={t('emp.notif.feed')}
        subtitle={
          unreadCount > 1
            ? t('emp.notif.unreadCount', { count: unreadCount })
            : unreadCount === 1
              ? t('emp.notif.unreadCountOne')
              : t('emp.notif.allCaughtUp')
        }
        headerAction={
          <Badge variant={unreadCount > 0 ? 'purple' : 'neutral'} dot={unreadCount > 0}>
            {unreadCount} {t('notif.unread')}
          </Badge>
        }
      >
        {filteredNotifications.length === 0 ? (
          <div className="py-12 text-center text-stone-400 space-y-2">
            <Bell className="w-10 h-10 mx-auto text-stone-300" />
            <p className="text-xs font-semibold text-stone-600">{t('emp.notif.emptyCategory')}</p>
            <p className="text-2xs text-stone-400">{t('emp.notif.emptyHint')}</p>
          </div>
        ) : (
          <div className="space-y-3 pt-1">
            {filteredNotifications.map((notif) => (
              <div
                key={notif.id}
                className={`p-4 rounded-xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  !notif.read
                    ? 'bg-brand-50/40 border-brand-200 shadow-xs'
                    : 'bg-white border-stone-200/80 hover:bg-stone-50'
                }`}
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="p-2.5 rounded-xl bg-white border border-stone-200 shadow-xs shrink-0 mt-0.5">
                    {getCategoryIcon(notif.type)}
                  </div>

                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-stone-900">
                        {notif.title}
                      </span>
                      {!notif.read && (
                        <span className="w-2 h-2 rounded-full bg-brand-600 inline-block" />
                      )}
                      <span className="text-3xs font-extrabold uppercase px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                        {t(`notif.type.${notif.type}`)}
                      </span>
                      <span className="text-3xs text-stone-400">
                        {notif.timestamp}
                      </span>
                    </div>

                    <p className="text-2xs text-stone-600 leading-relaxed max-w-2xl font-normal">
                      {notif.message}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  {notif.actionText && notif.targetPage && onNavigate && (
                    <Button
                      variant="primary"
                      size="sm"
                      className="text-2xs"
                      rightIcon={<ArrowRight className="w-3 h-3" data-flip-rtl />}
                      onClick={() => onNavigate(notif.targetPage as PageId)}
                    >
                      {notif.actionText}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-2xs text-stone-500 hover:text-stone-800"
                    onClick={() => handleToggleRead(notif.id)}
                  >
                    {notif.read ? t('notif.markUnread') : t('notif.markRead')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
