import React, { useMemo, useRef, useState } from 'react';
import {
  Upload,
  FileText,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  Info,
  Mail,
  Phone,
  MapPin,
  GraduationCap,
  Briefcase,
  Award,
  Languages as LanguagesIcon,
  X,
  Loader2,
  Database,
  ShieldCheck,
} from 'lucide-react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { InfoPanel } from '../ui/States';
import { SmartHRApi } from '../../services/api';
import { CvApplyResponse, CvUploadResponse, ParsedCv } from '../../types';
import { useT } from '../../i18n';

/**
 * AI CV analysis for a candidate.
 *
 *   pick a PDF/DOCX -> POST /cvs/upload -> text extraction -> LLM -> panel
 *
 * The browser does none of that work and holds no API key: it posts the file
 * to FastAPI and renders what comes back.
 *
 * Every section renders only what the document actually contained. A field the
 * CV did not state comes back null and is shown as "Not stated in the CV" -
 * never as an empty string, "undefined", or a plausible guess.
 */

export interface CvAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  candidateId: number;
  candidateName: string;
  /** Called after a successful upload so the caller can refresh its list. */
  onUploaded?: () => void;
}

const ACCEPT = '.pdf,.docx';
const MAX_MB = 5;

const NotStated: React.FC = () => {
  const { t } = useT();
  return <span className="text-stone-400 italic">{t('ai.cv.notStated')}</span>;
};

const EMPTY = <NotStated />;

const Section: React.FC<{
  title: string;
  icon: React.ReactNode;
  count?: number;
  children: React.ReactNode;
}> = ({ title, icon, count, children }) => (
  <section className="space-y-2.5">
    <div className="flex items-center gap-2">
      <span className="w-7 h-7 rounded-lg bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center shrink-0">
        {icon}
      </span>
      <h4 className="text-2xs font-extrabold uppercase tracking-wider text-stone-500">{title}</h4>
      {count !== undefined && count > 0 && (
        <span className="text-3xs font-extrabold text-brand-700 bg-brand-50 border border-brand-200 rounded-full px-1.5 tabular-nums">
          {count}
        </span>
      )}
    </div>
    <div className="ps-9">{children}</div>
  </section>
);

const dateRange = (start: string | null, end: string | null) => {
  if (!start && !end) return null;
  if (start && end) return `${start} – ${end}`;
  return start || end;
};

