import React, { useState } from "react";
import { SmartHRApi } from "../services/api";
import { LanguageSwitcher, useT } from "../i18n";

interface LoginPageProps {
  onLogin: () => void;
  /** Opens applicant registration. Staff accounts are made by an admin. */
  onRegister?: () => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLogin, onRegister }) => {
  const { t } = useT();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    setError("");
    setLoading(true);

    try {
      await SmartHRApi.login(email, password);
      onLogin();
    } catch (err) {
      // A message the API produced is shown as the API worded it; only the
       // generic fallback, which is SmartHR's own sentence, is translated.
      setError(err instanceof Error ? err.message : t("auth.invalidCredentials"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-100 px-4">
      {/*
        The switcher is available before sign-in: somebody who cannot read
        English must be able to reach their own language from the first screen.
        The preference lives in localStorage, which is readable signed out.
      */}
      <div className="fixed top-4 end-4">
        <LanguageSwitcher variant="full" />
      </div>

      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-stone-900">{t("auth.title")}</h1>

          <p className="text-stone-500 mt-2">{t("auth.subtitle")}</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">
              {t("auth.email")}
            </label>

            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("auth.emailPlaceholder")}
              required
              className="w-full px-4 py-3 border border-stone-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-400 text-start"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">
              {t("auth.password")}
            </label>

            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("auth.passwordPlaceholder")}
              required
              className="w-full px-4 py-3 border border-stone-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-400 text-start"
            />
          </div>

          {error && (
            <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-3 rounded-lg transition disabled:opacity-50"
          >
            {loading ? t("auth.signingIn") : t("auth.signIn")}
          </button>
        </form>

        {onRegister && (
          <p className="text-center text-sm text-stone-500 mt-6">
            {t("auth.lookingForJob")}{' '}
            <button
              type="button"
              onClick={onRegister}
              className="font-semibold text-orange-600 hover:text-orange-700"
            >
              {t("auth.createApplicantAccount")}
            </button>
          </p>
        )}

        <p className="text-center text-xs text-stone-400 mt-4">
          {t("auth.footer")}
        </p>
      </div>
    </div>
  );
};