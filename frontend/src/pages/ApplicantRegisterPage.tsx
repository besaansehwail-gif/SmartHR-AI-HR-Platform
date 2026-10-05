import React, { useState } from 'react';

import { SmartHRApi } from '../services/api';
import { LanguageSwitcher, useT } from '../i18n';

/**
 * Applicant registration.
 *
 * The only screen in SmartHR reachable without a token, matching the only
 * unauthenticated endpoint (`POST /applicant/register`). It collects exactly
 * three fields, and notably does **not** collect a role: the account is
 * created as an Applicant server-side, and a form that could choose a role
 * would be a way in.
 *
 * Styled to match LoginPage, which it sits beside.
 */
export const ApplicantRegisterPage: React.FC<{
  onRegistered: (email: string) => void;
  onBackToLogin: () => void;
}> = ({ onRegistered, onBackToLogin }) => {
  const { t } = useT();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await SmartHRApi.registerApplicant({
        full_name: fullName,
        email,
        password,
      });
      onRegistered(email);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('register.failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-100 px-4 py-10">
      <div className="fixed top-4 end-4">
        <LanguageSwitcher variant="full" />
      </div>

      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8">
        <div className="text-center mb-7">
          <h1 className="text-3xl font-bold text-stone-900">{t('auth.title')}</h1>
          <p className="text-stone-500 mt-2">{t('register.title')}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">
              {t('register.fullName')}
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder={t('register.fullNamePlaceholder')}
              required
              className="w-full px-4 py-3 border border-stone-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-400 text-start"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">
              {t('register.email')}
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('register.emailPlaceholder')}
              required
              className="w-full px-4 py-3 border border-stone-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-400 text-start"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">
              {t('register.password')}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('register.passwordHint')}
              minLength={8}
              required
              className="w-full px-4 py-3 border border-stone-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-400 text-start"
            />
            <p className="text-xs text-stone-400 mt-1.5">{t('register.passwordHint')}</p>
          </div>

          {error && (
            <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-3 rounded-lg transition disabled:opacity-50"
          >
            {loading ? t('register.submitting') : t('register.submit')}
          </button>
        </form>

        <p className="text-center text-sm text-stone-500 mt-6">
          {t('register.haveAccount')}{' '}
          <button
            type="button"
            onClick={onBackToLogin}
            className="font-semibold text-orange-600 hover:text-orange-700"
          >
            {t('auth.signIn')}
          </button>
        </p>

        <p className="text-center text-xs text-stone-400 mt-4 leading-relaxed">
          {t('register.staffNote')}
        </p>
      </div>
    </div>
  );
};
