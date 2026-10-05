import React, { useState } from 'react';
import {
  TrendingUp,
  Award,
  Star,
  CheckCircle2,
  ArrowRight,
  ArrowDown,
  Sparkles,
  BookOpen,
  Target,
  Milestone,
  Check,
  ShieldCheck,
  ChevronRight,
  GraduationCap,
  Layers,
  Compass,
  Zap,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import { PageId } from '../../components/layout/Sidebar';
import {
  initialCareerLadder,
  initialSkillsMatrix,
  initialEmployeeProfile,
  CareerLadderStep,
  EmployeeSkillMatrixItem,
} from '../../mock/employeeData';
import { useT } from '../../i18n';

export interface CareerGrowthPageProps {
  onNavigate?: (page: PageId) => void;
}

export const CareerGrowthPage: React.FC<CareerGrowthPageProps> = ({ onNavigate }) => {
  const { t } = useT();
  const { showToast } = useToast();
  const profile = initialEmployeeProfile;

  const [skillsMatrix, setSkillsMatrix] = useState<EmployeeSkillMatrixItem[]>(initialSkillsMatrix);
  const [activeSkillCategory, setActiveSkillCategory] = useState<string>('All');

  const categories = [
    'All',
    t('emp.career.domainCore'),
    t('emp.career.domainArchitecture'),
    t('emp.career.domainLeadership'),
    t('emp.career.domainProduct'),
  ];

  const filteredSkills = skillsMatrix.filter(
    (item) => activeSkillCategory === 'All' || item.category === activeSkillCategory
  );

  const currentStep = initialCareerLadder.find((s) => s.status === 'current')!;
  const nextTargetStep = initialCareerLadder.find((s) => s.status === 'target')!;

  const handleAddGoal = (skillName: string) => {
    showToast(t('emp.career.goalAdded'), {
      message: `"${skillName}" has been added to your active Q4 career development objectives.`,
      type: 'success',
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.career.title')}
        subtitle={t('emp.career.subtitle')}
        breadcrumbs={[
          { label: t('workspace.employee'), href: '#' },
          { label: t('emp.career.careerGrowth'), active: true },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<GraduationCap className="w-4 h-4" />}
              onClick={() => onNavigate && onNavigate('emp-training')}
            >
              {t('emp.career.learningCatalog')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Target className="w-4 h-4" />}
              onClick={() => onNavigate && onNavigate('emp-performance')}
            >
              {t('emp.career.myOkrs')}
            </Button>
          </div>
        }
      />

      {/* 1. Distinctive Promotion Horizon Hero Banner */}
      <div className="p-6 rounded-2xl bg-white border border-stone-200/90 shadow-2xs relative overflow-hidden">
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-3xs font-extrabold uppercase px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-200">
                {t('emp.career.pathway')}
              </span>
              <span className="text-3xs font-bold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-emerald-600" />
                {t('emp.career.targetCycle')}
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-black text-stone-900 tracking-tight">
              {currentStep.title}{' '}
              <span className="text-brand-600 font-light mx-2">→</span>{' '}
              <span className="text-brand-700">{nextTargetStep.title}</span>
            </h1>

            <p className="text-xs sm:text-sm text-stone-600 leading-relaxed">
              {t('emp.career.currentlyAt')} <strong className="text-stone-900">{currentStep.level} ({currentStep.grade})</strong> with an estimated{' '}
              <strong className="text-brand-700">82% promotion readiness score</strong>. Your verified competencies, RFC contributions, and leadership meet 4 of the 5 promotion requirements.
            </p>
          </div>

          {/* Promotion Readiness Gauge */}
          <div className="p-4 rounded-xl bg-stone-50 border border-stone-200 shrink-0 sm:min-w-[260px] space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-3xs font-bold uppercase text-brand-700 tracking-wider">
                {t('emp.career.readiness')}
              </span>
              <span className="text-base font-black text-stone-900">82%</span>
            </div>

            <div className="w-full h-3 rounded-full bg-stone-200 overflow-hidden">
              <div
                className="h-full bg-brand-700 rounded-full transition-all duration-500"
                style={{ width: '82%' }}
              />
            </div>

            <div className="flex justify-between items-center text-3xs text-stone-500">
              <span>{t('emp.career.nextReview')}</span>
              <span className="text-emerald-700 font-bold">1 Milestone Left</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Career Path Progression Ladder */}
      <Card
        title={t('emp.career.ladder')}
        subtitle={t('emp.career.ladderHint')}
        headerAction={
          <Badge variant="purple">
            {t('emp.career.icTrack')}
          </Badge>
        }
      >
        <div className="space-y-4 pt-1">
          {initialCareerLadder.map((step, idx) => {
            const isCompleted = step.status === 'completed';
            const isCurrent = step.status === 'current';
            const isTarget = step.status === 'target';
            const isFuture = step.status === 'future';

            return (
              <div key={step.level} className="relative">
                {/* Visual Connector Line */}
                {idx < initialCareerLadder.length - 1 && (
                  <div
                    className={`absolute start-5 top-12 bottom-[-16px] w-0.5 z-0 ${
                      isCompleted ? 'bg-emerald-500' : isCurrent ? 'bg-brand-600' : 'bg-stone-200'
                    }`}
                  />
                )}

                <div
                  className={`p-4 rounded-2xl border transition-all relative z-10 ${
                    isCurrent
                      ? 'bg-brand-50/70 border-brand-300 ring-2 ring-brand-400/30 shadow-sm'
                      : isTarget
                      ? 'bg-white border-brand-200 shadow-xs'
                      : isCompleted
                      ? 'bg-stone-50/70 border-stone-200'
                      : 'bg-white border-stone-100 opacity-70'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      {/* Step Indicator Node */}
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center font-black text-xs shrink-0 ${
                          isCompleted
                            ? 'bg-emerald-600 text-white'
                            : isCurrent
                            ? 'bg-brand-700 text-white shadow-md'
                            : isTarget
                            ? 'bg-brand-100 text-brand-900 border border-brand-300'
                            : 'bg-stone-100 text-stone-400'
                        }`}
                      >
                        {isCompleted ? <CheckCircle2 className="w-5 h-5" /> : step.level}
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-sm font-black text-stone-900">
                            {step.title}
                          </h3>
                          <span className="text-3xs font-bold uppercase px-2 py-0.5 rounded bg-stone-100 text-stone-600">
                            {step.grade}
                          </span>
                          {isCurrent && (
                            <Badge variant="purple" dot>
                              {t('emp.career.currentRole')}
                            </Badge>
                          )}
                          {isTarget && (
                            <Badge variant="success" dot>
                              {t('emp.career.nextRole')}
                            </Badge>
                          )}
                          {isCompleted && (
                            <Badge variant="neutral">
                              {t('emp.career.achieved')}
                            </Badge>
                          )}
                        </div>

                        <p className="text-2xs text-stone-600 leading-relaxed max-w-2xl">
                          {step.summary}
                        </p>
                        <span className="text-3xs font-medium text-stone-400 block pt-0.5">
                          {step.dateOrTimeline}
                        </span>
                      </div>
                    </div>

                    {/* Readiness Bar for Target */}
                    {isTarget && (
                      <div className="sm:w-44 shrink-0 space-y-1 pt-1 sm:pt-0">
                        <div className="flex justify-between text-3xs font-bold text-brand-900">
                          <span>{t('emp.career.promotionTrack')}</span>
                          <span>82%</span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-stone-100 overflow-hidden">
                          <div
                            className="h-full bg-brand-700 rounded-full"
                            style={{ width: '82%' }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Requirements & Competency Checklist */}
                  <div className="mt-3 pt-3 border-t border-stone-100 grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {step.requirements.map((req, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-1.5 text-2xs text-stone-700"
                      >
                        {isCompleted || (isCurrent && i < 2) || (isTarget && i === 0) ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                        ) : (
                          <span className="w-3.5 h-3.5 rounded-full border border-brand-400 shrink-0 mt-0.5" />
                        )}
                        <span>{req}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* 3. Skills Matrix & Proficiency Grid */}
      <Card
        title={t('emp.career.matrix')}
        subtitle={t('emp.career.matrixHint')}
        headerAction={
          <div className="flex items-center gap-1 p-1 bg-stone-100 rounded-lg overflow-x-auto max-w-full">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveSkillCategory(cat)}
                className={`px-2.5 py-1 text-3xs font-bold rounded transition-all whitespace-nowrap ${
                  activeSkillCategory === cat
                    ? 'bg-white text-brand-900 shadow-xs'
                    : 'text-stone-600 hover:text-stone-900'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        }
      >
        <div className="overflow-x-auto -mx-6 pt-1">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-y border-stone-200 bg-stone-50/70 text-stone-500 uppercase tracking-wider text-3xs font-bold">
                <th className="py-2.5 px-6">{t('emp.career.colSkill')}</th>
                <th className="py-2.5 px-4">{t('emp.career.colDomain')}</th>
                <th className="py-2.5 px-4">{t('emp.career.colCurrent')}</th>
                <th className="py-2.5 px-4">{t('emp.career.colTarget')}</th>
                <th className="py-2.5 px-4">{t('table.status')}</th>
                <th className="py-2.5 px-6">{t('emp.career.colVerifiedBy')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 font-medium">
              {filteredSkills.map((item) => (
                <tr key={item.skill} className="hover:bg-brand-50/30 transition-colors">
                  <td className="py-3 px-6 font-bold text-stone-900 whitespace-nowrap">
                    {item.skill}
                  </td>
                  <td className="py-3 px-4 text-stone-500 text-2xs whitespace-nowrap">
                    {item.category}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    <div className="flex items-center gap-1">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <Star
                          key={star}
                          className={`w-3.5 h-3.5 ${
                            star <= item.currentLevel
                              ? 'text-amber-400 fill-amber-400'
                              : 'text-stone-200'
                          }`}
                        />
                      ))}
                      <span className="font-mono text-2xs font-bold text-stone-700 ms-1">
                        {item.currentLevel}.0
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap font-mono font-bold text-brand-700">
                    {item.targetLevel}.0
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    <Badge
                      variant={
                        item.status === t('emp.career.mastered')
                          ? 'success'
                          : item.status === t('emp.career.proficient')
                          ? 'purple'
                          : 'warning'
                      }
                      dot={item.status === t('emp.career.developing')}
                    >
                      {item.status}
                    </Badge>
                  </td>
                  <td className="py-3 px-6 text-2xs text-stone-500 whitespace-nowrap">
                    {item.verifiedBy}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 4. Recommended Skills & Recommended Training to Unlock Next Role */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recommended Skills */}
        <Card
          title={t('emp.career.recommendedSkills')}
          subtitle={t('emp.career.recommendedSkillsHint')}
          headerAction={<Sparkles className="w-4 h-4 text-brand-600" />}
        >
          <div className="space-y-3 pt-1">
            {[
              {
                title: t('emp.career.gap1'),
                reason: t('emp.career.gap1Body'),
                levelGap: t('emp.career.gap1Target'),
              },
              {
                title: t('emp.career.gap2'),
                reason: t('emp.career.gap2Body'),
                levelGap: t('emp.career.gap2Target'),
              },
              {
                title: t('emp.career.gap3'),
                reason: t('emp.career.gap3Body'),
                levelGap: t('emp.career.gap3Target'),
              },
            ].map((rec) => (
              <div
                key={rec.title}
                className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 flex flex-col justify-between gap-2.5"
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-stone-900">{rec.title}</span>
                    <span className="text-3xs font-extrabold uppercase px-2 py-0.5 rounded bg-brand-100 text-brand-800">
                      {rec.levelGap}
                    </span>
                  </div>
                  <p className="text-2xs text-stone-600 leading-relaxed">{rec.reason}</p>
                </div>
                <div className="flex justify-end pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-2xs text-brand-700"
                    onClick={() => handleAddGoal(rec.title)}
                  >
                    {t('emp.career.addGoal')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Recommended Training */}
        <Card
          title={t('emp.career.recommendedCourses')}
          subtitle={t('emp.career.recommendedCoursesHint')}
          headerAction={<BookOpen className="w-4 h-4 text-brand-600" />}
        >
          <div className="space-y-3 pt-1">
            {[
              {
                title: t('emp.career.gap2'),
                provider: 'O’Reilly Enterprise',
                duration: '6 Hours',
                badge: t('emp.career.recommendedForStaff'),
                id: 'CRS-06',
              },
              {
                title: t('emp.career.course1'),
                provider: t('emp.career.course1Provider'),
                duration: '5 Hours',
                badge: t('emp.career.course1Tag'),
                id: 'CRS-07',
              },
              {
                title: t('emp.career.course2'),
                provider: t('emp.career.course2Provider'),
                duration: '7 Hours',
                badge: t('emp.career.course2Tag'),
                id: 'CRS-08',
              },
            ].map((course) => (
              <div
                key={course.title}
                className="p-3.5 rounded-xl bg-brand-50/50 border border-brand-100 flex items-center justify-between gap-3"
              >
                <div className="space-y-0.5">
                  <span className="text-3xs font-extrabold uppercase text-brand-700">
                    {course.badge}
                  </span>
                  <h4 className="text-xs font-bold text-stone-900">{course.title}</h4>
                  <span className="text-2xs text-stone-500">
                    {course.provider} • {course.duration}
                  </span>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  className="text-2xs shrink-0"
                  onClick={() => onNavigate && onNavigate('emp-training')}
                >
                  {t('emp.career.viewCourse')}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* 5. Career Milestones Timeline */}
      <Card
        title={t('emp.career.milestones')}
        subtitle={t('emp.career.milestonesHint')}
      >
        <div className="space-y-3 pt-1">
          {[
            {
              date: t('emp.career.ms1Date'),
              title: t('emp.career.ms1'),
              description: t('emp.career.ms1Body'),
              tag: t('emp.career.tagLeadership'),
            },
            {
              date: t('emp.career.ms2Date'),
              title: t('emp.career.ms2'),
              description: t('emp.career.ms2Body'),
              tag: 'Award',
            },
            {
              date: t('emp.career.ms3Date'),
              title: t('emp.career.ms3'),
              description: t('emp.career.ms3Body'),
              tag: t('emp.career.tagPromotion'),
            },
            {
              date: t('emp.career.ms4Date'),
              title: t('emp.career.ms4'),
              description: t('emp.career.ms4Body'),
              tag: t('emp.career.tagOnboarding'),
            },
          ].map((item, idx) => (
            <div
              key={idx}
              className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
            >
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-3xs font-extrabold uppercase px-2 py-0.5 rounded bg-brand-100 text-brand-800">
                    {item.tag}
                  </span>
                  <span className="text-xs font-bold text-stone-900">{item.title}</span>
                </div>
                <p className="text-2xs text-stone-600">{item.description}</p>
              </div>
              <span className="text-2xs font-semibold text-stone-400 shrink-0">
                {item.date}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
