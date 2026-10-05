import React, { useState } from 'react';
import {
  User,
  Building,
  Briefcase,
  MapPin,
  Calendar,
  Clock,
  Award,
  CheckCircle2,
  TrendingUp,
  Star,
  GraduationCap,
  FileText,
  Mail,
  Phone,
  Shield,
  Laptop,
  Home,
  Building2,
  ChevronRight,
  ExternalLink,
  Download,
  AlertTriangle,
  HeartHandshake,
  Milestone,
  History,
  Check,
  Sparkles,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge, WorkModeBadge } from '../../components/ui/Badge';
import { useToast } from '../../components/ui/Toast';
import { initialEmployees, getEmployee360Profile } from '../../mock/hrData';
import { Employee360Profile } from '../../types';
import { useT } from '../../i18n';

export interface Employee360PageProps {
  selectedEmployeeId?: string;
  onBackToDirectory?: () => void;
}

export const Employee360Page: React.FC<Employee360PageProps> = ({
  selectedEmployeeId = 'EMP-0101',
  onBackToDirectory,
}) => {
  const { t } = useT();
  const { showToast } = useToast();
  const [activeEmpId, setActiveEmpId] = useState(selectedEmployeeId);
  const [activeTab, setActiveTab] = useState<
    'overview' | 'employment' | 'attendance' | 'performance' | 'training' | 'skills' | 'timeline'
  >('overview');

  const profile: Employee360Profile = getEmployee360Profile(activeEmpId);
  const { employee, personalInfo, attendanceSummary, leaveSummary, performance, trainingSummary, skills, careerPath, activityTimeline } = profile;

  const handleExportProfile = () => {
    showToast(t('hr.e360.exporting'), {
      message: `Generating complete executive intelligence dossier for ${employee.firstName} ${employee.lastName}...`,
      type: 'info',
    });
  };

  return (
    <div className="space-y-6">
      {/* Top Controls & Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-stone-200/80">
        <div className="flex items-center gap-3">
          {onBackToDirectory && (
            <Button
              variant="outline"
              size="sm"
              onClick={onBackToDirectory}
              leftIcon={<ChevronRight className="w-3.5 h-3.5 rotate-180" data-flip-rtl />}
            >
              {t('hr.e360.backToDirectory')}
            </Button>
          )}
          <span className="text-xs font-semibold text-stone-500 hidden sm:inline">{t('hr.e360.selectProfile')}</span>
          <select
            value={activeEmpId}
            onChange={(e) => setActiveEmpId(e.target.value)}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-800 focus:ring-2 focus:ring-brand-600 focus:outline-none"
          >
            {initialEmployees.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.firstName} {emp.lastName} — {emp.position} ({emp.department})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leftIcon={<Download className="w-3.5 h-3.5" />}
            onClick={handleExportProfile}
          >
            {t('hr.e360.exportDossier')}
          </Button>
        </div>
      </div>

      {/* Hero Employee Identity Card */}
      <div className="bg-white rounded-2xl p-6 border border-stone-200 shadow-2xs relative overflow-hidden">
        {/* Subtle background glow accent */}
        <div className="absolute top-0 end-0 w-96 h-48 bg-gradient-to-bl from-brand-100/60 via-brand-50/40 to-transparent -z-0 pointer-events-none" />

        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
          <div className="flex items-start sm:items-center gap-4">
            {/* Avatar Badge */}
            <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-gradient-to-tr from-brand-700 via-brand-600 to-brand-600 text-white font-extrabold text-xl sm:text-2xl flex items-center justify-center shrink-0 shadow-md ring-4 ring-brand-100">
              {employee.firstName[0]}
              {employee.lastName[0]}
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl sm:text-2xl font-black text-stone-900 tracking-tight">
                  {employee.firstName} {employee.lastName}
                </h1>
                <span className="font-mono text-3xs font-bold px-2 py-0.5 rounded bg-stone-100 text-stone-700 border border-stone-200">
                  {employee.employeeId}
                </span>
                <span className="inline-flex items-center gap-1 text-3xs font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  {employee.status}
                </span>
              </div>

              <p className="text-sm font-semibold text-brand-700">
                {employee.position}{' '}
                <span className="text-stone-400 font-normal">• {employee.gradeLevel}</span>
              </p>

              <div className="flex items-center gap-4 text-xs text-stone-500 pt-1 flex-wrap">
                <span className="flex items-center gap-1">
                  <Building className="w-3.5 h-3.5 text-stone-400" />
                  {employee.department}
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="w-3.5 h-3.5 text-stone-400" />
                  {employee.location}
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5 text-stone-400" />
                  Hired: {employee.hireDate}
                </span>
              </div>
            </div>
          </div>

          {/* Quick Metrics Badge Group */}
          <div className="flex items-center gap-3 border-t md:border-t-0 md:border-s border-stone-100 pt-4 md:pt-0 md:ps-6 w-full md:w-auto justify-between md:justify-end">
            <div className="text-center px-3">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400 block">{t('hr.e360.performance')}</span>
              <span className="text-xl font-extrabold text-stone-900 flex items-center justify-center gap-1 mt-0.5">
                <Star className="w-4 h-4 text-amber-500 fill-amber-500" />
                {performance.overallRating}
              </span>
              <span className="text-3xs font-medium text-stone-500">{t('hr.e360.outOf5')}</span>
            </div>

            <div className="text-center px-3 border-s border-stone-100">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400 block">{t('hr.e360.attendance')}</span>
              <span className="text-xl font-extrabold text-stone-900 mt-0.5 block">
                {attendanceSummary.attendanceRate}%
              </span>
              <span className="text-3xs font-medium text-emerald-600">{t('hr.e360.onTime98')}</span>
            </div>

            <div className="text-center px-3 border-s border-stone-100">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400 block">{t('hr.e360.workMode')}</span>
              <div className="mt-1">
                <WorkModeBadge mode={employee.workMode} />
              </div>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 mt-6 pt-4 border-t border-stone-100 overflow-x-auto">
          {[
            { id: 'overview', label: t('hr.e360.tabOverview') },
            { id: 'employment', label: t('hr.e360.tabEmployment') },
            { id: 'attendance', label: t('hr.e360.tabAttendance') },
            { id: 'performance', label: t('hr.e360.tabPerformance') },
            { id: 'training', label: t('hr.e360.tabTraining') },
            { id: 'skills', label: t('hr.e360.tabSkills') },
            { id: 'timeline', label: t('hr.e360.tabActivity') },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-brand-700 text-white shadow-xs'
                  : 'text-stone-600 hover:text-stone-900 hover:bg-stone-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab 1: OVERVIEW & 360 INTELLIGENCE */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Quick Bio & Core Info */}
            <div className="space-y-6">
              <Card title={t('hr.e360.executiveSummary')}>
                <div className="space-y-3.5 text-xs">
                  <div className="flex justify-between py-1.5 border-b border-stone-100">
                    <span className="text-stone-500 font-medium">{t('hr.e360.manager')}</span>
                    <span className="font-bold text-stone-900">{employee.manager}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-stone-100">
                    <span className="text-stone-500 font-medium">{t('hr.e360.compensation')}</span>
                    <span className="font-bold text-stone-900">{employee.salary}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-stone-100">
                    <span className="text-stone-500 font-medium">{t('table.email')}</span>
                    <span className="font-bold text-stone-900 truncate max-w-[160px]">{employee.email}</span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-stone-100">
                    <span className="text-stone-500 font-medium">{t('table.phone')}</span>
                    <span className="font-bold text-stone-900">{employee.phone}</span>
                  </div>
                  <div className="flex justify-between py-1.5">
                    <span className="text-stone-500 font-medium">{t('hr.e360.emergencyContact')}</span>
                    <span className="font-bold text-stone-900">
                      {personalInfo.emergencyContactName} ({personalInfo.emergencyContactRelation})
                    </span>
                  </div>
                </div>
              </Card>

              {/* Leave Balances */}
              <Card title={t('hr.e360.leaveQuota')}>
                <div className="grid grid-cols-2 gap-3 text-center">
                  <div className="p-3 bg-brand-50 rounded-xl border border-brand-100">
                    <span className="text-2xs font-semibold text-brand-700">{t('hr.e360.annualLeave')}</span>
                    <p className="text-2xl font-black text-brand-900 mt-1">
                      {leaveSummary.annualBalance}{' '}
                      <span className="text-xs font-normal text-brand-600">/ {leaveSummary.annualTotal}d</span>
                    </p>
                    <span className="text-3xs text-brand-600">{t('hr.e360.daysRemaining')}</span>
                  </div>
                  <div className="p-3 bg-sky-50 rounded-xl border border-sky-100">
                    <span className="text-2xs font-semibold text-sky-700">{t('hr.e360.sickLeave')}</span>
                    <p className="text-2xl font-black text-sky-900 mt-1">
                      {leaveSummary.sickBalance}{' '}
                      <span className="text-xs font-normal text-sky-600">/ {leaveSummary.sickTotal}d</span>
                    </p>
                    <span className="text-3xs text-sky-600">{t('hr.e360.daysAvailable')}</span>
                  </div>
                </div>
              </Card>
            </div>

            {/* Performance & Active OKRs (2 Cols) */}
            <div className="lg:col-span-2 space-y-6">
              <Card
                title={t('hr.e360.okrs')}
                subtitle={t('hr.e360.okrsHint')}
                headerAction={
                  <Badge variant="success">Review Rating: {performance.overallRating} / 5.0</Badge>
                }
              >
                <div className="space-y-4">
                  {performance.okrs.map((okr, idx) => (
                    <div key={idx} className="space-y-1.5 p-3 rounded-xl border border-stone-100 bg-stone-50/50">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-stone-800">{okr.title}</span>
                        <span className="font-extrabold text-brand-700">{okr.progress}%</span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-brand-600 transition-all duration-500"
                          style={{ width: `${okr.progress}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-3xs text-stone-400 pt-0.5">
                        <span>Target: {okr.target}</span>
                        <span className="font-semibold text-emerald-600">{okr.status}</span>
                      </div>
                    </div>
                  ))}

                  {/* Manager Summary */}
                  <div className="p-3.5 rounded-xl bg-brand-50/50 border border-brand-100 text-xs">
                    <span className="font-bold text-brand-900 block mb-1">
                      Performance Evaluation by {performance.reviewerName}
                    </span>
                    <p className="text-stone-700 leading-relaxed italic">
                      "{performance.managerSummary}"
                    </p>
                  </div>
                </div>
              </Card>

              {/* Top Skills Preview */}
              <Card title={t('hr.e360.competencies')}>
                <div className="grid grid-cols-2 gap-3">
                  {skills.slice(0, 4).map((s, idx) => (
                    <div key={idx} className="p-3 rounded-xl border border-stone-100 bg-white space-y-1 text-xs">
                      <div className="flex justify-between items-center">
                        <span className="font-bold text-stone-800">{s.skill}</span>
                        <div className="flex text-amber-500">
                          {Array.from({ length: 5 }).map((_, i) => (
                            <Star
                              key={i}
                              className={`w-3 h-3 ${i < s.rating ? 'fill-amber-400 text-amber-400' : 'text-stone-200'}`}
                            />
                          ))}
                        </div>
                      </div>
                      <span className="text-3xs text-stone-400 font-medium">
                        {s.category} • {s.endorsements} peer endorsements
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: EMPLOYMENT & PERSONAL INFORMATION */}
      {activeTab === 'employment' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card title={t('hr.e360.personalInfo')}>
            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.dob')}</span>
                <span className="font-bold text-stone-900">{personalInfo.dob}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.nationality')}</span>
                <span className="font-bold text-stone-900">{personalInfo.nationality}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.gender')}</span>
                <span className="font-bold text-stone-900">{personalInfo.gender}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.address')}</span>
                <span className="font-bold text-stone-900 text-end">{personalInfo.address}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-stone-500">{t('hr.e360.emergencyContact')}</span>
                <span className="font-bold text-stone-900 text-end">
                  {personalInfo.emergencyContactName} ({personalInfo.emergencyContactPhone})
                </span>
              </div>
            </div>
          </Card>

          <Card title={t('hr.e360.employmentInfo')}>
            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.employeeId')}</span>
                <span className="font-mono font-bold text-stone-900">{employee.employeeId}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('table.department')}</span>
                <span className="font-bold text-stone-900">{employee.department}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.jobPosition')}</span>
                <span className="font-bold text-stone-900">{employee.position}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.grade')}</span>
                <span className="font-bold text-stone-900">{employee.gradeLevel}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.reportingLine')}</span>
                <span className="font-bold text-brand-700">{employee.manager}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-stone-100">
                <span className="text-stone-500">{t('hr.e360.employmentType')}</span>
                <span className="font-bold text-stone-900">{employee.employmentType}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-stone-500">{t('hr.e360.workMode')}</span>
                <WorkModeBadge mode={employee.workMode} />
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Tab 3: ATTENDANCE & LEAVE */}
      {activeTab === 'attendance' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div className="bg-white p-4 rounded-xl border border-stone-200">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">{t('hr.e360.attendanceRate')}</span>
              <p className="text-2xl font-black text-stone-900 mt-1">{attendanceSummary.attendanceRate}%</p>
              <span className="text-3xs text-emerald-600 font-semibold">{t('hr.e360.consistentlyHigh')}</span>
            </div>
            <div className="bg-white p-4 rounded-xl border border-stone-200">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">{t('hr.e360.punctuality')}</span>
              <p className="text-2xl font-black text-stone-900 mt-1">{attendanceSummary.onTimeRate}%</p>
              <span className="text-3xs text-stone-500 font-medium">{t('hr.e360.onTimeCheckIns')}</span>
            </div>
            <div className="bg-white p-4 rounded-xl border border-stone-200">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">{t('hr.e360.remoteDays')}</span>
              <p className="text-2xl font-black text-sky-700 mt-1">{attendanceSummary.remoteDaysThisMonth} Days</p>
              <span className="text-3xs text-stone-500 font-medium">{t('hr.e360.loggedThisMonth')}</span>
            </div>
            <div className="bg-white p-4 rounded-xl border border-stone-200">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-400">{t('hr.e360.officeDays')}</span>
              <p className="text-2xl font-black text-brand-700 mt-1">{attendanceSummary.inOfficeDaysThisMonth} Days</p>
              <span className="text-3xs text-stone-500 font-medium">{t('hr.e360.loggedThisMonth')}</span>
            </div>
          </div>

          <Card title={t('hr.e360.clockInHistory')} noPadding>
            <table className="w-full text-start text-xs">
              <thead className="bg-stone-50 border-b border-stone-200 text-3xs font-bold uppercase text-stone-400">
                <tr>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">{t('hr.e360.clockIn')}</th>
                  <th className="py-3 px-4">{t('hr.e360.clockOut')}</th>
                  <th className="py-3 px-4">{t('hr.e360.totalHours')}</th>
                  <th className="py-3 px-4">Mode</th>
                  <th className="py-3 px-4">{t('table.status')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 text-stone-700">
                {attendanceSummary.recentClockIns.map((row, i) => (
                  <tr key={i} className="hover:bg-stone-50/50">
                    <td className="py-3 px-4 font-bold text-stone-900">{row.date}</td>
                    <td className="py-3 px-4">{row.checkIn}</td>
                    <td className="py-3 px-4">{row.checkOut}</td>
                    <td className="py-3 px-4 font-mono font-medium">{row.hours}</td>
                    <td className="py-3 px-4"><WorkModeBadge mode={row.mode} /></td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded-full text-3xs font-bold ${
                        row.status === t('hr.e360.onTime')
                          ? 'bg-emerald-50 text-emerald-700'
                          : 'bg-amber-50 text-amber-700'
                      }`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {/* Tab 4: PERFORMANCE & OKRs */}
      {activeTab === 'performance' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title={t('hr.e360.strengths')}>
              <ul className="space-y-2.5 text-xs">
                {performance.strengths.map((str, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-stone-700">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <span>{str}</span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title={t('hr.e360.growthAreas')}>
              <ul className="space-y-2.5 text-xs">
                {performance.growthAreas.map((gr, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-stone-700">
                    <TrendingUp className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
                    <span>{gr}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}

      {/* Tab 5: TRAINING & CERTIFICATIONS */}
      {activeTab === 'training' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title={t('hr.e360.certifications')}>
              <div className="space-y-3">
                {trainingSummary.certifications.map((cert, idx) => (
                  <div key={idx} className="p-3.5 rounded-xl border border-stone-100 bg-brand-50/30 text-xs flex items-start gap-3">
                    <Award className="w-5 h-5 text-brand-700 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="font-bold text-stone-900">{cert.name}</p>
                      <p className="text-stone-500 text-3xs mt-0.5">{cert.issuer} • Issued {cert.date}</p>
                      <p className="font-mono text-3xs text-brand-700 mt-1">Credential: {cert.credentialId}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title={t('hr.e360.learningPaths')}>
              <div className="space-y-3">
                {trainingSummary.currentCourses.map((c, idx) => (
                  <div key={idx} className="p-3.5 rounded-xl border border-stone-100 bg-stone-50 text-xs space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-stone-800">{c.title}</span>
                      <span className="font-extrabold text-brand-700">{c.progress}%</span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                      <div className="h-full bg-brand-600 rounded-full" style={{ width: `${c.progress}%` }} />
                    </div>
                    <span className="text-3xs text-stone-400 block">Due date: {c.dueDate}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* Tab 6: SKILLS MATRIX */}
      {activeTab === 'skills' && (
        <Card title={t('hr.e360.skillsMatrix')}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {skills.map((item, idx) => (
              <div key={idx} className="p-3.5 rounded-xl border border-stone-100 bg-white space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-stone-900">{item.skill}</span>
                  <span className="text-3xs font-semibold px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                    {item.category}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1 text-amber-500">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star
                        key={i}
                        className={`w-4 h-4 ${i < item.rating ? 'fill-amber-400 text-amber-400' : 'text-stone-200'}`}
                      />
                    ))}
                  </div>
                  <span className="text-2xs font-semibold text-stone-500">
                    {item.endorsements} Endorsements
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Tab 7: ACTIVITY & CAREER GROWTH */}
      {activeTab === 'timeline' && (
        <div className="space-y-6">
          <Card title={t('hr.e360.milestones')}>
            <div className="relative border-s-2 border-brand-200 ms-4 ps-6 space-y-6 py-2">
              {careerPath.map((milestone, idx) => (
                <div key={idx} className="relative">
                  <span className="absolute -left-[31px] top-0.5 w-4 h-4 rounded-full bg-brand-600 ring-4 ring-brand-100" />
                  <div className="text-xs">
                    <span className="text-3xs font-bold text-brand-700">{milestone.date}</span>
                    <p className="font-bold text-stone-900 mt-0.5">{milestone.title}</p>
                    <p className="text-stone-500 mt-0.5 leading-relaxed">{milestone.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card title={t('hr.e360.activityFeed')}>
            <div className="divide-y divide-stone-100 text-xs">
              {activityTimeline.map((item) => (
                <div key={item.id} className="py-3 flex items-start gap-3">
                  <span className="w-16 font-mono text-3xs text-stone-400 shrink-0 mt-0.5">
                    {item.date}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-stone-900">{item.title}</p>
                    <p className="text-stone-500 text-2xs mt-0.5">{item.description}</p>
                  </div>
                  <span className="text-3xs font-semibold px-2 py-0.5 rounded bg-brand-50 text-brand-700">
                    {item.category}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};
