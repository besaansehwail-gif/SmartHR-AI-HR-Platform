import React, { useEffect, useMemo, useState } from "react";
import {
  Users,
  Search,
  Plus,
  MoreHorizontal,
  Edit2,
  Trash2,
  Eye,
  Mail,
  Phone,
  Calendar,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { PageHeader } from "../../components/ui/PageHeader";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Modal } from "../../components/ui/Modal";
import { Input, Select } from "../../components/ui/Input";
import { useToast } from "../../components/ui/Toast";

import { SmartHRApi } from "../../services/api";
import { Employee, EmployeeRecord } from "../../types";
import { useT } from '../../i18n';

export interface EmployeesPageProps {
  onView360?: (employeeId: string) => void;
}

// =========================
// Celebration dates (AI Employee Celebration)
//
// Optional employee dates the daily celebration check reads: birth_date
// recurs every year like hire_date; the others are celebrated on the date.
// Empty means "not recorded", sent as null.
// =========================

const CELEBRATION_DATE_KEYS = [
  ["birthDate", "birth_date", "hr.employees.birthDate"],
  ["promotionDate", "promotion_date", "hr.employees.promotionDate"],
  ["graduationDate", "graduation_date", "hr.employees.graduationDate"],
  ["weddingDate", "wedding_date", "hr.employees.weddingDate"],
  ["newBabyDate", "new_baby_date", "hr.employees.newBabyDate"],
] as const;

type CelebrationFormKey = (typeof CELEBRATION_DATE_KEYS)[number][0];
type CelebrationApiKey = (typeof CELEBRATION_DATE_KEYS)[number][1];

const EMPTY_CELEBRATION_DATES: Record<CelebrationFormKey, string> = {
  birthDate: "",
  promotionDate: "",
  graduationDate: "",
  weddingDate: "",
  newBabyDate: "",
};

function celebrationDatesOf(record?: EmployeeRecord): Record<CelebrationFormKey, string> {
  const out = { ...EMPTY_CELEBRATION_DATES };
  for (const [formKey, apiKey] of CELEBRATION_DATE_KEYS) {
    out[formKey] = record?.[apiKey] ?? "";
  }
  return out;
}

function celebrationPayload(form: Record<CelebrationFormKey, string>) {
  const out = {} as Record<CelebrationApiKey, string | null>;
  for (const [formKey, apiKey] of CELEBRATION_DATE_KEYS) {
    out[apiKey] = form[formKey] || null;
  }
  return out;
}

const CelebrationDateFields: React.FC<{
  values: Record<CelebrationFormKey, string>;
  onChange: (key: CelebrationFormKey, value: string) => void;
}> = ({ values, onChange }) => {
  const { t } = useT();
  return (
    <fieldset className="space-y-3 border-t border-stone-200 pt-3">
      <legend className="text-sm font-semibold text-stone-700">
        {t('hr.employees.celebrationDates')}
      </legend>
      <p className="text-xs text-stone-500">{t('hr.employees.celebrationDatesHint')}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {CELEBRATION_DATE_KEYS.map(([formKey, , labelKey]) => (
          <Input
            key={formKey}
            label={t(labelKey)}
            type="date"
            value={values[formKey]}
            onChange={(e) => onChange(formKey, e.target.value)}
          />
        ))}
      </div>
    </fieldset>
  );
};

