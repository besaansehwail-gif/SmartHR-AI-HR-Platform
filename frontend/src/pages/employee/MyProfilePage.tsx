import React, { useState } from 'react';
import {
  User,
  Mail,
  Phone,
  Building2,
  Briefcase,
  Calendar,
  MapPin,
  Clock,
  Shield,
  Edit3,
  Award,
  CheckCircle2,
  Globe,
  HeartHandshake,
  Laptop,
  Star,
  Plus,
  X,
  Camera,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { initialEmployeeProfile, EmployeeProfile } from '../../mock/employeeData';
import { WorkMode } from '../../types';
import { useT } from '../../i18n';

export const MyProfilePage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();
  const [profile, setProfile] = useState<EmployeeProfile>(initialEmployeeProfile);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  // Edit form state
  const [formName, setFormName] = useState(profile.name);
  const [formPreferredName, setFormPreferredName] = useState(profile.preferredName || '');
  const [formPhone, setFormPhone] = useState(profile.phone);
  const [formBio, setFormBio] = useState(profile.bio);
  const [formWorkMode, setFormWorkMode] = useState<WorkMode>(profile.workMode);
  const [formEmergencyName, setFormEmergencyName] = useState(profile.emergencyContact.name);
  const [formEmergencyRel, setFormEmergencyRel] = useState(profile.emergencyContact.relationship);
  const [formEmergencyPhone, setFormEmergencyPhone] = useState(profile.emergencyContact.phone);
  const [skillsList, setSkillsList] = useState<string[]>(profile.skills);
  const [newSkillInput, setNewSkillInput] = useState('');

  const handleOpenEdit = () => {
    setFormName(profile.name);
    setFormPreferredName(profile.preferredName || '');
    setFormPhone(profile.phone);
    setFormBio(profile.bio);
    setFormWorkMode(profile.workMode);
    setFormEmergencyName(profile.emergencyContact.name);
    setFormEmergencyRel(profile.emergencyContact.relationship);
    setFormEmergencyPhone(profile.emergencyContact.phone);
    setSkillsList([...profile.skills]);
    setIsEditModalOpen(true);
  };

  const handleAddSkill = () => {
    if (newSkillInput.trim() && !skillsList.includes(newSkillInput.trim())) {
      setSkillsList([...skillsList, newSkillInput.trim()]);
      setNewSkillInput('');
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkillsList(skillsList.filter((s) => s !== skillToRemove));
  };

  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    setProfile({
      ...profile,
      name: formName,
      preferredName: formPreferredName,
      phone: formPhone,
      bio: formBio,
      workMode: formWorkMode,
      emergencyContact: {
        name: formEmergencyName,
        relationship: formEmergencyRel,
        phone: formEmergencyPhone,
      },
      skills: skillsList,
    });
    setIsEditModalOpen(false);
    showToast(t('emp.profile.updated'), {
      message: t('emp.profile.updatedMessage'),
      type: 'success',
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('emp.profile.title')}
        subtitle={t('emp.profile.pageSubtitle')}
        breadcrumbs={[
          { label: t('emp.profile.breadcrumbSpace'), href: '#' },
          { label: t('emp.profile.title'), active: true },
        ]}
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Edit3 className="w-4 h-4" />}
            onClick={handleOpenEdit}
          >
            {t('emp.profile.editProfile')}
          </Button>
        }
      />

      {/* Hero Profile Overview Card */}
      <div className="p-6 rounded-2xl bg-white border border-stone-200 shadow-sm relative overflow-hidden">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5">
            <div className="relative group">
              <img
                src={profile.avatar}
                alt={profile.name}
                className="w-24 h-24 sm:w-28 sm:h-28 rounded-2xl object-cover border-4 border-white shadow-md ring-2 ring-brand-500/20"
              />
              <button
                type="button"
                onClick={handleOpenEdit}
                className="absolute bottom-1 end-1 p-1.5 rounded-lg bg-brand-700 text-white shadow-sm hover:bg-brand-800 transition-colors"
                title={t('emp.profile.changePhoto')}
              >
                <Camera className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-2xl font-black text-stone-900 tracking-tight">
                  {profile.name}
                </h1>
                {profile.preferredName && profile.preferredName !== profile.name && (
                  <span className="text-xs text-stone-500 font-medium">
                    (Preferred: {profile.preferredName})
                  </span>
                )}
                <Badge variant="success" dot>
                  {profile.employmentStatus}
                </Badge>
                <Badge variant="purple">
                  {profile.gradeLevel}
                </Badge>
              </div>

              <p className="text-sm font-bold text-brand-700">
                {profile.position} • {profile.department}
              </p>

              <div className="flex items-center gap-4 text-xs text-stone-500 flex-wrap pt-1">
                <span className="flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5 text-stone-400" />
                  ID: <strong className="text-stone-800 font-mono">{profile.employeeId}</strong>
                </span>
                <span className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-stone-400" />
                  {profile.officeLocation}
                </span>
                <span className="flex items-center gap-1.5">
                  <Laptop className="w-3.5 h-3.5 text-stone-400" />
                  {t('emp.profile.mode')} <strong className="text-brand-700 font-semibold">{profile.workMode}</strong>
                </span>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-brand-50/60 border border-brand-100 flex flex-col items-start sm:items-end gap-2 shrink-0 self-stretch md:self-auto">
            <span className="text-3xs font-extrabold uppercase tracking-wider text-brand-800">
              {t('emp.profile.supervisor')}
            </span>
            <div className="flex items-center gap-2.5">
              <img
                src={profile.managerAvatar}
                alt={profile.manager}
                className="w-9 h-9 rounded-full object-cover border border-brand-200"
              />
              <div className="text-start sm:text-end">
                <span className="text-xs font-bold text-stone-900 block leading-tight">
                  {profile.manager}
                </span>
                <span className="text-3xs text-brand-700 font-medium block">
                  {profile.managerTitle}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Personal & Contact info vs Work info & Skills */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Personal Information & Contact */}
        <div className="space-y-6">
          {/* Personal Information */}
          <Card title={t('emp.profile.personalInfo')} subtitle={t('emp.profile.officialRecords')}>
            <dl className="divide-y divide-stone-100 text-xs">
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium">{t('emp.profile.legalName')}</dt>
                <dd className="font-bold text-stone-900 text-end">{profile.name}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium">{t('emp.profile.employeeId')}</dt>
                <dd className="font-mono font-bold text-brand-700 text-end">{profile.employeeId}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium">{t('emp.profile.hireDate')}</dt>
                <dd className="font-semibold text-stone-900 text-end">{profile.hireDate}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium">{t('emp.profile.tenure')}</dt>
                <dd className="font-semibold text-stone-900 text-end">{profile.tenure}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium">{t('emp.profile.employmentType')}</dt>
                <dd className="font-semibold text-stone-900 text-end">{profile.employmentType}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium">{t('emp.profile.timezone')}</dt>
                <dd className="font-semibold text-stone-900 text-end">{profile.timezone}</dd>
              </div>
            </dl>
          </Card>

          {/* Contact Information */}
          <Card title={t('emp.profile.contactInfo')} subtitle={t('emp.profile.contactChannels')}>
            <dl className="divide-y divide-stone-100 text-xs">
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-stone-400" />
                  {t('emp.profile.corporateEmail')}
                </dt>
                <dd className="font-semibold text-brand-700 text-end">{profile.email}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium flex items-center gap-1.5">
                  <Phone className="w-3.5 h-3.5 text-stone-400" />
                  {t('emp.profile.phoneNumber')}
                </dt>
                <dd className="font-semibold text-stone-900 text-end">{profile.phone}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-2">
                <dt className="text-stone-500 font-medium flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-stone-400" />
                  {t('emp.profile.desk')}
                </dt>
                <dd className="font-semibold text-stone-900 text-end">{profile.deskLocation}</dd>
              </div>
            </dl>

            <div className="mt-4 p-3 rounded-xl bg-stone-50 border border-stone-200">
              <span className="text-3xs font-bold uppercase tracking-wider text-stone-500 block mb-1.5 flex items-center gap-1">
                <HeartHandshake className="w-3.5 h-3.5 text-rose-500" />
                {t('emp.profile.emergencyContact')}
              </span>
              <div className="text-xs space-y-0.5">
                <div className="font-bold text-stone-900">{profile.emergencyContact.name}</div>
                <div className="text-stone-500">
                  {profile.emergencyContact.relationship} • {profile.emergencyContact.phone}
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Right 2 Columns: Position & Org, Work Mode & Policy, Skills & Bio */}
        <div className="lg:col-span-2 space-y-6">
          {/* Bio & Professional Summary */}
          <Card title={t('emp.profile.professionalSummary')} subtitle={t('emp.profile.roleCharter')}>
            <p className="text-xs text-stone-700 leading-relaxed font-normal">
              {profile.bio}
            </p>
          </Card>

          {/* Department, Position & Work Mode Details */}
          <Card title={t('emp.profile.roleConfig')} subtitle={t('emp.profile.corporateAssignment')}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 space-y-2">
                <span className="text-3xs font-extrabold uppercase text-stone-400 tracking-wider">
                  {t('emp.profile.orgPlacement')}
                </span>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-stone-500">{t('table.department')}</span>
                    <span className="font-bold text-stone-900">{profile.department}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-500">{t('emp.profile.officialPosition')}</span>
                    <span className="font-bold text-stone-900">{profile.position}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-500">{t('emp.profile.gradeLevel')}</span>
                    <span className="font-bold text-brand-700">{profile.gradeLevel}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-500">{t('emp.profile.reportingLine')}</span>
                    <span className="font-bold text-stone-900">{profile.manager}</span>
                  </div>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-brand-50/50 border border-brand-100 space-y-2">
                <span className="text-3xs font-extrabold uppercase text-brand-700 tracking-wider">
                  {t('emp.profile.workModeHours')}
                </span>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-stone-600">{t('emp.profile.workMode')}</span>
                    <Badge variant="purple">{profile.workMode}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-600">{t('emp.profile.schedule')}</span>
                    <span className="font-semibold text-stone-900">{profile.workSchedule}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-600">{t('emp.profile.officePolicy')}</span>
                    <span className="font-semibold text-stone-900">2 Days / Week (Tue, Wed)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-600">{t('emp.profile.primaryCampus')}</span>
                    <span className="font-semibold text-stone-900">{profile.officeLocation}</span>
                  </div>
                </div>
              </div>
            </div>
          </Card>

          {/* Skills Portfolio */}
          <Card
            title={t('emp.profile.skills')}
            subtitle={t('emp.profile.skillsHint')}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                leftIcon={<Plus className="w-3.5 h-3.5" />}
                onClick={handleOpenEdit}
              >
                {t('emp.profile.addSkill')}
              </Button>
            }
          >
            <div className="flex flex-wrap gap-2 pt-1">
              {profile.skills.map((skill) => (
                <div
                  key={skill}
                  className="px-3 py-1.5 rounded-xl bg-stone-100 border border-stone-200 text-xs font-semibold text-stone-800 flex items-center gap-1.5 shadow-xs"
                >
                  <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                  {skill}
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* Edit Profile Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title={t('emp.profile.editTitle')}
        subtitle={t('emp.profile.editSubtitle')}
        size="lg"
        footer={
          <div className="flex justify-end gap-2.5">
            <Button variant="outline" onClick={() => setIsEditModalOpen(false)}>
              {t('action.cancel')}
            </Button>
            <Button variant="primary" onClick={handleSaveProfile}>
              {t('emp.profile.saveChanges')}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSaveProfile} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-2xs font-bold text-stone-700 mb-1">
                {t('emp.profile.legalNameField')}
              </label>
              <Input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder={t('emp.profile.fullName')}
                required
              />
            </div>
            <div>
              <label className="block text-2xs font-bold text-stone-700 mb-1">
                {t('emp.profile.preferredName')}
              </label>
              <Input
                value={formPreferredName}
                onChange={(e) => setFormPreferredName(e.target.value)}
                placeholder={t('emp.profile.preferredNamePlaceholder')}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-2xs font-bold text-stone-700 mb-1">
                {t('emp.profile.phoneNumber')}
              </label>
              <Input
                value={formPhone}
                onChange={(e) => setFormPhone(e.target.value)}
                placeholder={t('emp.profile.phonePlaceholder')}
              />
            </div>
            <div>
              <label className="block text-2xs font-bold text-stone-700 mb-1">
                {t('emp.profile.workModePreference')}
              </label>
              <select
                value={formWorkMode}
                onChange={(e) => setFormWorkMode(e.target.value as WorkMode)}
                className="w-full px-3 py-2 text-xs rounded-xl border border-stone-300 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="Hybrid">{t('emp.profile.modeHybrid')}</option>
                <option value="Remote">{t('emp.profile.modeRemote')}</option>
                <option value="Onsite">{t('emp.profile.modeOnsite')}</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-2xs font-bold text-stone-700 mb-1">
              {t('emp.profile.bio')}
            </label>
            <textarea
              rows={3}
              value={formBio}
              onChange={(e) => setFormBio(e.target.value)}
              className="w-full p-2.5 text-xs rounded-xl border border-stone-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder={t('emp.profile.bioPlaceholder')}
            />
          </div>

          {/* Emergency Contact Section */}
          <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 space-y-3">
            <span className="text-3xs font-extrabold uppercase text-stone-500 tracking-wider">
              {t('emp.profile.emergencyInfo')}
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-3xs font-semibold text-stone-600 mb-1">{t('emp.profile.contactName')}</label>
                <Input
                  value={formEmergencyName}
                  onChange={(e) => setFormEmergencyName(e.target.value)}
                  placeholder={t('emp.profile.contactName')}
                />
              </div>
              <div>
                <label className="block text-3xs font-semibold text-stone-600 mb-1">{t('emp.profile.relationship')}</label>
                <Input
                  value={formEmergencyRel}
                  onChange={(e) => setFormEmergencyRel(e.target.value)}
                  placeholder={t('emp.profile.relationshipPlaceholder')}
                />
              </div>
              <div>
                <label className="block text-3xs font-semibold text-stone-600 mb-1">{t('emp.profile.contactPhone')}</label>
                <Input
                  value={formEmergencyPhone}
                  onChange={(e) => setFormEmergencyPhone(e.target.value)}
                  placeholder={t('emp.profile.emergencyPhonePlaceholder')}
                />
              </div>
            </div>
          </div>

          {/* Skills Editor */}
          <div className="space-y-2">
            <label className="block text-2xs font-bold text-stone-700">
              {t('emp.profile.skillsPortfolio')}
            </label>
            <div className="flex gap-2">
              <Input
                value={newSkillInput}
                onChange={(e) => setNewSkillInput(e.target.value)}
                placeholder={t('emp.profile.addSkillPlaceholder')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddSkill();
                  }
                }}
              />
              <Button type="button" variant="secondary" size="sm" onClick={handleAddSkill}>
                Add
              </Button>
            </div>

            <div className="flex flex-wrap gap-1.5 pt-1">
              {skillsList.map((skill) => (
                <span
                  key={skill}
                  className="px-2.5 py-1 rounded-lg bg-brand-50 border border-brand-200 text-xs font-semibold text-brand-900 flex items-center gap-1.5"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => handleRemoveSkill(skill)}
                    className="hover:text-rose-600 transition-colors"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
};
