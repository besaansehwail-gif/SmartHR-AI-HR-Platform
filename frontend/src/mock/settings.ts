import { AppSettings } from '../types';

export const initialSettings: AppSettings = {
  general: {
    platformName: 'SmartHR Enterprise',
    timezone: 'America/Los_Angeles (PST/PDT)',
    language: 'English (United States)',
    dateFormat: 'YYYY-MM-DD',
    fiscalYearStart: 'January 1',
  },
  company: {
    companyName: 'SmartHR Technologies Inc.',
    legalName: 'SmartHR Global Corporation',
    taxId: 'XX-XXXX-8921',
    website: 'https://smarthr.io',
    contactEmail: 'admin-operations@example.com',
    phone: '+1 (202) 555-0100',
    address: '500 Howard Street, Suite 1200',
    city: 'San Francisco, CA 94105',
    country: 'United States',
  },
  security: {
    sessionTimeoutMinutes: 30,
    enforce2FA: true,
    passwordExpirationDays: 90,
    ipWhitelistEnabled: false,
    ipWhitelist: '192.168.1.0/24, 10.0.0.0/16',
    singleSignOn: true,
    failedLoginLockout: 5,
  },
  notifications: {
    emailDigestFrequency: 'daily',
    notifyNewHires: true,
    notifyLeaveRequests: true,
    notifyComplianceAlerts: true,
    slackIntegration: true,
  },
  workMode: {
    defaultPolicy: 'Hybrid',
    coreHoursStart: '09:00',
    coreHoursEnd: '17:00',
    minInOfficeDays: 2,
    allowFlexibleHours: true,
  },
  system: {
    apiBaseUrl: 'https://api.example.com/api/v1',
    useMockData: true,
    enableDebugLogs: false,
    telemetryEnabled: true,
  },
};
