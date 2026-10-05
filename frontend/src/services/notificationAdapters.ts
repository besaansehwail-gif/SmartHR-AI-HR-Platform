import { NotificationRecord, SystemNotification } from '../types';
import { ManagerNotificationItem } from '../mock/managerData';
import { EmployeeNotificationItem } from '../mock/employeeData';
import { documentLocale, formatDateTime } from '../i18n/format';

/**
 * Adapters between the PostgreSQL `notifications` row and the three UI shapes
 * the existing pages render.
 *
 * The database stores: id, user_id, title, message, type (nullable free text),
 * is_read, created_at. Every UI shape is a subset of that plus optional
 * navigation hints (linkPage / actionType / targetPage), which have no column
 * and are therefore left undefined rather than invented.
 */

/**
 * `created_at` is a naive ISO timestamp; render it in the selected language.
 *
 * These adapters are plain functions, not components, so the locale is read
 * from `<html lang>` - which `LocaleProvider` owns - rather than from context.
 */
export const formatNotificationTimestamp = (value: string): string => {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return formatDateTime(parsed, documentLocale());
};

const normalizeType = (type: string | null): string =>
  (type ?? '').trim().toLowerCase();

// ---------- SystemNotification (top-nav bell + HR page) ----------

const SYSTEM_TYPES: SystemNotification['type'][] = [
  'info',
  'success',
  'warning',
  'alert',
];

export const SYSTEM_NOTIFICATION_TYPES = SYSTEM_TYPES;

const toSystemType = (type: string | null): SystemNotification['type'] => {
  const value = normalizeType(type);

  if ((SYSTEM_TYPES as string[]).includes(value)) {
    return value as SystemNotification['type'];
  }

  // Map the operational categories the other pages use onto a severity.
  switch (value) {
    case 'approval':
    case 'leave':
    case 'attendance':
      return 'warning';
    case 'performance':
    case 'training':
      return 'info';
    case 'error':
    case 'critical':
      return 'alert';
    case 'completed':
    case 'done':
      return 'success';
    default:
      return 'info';
  }
};

export const toSystemNotification = (
  record: NotificationRecord
): SystemNotification => ({
  id: String(record.id),
  title: record.title,
  message: record.message,
  timestamp: formatNotificationTimestamp(record.created_at),
  read: record.is_read,
  type: toSystemType(record.type),
});

// ---------- ManagerNotificationItem ----------

const MANAGER_TYPES: ManagerNotificationItem['type'][] = [
  'approval',
  'attendance',
  'leave',
  'performance',
  'training',
];

export const MANAGER_NOTIFICATION_TYPES = MANAGER_TYPES;

const toManagerType = (type: string | null): ManagerNotificationItem['type'] => {
  const value = normalizeType(type);

  if ((MANAGER_TYPES as string[]).includes(value)) {
    return value as ManagerNotificationItem['type'];
  }

  return 'approval';
};

export const toManagerNotification = (
  record: NotificationRecord
): ManagerNotificationItem => ({
  id: String(record.id),
  type: toManagerType(record.type),
  title: record.title,
  message: record.message,
  timestamp: formatNotificationTimestamp(record.created_at),
  read: record.is_read,
});

// ---------- EmployeeNotificationItem ----------

const EMPLOYEE_TYPES: EmployeeNotificationItem['type'][] = [
  'leave',
  'attendance',
  'training',
  'performance',
  'company',
];

export const EMPLOYEE_NOTIFICATION_TYPES = EMPLOYEE_TYPES;

const toEmployeeType = (
  type: string | null
): EmployeeNotificationItem['type'] => {
  const value = normalizeType(type);

  if ((EMPLOYEE_TYPES as string[]).includes(value)) {
    return value as EmployeeNotificationItem['type'];
  }

  return 'company';
};

export const toEmployeeNotification = (
  record: NotificationRecord
): EmployeeNotificationItem => ({
  id: String(record.id),
  type: toEmployeeType(record.type),
  title: record.title,
  message: record.message,
  timestamp: formatNotificationTimestamp(record.created_at),
  read: record.is_read,
});
