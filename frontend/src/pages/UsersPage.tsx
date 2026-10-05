import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  Plus,
  MoreVertical,
  UserCheck,
  UserX,
  Edit2,
  Trash2,
  Mail,
  Building,
  Briefcase,
  Download,
  ChevronLeft,
  ChevronRight,
  Shield,
  KeyRound,
  Loader2,
  XCircle,
} from 'lucide-react';
import {
  RoleRecord,
  UserAccountRecord,
  UserCreatePayload,
  UserUpdatePayload,
} from '../types';
import { SmartHRApi } from '../services/api';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { useT } from '../i18n';

const formatDate = (value: string): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

const initialsOf = (user: UserAccountRecord): string => {
  const source = user.full_name ?? user.email;
  return source
    .split(/[\s@.]+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
};

const roleBadgeClass = (roleName: string | null): string => {
  switch (roleName) {
    case 'Admin':
      return 'bg-brand-100 text-brand-800 border border-brand-200';
    case 'HR':
      return 'bg-sky-50 text-sky-700 border border-sky-200';
    case 'Manager':
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    default:
      return 'bg-stone-100 text-stone-700 border border-stone-200';
  }
};

interface UserFormState {
  email: string;
  password: string;
  role_id: string;
  is_active: boolean;
}

const EMPTY_FORM: UserFormState = {
  email: '',
  password: '',
  role_id: '',
  is_active: true,
};

export const UsersPage: React.FC = () => {
  const { t } = useT();
  const { showToast } = useToast();

  const [users, setUsers] = useState<UserAccountRecord[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingId, setPendingId] = useState<number | null>(null);

  // Filters state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRole, setSelectedRole] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 8;

  // Modals state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserAccountRecord | null>(null);
  const [deletingUser, setDeletingUser] = useState<UserAccountRecord | null>(
    null
  );
  const [activeActionMenuId, setActiveActionMenuId] = useState<number | null>(
    null
  );

  const [formData, setFormData] = useState<UserFormState>(EMPTY_FORM);

  const loadUsers = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await SmartHRApi.getUsers();
      setUsers(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('admin.users.unableToLoad');
      setLoadError(message);
      showToast(t('admin.users.errorLoading'), { message, type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [showToast]);

  const loadRoles = useCallback(async () => {
    try {
      const data = await SmartHRApi.getRoles();
      setRoles(data);
    } catch {
      // Non-fatal: the directory still renders, only the picker stays empty.
      showToast(t('admin.users.rolesFailed'), {
        message: t('admin.users.rolesIncomplete'),
        type: 'error',
      });
    }
  }, [showToast]);

  useEffect(() => {
    loadUsers();
    loadRoles();
  }, [loadUsers, loadRoles]);

  const roleOptions = useMemo(
    () => roles.map((r) => ({ label: r.name, value: String(r.id) })),
    [roles]
  );

  // Filter logic
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        !query ||
        (u.full_name ?? '').toLowerCase().includes(query) ||
        u.email.toLowerCase().includes(query) ||
        (u.position_title ?? '').toLowerCase().includes(query) ||
        (u.department_name ?? '').toLowerCase().includes(query);

      const matchesRole =
        selectedRole === 'all' || String(u.role_id) === selectedRole;

      const matchesStatus =
        selectedStatus === 'all' ||
        (selectedStatus === 'active' ? u.is_active : !u.is_active);

      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [users, searchQuery, selectedRole, selectedStatus]);

  const totalPages = Math.ceil(filteredUsers.length / pageSize) || 1;

  const paginatedUsers = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredUsers.slice(start, start + pageSize);
  }, [filteredUsers, currentPage, pageSize]);

  const applyUpdated = (updated: UserAccountRecord) => {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
  };

  // ---------- Create ----------

  const handleOpenAdd = () => {
    setFormData({
      ...EMPTY_FORM,
      role_id: roles.length ? String(roles[roles.length - 1].id) : '',
    });
    setIsAddModalOpen(true);
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.email.trim()) {
      showToast(t('admin.users.validationError'), {
        message: t('admin.users.emailRequired'),
        type: 'warning',
      });
      return;
    }

    if (formData.password.length < 8) {
      showToast(t('admin.users.validationError'), {
        message: t('admin.users.passwordMin'),
        type: 'warning',
      });
      return;
    }

    if (!formData.role_id) {
      showToast(t('admin.users.validationError'), {
        message: t('admin.users.selectRole'),
        type: 'warning',
      });
      return;
    }

    setIsSaving(true);

    try {
      const payload: UserCreatePayload = {
        email: formData.email.trim(),
        password: formData.password,
        role_id: Number(formData.role_id),
        is_active: formData.is_active,
      };

      const created = await SmartHRApi.createUser(payload);
      setUsers((prev) => [...prev, created]);
      setIsAddModalOpen(false);
      setFormData(EMPTY_FORM);
      loadRoles();

      showToast(t('admin.users.createdOk'), {
        message: `${created.email} was added with role ${created.role_name}.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('admin.users.createFailed'), {
        message: error instanceof Error ? error.message : t('admin.users.unexpectedError'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // ---------- Edit ----------

  const handleOpenEdit = (user: UserAccountRecord) => {
    setEditingUser(user);
    setFormData({
      email: user.email,
      password: '',
      role_id: String(user.role_id),
      is_active: user.is_active,
    });
    setActiveActionMenuId(null);
  };

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    if (!formData.email.trim()) {
      showToast(t('admin.users.validationError'), {
        message: t('admin.users.emailRequired'),
        type: 'warning',
      });
      return;
    }

    if (formData.password && formData.password.length < 8) {
      showToast(t('admin.users.validationError'), {
        message: t('admin.users.newPasswordMin'),
        type: 'warning',
      });
      return;
    }

    setIsSaving(true);

    try {
      const payload: UserUpdatePayload = {
        email: formData.email.trim(),
        role_id: Number(formData.role_id),
        is_active: formData.is_active,
        password: formData.password || null,
      };

      const updated = await SmartHRApi.updateUser(editingUser.id, payload);
      applyUpdated(updated);
      setEditingUser(null);
      loadRoles();

      showToast(t('admin.users.updatedOk'), {
        message: `${updated.email} was updated${formData.password ? ' (password reset)' : ''}.`,
        type: 'success',
      });
    } catch (error) {
      showToast(t('admin.users.updateFailed'), {
        message: error instanceof Error ? error.message : t('admin.users.unexpectedError'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // ---------- Activate / Deactivate ----------

  const handleToggleStatus = async (user: UserAccountRecord) => {
    setPendingId(user.id);
    setActiveActionMenuId(null);

    try {
      const updated = await SmartHRApi.setUserStatus(user.id, !user.is_active);
      applyUpdated(updated);

      showToast(updated.is_active ? t('admin.users.activatedOk') : t('admin.users.deactivatedOk'), {
        message: t('users.nowStatus', {
          email: updated.email,
          status: updated.is_active ? t('status.active') : t('status.inactive'),
        }),
        type: updated.is_active ? 'success' : 'warning',
      });
    } catch (error) {
      showToast(t('admin.users.actionFailed'), {
        message: error instanceof Error ? error.message : t('admin.users.unexpectedError'),
        type: 'error',
      });
    } finally {
      setPendingId(null);
    }
  };

  // ---------- Delete ----------

  const handleDeleteUser = async () => {
    if (!deletingUser) return;

    setIsSaving(true);

    try {
      await SmartHRApi.deleteUser(deletingUser.id);
      setUsers((prev) => prev.filter((u) => u.id !== deletingUser.id));
      loadRoles();

      showToast(t('admin.users.deletedOk'), {
        message: `Account for ${deletingUser.email} was deleted.`,
        type: 'info',
      });
      setDeletingUser(null);
    } catch (error) {
      showToast(t('admin.users.deleteFailed'), {
        message: error instanceof Error ? error.message : t('admin.users.unexpectedError'),
        type: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // ---------- Export ----------

  const handleExportCSV = () => {
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      ['ID,Name,Email,Role,Department,Position,Status,Created']
        .concat(
          filteredUsers.map(
            (u) =>
              `${u.id},"${u.full_name ?? ''}",${u.email},${u.role_name ?? ''},${u.department_name ?? ''},${u.position_title ?? ''},${u.is_active ? 'Active' : 'Inactive'},${u.created_at}`
          )
        )
        .join('\n');

    const link = document.createElement('a');
    link.setAttribute('href', encodeURI(csvContent));
    link.setAttribute('download', 'smarthr_users.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast(t('admin.users.exportStarted'), {
      message: `${filteredUsers.length} user account(s) exported to CSV.`,
      type: 'info',
    });
  };

  const activeCount = users.filter((u) => u.is_active).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={t('admin.users.title')}
        subtitle={t('admin.users.subtitle')}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Download className="w-3.5 h-3.5" />}
              onClick={handleExportCSV}
            >
              {t('admin.users.exportCsv')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={handleOpenAdd}
            >
              + Add User
            </Button>
          </div>
        }
      />

      {/* Filters */}
      <Card>
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-stone-400 absolute start-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              placeholder={t('admin.users.searchAll')}
              className="w-full ps-9 pe-4 py-2 text-xs rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-brand-600 bg-stone-50/50"
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto">
            <select
              value={selectedRole}
              onChange={(e) => {
                setSelectedRole(e.target.value);
                setCurrentPage(1);
              }}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="all">{t('admin.users.allRoles')}</option>
              {roles.map((r) => (
                <option key={r.id} value={String(r.id)}>
                  {r.name} ({r.user_count})
                </option>
              ))}
            </select>

            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setCurrentPage(1);
              }}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-stone-200 bg-white text-stone-700 focus:outline-none"
            >
              <option value="all">{t('admin.users.allStatuses')}</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Users Table */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-xs border-collapse">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50 text-stone-400 uppercase tracking-wider font-bold text-3xs">
                <th className="py-3.5 px-4">User</th>
                <th className="py-3.5 px-4">Role</th>
                <th className="py-3.5 px-4">{t('table.department')}</th>
                <th className="py-3.5 px-4">{t('table.position')}</th>
                <th className="py-3.5 px-4">{t('table.status')}</th>
                <th className="py-3.5 px-4">{t('table.createdAt')}</th>
                <th className="py-3.5 px-4 text-end">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-stone-700">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-stone-400">
                    <Loader2 className="w-7 h-7 mx-auto mb-2 text-stone-300 animate-spin" />
                    {t('admin.users.loading')}
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center">
                    <XCircle className="w-7 h-7 mx-auto mb-2 text-rose-300" />
                    <p className="font-semibold text-stone-600">
                      {t('admin.users.loadFailed')}
                    </p>
                    <p className="text-2xs text-stone-400 mt-1">{loadError}</p>
                    <div className="mt-3">
                      <Button variant="outline" size="sm" onClick={loadUsers}>
                        {t('admin.users.retry')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : paginatedUsers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-4">
                    <EmptyState
                      icon={<Shield className="w-8 h-8 text-stone-300" />}
                      title={t('admin.users.noneFound')}
                      description={
                        users.length === 0
                          ? t('admin.users.firstAccountHint')
                          : t('admin.users.adjustFilters')
                      }
                    />
                  </td>
                </tr>
              ) : (
                paginatedUsers.map((user) => (
                  <tr
                    key={user.id}
                    className="hover:bg-stone-50/60 transition-colors"
                  >
                    {/* Identity */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-brand-700 to-brand-600 text-white font-bold text-xs flex items-center justify-center shrink-0 shadow-2xs">
                          {initialsOf(user)}
                        </div>
                        <div className="min-w-0">
                          <span className="font-bold text-stone-900 block truncate">
                            {user.full_name ?? t('admin.users.noLinkedEmployeeShort')}
                          </span>
                          <span className="text-stone-400 text-3xs truncate flex items-center gap-1">
                            <Mail className="w-3 h-3" />
                            {user.email}
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* Role */}
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-3xs font-bold ${roleBadgeClass(
                          user.role_name
                        )}`}
                      >
                        <Shield className="w-3 h-3" />
                        {user.role_name ?? `Role ${user.role_id}`}
                      </span>
                    </td>

                    {/* Department */}
                    <td className="py-3 px-4 text-stone-600">
                      <span className="flex items-center gap-1.5 text-2xs">
                        <Building className="w-3.5 h-3.5 text-stone-400" />
                        {user.department_name ?? '—'}
                      </span>
                    </td>

                    {/* Position */}
                    <td className="py-3 px-4 text-stone-600">
                      <span className="flex items-center gap-1.5 text-2xs">
                        <Briefcase className="w-3.5 h-3.5 text-stone-400" />
                        {user.position_title ?? '—'}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-3xs font-bold ${
                          user.is_active
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-stone-100 text-stone-600 border border-stone-200'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            user.is_active ? 'bg-emerald-500' : 'bg-stone-400'
                          }`}
                        />
                        {user.is_active ? t('status.active') : t('status.inactive')}
                      </span>
                    </td>

                    {/* Created */}
                    <td className="py-3 px-4 text-stone-500 font-mono text-2xs">
                      {formatDate(user.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-end relative">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          className="px-2 h-7"
                          title={t('admin.users.editUser')}
                          onClick={() => handleOpenEdit(user)}
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          className="px-2 h-7"
                          title={t('admin.users.moreActions')}
                          onClick={() =>
                            setActiveActionMenuId(
                              activeActionMenuId === user.id ? null : user.id
                            )
                          }
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </Button>
                      </div>

                      {activeActionMenuId === user.id && (
                        <div className="absolute end-4 top-11 z-20 w-52 rounded-xl border border-stone-200 bg-white shadow-lg py-1 text-start">
                          <button
                            disabled={pendingId === user.id}
                            onClick={() => handleToggleStatus(user)}
                            className="w-full px-3 py-2 text-xs font-semibold text-stone-700 hover:bg-stone-50 flex items-center gap-2 disabled:opacity-50"
                          >
                            {user.is_active ? (
                              <>
                                <UserX className="w-3.5 h-3.5 text-amber-600" />
                                {t('admin.users.deactivateAccount')}
                              </>
                            ) : (
                              <>
                                <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
                                {t('admin.users.activateAccount')}
                              </>
                            )}
                          </button>
                          <button
                            onClick={() => {
                              setDeletingUser(user);
                              setActiveActionMenuId(null);
                            }}
                            className="w-full px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 flex items-center gap-2"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            {t('admin.users.deleteAccount')}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!isLoading && !loadError && filteredUsers.length > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-stone-100 text-xs">
            <span className="text-stone-500">
              Showing {(currentPage - 1) * pageSize + 1}-
              {Math.min(currentPage * pageSize, filteredUsers.length)} of{' '}
              {filteredUsers.length} account(s) • {activeCount} active
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="w-3.5 h-3.5" data-flip-rtl />
              </Button>
              <span className="font-semibold text-stone-600">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() =>
                  setCurrentPage((p) => Math.min(totalPages, p + 1))
                }
              >
                <ChevronRight className="w-3.5 h-3.5" data-flip-rtl />
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Add User Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t('admin.users.provisionTitle')}
        subtitle={t('admin.users.provisionSubtitle')}
        size="md"
      >
        <form onSubmit={handleCreateUser} className="space-y-4">
          <Input
            label={t('admin.users.workEmail')}
            type="email"
            required
            value={formData.email}
            onChange={(e) =>
              setFormData({ ...formData, email: e.target.value })
            }
            placeholder={t('admin.users.emailPlaceholder')}
            helperText="Must be unique; this is the sign-in identifier."
          />

          <Input
            label={t('admin.users.initialPassword')}
            type="password"
            required
            value={formData.password}
            onChange={(e) =>
              setFormData({ ...formData, password: e.target.value })
            }
            placeholder={t('admin.users.atLeast8')}
            helperText="Hashed with Argon2 before storage; never stored in plain text."
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('admin.users.platformRole')}
              required
              options={roleOptions}
              value={formData.role_id}
              onChange={(e) =>
                setFormData({ ...formData, role_id: e.target.value })
              }
            />

            <Select
              label={t('admin.users.accountStatus')}
              options={[
                { label: t('status.active'), value: 'active' },
                { label: t('status.inactive'), value: 'inactive' },
              ]}
              value={formData.is_active ? 'active' : 'inactive'}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  is_active: e.target.value === 'active',
                })
              }
            />
          </div>

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setIsAddModalOpen(false)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
            >
              {t('admin.users.createAccount')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        isOpen={editingUser !== null}
        onClose={() => setEditingUser(null)}
        title={t('admin.users.editTitle')}
        subtitle={
          editingUser
            ? `${editingUser.full_name ?? editingUser.email} • ${editingUser.role_name ?? ''}`
            : ''
        }
        size="md"
      >
        <form onSubmit={handleUpdateUser} className="space-y-4">
          <Input
            label={t('admin.users.workEmail')}
            type="email"
            required
            value={formData.email}
            onChange={(e) =>
              setFormData({ ...formData, email: e.target.value })
            }
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label={t('admin.users.platformRole')}
              required
              options={roleOptions}
              value={formData.role_id}
              onChange={(e) =>
                setFormData({ ...formData, role_id: e.target.value })
              }
            />

            <Select
              label={t('admin.users.accountStatus')}
              options={[
                { label: t('status.active'), value: 'active' },
                { label: t('status.inactive'), value: 'inactive' },
              ]}
              value={formData.is_active ? 'active' : 'inactive'}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  is_active: e.target.value === 'active',
                })
              }
            />
          </div>

          <Input
            label={t('admin.users.resetPassword')}
            type="password"
            value={formData.password}
            onChange={(e) =>
              setFormData({ ...formData, password: e.target.value })
            }
            placeholder={t('admin.users.leaveBlank')}
            helperText="Existing passwords cannot be read back, only replaced."
          />

          {editingUser?.employee_id === null && (
            <p className="text-3xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2.5">
              This account has no linked employee record, so it shows no name,
              department or position.
            </p>
          )}

          <div className="pt-4 border-t border-stone-100 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setEditingUser(null)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              isLoading={isSaving}
              leftIcon={<KeyRound className="w-3.5 h-3.5" />}
            >
              {t('admin.users.saveChanges')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={deletingUser !== null}
        onClose={() => setDeletingUser(null)}
        title={t('admin.users.deleteTitle')}
        subtitle={t('admin.users.deleteBody')}
        size="sm"
      >
        <div className="space-y-4 text-xs">
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-900">
            <p className="font-bold">
              {deletingUser?.full_name ?? deletingUser?.email}
            </p>
            <p className="text-2xs mt-1">
              {deletingUser?.email} • {deletingUser?.role_name}
            </p>
          </div>

          <p className="text-stone-600">
            Accounts still referenced by other records cannot be deleted.
            Deactivate the account instead to revoke access while preserving
            history.
          </p>

          <div className="pt-3 border-t border-stone-100 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeletingUser(null)}
            >
              {t('action.cancel')}
            </Button>
            <Button
              variant="danger"
              size="sm"
              isLoading={isSaving}
              onClick={handleDeleteUser}
            >
              {t('admin.users.deleteAccountBtn')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
