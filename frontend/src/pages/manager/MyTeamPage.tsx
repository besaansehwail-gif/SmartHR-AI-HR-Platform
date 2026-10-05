import React, { useState, useMemo } from 'react';
import {
  Users,
  Search,
  Filter,
  Star,
  GraduationCap,
  MessageSquare,
  Clock,
  MoreVertical,
  CheckCircle2,
  Calendar,
  Laptop,
  Building2,
  MapPin,
  Eye,
  Plus,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input, Select, Textarea } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { initialTeamMembers, TeamMember } from '../../mock/managerData';
import { useT } from '../../i18n';

export interface MyTeamPageProps {
  onNavigateToPerformance?: () => void;
}

export const MyTeamPage: React.FC<MyTeamPageProps> = ({ onNavigateToPerformance }) => {
  const { t } = useT();
  const { showToast } = useToast();
  const [team, setTeam] = useState<TeamMember[]>(initialTeamMembers);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('ALL');
  const [workModeFilter, setWorkModeFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Modals
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null);
  const [isDossierOpen, setIsDossierOpen] = useState(false);
  const [isOneOnOneOpen, setIsOneOnOneOpen] = useState(false);
  const [oneOnOneNote, setOneOnOneNote] = useState('');

  const filteredTeam = useMemo(() => {
    return team.filter((member) => {
      const matchesSearch =
        searchQuery.trim() === '' ||
        member.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        member.position.toLowerCase().includes(searchQuery.toLowerCase()) ||
        member.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        member.location.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesDept = departmentFilter === 'ALL' || member.department === departmentFilter;
      const matchesWorkMode = workModeFilter === 'ALL' || member.workMode === workModeFilter;
      const matchesStatus = statusFilter === 'ALL' || member.attendanceStatus === statusFilter;

      return matchesSearch && matchesDept && matchesWorkMode && matchesStatus;
    });
  }, [team, searchQuery, departmentFilter, workModeFilter, statusFilter]);

  const handleOpenDossier = (member: TeamMember) => {
    setSelectedMember(member);
    setIsDossierOpen(true);
  };

  const handleOpenOneOnOne = (member: TeamMember) => {
    setSelectedMember(member);
    setOneOnOneNote('');
    setIsOneOnOneOpen(true);
  };

  const handleSaveOneOnOne = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMember) return;
    showToast('1:1 Notes Logged', {
      message: `Supervisor notes for ${selectedMember.name} recorded in team journal.`,
      type: 'success',
    });
    setIsOneOnOneOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('mgr.team.title')}
        subtitle={t('mgr.team.subtitle')}
        badge={
          <Badge variant="purple" dot>
            {team.length} Direct Reports
          </Badge>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            leftIcon={<MessageSquare className="w-3.5 h-3.5" />}
            onClick={() => {
              if (team.length > 0) handleOpenOneOnOne(team[0]);
            }}
          >
            + {t('mgr.team.logCheckin')}
          </Button>
        }
      />

      {/* Filter Toolbar */}
      <Card>
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('mgr.team.search')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto flex-wrap">
            <select
              value={departmentFilter}
              onChange={(e) => setDepartmentFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="ALL">{t('mgr.team.allDepartments')}</option>
              <option value="Engineering">{t('mgr.team.deptEngineering')}</option>
              <option value="Product & Design">{t('mgr.team.deptProduct')}</option>
            </select>

            <select
              value={workModeFilter}
              onChange={(e) => setWorkModeFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="ALL">{t('mgr.team.allWorkModes')}</option>
              <option value="Remote">{t('badge.workMode.remote')}</option>
              <option value="Hybrid">{t('badge.workMode.hybrid')}</option>
              <option value="Onsite">{t('badge.workMode.onsite')}</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="ALL">{t('mgr.team.allAttendance')}</option>
              <option value="Present">{t('status.attendance.Present')}</option>
              <option value="Remote Active">{t('mgr.team.remoteActive')}</option>
              <option value="Late">{t('status.attendance.Late')}</option>
              <option value="On Leave">{t('status.attendance.On Leave')}</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Team Management Table */}
      <Card noPadding>
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3.5 px-4">{t('table.employee')}</th>
                <th className="py-3.5 px-4">{t('mgr.team.colPositionDept')}</th>
                <th className="py-3.5 px-4">{t('mgr.team.colWorkMode')}</th>
                <th className="py-3.5 px-4">{t('mgr.team.colAttendance')}</th>
                <th className="py-3.5 px-4">{t('mgr.team.colRating')}</th>
                <th className="py-3.5 px-4">{t('mgr.team.colTraining')}</th>
                <th className="py-3.5 px-4 text-end">{t('mgr.team.colActions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {filteredTeam.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    <Users className="w-8 h-8 mx-auto mb-2 text-stone-300" />
                    <p className="font-semibold text-stone-600">{t('mgr.team.empty')}</p>
                  </td>
                </tr>
              ) : (
                filteredTeam.map((member) => (
                  <tr key={member.id} className="hover:bg-stone-50/60 transition-colors">
                    {/* Employee info */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-brand-700 text-white font-bold text-xs flex items-center justify-center shrink-0 ring-2 ring-brand-100">
                          {member.firstName[0]}
                          {member.lastName[0]}
                        </div>
                        <div>
                          <p className="font-bold text-stone-900 text-xs hover:text-brand-700 cursor-pointer" onClick={() => handleOpenDossier(member)}>
                            {member.name}
                          </p>
                          <p className="text-2xs text-stone-400">{member.email}</p>
                        </div>
                      </div>
                    </td>

                    {/* Position & Dept */}
                    <td className="py-3 px-4">
                      <p className="font-semibold text-stone-800 text-xs">{member.position}</p>
                      <p className="text-3xs text-brand-700 font-bold uppercase tracking-wider">{member.department}</p>
                    </td>

                    {/* Work Mode */}
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-bold ${
                          member.workMode === 'Remote'
                            ? 'bg-brand-50 text-brand-700 border border-brand-200'
                            : member.workMode === 'Hybrid'
                            ? 'bg-sky-50 text-sky-700 border border-sky-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        {member.workMode === 'Remote' ? (
                          <Laptop className="w-3 h-3" />
                        ) : member.workMode === 'Hybrid' ? (
                          <Building2 className="w-3 h-3" />
                        ) : (
                          <MapPin className="w-3 h-3" />
                        )}
                        {member.workMode === 'Remote'
                          ? t('badge.workMode.remote')
                          : member.workMode === 'Hybrid'
                            ? t('badge.workMode.hybrid')
                            : t('badge.workMode.onsite')}
                      </span>
                    </td>

                    {/* Attendance Status */}
                    <td className="py-3 px-4">
                      <div className="space-y-0.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-3xs font-bold ${
                            member.attendanceStatus === 'Present' ||
                            member.attendanceStatus === 'Remote Active'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : member.attendanceStatus === 'Late'
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : 'bg-stone-100 text-stone-600'
                          }`}
                        >
                          {member.attendanceStatus === 'Remote Active'
                            ? t('mgr.team.remoteActive')
                            : t(`status.attendance.${member.attendanceStatus}`)}
                        </span>
                        {member.checkInTime && member.checkInTime !== '—' && (
                          <span className="block text-3xs text-stone-400">
                            In: {member.checkInTime}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Performance Rating */}
                    <td className="py-3 px-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-1">
                          <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                          <span className="font-extrabold text-stone-900 text-xs">
                            {member.performanceScore} / 5.0
                          </span>
                        </div>
                        <span className="text-3xs text-stone-400 block truncate max-w-[130px]">
                          {member.performanceTier}
                        </span>
                      </div>
                    </td>

                    {/* Training Progress */}
                    <td className="py-3 px-4">
                      <div className="space-y-1 min-w-[110px]">
                        <div className="flex justify-between text-3xs font-bold text-stone-600">
                          <span>{member.trainingProgress}%</span>
                          <span className="text-stone-400">{member.completedCoursesCount}/{member.totalAssignedCourses}</span>
                        </div>
                        <div className="w-full h-1.5 rounded-full bg-stone-100 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              member.trainingProgress === 100
                                ? 'bg-emerald-500'
                                : 'bg-brand-600'
                            }`}
                            style={{ width: `${member.trainingProgress}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Manager Actions */}
                    <td className="py-3 px-4 text-end">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs text-brand-700 hover:bg-brand-50"
                          onClick={() => handleOpenDossier(member)}
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-2xs"
                          onClick={() => handleOpenOneOnOne(member)}
                        >
                          1:1 Note
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Member Dossier Modal */}
      {selectedMember && (
        <Modal
          isOpen={isDossierOpen}
          onClose={() => setIsDossierOpen(false)}
          title={`Team Member: ${selectedMember.name}`}
          subtitle={`${selectedMember.position} • ${selectedMember.department}`}
          size="lg"
        >
          <div className="space-y-5 text-xs">
            {/* Header info card */}
            <div className="p-4 rounded-xl bg-brand-50/60 border border-brand-100 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-brand-700 text-white font-black text-base flex items-center justify-center shadow-xs">
                  {selectedMember.firstName[0]}
                  {selectedMember.lastName[0]}
                </div>
                <div>
                  <h3 className="font-extrabold text-sm text-stone-900">{selectedMember.name}</h3>
                  <p className="text-2xs text-brand-800 font-medium">{selectedMember.email} • {selectedMember.location}</p>
                  <p className="text-3xs text-stone-500 mt-0.5">Tenure: {selectedMember.tenure} • Weekly: {selectedMember.weeklyHours} hrs</p>
                </div>
              </div>

              <div className="text-end">
                <span className="text-3xs font-bold uppercase tracking-wider text-stone-400 block">{t('mgr.team.colRating')}</span>
                <span className="text-xl font-black text-brand-900 flex items-center gap-1 justify-end">
                  <Star className="w-4 h-4 text-amber-500 fill-amber-500" />
                  {selectedMember.performanceScore} / 5.0
                </span>
                <span className="text-3xs text-emerald-700 font-bold">{selectedMember.performanceTier}</span>
              </div>
            </div>

            {/* Key Goals & OKRs */}
            <div>
              <h4 className="font-bold text-stone-900 text-xs mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-brand-600" />
                {t('mgr.team.okrs')}
              </h4>
              <div className="space-y-2">
                {selectedMember.keyGoals.map((g, idx) => (
                  <div key={idx} className="p-3 rounded-lg bg-stone-50 border border-stone-200/80 space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-semibold text-stone-800">{g.title}</span>
                      <span
                        className={`text-3xs font-bold px-2 py-0.5 rounded-full ${
                          g.status === 'Completed'
                            ? 'bg-emerald-50 text-emerald-700'
                            : g.status === 'At Risk'
                            ? 'bg-rose-50 text-rose-700'
                            : 'bg-brand-50 text-brand-700'
                        }`}
                      >
                        {g.status === 'Completed'
                          ? t('mgr.team.goalCompleted')
                          : g.status === 'At Risk'
                            ? t('mgr.team.goalAtRisk')
                            : t('mgr.team.goalOnTrack')}{' '}
                        ({g.progress}%)
                      </span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-stone-200 overflow-hidden">
                      <div
                        className="h-full bg-brand-600 rounded-full"
                        style={{ width: `${g.progress}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Skills Snapshot */}
            <div>
              <h4 className="font-bold text-stone-900 text-xs mb-2">{t('mgr.team.competencies')}</h4>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(selectedMember.skills).map(([skill, level]) => (
                  <div key={skill} className="p-2.5 rounded-lg border border-stone-100 bg-white flex justify-between items-center">
                    <span className="font-semibold text-stone-700 text-2xs">{skill}</span>
                    <span className="font-mono font-black text-brand-700 text-2xs">
                      Level {level} / 5
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Recent Supervisor Feedback */}
            <div className="p-3 rounded-lg bg-stone-50 border border-stone-200 text-stone-600 text-2xs italic">
              <strong className="not-italic font-bold text-stone-800 block mb-0.5">{t('mgr.team.feedbackNotes')}</strong>
              "{selectedMember.recentFeedback}"
            </div>

            <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setIsDossierOpen(false)}>
                {t('action.close')}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setIsDossierOpen(false);
                  handleOpenOneOnOne(selectedMember);
                }}
              >
                {t('mgr.team.logNote')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* 1-on-1 Check-in Modal */}
      {selectedMember && (
        <Modal
          isOpen={isOneOnOneOpen}
          onClose={() => setIsOneOnOneOpen(false)}
          title={t('mgr.team.logCheckinFor', { name: selectedMember.name })}
          subtitle={t('mgr.team.noteHint')}
          size="md"
        >
          <form onSubmit={handleSaveOneOnOne} className="space-y-4">
            <div className="p-3 rounded-lg bg-stone-50 border border-stone-200 text-xs">
              <span className="font-bold text-stone-900 block">{selectedMember.position}</span>
              <span className="text-stone-500 text-2xs">Current OKR status: 2 on track, capacity at {selectedMember.capacityUtilization}%</span>
            </div>

            <Textarea
              label={t('mgr.team.discussion')}
              required
              rows={4}
              value={oneOnOneNote}
              onChange={(e) => setOneOnOneNote(e.target.value)}
              placeholder={t('mgr.team.discussionPlaceholder')}
            />

            <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
              <Button variant="outline" size="sm" type="button" onClick={() => setIsOneOnOneOpen(false)}>
                {t('action.cancel')}
              </Button>
              <Button variant="primary" size="sm" type="submit">
                {t('mgr.team.saveNote')}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
