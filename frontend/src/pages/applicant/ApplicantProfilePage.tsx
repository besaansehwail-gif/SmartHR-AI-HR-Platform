import React, { useCallback, useEffect, useState } from 'react';
import { Save, User } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, Field } from '../../components/ui/Card';
import { Input, Textarea } from '../../components/ui/Input';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState, InfoPanel, LoadingState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { SmartHRApi } from '../../services/api';
import { ApplicantProfile } from '../../types';
import { useT } from '../../i18n';

/**
 * My Profile.
 *
 * The skills box is the important control on this page: it is the only source
 * of the skills used for matching, and it is typed by the applicant. The CV
 * analyser can *suggest* skills, but nothing it produces is stored until the
 * applicant saves it here - which is why a match score can never contain a
 * skill the person did not claim.
 *
 * Email is shown and not editable: it is the account identifier, and the
 * update endpoint does not accept it.
 */
export const ApplicantProfilePage: React.FC = () => {
  const { t } = useT();
  const [profile, setProfile] = useState<ApplicantProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    location: '',
    skills: '',
  });

  const { showToast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await SmartHRApi.getApplicantProfile();
      setProfile(data);
      setForm({
        first_name: data.first_name ?? '',
        last_name: data.last_name ?? '',
        phone: data.phone ?? '',
        location: data.location ?? '',
        skills: data.skills.join(', '),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('app.profile.failed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const updated = await SmartHRApi.updateApplicantProfile(form);
      setProfile(updated);
      setForm((prev) => ({ ...prev, skills: updated.skills.join(', ') }));
      showToast(t('app.profile.saved'), {
        message: `${updated.skills.length} skill(s) on your profile.`,
        type: 'success',
      });
    } catch (err) {
      showToast(t('app.profile.saveFailed'), {
        message: err instanceof Error ? err.message : t('app.profile.tryAgain'),
        type: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingState title={t('app.profile.loading')} />;
  if (error || !profile) return <ErrorState message={error ?? t('app.profile.noProfile')} onRetry={load} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('app.profile.title')}
        subtitle={t('app.profile.pageSubtitle')}
        icon={<User className="w-5 h-5" />}
        badge={
          <Badge variant={profile.completeness.percent === 100 ? 'success' : 'warning'}>
            {profile.completeness.percent}% complete
          </Badge>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card padding="md">
            <CardHeader
              title={t('app.profile.yourDetails')}
              subtitle={t('app.profile.yourDetailsHint')}
            />

            <form onSubmit={handleSave} className="space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input
                  label={t('app.profile.firstName')}
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  required
                />
                <Input
                  label={t('app.profile.lastName')}
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                />
                <Input
                  label={t('app.profile.phone')}
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder={t('ui.form.optional')}
                />
                <Input
                  label={t('app.profile.location')}
                  value={form.location}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder={t('ui.form.optional')}
                />
              </div>

              <Textarea
                label={t('app.profile.skills')}
                hint="Comma-separated, in your own words — for example: Python, SQL, Excel. These are the only skills used for matching."
                rows={3}
                value={form.skills}
                onChange={(e) => setForm({ ...form, skills: e.target.value })}
                placeholder={t('app.profile.skillsPlaceholder')}
              />

              <div className="flex items-center justify-between gap-3 pt-2 border-t border-stone-100">
                <p className="text-2xs text-stone-500">
                  Your email address ({profile.email}) is your sign-in and cannot be changed here.
                </p>
                <Button
                  type="submit"
                  variant="primary"
                  leftIcon={<Save className="w-4 h-4" />}
                  isLoading={saving}
                >
                  {t('app.profile.save')}
                </Button>
              </div>
            </form>
          </Card>
        </div>

        <div className="space-y-6">
          <Card padding="md">
            <CardHeader title={t('app.dashboard.profileCompleteness')} />
            <ul className="space-y-2">
              {Object.entries(profile.completeness.fields).map(([field, present]) => (
                <li key={field} className="flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold text-stone-700 capitalize">{field}</span>
                  <Badge variant={present ? 'success' : 'neutral'} size="sm">
                    {present ? t('app.profile.skillAdded') : t('app.profile.skillMissing')}
                  </Badge>
                </li>
              ))}
            </ul>
          </Card>

          <Card padding="md">
            <CardHeader title={t('app.profile.currentSkills')} />
            {profile.skills.length === 0 ? (
              <p className="text-xs text-stone-500 leading-relaxed">
                None listed yet. Without skills, SmartHR will show you the newest opportunities
                but will not claim to know which ones suit you.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {profile.skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-2 py-0.5 rounded-md bg-brand-50 text-brand-700 border border-brand-200 text-2xs font-semibold"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            )}
          </Card>

          <InfoPanel title={t('app.profile.whoCanSee')} tone="neutral">
            <p>
              SmartHR recruiters can see your name, contact details and CV once you apply to one
              of their opportunities. Other applicants cannot see anything about you.
            </p>
          </InfoPanel>
        </div>
      </div>
    </div>
  );
};
