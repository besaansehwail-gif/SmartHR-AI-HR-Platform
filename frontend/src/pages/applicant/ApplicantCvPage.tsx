import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, FileText, Upload } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, Field } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState, InfoPanel, InlineEmpty, LoadingState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import { SmartHRApi } from '../../services/api';
import { ApplicantCvListResponse, ApplicantCvUploadResponse } from '../../types';
import { useT } from '../../i18n';

/**
 * My CV.
 *
 * Uploads go through the **same** `analyse_cv_bytes()` pipeline HR's Candidates
 * page uses - the same extraction, the same prompt, the same Pydantic
 * validation. There is no second parser.
 *
 * The one rule this page exists to make visible: **nothing the AI extracted is
 * saved**. Skills it found are shown as suggestions with a button that copies
 * them into the profile form, and the applicant has to save them there. A
 * missing field reads "Not stated in the CV", never a plausible guess.
 */
export const ApplicantCvPage: React.FC<{ onNavigate: (page: PageId) => void }> = ({
  onNavigate,
}) => {
  const { t } = useT();
  const [data, setData] = useState<ApplicantCvListResponse | null>(null);
  const [analysis, setAnalysis] = useState<ApplicantCvUploadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const { showToast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await SmartHRApi.getMyCvs());
    } catch (err) {
      setError(err instanceof Error ? err.message : t('app.cv.failed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setAnalysis(null);
    try {
      const result = await SmartHRApi.uploadMyCv(file, true);
      setAnalysis(result);
      showToast('CV uploaded', {
        message: `${file.name} is now the CV recruiters will read.`,
        type: 'success',
      });
      await load();
    } catch (err) {
      showToast(t('app.cv.uploadFailed'), {
        message: err instanceof Error ? err.message : t('app.profile.tryAgain'),
        type: 'error',
      });
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  if (loading) return <LoadingState title={t('app.cv.loading')} />;
  if (error || !data) return <ErrorState message={error ?? t('app.common.noData')} onRetry={load} />;

  const parsed = analysis?.analysis;
  const notStated = <span className="text-stone-400 italic">{t('ai.cv.notStated')}</span>;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('app.cv.title')}
        subtitle={t('app.cv.pageSubtitle')}
        icon={<FileText className="w-5 h-5" />}
        badge={
          data.has_cv ? <Badge variant="success">{t('app.cv.onFileBadge')}</Badge> : <Badge variant="warning">{t('app.cv.noneYet')}</Badge>
        }
        actions={
          <>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={handleUpload}
            />
            <Button
              variant="primary"
              leftIcon={<Upload className="w-4 h-4" />}
              isLoading={uploading}
              onClick={() => fileInput.current?.click()}
            >
              {data.has_cv ? t('app.cv.uploadNew') : t('app.cv.uploadMyCv')}
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {analysis && (
            <Card padding="md" variant="featured">
              <CardHeader
                title={t('ai.cv.reviewNotice')}
                subtitle={t('app.cv.justUploadedHint')}
                icon={<CheckCircle2 className="w-4 h-4" />}
              />

              {analysis.analysis_error_code ? (
                <InfoPanel
                  title={
                    analysis.analysis_error_code === 'llm_not_configured'
                      ? t('ai.noModelTitle')
                      : t('app.cv.analysisFailed')
                  }
                  tone="warning"
                >
                  <p>
                    {analysis.analysis_error ??
                      t('app.cv.textOnly')}
                  </p>
                  {analysis.contact_found_in_text &&
                    (analysis.contact_found_in_text.email ||
                      analysis.contact_found_in_text.phone) && (
                      <div className="mt-3">
                        <p className="text-2xs font-bold uppercase tracking-wider text-stone-500">
                          {t('ai.cv.foundInText')}
                        </p>
                        <p className="text-xs text-stone-700 mt-1">
                          {analysis.contact_found_in_text.email ?? '—'}
                          {analysis.contact_found_in_text.phone
                            ? ` • ${analysis.contact_found_in_text.phone}`
                            : ''}
                        </p>
                      </div>
                    )}
                </InfoPanel>
              ) : parsed ? (
                <div className="space-y-5">
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Field label={t('ai.cv.fullName')} value={parsed.full_name || notStated} />
                    <Field label={t('table.email')} value={parsed.email || notStated} />
                    <Field label={t('table.phone')} value={parsed.phone || notStated} />
                    <Field label={t('table.location')} value={parsed.location || notStated} />
                  </dl>

                  {parsed.summary && (
                    <div>
                      <p className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                        {t('ai.cv.summary')}
                      </p>
                      <p className="text-sm text-stone-700 mt-1 leading-relaxed">
                        {parsed.summary}
                      </p>
                    </div>
                  )}

                  {parsed.experience?.length > 0 && (
                    <div>
                      <p className="text-3xs font-bold uppercase tracking-wider text-stone-400 mb-2">
                        {t('ai.cv.experience')}
                      </p>
                      <ul className="space-y-2">
                        {parsed.experience.map((role, index) => (
                          <li
                            key={`${role.title}-${index}`}
                            className="p-3 rounded-xl border border-stone-200"
                          >
                            <p className="text-xs font-bold text-stone-900">
                              {role.title || t('app.cv.roleNotStated')}
                              {role.company ? ` — ${role.company}` : ''}
                            </p>
                            {(role.start_date || role.end_date) && (
                              <p className="text-3xs text-stone-500 mt-0.5">
                                {role.start_date ?? '?'} → {role.end_date ?? 'present'}
                              </p>
                            )}
                            {role.technologies?.length > 0 && (
                              <p className="text-3xs text-stone-600 mt-1">
                                {role.technologies.join(', ')}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : null}
            </Card>
          )}

          {analysis?.suggested_skills && analysis.suggested_skills.skills.length > 0 && (
            <Card padding="md" variant="brand">
              <CardHeader
                title={t('app.cv.skillsFound')}
                subtitle={analysis.suggested_skills.note}
              />
              <div className="flex flex-wrap gap-1.5 mb-4">
                {analysis.suggested_skills.skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-2 py-0.5 rounded-md bg-white text-stone-800 border border-stone-200 text-2xs font-semibold"
                  >
                    {skill}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  size="sm"
                  variant="primary"
                  onClick={async () => {
                    await navigator.clipboard
                      ?.writeText(analysis.suggested_skills.skills.join(', '))
                      .catch(() => undefined);
                    showToast(t('app.cv.copied'), {
                      message: t('app.cv.pasteHint'),
                      type: 'info',
                    });
                    onNavigate('app-profile');
                  }}
                >
                  {t('app.cv.copyToProfile')}
                </Button>
                <span className="text-3xs text-stone-600">
                  {t('app.cv.notSaved')}
                </span>
              </div>
            </Card>
          )}

          <Card padding="md">
            <CardHeader title={t('app.cv.onFile')} subtitle={data.note} />
            {data.cvs.length === 0 ? (
              <InlineEmpty
                title={t('app.cv.noCvYet')}
                description={t('app.cv.noCvYetHint')}
                icon={<FileText className="w-5 h-5" />}
              />
            ) : (
              <ul className="space-y-2">
                {data.cvs.map((cv, index) => (
                  <li
                    key={cv.id}
                    className="flex items-center justify-between gap-3 p-3 rounded-xl border border-stone-200"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-stone-900 break-words">
                        {cv.file_name}
                      </p>
                      <p className="text-3xs text-stone-500 mt-0.5">
                        Uploaded {(cv.uploaded_at ?? '').slice(0, 10)}
                      </p>
                    </div>
                    {index === 0 && <Badge variant="success" size="sm">{t('app.cv.currentBadge')}</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <InfoPanel title={t('app.cv.whatStored')} tone="neutral">
            <p>
              The file itself, its name and the date you uploaded it. The text and anything the AI
              read out of it are <strong>not</strong> saved — they are shown to you once and
              re-derived if needed. Your profile changes only when you save it.
            </p>
          </InfoPanel>

          <InfoPanel title={t('app.cv.acceptedFiles')} tone="info">
            <p>
              PDF or DOCX, up to 5 MB. The file type is checked by its actual contents, not its
              name. A scanned CV with no text layer cannot be read — if yours is a scan, export a
              text PDF instead.
            </p>
          </InfoPanel>
        </div>
      </div>
    </div>
  );
};
