import React, { useState, useEffect, useMemo } from 'react';
import {
  BookOpen,
  CheckCircle2,
  Clock,
  Award,
  Search,
  GraduationCap,
  Info,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { Modal } from '../../components/ui/Modal';
import { useToast } from '../../components/ui/Toast';
import { EmployeeTrainingRecord, MyEmployeeIdentity } from '../../types';
import { SmartHRApi } from '../../services/api';
import { useT } from '../../i18n';

/**
 * GET /employee-trainings/me returns only the assignments belonging to the
 * employees row linked to the signed-in account.
 *
 * The assignment row carries (employee_id, training_id, status, started_at,
 * completed_at) and the course carries (title, provider, duration_hours).
 * There is **no progress percentage, module count, score, category, due date
 * or instructor column**, so none of those are shown - status and the two
 * timestamps are the whole of what the database records about progress.
 */

const KNOWN_STATUSES = ['assigned', 'in_progress', 'completed', 'cancelled'];

const badgeVariant = (status: string | null) => {
  switch ((status ?? '').toLowerCase()) {
    case 'completed':
      return 'success' as const;
    case 'in_progress':
      return 'info' as const;
    case 'cancelled':
      return 'danger' as const;
    default:
      return 'neutral' as const;
  }
};

const asDate = (value: string | null): string =>
  value ? value.split('T')[0] : '—';

export const MyTrainingPage: React.FC = () => {
  const { t } = useT();

  // employee_trainings.status is free text in principle; a value outside the
  // four the router writes is shown as stored rather than as a missing key.
  const statusLabel = (status: string | null): string => {
    const token = (status ?? '').toLowerCase();
    if (KNOWN_STATUSES.includes(token)) return t(`status.training.${token}`);
    return status ?? t('emp.training.unknown');
  };
  const { showToast } = useToast();

  const [identity, setIdentity] = useState<MyEmployeeIdentity | null>(null);
  const [courses, setCourses] = useState<EmployeeTrainingRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [linkError, setLinkError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<'all' | 'in_progress' | 'completed' | 'assigned'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCourse, setSelectedCourse] = useState<EmployeeTrainingRecord | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [me, rows] = await Promise.all([
          SmartHRApi.getMyEmployee(),
          SmartHRApi.getMyTrainings(),
        ]);
        if (!cancelled) {
          setIdentity(me);
          setCourses(rows);
        }
      } catch (err) {
        if (!cancelled) {
          setLinkError(
            err instanceof Error ? err.message : t('emp.training.loadError')
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const counts = useMemo(() => {
    const by = (token: string) =>
      courses.filter((c) => (c.status ?? '').toLowerCase() === token).length;
    return {
      completed: by('completed'),
      inProgress: by('in_progress'),
      assigned: by('assigned'),
      cancelled: by('cancelled'),
    };
  }, [courses]);

  const completionRate = courses.length
    ? Math.round((counts.completed / courses.length) * 1000) / 10
    : 0;

  // trainings.duration_hours is the only hours figure stored; summing it over
  // completed assignments is the closest real equivalent to "hours logged".
  const hoursCompleted = useMemo(
    () =>
      courses
        .filter((c) => (c.status ?? '').toLowerCase() === 'completed')
        .reduce((sum, c) => sum + (c.training_duration_hours ?? 0), 0),
    [courses]
  );

  const filteredCourses = useMemo(
    () =>
      courses.filter((course) => {
        const status = (course.status ?? '').toLowerCase();
        const matchesTab = activeTab === 'all' ? true : status === activeTab;

        const needle = searchQuery.toLowerCase();
        const matchesSearch =
          !searchQuery ||
          (course.training_title ?? '').toLowerCase().includes(needle) ||
          (course.training_provider ?? '').toLowerCase().includes(needle);

        return matchesTab && matchesSearch;
      }),
    [courses, activeTab, searchQuery]
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.training.title')}
        subtitle={
          identity
            ? `Courses assigned to ${identity.full_name}`
            : t('emp.training.subtitle')
        }
        breadcrumbs={[
          { label: t('workspace.employee'), href: '#' },
          { label: t('emp.training.myTraining') },
        ]}
      />

      {linkError && (
        <Card>
          <div className="py-6 text-center">
            <Info className="w-6 h-6 text-stone-400 mx-auto mb-2" />
            <p className="text-sm font-bold text-stone-800">{t('emp.training.noneAvailable')}</p>
            <p className="text-xs text-stone-500 mt-1 max-w-xl mx-auto leading-relaxed">
              {linkError}
            </p>
          </div>
        </Card>
      )}

      {/* 1. Learning Hub KPI Summary - counted from your own assignments */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title={t('emp.training.completionRate')}
          value={`${completionRate}%`}
          change={`${counts.completed} of ${courses.length}`}
          changeType={completionRate >= 50 ? 'positive' : 'neutral'}
          comparison="completed assignments"
          icon={<Award className="w-5 h-5 text-brand-600" />}
        />
        <KpiCard
          title={t('emp.training.completedCourses')}
          value={counts.completed}
          change={counts.completed > 0 ? 'finished' : 'none yet'}
          changeType={counts.completed > 0 ? 'positive' : 'neutral'}
          comparison="status completed"
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
        />
        <KpiCard
          title={t('emp.training.inProgress')}
          value={counts.inProgress}
          change={`${counts.assigned} not started`}
          changeType="neutral"
          comparison="status in_progress"
          icon={<BookOpen className="w-5 h-5 text-amber-500" />}
        />
        <KpiCard
          title={t('emp.training.hoursCompleted')}
          value={`${hoursCompleted} hrs`}
          change="from course duration"
          changeType="neutral"
          comparison="trainings.duration_hours"
          icon={<GraduationCap className="w-5 h-5 text-sky-600" />}
        />
      </div>

      {/* 2. Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-1.5 p-1 bg-stone-100 rounded-xl">
          {[
            { id: 'all' as const, label: `All (${courses.length})` },
            { id: 'in_progress' as const, label: `${t('emp.training.inProgress')} (${counts.inProgress})` },
            { id: 'completed' as const, label: `${t('emp.training.completed')} (${counts.completed})` },
            { id: 'assigned' as const, label: `Not Started (${counts.assigned})` },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                activeTab === tab.id
                  ? 'bg-white text-brand-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-3.5 h-3.5 absolute start-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('emp.training.search')}
            className="w-full ps-9 pe-3 py-1.5 text-xs rounded-xl border border-stone-200 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
      </div>

      {/* 3. Course Cards Grid */}
      {filteredCourses.length === 0 ? (
        <Card>
          <div className="py-10 text-center space-y-2">
            <BookOpen className="w-7 h-7 text-stone-300 mx-auto" />
            <p className="text-sm font-bold text-stone-700">
              {isLoading
                ? t('emp.training.loading')
                : linkError
                ? t('emp.training.notLinked')
                : courses.length === 0
                ? t('emp.training.empty')
                : t('emp.training.noMatch')}
            </p>
            <p className="text-xs text-stone-500 max-w-md mx-auto leading-relaxed">
              {courses.length === 0 && !linkError && !isLoading
                ? t('emp.training.emptyHint')
                : ''}
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredCourses.map((course) => {
            const status = (course.status ?? '').toLowerCase();
            const isCompleted = status === 'completed';

            return (
              <div
                key={course.id}
                className="p-5 rounded-2xl bg-white border border-stone-200 shadow-sm hover:border-brand-300 hover:shadow-md transition-all flex flex-col justify-between gap-4"
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-3xs font-extrabold uppercase tracking-wider text-stone-400">
                      {course.training_provider ?? t('emp.training.noProvider')}
                    </span>
                    <Badge variant={badgeVariant(course.status)} dot={status === 'in_progress'}>
                      {statusLabel(course.status)}
                    </Badge>
                  </div>

                  <div className="space-y-1">
                    <h3 className="text-sm font-black text-stone-900 leading-snug">
                      {course.training_title ?? t('emp.training.untitled')}
                    </h3>
                    <p className="text-2xs text-stone-500 leading-relaxed">
                      {course.training_duration_hours
                        ? `${course.training_duration_hours} hours of content`
                        : t('emp.training.noDuration')}
                    </p>
                  </div>

                  <dl className="space-y-1 text-2xs pt-1 border-t border-stone-100">
                    <div className="flex justify-between pt-1.5">
                      <dt className="text-stone-500">{t('emp.training.started')}</dt>
                      <dd className="font-semibold text-stone-800">{asDate(course.started_at)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-stone-500">{t('emp.training.completed')}</dt>
                      <dd className="font-semibold text-stone-800">
                        {asDate(course.completed_at)}
                      </dd>
                    </div>
                  </dl>
                </div>

                <Button
                  variant={isCompleted ? 'outline' : 'primary'}
                  size="sm"
                  className="w-full text-xs font-bold justify-center"
                  leftIcon={
                    isCompleted ? (
                      <Award className="w-3.5 h-3.5" />
                    ) : (
                      <BookOpen className="w-3.5 h-3.5" />
                    )
                  }
                  onClick={() => setSelectedCourse(course)}
                >
                  {t('emp.training.viewDetails')}
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {/* 4. Course Details Modal */}
      {selectedCourse && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedCourse(null)}
          title={selectedCourse.training_title ?? t('emp.training.untitled')}
          subtitle={`${selectedCourse.training_provider ?? t('emp.training.noProvider')} • ${
            selectedCourse.training_duration_hours
              ? `${selectedCourse.training_duration_hours} hours`
              : 'duration not recorded'
          }`}
          size="lg"
          footer={
            <div className="flex justify-between items-center w-full">
              <span className="text-2xs text-stone-500">
                Assignment #{selectedCourse.id}
              </span>
              <Button variant="outline" onClick={() => setSelectedCourse(null)}>
                {t('action.close')}
              </Button>
            </div>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between p-3.5 rounded-xl bg-stone-50 border border-stone-200">
              <div>
                <span className="text-3xs font-bold text-stone-400 uppercase block">{t('table.status')}</span>
                <span className="text-sm font-black text-stone-900">
                  {statusLabel(selectedCourse.status)}
                </span>
              </div>
              <Badge variant={badgeVariant(selectedCourse.status)}>
                {statusLabel(selectedCourse.status)}
              </Badge>
            </div>

            <dl className="divide-y divide-stone-100">
              <div className="py-2.5 flex justify-between">
                <dt className="text-stone-500">{t('emp.training.started')}</dt>
                <dd className="font-bold text-stone-900">{asDate(selectedCourse.started_at)}</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-stone-500">{t('emp.training.completed')}</dt>
                <dd className="font-bold text-stone-900">{asDate(selectedCourse.completed_at)}</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-stone-500">{t('emp.training.duration')}</dt>
                <dd className="font-bold text-brand-700">
                  {selectedCourse.training_duration_hours
                    ? `${selectedCourse.training_duration_hours} hours`
                    : t('emp.training.notRecorded')}
                </dd>
              </div>
            </dl>

            <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 text-2xs text-stone-600 flex items-start gap-2">
              <Clock className="w-4 h-4 text-stone-400 shrink-0 mt-0.5" />
              <span>
                Progress is recorded as a status plus these two timestamps. The database
                stores no percentage, module count or score, so none is shown here. Your
                manager or HR moves an assignment between statuses.
              </span>
            </div>

            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-brand-700 font-semibold"
              onClick={() =>
                showToast(t('emp.training.statusByHr'), {
                  message:
                    t('emp.training.statusByHrHint'),
                  type: 'info',
                })
              }
            >
              {t('emp.training.howUpdate')}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
};
