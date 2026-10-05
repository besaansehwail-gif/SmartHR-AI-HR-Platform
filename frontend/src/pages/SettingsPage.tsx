import React, { useState, useEffect } from 'react';
import {
  Settings as SettingsIcon,
  Building2,
  ShieldCheck,
  Bell,
  Briefcase,
  Server,
  Save,
  RotateCcw,
  CheckCircle2,
  ExternalLink,
  Globe,
  Mail,
  Lock,
  Clock,
  Laptop,
  Check,
  Radio,
  Zap,
} from 'lucide-react';
import { AppSettings } from '../types';
import { initialSettings } from '../mock/settings';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Card, CardHeader } from '../components/ui/Card';
import { Input, Select } from '../components/ui/Input';
import { useToast } from '../components/ui/Toast';
import { useT } from '../i18n';

const SETTINGS_STORAGE_KEY = 'smarthr_app_settings';

export const SettingsPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();
  const [activeTab, setActiveTab] = useState<
    'general' | 'company' | 'security' | 'notifications' | 'workmode' | 'system'
  >('general');

  const [settings, setSettings] = useState<AppSettings>(initialSettings);
  const [isSaving, setIsSaving] = useState(false);
  const [isTestingFastApi, setIsTestingFastApi] = useState(false);
  const [fastApiStatus, setFastApiStatus] = useState<'idle' | 'connected' | 'mocked'>('mocked');

  // There is no `settings` table in PostgreSQL and no /settings endpoint, so
  // this screen keeps configuration in the browser. `initialSettings` supplies
  // the default shape; anything previously saved on this device wins.
  useEffect(() => {
    try {
      const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (stored) {
        setSettings({ ...initialSettings, ...(JSON.parse(stored) as Partial<AppSettings>) });
      }
    } catch {
      // Corrupt or unavailable storage: fall back to the defaults already set.
    }
  }, []);

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsSaving(true);
    try {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
      showToast(t('settings.saved'), {
        message: t('settings.savedMessage'),
        type: 'success',
      });
    } catch (err) {
      showToast(t('settings.saveFailed'), {
        message:
          err instanceof Error ? err.message : t('settings.storageUnavailable'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestFastApiConnection = () => {
    setIsTestingFastApi(true);
    setTimeout(() => {
      setIsTestingFastApi(false);
      setFastApiStatus('connected');
      showToast(t('settings.api.testedTitle'), {
        message: t('settings.api.testedMessage', { url: settings.fastApiBaseUrl }),
        type: 'success',
      });
    }, 800);
  };

  const tabs = [
    { id: 'general', label: t('settings.tab.general'), icon: SettingsIcon },
    { id: 'company', label: t('settings.tab.company'), icon: Building2 },
    { id: 'security', label: t('settings.tab.security'), icon: ShieldCheck },
    { id: 'notifications', label: t('settings.tab.notifications'), icon: Bell },
    { id: 'workmode', label: t('settings.tab.workmode'), icon: Laptop },
    { id: 'system', label: t('settings.tab.system'), icon: Server },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('settings.title')}
        subtitle={t('settings.subtitle')}
        badge={
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-brand-50 text-brand-700 border border-brand-200">
            {t('settings.tenant')}
          </span>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            isLoading={isSaving}
            onClick={() => handleSave()}
            leftIcon={<Save className="w-4 h-4" />}
          >
            {t('action.saveChanges')}
          </Button>
        }
      />

      {/* Settings Navigation Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto border-b border-stone-200 pb-1 scrollbar-none">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-3.5 py-2.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
                isActive
                  ? 'bg-brand-100/70 text-brand-900 shadow-2xs font-bold'
                  : 'text-stone-500 hover:text-stone-900 hover:bg-stone-100'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-brand-700' : 'text-stone-400'}`} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Panels */}
      <div className="space-y-6">
        {/* 1. GENERAL TAB */}
        {activeTab === 'general' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.localization.title')}
                  subtitle={t('settings.localization.subtitle')}
                />
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Select
                      label={t('settings.field.language')}
                      value={settings.language}
                      onChange={(e) => setSettings({ ...settings, language: e.target.value })}
                      options={[
                        { label: t('settings.lang.enUS'), value: 'en-US' },
                        { label: t('settings.lang.enGB'), value: 'en-GB' },
                        { label: t('settings.lang.frFR'), value: 'fr-FR' },
                        { label: t('settings.lang.deDE'), value: 'de-DE' },
                        { label: t('settings.lang.jaJP'), value: 'ja-JP' },
                      ]}
                    />
                    <Select
                      label={t('settings.field.timezone')}
                      value={settings.timeZone}
                      onChange={(e) => setSettings({ ...settings, timeZone: e.target.value })}
                      options={[
                        { label: t('settings.tz.la'), value: 'America/Los_Angeles' },
                        { label: t('settings.tz.ny'), value: 'America/New_York' },
                        { label: t('settings.tz.london'), value: 'Europe/London' },
                        { label: t('settings.tz.tokyo'), value: 'Asia/Tokyo' },
                      ]}
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Select
                      label={t('settings.field.dateFormat')}
                      value={settings.dateFormat}
                      onChange={(e) => setSettings({ ...settings, dateFormat: e.target.value })}
                      options={[
                        { label: 'YYYY-MM-DD (ISO 8601)', value: 'YYYY-MM-DD' },
                        { label: 'MM/DD/YYYY (US Standard)', value: 'MM/DD/YYYY' },
                        { label: 'DD/MM/YYYY (UK/Europe)', value: 'DD/MM/YYYY' },
                      ]}
                    />
                    <Select
                      label={t('settings.field.currency')}
                      value={settings.currency}
                      onChange={(e) => setSettings({ ...settings, currency: e.target.value })}
                      options={[
                        { label: 'USD ($)', value: 'USD' },
                        { label: 'EUR (€)', value: 'EUR' },
                        { label: 'GBP (£)', value: 'GBP' },
                        { label: 'JPY (¥)', value: 'JPY' },
                      ]}
                    />
                  </div>
                </div>
              </Card>

              <Card>
                <CardHeader
                  title={t('settings.compliance.title')}
                  subtitle={t('settings.compliance.subtitle')}
                />
                <div className="space-y-4 text-xs">
                  <div className="flex items-center justify-between p-3.5 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-800">{t('settings.compliance.auditRetention')}</p>
                      <p className="text-stone-500 mt-0.5">{t('settings.compliance.auditRetentionDesc')}</p>
                    </div>
                    <span className="text-2xs font-bold px-2 py-1 bg-emerald-100 text-emerald-800 rounded-md">
                      {t('settings.compliance.enabled')}
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3.5 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-800">{t('settings.compliance.gdpr')}</p>
                      <p className="text-stone-500 mt-0.5">{t('settings.compliance.gdprDesc')}</p>
                    </div>
                    <span className="text-2xs font-bold px-2 py-1 bg-emerald-100 text-emerald-800 rounded-md">
                      {t('settings.compliance.compliant')}
                    </span>
                  </div>
                </div>
              </Card>
            </div>

            {/* Quick Summary Card */}
            <div className="space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.brand.title')}
                  subtitle={t('settings.brand.subtitle')}
                />
                <div className="space-y-3 text-xs">
                  <div className="p-4 rounded-xl bg-brand-50 border border-brand-200/70 text-stone-900">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-md bg-brand-700 flex items-center justify-center font-black text-white text-xs">
                        S
                      </div>
                      <span className="font-bold text-sm tracking-tight text-stone-900">SmartHR</span>
                    </div>
                    <p className="text-brand-700 text-3xs italic mt-1 font-medium">"People • Intelligence • Growth"</p>
                    <p className="text-stone-600 text-2xs mt-3 leading-relaxed">
                      {t('settings.brand.tagline')}
                    </p>
                  </div>

                  <div className="pt-2">
                    <span className="text-3xs text-stone-400 font-bold uppercase">
                      {t('settings.brand.palette')}
                    </span>
                    <div className="flex items-center gap-2 mt-2">
                      <div className="w-7 h-7 rounded-lg bg-white border border-stone-300 shadow-2xs" title={t('settings.brand.swatchSidebar')} />
                      <div className="w-7 h-7 rounded-lg bg-[#A44820] shadow-2xs" title={t('settings.brand.swatchPrimary')} />
                      <div className="w-7 h-7 rounded-lg bg-[#FEE1C7] shadow-2xs" title={t('settings.brand.swatchSoft')} />
                      <div className="w-7 h-7 rounded-lg bg-[#F8FAFC] border border-stone-200 shadow-2xs" title={t('settings.brand.swatchCanvas')} />
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* 2. COMPANY TAB */}
        {activeTab === 'company' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.company.title')}
                  subtitle={t('settings.company.subtitle')}
                />
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Input
                      label={t('settings.company.legalName')}
                      value={settings.companyName}
                      onChange={(e) => setSettings({ ...settings, companyName: e.target.value })}
                    />
                    <Input
                      label={t('settings.company.tax')}
                      value="XX-XXXXXXX-99"
                      disabled
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Input
                      label={t('settings.company.website')}
                      value={settings.companyWebsite}
                      onChange={(e) => setSettings({ ...settings, companyWebsite: e.target.value })}
                      leftIcon={<Globe className="w-4 h-4" />}
                    />
                    <Input
                      label={t('settings.company.hrEmail')}
                      type="email"
                      value={settings.supportEmail}
                      onChange={(e) => setSettings({ ...settings, supportEmail: e.target.value })}
                      leftIcon={<Mail className="w-4 h-4" />}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-stone-700 mb-1.5">
                      {t('settings.company.address')}
                    </label>
                    <textarea
                      rows={2}
                      value={settings.companyAddress}
                      onChange={(e) => setSettings({ ...settings, companyAddress: e.target.value })}
                      className="w-full rounded-lg border border-stone-300 p-3 text-xs text-stone-900 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-100"
                    />
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.offices.title')}
                  subtitle={t('settings.offices.subtitle')}
                />
                <div className="space-y-2.5 text-xs text-stone-600">
                  <div className="p-3 bg-stone-50 rounded-lg border border-stone-200">
                    <p className="font-bold text-stone-900">{t('settings.offices.sf')}</p>
                    <p className="text-2xs text-stone-500">{t('settings.offices.sfAddress')}</p>
                    <span className="inline-block mt-1 text-3xs font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
                      {t('settings.offices.primary')}
                    </span>
                  </div>

                  <div className="p-3 bg-stone-50 rounded-lg border border-stone-200">
                    <p className="font-bold text-stone-900">{t('settings.offices.ny')}</p>
                    <p className="text-2xs text-stone-500">{t('settings.offices.nyAddress')}</p>
                    <span className="inline-block mt-1 text-3xs font-bold text-brand-700 bg-brand-50 px-1.5 py-0.5 rounded">
                      {t('settings.offices.satellite')}
                    </span>
                  </div>

                  <div className="p-3 bg-stone-50 rounded-lg border border-stone-200">
                    <p className="font-bold text-stone-900">{t('settings.offices.london')}</p>
                    <p className="text-2xs text-stone-500">{t('settings.offices.londonAddress')}</p>
                    <span className="inline-block mt-1 text-3xs font-bold text-brand-700 bg-brand-50 px-1.5 py-0.5 rounded">
                      {t('settings.offices.international')}
                    </span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* 3. USERS & SECURITY TAB */}
        {activeTab === 'security' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.auth.title')}
                  subtitle={t('settings.auth.subtitle')}
                />
                <div className="space-y-4">
                  {/* MFA Toggle */}
                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.auth.mfa')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.auth.mfaDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSettings({ ...settings, requireMfa: !settings.requireMfa })}
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.requireMfa ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.requireMfa ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>

                  {/* SSO Toggle */}
                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.auth.sso')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.auth.ssoDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSettings({ ...settings, enableSso: !settings.enableSso })}
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.enableSso ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.enableSso ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>

                  {/* Session Timeout */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                    <Select
                      label={t('settings.auth.sessionTimeout')}
                      value={settings.sessionTimeoutMinutes.toString()}
                      onChange={(e) =>
                        setSettings({ ...settings, sessionTimeoutMinutes: parseInt(e.target.value) })
                      }
                      options={[
                        { label: t('settings.auth.min15'), value: '15' },
                        { label: t('settings.auth.min30'), value: '30' },
                        { label: t('settings.auth.min60'), value: '60' },
                        { label: t('settings.auth.min120'), value: '120' },
                      ]}
                    />

                    <Select
                      label={t('settings.auth.passwordPolicy')}
                      value={settings.passwordPolicy}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          passwordPolicy: e.target.value as any,
                        })
                      }
                      options={[
                        { label: t('settings.auth.pwStandard'), value: 'Standard' },
                        { label: t('settings.auth.pwStrict'), value: 'Strict' },
                        { label: t('settings.auth.pwEnterprise'), value: 'Enterprise' },
                      ]}
                    />
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.posture.title')}
                  subtitle={t('settings.posture.subtitle')}
                />
                <div className="space-y-3 text-xs">
                  <div className="flex items-center gap-2 text-emerald-700 font-semibold">
                    <ShieldCheck className="w-4 h-4" />
                    <span>{t('settings.posture.zeroTrust')}</span>
                  </div>
                  <p className="text-stone-500 text-2xs leading-relaxed">
                    {t('settings.posture.zeroTrustDesc')}
                  </p>
                  <div className="pt-2 border-t border-stone-100">
                    <span className="text-3xs text-stone-400 font-bold uppercase">
                      {t('settings.posture.activeSessions')}
                    </span>
                    <p className="font-bold text-stone-900 text-sm mt-0.5">
                      {t('settings.posture.concurrent')}
                    </p>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* 4. NOTIFICATIONS TAB */}
        {activeTab === 'notifications' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.dispatch.title')}
                  subtitle={t('settings.dispatch.subtitle')}
                />
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.dispatch.email')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.dispatch.emailDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setSettings({ ...settings, emailNotifications: !settings.emailNotifications })
                      }
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.emailNotifications ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.emailNotifications ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>

                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.dispatch.slack')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">
                        {t('settings.dispatch.slackDesc')}{' '}
                        <code className="text-brand-700">#hr-announcements</code>.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setSettings({ ...settings, slackNotifications: !settings.slackNotifications })
                      }
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.slackNotifications ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.slackNotifications ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>

                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.dispatch.digest')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.dispatch.digestDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setSettings({ ...settings, weeklyDigest: !settings.weeklyDigest })
                      }
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.weeklyDigest ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.weeklyDigest ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.channel.title')}
                  subtitle={t('settings.channel.subtitle')}
                />
                <div className="space-y-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-stone-600">{t('settings.channel.emailGateway')}</span>
                    <span className="font-bold text-emerald-600">{t('settings.channel.operational')}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-600">{t('settings.channel.slackWebhooks')}</span>
                    <span className="font-bold text-emerald-600">{t('settings.channel.active')}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-600">{t('settings.channel.inAppBanner')}</span>
                    <span className="font-bold text-emerald-600">{t('settings.channel.healthy')}</span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* 5. WORK MODE & HOURS TAB */}
        {activeTab === 'workmode' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.work.title')}
                  subtitle={t('settings.work.subtitle')}
                />
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Input
                      label={t('settings.work.dailyHours')}
                      type="number"
                      value={settings.standardHoursPerDay}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          standardHoursPerDay: parseFloat(e.target.value) || 8,
                        })
                      }
                    />
                    <Input
                      label={t('settings.work.hybridMin')}
                      type="number"
                      value={settings.hybridMinDaysInOffice}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          hybridMinDaysInOffice: parseInt(e.target.value) || 2,
                        })
                      }
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Input
                      label={t('settings.work.coreStart')}
                      value={settings.coreHoursStart}
                      onChange={(e) => setSettings({ ...settings, coreHoursStart: e.target.value })}
                      leftIcon={<Clock className="w-4 h-4" />}
                    />
                    <Input
                      label={t('settings.work.coreEnd')}
                      value={settings.coreHoursEnd}
                      onChange={(e) => setSettings({ ...settings, coreHoursEnd: e.target.value })}
                      leftIcon={<Clock className="w-4 h-4" />}
                    />
                  </div>

                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.work.override')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.work.overrideDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setSettings({
                          ...settings,
                          allowWorkModeOverride: !settings.allowWorkModeOverride,
                        })
                      }
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.allowWorkModeOverride ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.allowWorkModeOverride ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.policy.title')}
                  subtitle={t('settings.policy.subtitle')}
                />
                <div className="space-y-3 text-xs">
                  <div className="p-3 bg-brand-50 rounded-lg border border-brand-100">
                    <p className="font-bold text-brand-900">{t('settings.policy.hybridDefault')}</p>
                    <p className="text-2xs text-brand-700 mt-1">{t('settings.policy.hybridDesc')}</p>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* 6. SYSTEM & FASTAPI TAB */}
        {activeTab === 'system' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              {/* FastAPI Integration Configuration Card */}
              <Card className="border-brand-200 shadow-sm">
                <CardHeader
                  title={
                    <div className="flex items-center gap-2">
                      <Zap className="w-5 h-5 text-brand-600" />
                      <span>{t('settings.api.title')}</span>
                    </div>
                  }
                  subtitle={t('settings.api.subtitle')}
                  action={
                    <Button
                      variant="purple-soft"
                      size="sm"
                      isLoading={isTestingFastApi}
                      onClick={handleTestFastApiConnection}
                    >
                      {t('settings.api.test')}
                    </Button>
                  }
                />

                <div className="space-y-4">
                  <div>
                    <Input
                      label={t('settings.api.baseUrl')}
                      value={settings.fastApiBaseUrl}
                      onChange={(e) => setSettings({ ...settings, fastApiBaseUrl: e.target.value })}
                      placeholder="https://api.example.com/api/v1"
                      helperText={t('settings.api.helper')}
                    />
                  </div>

                  {/* API Connection Banner */}
                  <div
                    className={`p-4 rounded-xl border flex items-start gap-3.5 transition-all ${
                      fastApiStatus === 'connected'
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                        : 'bg-brand-50/70 border-brand-200 text-brand-900'
                    }`}
                  >
                    <CheckCircle2
                      className={`w-5 h-5 shrink-0 mt-0.5 ${
                        fastApiStatus === 'connected' ? 'text-emerald-600' : 'text-brand-600'
                      }`}
                    />
                    <div className="space-y-1 text-xs">
                      <p className="font-bold">
                        {fastApiStatus === 'connected'
                          ? t('settings.api.verified')
                          : t('settings.api.ready')}
                      </p>
                      <p className="leading-relaxed opacity-90">
                        {fastApiStatus === 'connected'
                          ? t('settings.api.verifiedDesc', { url: settings.fastApiBaseUrl })
                          : t('settings.api.readyDesc')}
                      </p>
                    </div>
                  </div>

                  {/* Endpoint specification blueprint */}
                  <div>
                    <span className="text-3xs font-bold text-stone-400 uppercase tracking-wider block mb-2">
                      {t('settings.api.contract')}
                    </span>
                    <div className="rounded-xl border border-stone-200 overflow-hidden bg-stone-50 text-xs">
                      <div className="divide-y divide-stone-200 font-mono text-2xs">
                        <div className="p-2.5 flex items-center justify-between">
                          <span className="font-bold text-brand-700">GET /api/v1/users</span>
                          <span className="text-stone-400">{t('settings.api.listUsers')}</span>
                        </div>
                        <div className="p-2.5 flex items-center justify-between">
                          <span className="font-bold text-emerald-700">POST /api/v1/users</span>
                          <span className="text-stone-400">{t('settings.api.createUser')}</span>
                        </div>
                        <div className="p-2.5 flex items-center justify-between">
                          <span className="font-bold text-brand-700">GET /api/v1/departments</span>
                          <span className="text-stone-400">{t('settings.api.listDepartments')}</span>
                        </div>
                        <div className="p-2.5 flex items-center justify-between">
                          <span className="font-bold text-amber-700">PUT /api/v1/roles/{'{role}'}/permissions</span>
                          <span className="text-stone-400">{t('settings.api.updateRbac')}</span>
                        </div>
                        <div className="p-2.5 flex items-center justify-between">
                          <span className="font-bold text-brand-700">GET /api/v1/audit-logs</span>
                          <span className="text-stone-400">{t('settings.api.auditLedger')}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Maintenance & System State */}
              <Card>
                <CardHeader
                  title={t('settings.maintenance.title')}
                  subtitle={t('settings.maintenance.subtitle')}
                />
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.maintenance.mode')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.maintenance.modeDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setSettings({ ...settings, maintenanceMode: !settings.maintenanceMode })
                      }
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.maintenanceMode ? 'bg-amber-600' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.maintenanceMode ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>

                  <div className="flex items-center justify-between p-4 bg-stone-50 rounded-xl border border-stone-200">
                    <div>
                      <p className="font-bold text-stone-900 text-xs">{t('settings.maintenance.telemetry')}</p>
                      <p className="text-2xs text-stone-500 mt-0.5">{t('settings.maintenance.telemetryDesc')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setSettings({
                          ...settings,
                          telemetryEnabled: !settings.telemetryEnabled,
                        })
                      }
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        settings.telemetryEnabled ? 'bg-brand-700' : 'bg-stone-300'
                      }`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white transition-transform absolute top-1 ${
                          settings.telemetryEnabled ? 'end-1' : 'start-1'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader
                  title={t('settings.runtime.title')}
                  subtitle={t('settings.runtime.subtitle')}
                />
                <div className="space-y-2.5 text-xs text-stone-600">
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">{t('settings.runtime.frontend')}</span>
                    <span className="font-bold text-stone-900 font-mono">v1.2.0-rc</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">{t('settings.runtime.backend')}</span>
                    <span className="font-bold text-brand-700 font-mono">FastAPIRestClient</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">{t('settings.runtime.node')}</span>
                    <span className="font-mono text-emerald-600 font-bold">production</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">{t('settings.runtime.tenant')}</span>
                    <span className="font-mono text-stone-700">smarthr-tenant-01</span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
