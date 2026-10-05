import React, { useState } from 'react';
import {
  TrendingUp,
  Download,
  Users,
  Calendar,
  Clock,
  Star,
  GraduationCap,
  Laptop,
  Building2,
  MapPin,
  Activity,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Award,
  BarChart2,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { KpiCard } from '../../components/ui/KpiCard';
import { useToast } from '../../components/ui/Toast';
import {
  initialTeamMembers,
  managerSkillsMatrixData,
} from '../../mock/managerData';
import { useT } from '../../i18n';

export const ManagerInsightsPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();
  const [selectedPeriod, setSelectedPeriod] = useState('Q3_2024');

  const totalTeam = initialTeamMembers.length;
  const avgUtilization = (
    initialTeamMembers.reduce((acc, m) => acc + m.capacityUtilization, 0) /
    initialTeamMembers.filter((m) => m.capacityUtilization > 0).length
  ).toFixed(0);

  const handleExport = () => {
    showToast(t('mgr.ins.exported'), {
      message: t('mgr.ins.exportedMessage'),
      type: 'success',
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('mgr.ins.title')}
        subtitle={t('mgr.ins.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {t('mgr.ins.engineActive')}
          </Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="text-xs font-semibold px-3 py-2 rounded-lg border border-stone-200 bg-white text-stone-700 shadow-2xs focus:outline-none"
            >
              <option value="Q3_2024">{t('mgr.ins.currentQuarter')}</option>
              <option value="Q2_2024">{t('mgr.ins.previousQuarter')}</option>
              <option value="YTD_2024">{t('mgr.ins.ytd')}</option>
            </select>
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Download className="w-3.5 h-3.5" />}
              onClick={handleExport}
            >
              {t('mgr.ins.export')}
            </Button>
          </div>
        }
      />

      {/* Top Overview KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <KpiCard
          title={t('mgr.ins.headcount')}
          value={totalTeam}
          change="+1 hire in Q3"
          changeType="positive"
          comparison="Full capacity"
          icon={<Users className="w-5 h-5 text-brand-600" />}
          description={t('mgr.ins.avgTenure')}
        />
        <KpiCard
          title={t('mgr.ins.capacity')}
          value={`${avgUtilization}%`}
          change="Optimal Band"
          changeType="positive"
          comparison="Target: 80-88%"
          icon={<Activity className="w-5 h-5 text-emerald-600" />}
          description={t('mgr.ins.zeroOverload')}
        />
        <KpiCard
          title={t('mgr.ins.avgPunctuality')}
          value="96.2%"
          change="+1.8% vs Q2"
          changeType="positive"
          comparison="98.5% remote active"
          icon={<Clock className="w-5 h-5 text-brand-600" />}
          description={t('mgr.ins.highAdherence')}
        />
        <KpiCard
          title={t('mgr.ins.skillsInventory')}
          value="8 Disciplines"
          change="4.55 avg proficiency"
          changeType="positive"
          comparison="Out of 5.0"
          icon={<Zap className="w-5 h-5 text-amber-500" />}
          description={t('mgr.ins.cloudReady')}
        />
      </div>

      {/* Row 1: Attendance Trends & Leave Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Attendance Trends */}
        <Card
          title={t('mgr.ins.attendanceTrends')}
          subtitle={t('mgr.ins.attendanceTrendsHint')}
          headerAction={<Badge variant="success">96.2% Avg Adherence</Badge>}
        >
          <div className="space-y-4 pt-2">
            <div className="h-44 flex items-end justify-between gap-3 px-2 border-b border-stone-100 pb-2">
              {[
                { week: 'Wk 32', rate: 93, hours: 472 },
                { week: 'Wk 33', rate: 95, hours: 480 },
                { week: 'Wk 34', rate: 94, hours: 476 },
                { week: 'Wk 35', rate: 97, hours: 485 },
                { week: 'Wk 36', rate: 96, hours: 482 },
                { week: 'Wk 37', rate: 98, hours: 488 },
              ].map((item) => (
                <div key={item.week} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end">
                  <span className="text-3xs font-mono font-bold text-brand-900">{item.rate}%</span>
                  <div
                    className="w-full rounded-t-lg bg-gradient-to-t from-brand-800 to-brand-600 transition-all hover:opacity-90"
                    style={{ height: `${(item.rate - 85) * 6.5}%` }}
                  />
                  <span className="text-3xs font-semibold text-stone-500 mt-1">{item.week}</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
              <div className="p-2 rounded-lg bg-stone-50 border border-stone-100">
                <span className="text-3xs text-stone-400 block font-semibold">{t('mgr.ins.totalHours')}</span>
                <span className="font-extrabold text-stone-900 text-sm">488.5 hrs</span>
              </div>
              <div className="p-2 rounded-lg bg-stone-50 border border-stone-100">
                <span className="text-3xs text-stone-400 block font-semibold">{t('mgr.ins.overtime')}</span>
                <span className="font-extrabold text-brand-700 text-sm">4.2 hrs (Low)</span>
              </div>
              <div className="p-2 rounded-lg bg-stone-50 border border-stone-100">
                <span className="text-3xs text-stone-400 block font-semibold">{t('mgr.ins.onTimeCheckins')}</span>
                <span className="font-extrabold text-emerald-700 text-sm">98.1%</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Leave Trends */}
        <Card
          title={t('mgr.ins.leaveTrends')}
          subtitle={t('mgr.ins.leaveTrendsHint')}
          headerAction={<Badge variant="neutral">28 Days Total</Badge>}
        >
          <div className="space-y-3.5 pt-2">
            {[
              { type: t('mgr.ins.leaveAnnual'), days: 16, pct: 57, color: 'bg-brand-600' },
              { type: t('mgr.ins.leaveSick'), days: 5, pct: 18, color: 'bg-rose-500' },
              { type: t('mgr.ins.leaveEmergency'), days: 4, pct: 14, color: 'bg-amber-500' },
              { type: t('mgr.ins.leaveTraining'), days: 3, pct: 11, color: 'bg-sky-500' },
            ].map((cat) => (
              <div key={cat.type} className="space-y-1">
                <div className="flex justify-between items-center text-xs font-semibold">
                  <span className="text-stone-800">{cat.type}</span>
                  <span className="text-stone-600">
                    <strong className="text-stone-900">{cat.days} days</strong> ({cat.pct}%)
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-stone-100 overflow-hidden">
                  <div className={`h-full rounded-full ${cat.color}`} style={{ width: `${cat.pct}%` }} />
                </div>
              </div>
            ))}

            <div className="p-3 rounded-xl bg-brand-50/50 border border-brand-100 text-2xs text-brand-900 flex items-center justify-between">
              <span>{t('mgr.ins.remainingBalance')} <strong className="font-bold">142 Days</strong></span>
              <span className="font-bold text-emerald-700">{t('mgr.ins.healthyAccrual')}</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Row 2: Skills Matrix (Interactive Heatmap) */}
      <Card
        title={t('mgr.ins.skillsMatrix')}
        subtitle={t('mgr.ins.skillsMatrixHint')}
        headerAction={
          <Badge variant="purple" dot>
            8 Core Disciplines
          </Badge>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3 px-4">{t('mgr.ins.colDiscipline')}</th>
                <th className="py-3 px-4">{t('mgr.ins.colChampion')}</th>
                <th className="py-3 px-4">{t('mgr.ins.colAvgProficiency')}</th>
                <th className="py-3 px-4">{t('mgr.ins.colCertified')}</th>
                <th className="py-3 px-4">{t('mgr.ins.colGauge')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {managerSkillsMatrixData.map((item) => (
                <tr key={item.skill} className="hover:bg-stone-50/60 transition-colors">
                  <td className="py-3 px-4 font-bold text-stone-900">{item.skill}</td>
                  <td className="py-3 px-4 font-semibold text-brand-900">
                    <span className="inline-flex items-center gap-1">
                      <Award className="w-3.5 h-3.5 text-amber-500" />
                      {item.lead}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono font-bold text-stone-900">
                    {item.avgProficiency} / 5.0
                  </td>
                  <td className="py-3 px-4 font-semibold text-stone-700">
                    {item.trainedCount} / {totalTeam} ({((item.trainedCount / totalTeam) * 100).toFixed(0)}%)
                  </td>
                  <td className="py-3 px-4 min-w-[140px]">
                    <div className="w-full h-2 rounded-full bg-stone-100 overflow-hidden">
                      <div
                        className="h-full bg-brand-700 rounded-full"
                        style={{ width: `${(item.avgProficiency / 5.0) * 100}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Row 3: Team Workload Indicators & Training Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Team Workload & Burnout Indicator */}
        <Card
          title={t('mgr.ins.workload')}
          subtitle={t('mgr.ins.workloadHint')}
          headerAction={<Badge variant="success">{t('mgr.ins.optimalLoad')}</Badge>}
        >
          <div className="space-y-4 pt-1">
            <div className="flex items-center justify-between p-4 rounded-xl bg-stone-50 border border-stone-200">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-emerald-100 text-emerald-800">
                  <Activity className="w-6 h-6" />
                </div>
                <div>
                  <span className="text-3xs text-stone-400 font-bold uppercase block">{t('mgr.ins.healthScore')}</span>
                  <p className="text-xl font-black text-stone-900">92 / 100 (Optimal)</p>
                  <p className="text-2xs text-emerald-700 font-medium">{t('mgr.ins.zeroBurnout')}</p>
                </div>
              </div>
              <Badge variant="success" dot>{t('mgr.ins.sustainableVelocity')}</Badge>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between font-medium text-stone-600">
                <span>{t('mgr.ins.heavyBand')}</span>
                <span className="font-bold text-stone-900">2 Members (Chloe, Tariq)</span>
              </div>
              <div className="flex justify-between font-medium text-stone-600">
                <span>{t('mgr.ins.optimalBand')}</span>
                <span className="font-bold text-stone-900">6 Members</span>
              </div>
              <div className="flex justify-between font-medium text-stone-600">
                <span>{t('mgr.ins.growthBand')}</span>
                <span className="font-bold text-stone-900">2 Members (Hannah, Lucas)</span>
              </div>
              <div className="flex justify-between font-medium text-stone-600">
                <span>{t('mgr.ins.onApprovedLeave')}</span>
                <span className="font-bold text-stone-900">2 Members (Mateo, Kenji)</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Training Progress Overview */}
        <Card
          title={t('mgr.ins.trainingProgress')}
          subtitle={t('mgr.ins.trainingProgressHint')}
          headerAction={<Badge variant="purple">84% Completion</Badge>}
        >
          <div className="space-y-4 pt-1">
            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-brand-50/60 border border-brand-100 space-y-1.5">
                <div className="flex justify-between items-center font-bold">
                  <span className="text-brand-950">{t('mgr.ins.soc2')}</span>
                  <span className="text-brand-900">10 / 12 Finished (83%)</span>
                </div>
                <div className="w-full h-2 rounded-full bg-brand-200 overflow-hidden">
                  <div className="h-full bg-brand-700 rounded-full" style={{ width: '83%' }} />
                </div>
                <span className="text-3xs text-brand-700 block">{t('mgr.ins.soc2Hint')}</span>
              </div>

              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 space-y-1.5">
                <div className="flex justify-between items-center font-bold">
                  <span className="text-stone-800">{t('mgr.ins.distributed')}</span>
                  <span className="text-stone-700">7 / 8 Engineers (88%)</span>
                </div>
                <div className="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                  <div className="h-full bg-emerald-600 rounded-full" style={{ width: '88%' }} />
                </div>
                <span className="text-3xs text-stone-500 block">{t('mgr.ins.upskilling')}</span>
              </div>

              <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 space-y-1.5">
                <div className="flex justify-between items-center font-bold">
                  <span className="text-stone-800">{t('mgr.ins.accessibility')}</span>
                  <span className="text-stone-700">4 / 4 Product & Design (100%)</span>
                </div>
                <div className="w-full h-2 rounded-full bg-stone-200 overflow-hidden">
                  <div className="h-full bg-emerald-600 rounded-full" style={{ width: '100%' }} />
                </div>
                <span className="text-3xs text-emerald-700 font-bold block">✓ 100% Completed</span>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