export const EmployeesPage: React.FC<EmployeesPageProps> = ({
  onView360,
}) => {
  const { t } = useT();
  const { showToast } = useToast();

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDepartment, setSelectedDepartment] = useState("ALL");
  const [selectedStatus, setSelectedStatus] = useState("ALL");

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const [currentEmployee, setCurrentEmployee] =
    useState<Employee | null>(null);

  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    phone: "",
    departmentId: "",
    positionId: "",
    hireDate: "",
    employmentStatus: "active",
    ...EMPTY_CELEBRATION_DATES,
  });
  // The API records by id: the celebration dates are not part of the
  // mock-shaped `Employee` the table renders, so the edit form reads them here.
  const [records, setRecords] = useState<Record<string, EmployeeRecord>>({});

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  // =========================
  // Load Employees
  // =========================

  const loadEmployees = async () => {
    try {
      setLoading(true);

      const data = await SmartHRApi.getEmployees();
      setRecords(Object.fromEntries(data.map((emp: EmployeeRecord) => [String(emp.id), emp])));

      const mappedEmployees: Employee[] = data.map((emp: EmployeeRecord) => ({
        id: String(emp.id),
        employeeId: `EMP-${String(emp.id).padStart(4, "0")}`,
        firstName: emp.first_name || "",
        lastName: emp.last_name || "",
        email: emp.email || "",
        phone: emp.phone || "",
        department: emp.department_name || "N/A",
        position: emp.position_title || "N/A",
        manager: emp.manager_name || "N/A",
        managerId: emp.manager_id
          ? String(emp.manager_id)
          : undefined,
        workMode: "Hybrid",
        employmentType: "Full-time",
        status:
          emp.employment_status === "active" ? "Active" : "Terminated",
        hireDate: emp.hire_date || "",
        location: "N/A",
        salary: "N/A",
        gradeLevel: "N/A",
        attendanceRate: 0,
      }));

      setEmployees(mappedEmployees);
    } catch (error) {
      console.error(error);
      showToast("Failed to load employees", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEmployees();
  }, []);

  // =========================
  // Filters
  // =========================

  const departments = useMemo(() => {
    const values = employees
      .map((employee) => employee.department)
      .filter(Boolean);

    return Array.from(new Set(values));
  }, [employees]);

  const filteredEmployees = useMemo(() => {
    const query = searchQuery.toLowerCase().trim();

    return employees.filter((employee) => {
      const fullName =
        `${employee.firstName} ${employee.lastName}`.toLowerCase();

      const matchesSearch =
        !query ||
        fullName.includes(query) ||
        employee.email.toLowerCase().includes(query) ||
        employee.employeeId.toLowerCase().includes(query);

      const matchesDepartment =
        selectedDepartment === "ALL" ||
        employee.department === selectedDepartment;

      const matchesStatus =
        selectedStatus === "ALL" ||
        employee.status === selectedStatus;

      return (
        matchesSearch &&
        matchesDepartment &&
        matchesStatus
      );
    });
  }, [
    employees,
    searchQuery,
    selectedDepartment,
    selectedStatus,
  ]);

  // =========================
  // Pagination
  // =========================

  const totalPages =
    Math.ceil(filteredEmployees.length / itemsPerPage) || 1;

  const paginatedEmployees = filteredEmployees.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // =========================
  // Form
  // =========================

  const resetForm = () => {
    setFormData({
      firstName: "",
      lastName: "",
      phone: "",
      departmentId: "",
      positionId: "",
      hireDate: "",
      employmentStatus: "active",
      ...EMPTY_CELEBRATION_DATES,
    });
  };

  const handleOpenAdd = () => {
    resetForm();
    setIsAddModalOpen(true);
  };

  const handleOpenEdit = (employee: Employee) => {
    setCurrentEmployee(employee);

    setFormData({
      firstName: employee.firstName,
      lastName: employee.lastName,
      phone: employee.phone,
      departmentId: "",
      positionId: "",
      hireDate: employee.hireDate,
      employmentStatus:
        employee.status === "Active"
          ? "active"
          : "terminated",
      ...celebrationDatesOf(records[employee.id]),
    });

    setIsEditModalOpen(true);
  };

  // =========================
  // Add Employee
  // =========================

  const handleAddEmployee = async () => {
    if (!formData.firstName || !formData.lastName) {
      showToast(
        "First name and last name are required",
        "error"
      );
      return;
    }

    try {
      await SmartHRApi.createEmployee({
        first_name: formData.firstName,
        last_name: formData.lastName,
        phone: formData.phone || null,
        department_id: formData.departmentId
          ? Number(formData.departmentId)
          : null,
        position_id: formData.positionId
          ? Number(formData.positionId)
          : null,
        hire_date: formData.hireDate || null,
        employment_status: formData.employmentStatus,
        ...celebrationPayload(formData),
      });

      showToast("Employee created successfully", "success");

      setIsAddModalOpen(false);

      resetForm();

      await loadEmployees();
    } catch (error) {
      console.error(error);
      showToast(
        error instanceof Error
          ? error.message
          : "Failed to create employee",
        "error"
      );
    }
  };

  // =========================
  // Update Employee
  // =========================

  const handleUpdateEmployee = async () => {
    if (!currentEmployee) return;

    try {
      await SmartHRApi.updateEmployee(
        Number(currentEmployee.id),
        {
          first_name: formData.firstName,
          last_name: formData.lastName,
          phone: formData.phone || null,
          department_id: formData.departmentId
            ? Number(formData.departmentId)
            : null,
          position_id: formData.positionId
            ? Number(formData.positionId)
            : null,
          hire_date: formData.hireDate || null,
          employment_status: formData.employmentStatus,
          ...celebrationPayload(formData),
        }
      );

      showToast("Employee updated successfully", "success");

      setIsEditModalOpen(false);

      setCurrentEmployee(null);

      await loadEmployees();
    } catch (error) {
      console.error(error);

      showToast(
        error instanceof Error
          ? error.message
          : "Failed to update employee",
        "error"
      );
    }
  };

  // =========================
  // Delete Employee
  // =========================

  const handleDeleteEmployee = async () => {
    if (!currentEmployee) return;

    try {
      await SmartHRApi.deleteEmployee(
        Number(currentEmployee.id)
      );

      showToast("Employee deleted successfully", "success");

      setIsDeleteModalOpen(false);

      setCurrentEmployee(null);

      await loadEmployees();
    } catch (error) {
      console.error(error);

      showToast(
        error instanceof Error
          ? error.message
          : "Failed to delete employee",
        "error"
      );
    }
  };

  // =========================
  // Render
  // =========================

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('hr.employees.title')}
        description={t('hr.employees.subtitle')}
        action={
          <Button onClick={handleOpenAdd}>
            <Plus size={18} />
            {t('hr.employees.add')}
          </Button>
        }
      />

      {/* Filters */}

      <Card>
        <div className="p-5 flex flex-col lg:flex-row gap-4">
          <div className="flex-1">
            <Input
              placeholder={t('hr.employees.search')}
              value={searchQuery}
              onChange={(e) =>
                setSearchQuery(e.target.value)
              }
            />
          </div>

          <div className="w-full lg:w-56">
            <Select
              value={selectedDepartment}
              onChange={(e) =>
                setSelectedDepartment(e.target.value)
              }
            >
              <option value="ALL">
                {t('hr.employees.allDepartments')}
              </option>

              {departments.map((department) => (
                <option
                  key={department}
                  value={department}
                >
                  {department}
                </option>
              ))}
            </Select>
          </div>

          <div className="w-full lg:w-48">
            <Select
              value={selectedStatus}
              onChange={(e) =>
                setSelectedStatus(e.target.value)
              }
            >
              <option value="ALL">
                {t('filter.allStatusesLabel')}
              </option>

              <option value="Active">
                {t('hr.employees.statusActive')}
              </option>

              <option value="Terminated">
                {t('hr.employees.statusTerminated')}
              </option>
            </Select>
          </div>
        </div>
      </Card>

      {/* Employee List */}

      <Card>
        {loading ? (
          <div className="p-10 text-center text-stone-500">
            {t('hr.employees.loading')}
          </div>
        ) : paginatedEmployees.length === 0 ? (
          <div className="p-10 text-center">
            <Users
              size={40}
              className="mx-auto mb-3 text-stone-400"
            />

            <h3 className="font-semibold text-stone-700">
              {t('hr.employees.empty')}
            </h3>

            <p className="text-sm text-stone-500 mt-1">
              {t('hr.employees.emptyHint')}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-start">
                  <th className="p-4 text-sm font-semibold">
                    {t('table.employee')}
                  </th>

                  <th className="p-4 text-sm font-semibold">
                    {t('table.department')}
                  </th>

                  <th className="p-4 text-sm font-semibold">
                    {t('table.position')}
                  </th>

                  <th className="p-4 text-sm font-semibold">
                    {t('table.phone')}
                  </th>

                  <th className="p-4 text-sm font-semibold">
                    {t('table.status')}
                  </th>

                  <th className="p-4 text-sm font-semibold">
                    {t('hr.employees.hireDate')}
                  </th>

                  <th className="p-4 text-sm font-semibold">
                    {t('table.actions')}
                  </th>
                </tr>
              </thead>

              <tbody>
                {paginatedEmployees.map((employee) => (
                  <tr
                    key={employee.id}
                    className="border-b hover:bg-stone-50"
                  >
                    <td className="p-4">
                      <div>
                        <div className="font-semibold">
                          {employee.firstName}{" "}
                          {employee.lastName}
                        </div>

                        <div className="text-sm text-stone-500 flex items-center gap-1">
                          <Mail size={14} />
                          {employee.email}
                        </div>

                        <div className="text-xs text-stone-400 mt-1">
                          {employee.employeeId}
                        </div>
                      </div>
                    </td>

                    <td className="p-4">
                      {employee.department}
                    </td>

                    <td className="p-4">
                      {employee.position}
                    </td>

                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <Phone size={14} />
                        {employee.phone || "N/A"}
                      </div>
                    </td>

                    <td className="p-4">
                      <Badge>
                        {employee.status === 'Active'
                          ? t('hr.employees.statusActive')
                          : t('hr.employees.statusTerminated')}
                      </Badge>
                    </td>

                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <Calendar size={14} />
                        {employee.hireDate || "N/A"}
                      </div>
                    </td>

                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <Button
                          onClick={() =>
                            onView360?.(employee.id)
                          }
                        >
                          <Eye size={16} />
                        </Button>

                        <Button
                          onClick={() =>
                            handleOpenEdit(employee)
                          }
                        >
                          <Edit2 size={16} />
                        </Button>

                        <Button
                          onClick={() => {
                            setCurrentEmployee(employee);
                            setIsDeleteModalOpen(true);
                          }}
                        >
                          <Trash2 size={16} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}

        {!loading &&
          filteredEmployees.length > 0 && (
            <div className="p-4 flex items-center justify-between border-t">
              <p className="text-sm text-stone-500">
                Showing{" "}
                {(currentPage - 1) * itemsPerPage + 1}–
                {Math.min(
                  currentPage * itemsPerPage,
                  filteredEmployees.length
                )}{" "}
                of {filteredEmployees.length}
              </p>

              <div className="flex gap-2">
                <Button
                  onClick={() =>
                    setCurrentPage((page) =>
                      Math.max(1, page - 1)
                    )
                  }
                >
                  <ChevronLeft size={16} data-flip-rtl />
                </Button>

                <span className="px-3 py-2 text-sm">
                  {currentPage} / {totalPages}
                </span>

                <Button
                  onClick={() =>
                    setCurrentPage((page) =>
                      Math.min(totalPages, page + 1)
                    )
                  }
                >
                  <ChevronRight size={16} data-flip-rtl />
                </Button>
              </div>
            </div>
          )}
      </Card>

      {/* Add Employee Modal */}

      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t('hr.employees.add')}
      >
        <div className="space-y-4">
          <Input
            label={t('hr.employees.firstName')}
            value={formData.firstName}
            onChange={(e) =>
              setFormData({
                ...formData,
                firstName: e.target.value,
              })
            }
          />

          <Input
            label={t('hr.employees.lastName')}
            value={formData.lastName}
            onChange={(e) =>
              setFormData({
                ...formData,
                lastName: e.target.value,
              })
            }
          />

          <Input
            label={t('table.phone')}
            value={formData.phone}
            onChange={(e) =>
              setFormData({
                ...formData,
                phone: e.target.value,
              })
            }
          />

          <Input
            label={t('hr.employees.hireDate')}
            type="date"
            value={formData.hireDate}
            onChange={(e) =>
              setFormData({
                ...formData,
                hireDate: e.target.value,
              })
            }
          />

          <CelebrationDateFields
            values={formData}
            onChange={(key, value) => setFormData({ ...formData, [key]: value })}
          />

          <div className="flex justify-end gap-3">
            <Button
              onClick={() =>
                setIsAddModalOpen(false)
              }
            >
              {t('action.cancel')}
            </Button>

            <Button onClick={handleAddEmployee}>
              {t('hr.employees.create')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Edit Employee Modal */}

      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title={t('hr.employees.edit')}
      >
        <div className="space-y-4">
          <Input
            label={t('hr.employees.firstName')}
            value={formData.firstName}
            onChange={(e) =>
              setFormData({
                ...formData,
                firstName: e.target.value,
              })
            }
          />

          <Input
            label={t('hr.employees.lastName')}
            value={formData.lastName}
            onChange={(e) =>
              setFormData({
                ...formData,
                lastName: e.target.value,
              })
            }
          />

          <Input
            label={t('table.phone')}
            value={formData.phone}
            onChange={(e) =>
              setFormData({
                ...formData,
                phone: e.target.value,
              })
            }
          />

          <Input
            label={t('hr.employees.hireDate')}
            type="date"
            value={formData.hireDate}
            onChange={(e) =>
              setFormData({
                ...formData,
                hireDate: e.target.value,
              })
            }
          />

          <CelebrationDateFields
            values={formData}
            onChange={(key, value) => setFormData({ ...formData, [key]: value })}
          />

          <div className="flex justify-end gap-3">
            <Button
              onClick={() =>
                setIsEditModalOpen(false)
              }
            >
              {t('action.cancel')}
            </Button>

            <Button onClick={handleUpdateEmployee}>
              {t('action.saveChanges')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Modal */}

      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        title={t('hr.employees.delete')}
      >
        <div className="space-y-5">
          <p className="text-stone-600">
            Are you sure you want to delete{" "}
            <strong>
              {currentEmployee?.firstName}{" "}
              {currentEmployee?.lastName}
            </strong>
            ?
          </p>

          <div className="flex justify-end gap-3">
            <Button
              onClick={() =>
                setIsDeleteModalOpen(false)
              }
            >
              {t('action.cancel')}
            </Button>

            <Button onClick={handleDeleteEmployee}>
              {t('action.delete')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};