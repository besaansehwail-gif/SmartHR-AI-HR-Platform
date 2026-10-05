import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Users,
  Check,
  RotateCcw,
  Save,
  Lock,
  Info,
  CheckCheck,
  Sparkles,
  Sliders,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { RoleBadge } from '../components/ui/Badge';
import { permissionCategories, initialRoles } from '../mock/rolesAndPermissions';
import { UserRole, RoleDefinition, PermissionCategory, RolePermissionsMatrix } from '../types';
import { SmartHRApi } from '../services/api';
import { useToast } from '../components/ui/Toast';
import { useT } from '../i18n';

export const RolesPermissionsPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();
  const [selectedRole, setSelectedRole] = useState<UserRole>('HR');
  const [roles, setRoles] = useState<Record<UserRole, RoleDefinition>>(initialRoles);
  const [currentMatrix, setCurrentMatrix] = useState<RolePermissionsMatrix>(initialRoles.HR.permissions);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Role names and user counts come from the real `roles` / `users` tables.
  // The permission matrix itself has no table in PostgreSQL, so the baseline
  // definitions are used for that part and changes are not persisted.
  useEffect(() => {
    let cancelled = false;

    SmartHRApi.getRoles()
      .then((data) => {
        if (cancelled) return;

        setRoles((prev) => {
          const merged = { ...prev };

          data.forEach((role) => {
            const key = role.name as UserRole;
            if (merged[key]) {
              merged[key] = { ...merged[key], userCount: role.user_count };
            }
          });

          return merged;
        });
      })
      .catch(() => {
        // Non-fatal: fall back to the baseline definitions already in state.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Show the selected role's matrix whenever the selection changes.
  useEffect(() => {
    setCurrentMatrix(initialRoles[selectedRole].permissions);
    setHasUnsavedChanges(false);
  }, [selectedRole]);

  const activeRoleDef = roles[selectedRole];

  // Toggle single permission
  const handleTogglePermission = (
    category: PermissionCategory,
    action: 'view' | 'create' | 'edit' | 'delete'
  ) => {
    if (selectedRole === 'Admin') {
      showToast(t('rbac.systemNotice'), {
        message: t('rbac.adminImmutable'),
        type: 'warning',
      });
      return;
    }

    const updated = {
      ...currentMatrix,
      [category]: {
        ...currentMatrix[category],
        [action]: !currentMatrix[category][action],
      },
    };
    setCurrentMatrix(updated);
    setHasUnsavedChanges(true);
  };

  // Toggle all permissions for a specific category
  const handleToggleCategoryAll = (category: PermissionCategory) => {
    if (selectedRole === 'Admin') return;

    const row = currentMatrix[category];
    const allEnabled = row.view && row.create && row.edit && row.delete;
    const targetState = !allEnabled;

    const updated = {
      ...currentMatrix,
      [category]: {
        view: targetState,
        create: targetState,
        edit: targetState,
        delete: targetState,
      },
    };
    setCurrentMatrix(updated);
    setHasUnsavedChanges(true);
  };

  // Grant all permissions for role
  const handleGrantAll = () => {
    if (selectedRole === 'Admin') return;
    const allOn: any = {};
    permissionCategories.forEach((c) => {
      allOn[c.id] = { view: true, create: true, edit: true, delete: true };
    });
    setCurrentMatrix(allOn);
    setHasUnsavedChanges(true);
  };

  // Revoke all
  const handleRevokeAll = () => {
    if (selectedRole === 'Admin') return;
    const allOff: any = {};
    permissionCategories.forEach((c) => {
      allOff[c.id] = { view: false, create: false, edit: false, delete: false };
    });
    setCurrentMatrix(allOff);
    setHasUnsavedChanges(true);
  };

  // Reset to default
  const handleResetToDefault = () => {
    setCurrentMatrix(initialRoles[selectedRole].permissions);
    setHasUnsavedChanges(false);
    showToast(t('rbac.resetComplete'), {
      message: t('rbac.resetMessage', { role: t(`role.name.${selectedRole}`) }),
      type: 'info',
    });
  };

  // Save changes
  //
  // There is no permissions table in PostgreSQL - `roles` holds only (id,
  // name) - so the matrix is applied in-session only. Role ASSIGNMENT is
  // real and lives on users.role_id, edited from the Users page.
  const handleSaveChanges = async () => {
    setIsSaving(true);
    try {
      setRoles((prev) => ({
        ...prev,
        [selectedRole]: {
          ...prev[selectedRole],
          permissions: currentMatrix,
        },
      }));
      setHasUnsavedChanges(false);
      showToast(t('rbac.appliedInSession'), {
        message: t('rbac.appliedMessage', { role: t(`role.name.${selectedRole}`) }),
        type: 'warning',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Count active permissions
  const totalGranted = Object.values(currentMatrix).reduce((acc: number, cat: any) => {
    return acc + (cat?.view ? 1 : 0) + (cat?.create ? 1 : 0) + (cat?.edit ? 1 : 0) + (cat?.delete ? 1 : 0);
  }, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('rbac.title')}
        subtitle={t('rbac.subtitle')}
        badge={
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-brand-100 text-brand-900 border border-brand-200">
            {t('rbac.badge')}
          </span>
        }
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasUnsavedChanges}
              onClick={handleResetToDefault}
              leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
            >
              {t('rbac.discard')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={isSaving}
              onClick={handleSaveChanges}
              leftIcon={<Save className="w-4 h-4" />}
            >
              {t('rbac.save')} {hasUnsavedChanges && '•'}
            </Button>
          </>
        }
      />

      {/* Role Selection Tabs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {(['Admin', 'HR', 'Manager', 'Employee'] as UserRole[]).map((roleKey) => {
          const roleData = roles[roleKey];
          const isSelected = selectedRole === roleKey;

          return (
            <div
              key={roleKey}
              onClick={() => {
                if (hasUnsavedChanges) {
                  if (confirm(t('rbac.switchConfirm'))) {
                    setSelectedRole(roleKey);
                  }
                } else {
                  setSelectedRole(roleKey);
                }
              }}
              className={`p-4 rounded-xl border cursor-pointer transition-all duration-150 relative flex flex-col justify-between ${
                isSelected
                  ? 'bg-brand-50/50 border-brand-500 shadow-xs ring-2 ring-brand-500/20'
                  : 'bg-white border-stone-200 hover:border-stone-300 hover:bg-stone-50/60'
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <RoleBadge role={roleKey} />
                  <span className="text-3xs font-semibold text-stone-400 flex items-center gap-1">
                    <Users className="w-3 h-3" /> {roleData.userCount} {t('rbac.users')}
                  </span>
                </div>
                <h4 className="text-sm font-bold text-stone-900 mt-2.5">
                  {t(`role.name.${roleKey}`)}
                </h4>
                <p className="text-2xs text-stone-500 mt-1 leading-relaxed line-clamp-2">
                  {t(`rbac.role.${roleKey}.desc`)}
                </p>
              </div>

              <div className="mt-3 pt-2.5 border-t border-stone-100 flex items-center justify-between text-3xs font-semibold">
                <span className={isSelected ? 'text-brand-700' : 'text-stone-400'}>
                  {isSelected ? t('rbac.currentlyEditing') : t('rbac.clickToConfigure')}
                </span>
                {roleData.isSystemRole && (
                  <span className="flex items-center gap-0.5 text-stone-400">
                    <Lock className="w-2.5 h-2.5" /> {t('rbac.core')}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Role Overview and Quick Batch Actions */}
      <Card padding="sm" className="bg-stone-50/70">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center font-bold">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-stone-900">
                  {t('rbac.matrixFor')}{' '}
                  <span className="text-brand-700">{t(`role.name.${selectedRole}`)}</span>
                </h3>
                <span className="text-3xs font-semibold px-2 py-0.5 rounded-full bg-brand-100 text-brand-800">
                  {t('rbac.privilegesEnabled', { count: Number(totalGranted) })}
                </span>
              </div>
              <p className="text-xs text-stone-500 mt-0.5">
                {selectedRole === 'Admin'
                  ? t('rbac.adminRootNotice')
                  : t('rbac.toggleNotice')}
              </p>
            </div>
          </div>

          {selectedRole !== 'Admin' && (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleGrantAll}>
                {t('rbac.enableAll')}
              </Button>
              <Button variant="ghost" size="sm" onClick={handleRevokeAll} className="text-rose-600 hover:text-rose-700">
                {t('rbac.revokeAll')}
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Permissions Matrix Table */}
      <Card padding="none" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs text-stone-600">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-3xs font-bold text-stone-500 uppercase tracking-wider">
                <th className="py-3 px-6 w-72">{t('rbac.col.category')}</th>
                <th className="py-3 px-4 text-center w-28">{t('rbac.col.view')}</th>
                <th className="py-3 px-4 text-center w-28">{t('rbac.col.create')}</th>
                <th className="py-3 px-4 text-center w-28">{t('rbac.col.edit')}</th>
                <th className="py-3 px-4 text-center w-28">{t('rbac.col.delete')}</th>
                <th className="py-3 px-6 text-end w-36">{t('rbac.col.rowAction')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 font-medium">
              {permissionCategories.map((cat) => {
                const perms = currentMatrix[cat.id] || { view: false, create: false, edit: false, delete: false };
                const isAllRowActive = perms.view && perms.create && perms.edit && perms.delete;
                const isNoneRowActive = !perms.view && !perms.create && !perms.edit && !perms.delete;

                return (
                  <tr key={cat.id} className="hover:bg-stone-50/80 transition-colors">
                    {/* Category Details */}
                    <td className="py-3.5 px-6">
                      <p className="font-bold text-stone-900 text-sm">
                        {t(`rbac.cat.${cat.id}.label`)}
                      </p>
                      <p className="text-2xs text-stone-500 mt-0.5 leading-relaxed">
                        {t(`rbac.cat.${cat.id}.desc`)}
                      </p>
                    </td>

                    {/* View Toggle */}
                    <td className="py-3.5 px-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleTogglePermission(cat.id, 'view')}
                        disabled={selectedRole === 'Admin'}
                        className={`w-7 h-7 rounded-lg border flex items-center justify-center mx-auto transition-all ${
                          perms.view
                            ? 'bg-brand-700 border-brand-700 text-white shadow-2xs'
                            : 'bg-white border-stone-300 text-stone-300 hover:border-stone-400'
                        } ${selectedRole === 'Admin' ? 'cursor-not-allowed opacity-90' : 'cursor-pointer'}`}
                        title={t('rbac.toggleFor', {
                          action: t('rbac.col.view'),
                          category: t(`rbac.cat.${cat.id}.label`),
                        })}
                      >
                        {perms.view ? <Check className="w-4 h-4 stroke-[3]" /> : null}
                      </button>
                    </td>

                    {/* Create Toggle */}
                    <td className="py-3.5 px-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleTogglePermission(cat.id, 'create')}
                        disabled={selectedRole === 'Admin'}
                        className={`w-7 h-7 rounded-lg border flex items-center justify-center mx-auto transition-all ${
                          perms.create
                            ? 'bg-brand-700 border-brand-700 text-white shadow-2xs'
                            : 'bg-white border-stone-300 text-stone-300 hover:border-stone-400'
                        } ${selectedRole === 'Admin' ? 'cursor-not-allowed opacity-90' : 'cursor-pointer'}`}
                        title={t('rbac.toggleFor', {
                          action: t('rbac.col.create'),
                          category: t(`rbac.cat.${cat.id}.label`),
                        })}
                      >
                        {perms.create ? <Check className="w-4 h-4 stroke-[3]" /> : null}
                      </button>
                    </td>

                    {/* Edit Toggle */}
                    <td className="py-3.5 px-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleTogglePermission(cat.id, 'edit')}
                        disabled={selectedRole === 'Admin'}
                        className={`w-7 h-7 rounded-lg border flex items-center justify-center mx-auto transition-all ${
                          perms.edit
                            ? 'bg-brand-700 border-brand-700 text-white shadow-2xs'
                            : 'bg-white border-stone-300 text-stone-300 hover:border-stone-400'
                        } ${selectedRole === 'Admin' ? 'cursor-not-allowed opacity-90' : 'cursor-pointer'}`}
                        title={t('rbac.toggleFor', {
                          action: t('rbac.col.edit'),
                          category: t(`rbac.cat.${cat.id}.label`),
                        })}
                      >
                        {perms.edit ? <Check className="w-4 h-4 stroke-[3]" /> : null}
                      </button>
                    </td>

                    {/* Delete Toggle */}
                    <td className="py-3.5 px-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleTogglePermission(cat.id, 'delete')}
                        disabled={selectedRole === 'Admin'}
                        className={`w-7 h-7 rounded-lg border flex items-center justify-center mx-auto transition-all ${
                          perms.delete
                            ? 'bg-rose-600 border-rose-600 text-white shadow-2xs'
                            : 'bg-white border-stone-300 text-stone-300 hover:border-stone-400'
                        } ${selectedRole === 'Admin' ? 'cursor-not-allowed opacity-90' : 'cursor-pointer'}`}
                        title={t('rbac.toggleFor', {
                          action: t('rbac.col.delete'),
                          category: t(`rbac.cat.${cat.id}.label`),
                        })}
                      >
                        {perms.delete ? <Check className="w-4 h-4 stroke-[3]" /> : null}
                      </button>
                    </td>

                    {/* Row Action */}
                    <td className="py-3.5 px-6 text-end">
                      {selectedRole !== 'Admin' ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleCategoryAll(cat.id)}
                          className="text-xs text-brand-700 font-semibold"
                        >
                          {isAllRowActive ? t('rbac.disableAll') : t('rbac.enableAll')}
                        </Button>
                      ) : (
                        <span className="text-3xs text-stone-400 font-semibold">
                          {t('rbac.lockedAdmin')}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer save reminder */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-6 py-4 border-t border-stone-200 bg-stone-50/60">
          <div className="flex items-center gap-2 text-xs text-stone-500">
            <Info className="w-4 h-4 text-brand-600 shrink-0" />
            <span>{t('rbac.cascadeNotice')}</span>
          </div>

          <div className="flex items-center gap-2.5">
            {hasUnsavedChanges && (
              <span className="text-xs font-bold text-amber-600 animate-pulse">
                {t('rbac.unsaved')}
              </span>
            )}
            <Button
              variant="primary"
              size="sm"
              isLoading={isSaving}
              onClick={handleSaveChanges}
              leftIcon={<Save className="w-4 h-4" />}
            >
              {t('rbac.save')}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};