const AnalysisPanel: React.FC<{ analysis: ParsedCv }> = ({ analysis }) => {
  const { t } = useT();
  return (
  <div className="space-y-6">
    {/* Identity */}
    <div className="rounded-xl border border-stone-200 bg-sand-50 p-4">
      <p className="text-3xs font-extrabold uppercase tracking-wider text-stone-400">{t('ai.cv.candidate')}</p>
      <p className="text-lg font-extrabold text-stone-900 tracking-tight mt-0.5 break-words">
        {analysis.full_name || EMPTY}
      </p>

      <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3 pt-3 border-t border-stone-200">
        {[
          { icon: <Mail className="w-3 h-3" />, label: t('table.email'), value: analysis.email },
          { icon: <Phone className="w-3 h-3" />, label: t('table.phone'), value: analysis.phone },
          { icon: <MapPin className="w-3 h-3" />, label: t('table.location'), value: analysis.location },
        ].map((row) => (
          <div key={row.label} className="min-w-0">
            <dt className="flex items-center gap-1.5 text-3xs font-bold uppercase tracking-wider text-stone-400">
              <span aria-hidden="true">{row.icon}</span>
              {row.label}
            </dt>
            <dd className="text-xs font-semibold text-stone-800 mt-1 break-words">
              {row.value || EMPTY}
            </dd>
          </div>
        ))}
      </dl>
    </div>

    <Section title={t('ai.cv.summary')} icon={<Sparkles className="w-3.5 h-3.5" />}>
      <p className="text-xs text-stone-700 leading-relaxed whitespace-pre-wrap">
        {analysis.summary || EMPTY}
      </p>
    </Section>

    <Section title={t('ai.cv.skills')} icon={<Award className="w-3.5 h-3.5" />} count={analysis.skills.length}>
      {analysis.skills.length === 0 ? (
        <p className="text-xs">{EMPTY}</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {analysis.skills.map((skill, i) => (
            <li key={`${skill}-${i}`}>
              <Badge variant="brand" size="sm">{skill}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Section>

    <Section
      title={t('ai.cv.experience')}
      icon={<Briefcase className="w-3.5 h-3.5" />}
      count={analysis.experience.length}
    >
      {analysis.experience.length === 0 ? (
        <p className="text-xs">{EMPTY}</p>
      ) : (
        <ol className="space-y-3">
          {analysis.experience.map((role, i) => (
            <li key={i} className="border-s-2 border-brand-200 ps-3">
              <p className="text-xs font-bold text-stone-900">{role.job_title || t('ai.cv.roleNotStated')}</p>
              <p className="text-2xs text-stone-600 mt-0.5">
                {[role.company, role.location].filter(Boolean).join(' · ') || EMPTY}
              </p>
              {dateRange(role.start_date, role.end_date) && (
                <p className="text-3xs font-semibold text-stone-400 mt-0.5 tabular-nums">
                  {dateRange(role.start_date, role.end_date)}
                </p>
              )}
              {role.description && (
                <p className="text-2xs text-stone-600 mt-1.5 leading-relaxed">{role.description}</p>
              )}
              {role.technologies.length > 0 && (
                <ul className="flex flex-wrap gap-1 mt-1.5">
                  {role.technologies.map((tech, techIdx) => (
                    <li key={`${tech}-${techIdx}`}>
                      <Badge variant="neutral" size="sm">{tech}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </Section>

    <Section
      title={t('ai.cv.education')}
      icon={<GraduationCap className="w-3.5 h-3.5" />}
      count={analysis.education.length}
    >
      {analysis.education.length === 0 ? (
        <p className="text-xs">{EMPTY}</p>
      ) : (
        <ol className="space-y-3">
          {analysis.education.map((entry, i) => (
            <li key={i} className="border-s-2 border-stone-200 ps-3">
              <p className="text-xs font-bold text-stone-900">
                {entry.degree || t('ai.cv.qualificationNotStated')}
              </p>
              <p className="text-2xs text-stone-600 mt-0.5">
                {[entry.institution, entry.field_of_study].filter(Boolean).join(' · ') || EMPTY}
              </p>
              {dateRange(entry.start_date, entry.end_date) && (
                <p className="text-3xs font-semibold text-stone-400 mt-0.5 tabular-nums">
                  {dateRange(entry.start_date, entry.end_date)}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Section>

    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <Section
        title={t('ai.cv.certifications')}
        icon={<Award className="w-3.5 h-3.5" />}
        count={analysis.certifications.length}
      >
        {analysis.certifications.length === 0 ? (
          <p className="text-xs">{EMPTY}</p>
        ) : (
          <ul className="space-y-1.5">
            {analysis.certifications.map((item, i) => (
              <li key={i} className="text-xs text-stone-700 flex items-start gap-1.5">
                <CheckCircle2 className="w-3 h-3 text-emerald-600 mt-0.5 shrink-0" aria-hidden="true" />
                <span className="min-w-0">
                  <span className="font-semibold break-words">
                    {item.name || t('ai.cv.certNotNamed')}
                  </span>
                  {(item.issuer || item.date) && (
                    <span className="block text-3xs text-stone-500 mt-0.5">
                      {[item.issuer, item.date].filter(Boolean).join(' · ')}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title={t('ai.cv.languages')}
        icon={<LanguagesIcon className="w-3.5 h-3.5" />}
        count={analysis.languages.length}
      >
        {analysis.languages.length === 0 ? (
          <p className="text-xs">{EMPTY}</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {analysis.languages.map((item, i) => (
              <li key={i}>
                <Badge variant="neutral" size="sm">
                  {item.language || t('ai.cv.languageNotNamed')}
                  {/* Shown only when the CV stated a level; never estimated. */}
                  {item.proficiency ? ` · ${item.proficiency}` : ''}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  </div>
  );
};


/**
 * The human-review step.
 *
 * The parser's output is a reading of a document, not a verified fact about a
 * person, so nothing it produced is written to the database automatically.
 * `candidates.phone` and `candidates.location` are the only two columns the
 * existing schema has for anything the CV yields; a recruiter sees the
 * extracted values, edits them if they are wrong, and saves deliberately.
 */
const ReviewAndApply: React.FC<{
  cvId: number;
  analysis: ParsedCv;
  candidate: CvUploadResponse['candidate'];
}> = ({ cvId, analysis, candidate }) => {
  const { t } = useT();
  const [phone, setPhone] = useState(analysis.phone ?? '');
  const [location, setLocation] = useState(analysis.location ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState<CvApplyResponse | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const nothingToApply = !phone.trim() && !location.trim();

  const handleApply = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      const response = await SmartHRApi.applyCvToCandidate(cvId, {
        phone: phone.trim() || null,
        location: location.trim() || null,
      });
      setSaved(response);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : t('ai.cv.updateFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const field = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    placeholder: string,
    maxLength: number
  ) => (
    <div>
      <label
        htmlFor={id}
        className="block text-3xs font-bold uppercase tracking-wider text-stone-400 mb-1"
      >
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-xs text-stone-800 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-brand-400"
      />
    </div>
  );

  return (
    <div className="rounded-xl border border-brand-200 bg-brand-50/50 p-4">
      <div className="flex items-start gap-2">
        <ShieldCheck className="w-4 h-4 text-brand-700 mt-0.5 shrink-0" aria-hidden="true" />
        <div className="min-w-0">
          <h4 className="text-xs font-extrabold text-stone-900">{t('ai.cv.reviewAndSave')}</h4>
          <p className="text-3xs text-stone-600 leading-relaxed mt-0.5">
            These are the only two extracted values SmartHR has a column for. Check them against the
            CV before saving - nothing here is written automatically.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
        {field('cv-review-phone', t('table.phone'), phone, setPhone, t('ai.cv.notStated'), 30)}
        {field('cv-review-location', t('table.location'), location, setLocation, t('ai.cv.notStated'), 150)}
      </div>

      <p className="text-3xs text-stone-500 mt-2">
        Currently on record: phone {candidate.phone || '—'} · location {candidate.location || '—'}
      </p>

      {saveError && (
        <p role="alert" className="text-3xs font-bold text-red-600 mt-2">
          {saveError}
        </p>
      )}

      {saved ? (
        <p className="flex items-center gap-1.5 text-3xs font-bold text-emerald-700 mt-3">
          <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
          Saved to the candidate record: {saved.applied_fields.join(', ')}
        </p>
      ) : (
        <Button
          variant="primary"
          size="sm"
          className="mt-3"
          onClick={handleApply}
          isLoading={isSaving}
          disabled={nothingToApply || isSaving}
          leftIcon={<Database className="w-3.5 h-3.5" />}
        >
          {isSaving ? t('state.saving') : t('ai.cv.saveToCandidate')}
        </Button>
      )}
    </div>
  );
};

export const CvAnalysisModal: React.FC<CvAnalysisModalProps> = ({
  isOpen,
  onClose,
  candidateId,
  candidateName,
  onUploaded,
}) => {
  const { t } = useT();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<CvUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const fileError = useMemo(() => {
    if (!file) return null;
    const name = file.name.toLowerCase();
    if (!name.endsWith('.pdf') && !name.endsWith('.docx')) {
      return t('ai.cv.unsupportedType');
    }
    if (file.size === 0) return t('ai.cv.emptyFile');
    if (file.size > MAX_MB * 1024 * 1024) return `The file is larger than the ${MAX_MB} MB limit.`;
    return null;
  }, [file]);

  const reset = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setIsUploading(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleUpload = async () => {
    if (!file || fileError) return;

    setIsUploading(true);
    setError(null);

    try {
      const response = await SmartHRApi.uploadCv(candidateId, file);
      setResult(response);
      onUploaded?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.cv.uploadFailed'));
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      size="xl"
      icon={<Sparkles className="w-4 h-4" />}
      title={t('ai.cv.modalTitle')}
      subtitle={`Upload a PDF or DOCX CV for ${candidateName}. SmartHR extracts the text and analyses it.`}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={handleClose}>
            {result ? 'Done' : t('action.cancel')}
          </Button>
          {result ? (
            <Button variant="soft" size="sm" onClick={reset} leftIcon={<Upload className="w-3.5 h-3.5" />}>
              {t('ai.cv.analyseAnother')}
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onClick={handleUpload}
              isLoading={isUploading}
              disabled={!file || !!fileError || isUploading}
              leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            >
              {isUploading ? t('ai.cv.analysing') : t('ai.cv.uploadAndAnalyse')}
            </Button>
          )}
        </>
      }
    >
      {!result ? (
        <div className="space-y-4">
          <label
            htmlFor="cv-file-input"
            className={`flex flex-col items-center justify-center gap-2 w-full rounded-2xl border-2 border-dashed px-6 py-10 text-center cursor-pointer transition-colors ${
              fileError
                ? 'border-red-300 bg-red-50/50'
                : file
                ? 'border-brand-300 bg-brand-50/60'
                : 'border-stone-300 bg-sand-50 hover:border-brand-300 hover:bg-brand-50/40'
            }`}
          >
            <span
              className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
                file ? 'bg-brand-100 text-brand-700' : 'bg-white border border-stone-200 text-stone-400'
              }`}
              aria-hidden="true"
            >
              {file ? <FileText className="w-5 h-5" /> : <Upload className="w-5 h-5" />}
            </span>

            {file ? (
              <>
                <span className="text-sm font-bold text-stone-900 break-all max-w-full px-4">
                  {file.name}
                </span>
                <span className="text-2xs text-stone-500">
                  {(file.size / 1024).toFixed(0)} KB · click to choose a different file
                </span>
              </>
            ) : (
              <>
                <span className="text-sm font-bold text-stone-800">{t('ai.cv.chooseFile')}</span>
                <span className="text-2xs text-stone-500">
                  PDF or DOCX, up to {MAX_MB} MB. The file is sent to the SmartHR server, not to a
                  model.
                </span>
              </>
            )}

            <input
              id="cv-file-input"
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
            />
          </label>

          {file && !fileError && (
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center gap-1 text-2xs font-bold text-stone-500 hover:text-red-700 transition-colors"
            >
              <X className="w-3 h-3" /> {t('ai.cv.removeFile')}
            </button>
          )}

          {fileError && (
            <p role="alert" className="text-2xs font-bold text-red-600">
              {fileError}
            </p>
          )}

          {error && (
            <InfoPanel
              tone="warning"
              title={t('ai.cv.failed')}
              icon={<AlertTriangle className="w-4 h-4" />}
            >
              {error}
            </InfoPanel>
          )}

          <InfoPanel tone="neutral" title={t('ai.cv.whatHappens')} icon={<Info className="w-4 h-4" />}>
            It is stored on the SmartHR server and linked to this candidate. The text is extracted
            and analysed; only the file name and path are saved to the database, because the{' '}
            <code className="font-mono">cvs</code> table has no column for the analysis.
          </InfoPanel>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Upload receipt */}
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="success" dot>{t('ai.cv.stored')}</Badge>
            <Badge variant="neutral" icon={<FileText className="w-2.5 h-2.5" />}>
              {result.cv.file_name}
            </Badge>
            <Badge variant="neutral">
              {result.extraction.file_type.toUpperCase()} ·{' '}
              {result.extraction.word_count.toLocaleString()} words
            </Badge>
            {result.analysis_available && (
              <Badge variant="brand" icon={<Sparkles className="w-2.5 h-2.5" />}>
                Analysed by {result.provider}
                {result.model ? ` · ${result.model}` : ''}
              </Badge>
            )}
          </div>

          {result.extraction.truncated && (
            <InfoPanel tone="info" title={t('ai.cv.longDocument')} icon={<Info className="w-4 h-4" />}>
              {t('ai.cv.longDocumentBody')}
            </InfoPanel>
          )}

          {/* Analysis, or an honest explanation of why there is none */}
          {result.analysis_available && result.analysis ? (
            <>
              {/* Said before the data, not after it. */}
              <InfoPanel
                tone="info"
                title={t('ai.cv.reviewNotice')}
                icon={<Sparkles className="w-4 h-4" />}
              >
                Every field below was read out of this document by a language model. It assists your
                review; it does not verify the candidate and makes no hiring recommendation.
              </InfoPanel>

              <AnalysisPanel analysis={result.analysis} />

              <ReviewAndApply
                cvId={result.cv.id}
                analysis={result.analysis}
                candidate={result.candidate}
              />
            </>
          ) : (
            <div className="space-y-4">
              <InfoPanel
                tone={result.analysis_error_code === 'llm_not_configured' ? 'warning' : 'warning'}
                title={
                  result.analysis_error_code === 'llm_not_configured'
                    ? t('ai.cv.noModel')
                    : t('ai.cv.incomplete')
                }
                icon={<AlertTriangle className="w-4 h-4" />}
              >
                {result.analysis_error ??
                  t('ai.cv.storedNotAnalysed')}{' '}
                {result.analysis_error_code === 'llm_not_configured' && (
                  <>
                    Set <code className="font-mono">SMARTHR_LLM_PROVIDER</code> and{' '}
                    <code className="font-mono">SMARTHR_LLM_API_KEY</code> on the server to enable
                    structured CV analysis. Nothing is guessed in the meantime.
                  </>
                )}
              </InfoPanel>

              {(result.contact_found_in_text.email || result.contact_found_in_text.phone) && (
                <div className="rounded-xl border border-stone-200 bg-sand-50 p-4">
                  <p className="text-3xs font-extrabold uppercase tracking-wider text-stone-400">
                    {t('ai.cv.foundInText')}
                  </p>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
                    <div>
                      <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                        {t('table.email')}
                      </dt>
                      <dd className="text-xs font-semibold text-stone-800 mt-0.5 break-words">
                        {result.contact_found_in_text.email || EMPTY}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-3xs font-bold uppercase tracking-wider text-stone-400">
                        {t('table.phone')}
                      </dt>
                      <dd className="text-xs font-semibold text-stone-800 mt-0.5 break-words">
                        {result.contact_found_in_text.phone || EMPTY}
                      </dd>
                    </div>
                  </dl>
                  <p className="text-3xs text-stone-500 mt-2 leading-relaxed">
                    {t('ai.cv.literalMatches')}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* What was written to the database */}
          <div className="rounded-xl border border-stone-200 bg-white p-3.5 flex items-start gap-2.5">
            <Database className="w-3.5 h-3.5 text-stone-400 mt-0.5 shrink-0" aria-hidden="true" />
            <p className="text-3xs text-stone-500 leading-relaxed">
              <span className="font-bold text-stone-700">{t('ai.cv.savedToDb')}</span>{' '}
              {result.persistence.stored_in_postgres.cvs.join(', ')} on the CV row; {' '}
              {result.persistence.stored_in_postgres.candidates_on_confirmation.join(', ')} on the
              candidate only when you confirm them above. {result.persistence.note}
            </p>
          </div>
        </div>
      )}

      {isUploading && (
        <p className="sr-only" role="status">
          {t('ai.cv.uploading')}
        </p>
      )}
      {isUploading && !result && (
        <div className="mt-4 flex items-center justify-center gap-2 text-2xs font-semibold text-stone-500">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-600" aria-hidden="true" />
          {t('ai.cv.extracting')}
        </div>
      )}
    </Modal>
  );
};
