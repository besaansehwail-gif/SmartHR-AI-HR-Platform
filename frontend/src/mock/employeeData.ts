import { WorkMode } from '../types';

export interface EmployeeProfile {
  id: string;
  employeeId: string;
  name: string;
  firstName: string;
  lastName: string;
  preferredName?: string;
  email: string;
  phone: string;
  avatar: string;
  position: string;
  department: string;
  gradeLevel: string;
  manager: string;
  managerTitle: string;
  managerEmail: string;
  managerAvatar: string;
  hireDate: string;
  tenure: string;
  employmentStatus: 'Active' | 'On Leave' | 'Probation';
  employmentType: string;
  workMode: WorkMode;
  workSchedule: string;
  officeLocation: string;
  deskLocation: string;
  timezone: string;
  bio: string;
  emergencyContact: {
    name: string;
    relationship: string;
    phone: string;
  };
  skills: string[];
}

export interface EmployeeAttendanceToday {
  date: string;
  dayOfWeek: string;
  status: 'Checked In' | 'Checked Out' | 'Not Checked In' | 'On Leave';
  checkInTime?: string;
  checkOutTime?: string;
  hoursLogged: string;
  workMode: WorkMode;
  location: string;
}

export interface AttendanceHistoryRecord {
  id: string;
  date: string;
  dayOfWeek: string;
  checkIn: string;
  checkOut: string;
  totalHours: string;
  workMode: WorkMode;
  status: 'Present' | 'Late' | 'Absent' | 'Leave' | 'Holiday';
  notes?: string;
}

export interface EmployeeLeaveBalance {
  type: string;
  total: number;
  used: number;
  pending: number;
  available: number;
  color: string;
}

export interface EmployeeLeaveRequestItem {
  id: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  duration: string;
  daysCount: number;
  reason: string;
  status: 'Approved' | 'Pending' | 'Rejected' | 'Cancelled';
  appliedDate: string;
  approvedBy?: string;
  approvalDate?: string;
  managerNotes?: string;
}

export interface EmployeeCourse {
  id: string;
  title: string;
  category: string;
  provider: string;
  duration: string;
  modulesCount: number;
  completedModules: number;
  progressPercentage: number;
  status: 'In Progress' | 'Completed' | 'Available';
  isMandatory: boolean;
  dueDate?: string;
  completionDate?: string;
  score?: number;
  description: string;
  instructor: string;
  badge?: string;
}

export interface EmployeeGoal {
  id: string;
  title: string;
  category: string;
  progress: number;
  targetDate: string;
  status: 'On Track' | 'At Risk' | 'Completed';
  keyResults: string[];
}

export interface CareerLadderStep {
  level: string;
  title: string;
  grade: string;
  status: 'completed' | 'current' | 'target' | 'future';
  dateOrTimeline: string;
  readinessPercentage?: number;
  summary: string;
  requirements: string[];
}

export interface EmployeeSkillMatrixItem {
  skill: string;
  category: 'Core Engineering' | 'Architecture & Cloud' | 'Leadership & Collaboration' | 'Product & Domain';
  currentLevel: number; // 1 to 5
  targetLevel: number; // 1 to 5
  status: 'Mastered' | 'Proficient' | 'Developing';
  verifiedBy: string;
}

export interface EmployeeAttentionItem {
  id: string;
  title: string;
  description: string;
  type: 'training' | 'meeting' | 'leave' | 'review' | 'action';
  dueDate: string;
  severity: 'high' | 'medium' | 'low';
  actionLabel: string;
  targetPage?: string;
}

export interface EmployeeNotificationItem {
  id: string;
  type: 'leave' | 'attendance' | 'training' | 'performance' | 'company';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  actionText?: string;
  targetPage?: string;
}

export const initialEmployeeProfile: EmployeeProfile = {
  id: 'EMP-0118',
  employeeId: 'EMP-0118',
  name: 'Alex Rivera',
  firstName: 'Alex',
  lastName: 'Rivera',
  preferredName: 'Alex',
  email: 'alex.rivera@example.com',
  phone: '+1 (202) 555-0100',
  avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200&auto=format&fit=crop&q=80',
  position: 'Senior Full-Stack Engineer',
  department: 'Engineering',
  gradeLevel: 'L4 - Senior Engineer',
  manager: 'Marcus Vance',
  managerTitle: 'VP of Technology',
  managerEmail: 'marcus.vance@example.com',
  managerAvatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80',
  hireDate: '2022-03-15',
  tenure: '2 yrs 6 mos',
  employmentStatus: 'Active',
  employmentType: 'Full-time Permanent',
  workMode: 'Hybrid',
  workSchedule: 'Mon-Fri, 9:00 AM - 5:30 PM PST',
  officeLocation: 'San Francisco HQ - Campus North',
  deskLocation: 'Building B, Floor 3, Desk 34-A',
  timezone: 'America/Los_Angeles (PST)',
  bio: 'Senior full-stack engineer leading cloud architectural scaling, design system orchestration, and resilient microservice APIs. Passionate about developer ergonomics and high-performance Web UI.',
  emergencyContact: {
    name: 'Sofia Rivera',
    relationship: 'Spouse',
    phone: '+1 (202) 555-0101',
  },
  skills: [
    'TypeScript & React',
    'FastAPI & Python',
    'Microservices Architecture',
    'PostgreSQL Optimization',
    'Docker & Kubernetes',
    'Tailwind CSS Systems',
    'Technical Mentorship',
    'Distributed Systems',
  ],
};

export const initialAttendanceToday: EmployeeAttendanceToday = {
  date: 'Today, Sep 12, 2024',
  dayOfWeek: 'Thursday',
  status: 'Checked In',
  checkInTime: '08:54 AM',
  checkOutTime: '—',
  hoursLogged: '6h 28m',
  workMode: 'Hybrid',
  location: 'San Francisco HQ (In-Office)',
};

export const initialAttendanceHistory: AttendanceHistoryRecord[] = [
  {
    id: 'ATT-101',
    date: '2024-09-12',
    dayOfWeek: 'Thu',
    checkIn: '08:54 AM',
    checkOut: '— (Active)',
    totalHours: '6.5 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'Campus North, Badge In',
  },
  {
    id: 'ATT-102',
    date: '2024-09-11',
    dayOfWeek: 'Wed',
    checkIn: '08:58 AM',
    checkOut: '05:32 PM',
    totalHours: '8.5 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'Desk 34-A',
  },
  {
    id: 'ATT-103',
    date: '2024-09-10',
    dayOfWeek: 'Tue',
    checkIn: '09:02 AM',
    checkOut: '05:45 PM',
    totalHours: '8.7 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'Home Office (VPN Connected)',
  },
  {
    id: 'ATT-104',
    date: '2024-09-09',
    dayOfWeek: 'Mon',
    checkIn: '09:16 AM',
    checkOut: '05:30 PM',
    totalHours: '8.2 hrs',
    workMode: 'Remote',
    status: 'Late',
    notes: 'Late clock-in (16m over core time). Grace period auto-applied.',
  },
  {
    id: 'ATT-105',
    date: '2024-09-06',
    dayOfWeek: 'Fri',
    checkIn: '08:48 AM',
    checkOut: '05:15 PM',
    totalHours: '8.4 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'Sprint demo deployment session',
  },
  {
    id: 'ATT-106',
    date: '2024-09-05',
    dayOfWeek: 'Thu',
    checkIn: '08:52 AM',
    checkOut: '05:40 PM',
    totalHours: '8.8 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'On-site team planning',
  },
  {
    id: 'ATT-107',
    date: '2024-09-04',
    dayOfWeek: 'Wed',
    checkIn: '08:55 AM',
    checkOut: '05:35 PM',
    totalHours: '8.6 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'Campus North',
  },
  {
    id: 'ATT-108',
    date: '2024-09-03',
    dayOfWeek: 'Tue',
    checkIn: '08:45 AM',
    checkOut: '05:20 PM',
    totalHours: '8.5 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'WFH standard check-in',
  },
  {
    id: 'ATT-109',
    date: '2024-09-02',
    dayOfWeek: 'Mon',
    checkIn: '—',
    checkOut: '—',
    totalHours: '0 hrs',
    workMode: 'Hybrid',
    status: 'Holiday',
    notes: 'Labor Day (Company Paid Holiday)',
  },
  {
    id: 'ATT-110',
    date: '2024-08-30',
    dayOfWeek: 'Fri',
    checkIn: '08:50 AM',
    checkOut: '05:25 PM',
    totalHours: '8.5 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'End-of-month release validation',
  },
  {
    id: 'ATT-111',
    date: '2024-08-29',
    dayOfWeek: 'Thu',
    checkIn: '—',
    checkOut: '—',
    totalHours: '0 hrs',
    workMode: 'Hybrid',
    status: 'Leave',
    notes: 'Approved Annual Vacation day',
  },
  {
    id: 'ATT-112',
    date: '2024-08-28',
    dayOfWeek: 'Wed',
    checkIn: '—',
    checkOut: '—',
    totalHours: '0 hrs',
    workMode: 'Hybrid',
    status: 'Leave',
    notes: 'Approved Annual Vacation day',
  },
];

export const initialLeaveBalances: EmployeeLeaveBalance[] = [
  {
    type: 'Annual Vacation',
    total: 22.0,
    used: 7.5,
    pending: 3.0,
    available: 11.5,
    color: 'purple',
  },
  {
    type: 'Sick & Medical Leave',
    total: 10.0,
    used: 2.0,
    pending: 0.0,
    available: 8.0,
    color: 'emerald',
  },
  {
    type: 'Floating Holiday / Personal',
    total: 3.0,
    used: 1.0,
    pending: 0.0,
    available: 2.0,
    color: 'amber',
  },
  {
    type: 'Volunteer & Learning Days',
    total: 2.0,
    used: 0.0,
    pending: 0.0,
    available: 2.0,
    color: 'sky',
  },
];

export const initialLeaveRequests: EmployeeLeaveRequestItem[] = [
  {
    id: 'LV-2024-088',
    leaveType: 'Annual Vacation',
    startDate: '2024-10-14',
    endDate: '2024-10-16',
    duration: '3 Days',
    daysCount: 3,
    reason: 'Family autumn getaway & personal recharge before Q4 platform launch.',
    status: 'Pending',
    appliedDate: '2024-09-08',
    managerNotes: 'Pending review by Marcus Vance.',
  },
  {
    id: 'LV-2024-071',
    leaveType: 'Annual Vacation',
    startDate: '2024-08-28',
    endDate: '2024-08-29',
    duration: '2 Days',
    daysCount: 2,
    reason: 'Long weekend family trip.',
    status: 'Approved',
    appliedDate: '2024-08-12',
    approvedBy: 'Marcus Vance',
    approvalDate: '2024-08-14',
    managerNotes: 'Approved. Enjoy the break!',
  },
  {
    id: 'LV-2024-049',
    leaveType: 'Sick & Medical Leave',
    startDate: '2024-07-08',
    endDate: '2024-07-09',
    duration: '2 Days',
    daysCount: 2,
    reason: 'Dental oral surgery recovery.',
    status: 'Approved',
    appliedDate: '2024-07-06',
    approvedBy: 'Marcus Vance',
    approvalDate: '2024-07-06',
    managerNotes: 'Medical note confirmed. Wishing you a quick recovery.',
  },
  {
    id: 'LV-2024-022',
    leaveType: 'Floating Holiday',
    startDate: '2024-05-17',
    endDate: '2024-05-17',
    duration: '1 Day',
    daysCount: 1,
    reason: 'Personal anniversary day off.',
    status: 'Approved',
    appliedDate: '2024-05-02',
    approvedBy: 'Marcus Vance',
    approvalDate: '2024-05-03',
  },
  {
    id: 'LV-2024-015',
    leaveType: 'Annual Vacation',
    startDate: '2024-03-25',
    endDate: '2024-03-29',
    duration: '5 Days',
    daysCount: 5,
    reason: 'Spring break travel.',
    status: 'Approved',
    appliedDate: '2024-02-28',
    approvedBy: 'Marcus Vance',
    approvalDate: '2024-03-02',
    managerNotes: 'Coverage confirmed with Tariq Mansoor.',
  },
];

export const initialEmployeeCourses: EmployeeCourse[] = [
  {
    id: 'CRS-01',
    title: 'Advanced FastAPI Microservices & Event Architecture',
    category: 'Engineering & Architecture',
    provider: 'SmartHR Tech Guild',
    duration: '8 Hours',
    modulesCount: 8,
    completedModules: 6,
    progressPercentage: 75,
    status: 'In Progress',
    isMandatory: false,
    dueDate: 'Sep 30, 2024',
    description: 'High-throughput async Python services, Redis pub/sub caching, OpenAPI validation, and containerized zero-downtime deployments.',
    instructor: 'Marcus Vance (VP of Tech)',
    badge: 'Core Tech Track',
  },
  {
    id: 'CRS-02',
    title: 'SOC-2 Type II Security Compliance & Zero Trust',
    category: 'Security & Compliance',
    provider: 'CyberTrust Global',
    duration: '4 Hours',
    modulesCount: 10,
    completedModules: 9,
    progressPercentage: 90,
    status: 'In Progress',
    isMandatory: true,
    dueDate: 'Oct 05, 2024',
    description: 'Mandatory annual organizational compliance on cryptographic key rotation, least-privilege RBAC, and PII protection.',
    instructor: 'Chief Information Security Office',
    badge: 'Mandatory',
  },
  {
    id: 'CRS-03',
    title: 'React 19 & Next-Gen State Synchronization',
    category: 'Frontend Engineering',
    provider: 'Frontend Masters Enterprise',
    duration: '12 Hours',
    modulesCount: 12,
    completedModules: 12,
    progressPercentage: 100,
    status: 'Completed',
    isMandatory: false,
    completionDate: 'Aug 14, 2024',
    score: 98,
    description: 'Mastering concurrent rendering, React Server Components, transition primitives, and accessibility design tokens.',
    instructor: 'Sarah Drasner & Dan Abramov',
    badge: 'Certified',
  },
  {
    id: 'CRS-04',
    title: 'Cloud-Native Docker & Kubernetes Production Patterns',
    category: 'DevOps & Cloud',
    provider: 'Cloud Native Computing Foundation',
    duration: '10 Hours',
    modulesCount: 8,
    completedModules: 8,
    progressPercentage: 100,
    status: 'Completed',
    isMandatory: false,
    completionDate: 'Jun 22, 2024',
    score: 94,
    description: 'Resilient pod configuration, readiness probes, Helm charts, and automated rollbacks under traffic spikes.',
    instructor: 'Kelsey Hightower',
    badge: 'Certified',
  },
  {
    id: 'CRS-05',
    title: 'Inclusive Technical Leadership & Code Review Ethics',
    category: 'Leadership & Mentorship',
    provider: 'SmartHR Leadership Institute',
    duration: '3 Hours',
    modulesCount: 5,
    completedModules: 5,
    progressPercentage: 100,
    status: 'Completed',
    isMandatory: true,
    completionDate: 'Apr 10, 2024',
    score: 100,
    description: 'Constructive asynchronous code reviews, psychological safety in pull request triage, and junior engineer sponsorship.',
    instructor: 'Sarah Chen (Chief People Officer)',
    badge: 'Completed',
  },
  {
    id: 'CRS-06',
    title: 'Distributed Tracing & OpenTelemetry at Scale',
    category: 'Architecture & SRE',
    provider: 'O’Reilly Enterprise',
    duration: '6 Hours',
    modulesCount: 6,
    completedModules: 0,
    progressPercentage: 0,
    status: 'Available',
    isMandatory: false,
    description: 'Instrumenting spans, Jaeger visualization, latency anomaly detection, and distributed bottleneck triage across microservices.',
    instructor: 'Charity Majors',
    badge: 'Recommended for Staff Role',
  },
  {
    id: 'CRS-07',
    title: 'Executive Engineering Presence & RFC Authorship',
    category: 'Leadership & Influence',
    provider: 'Pragmatic Leadership Guild',
    duration: '5 Hours',
    modulesCount: 5,
    completedModules: 0,
    progressPercentage: 0,
    status: 'Available',
    isMandatory: false,
    description: 'Structuring clear Request For Comments, facilitating architecture review meetings, and aligning executive stakeholders on technical debt.',
    instructor: 'Gergely Orosz',
    badge: 'Career Accelerator',
  },
  {
    id: 'CRS-08',
    title: 'PostgreSQL Deep Dive: Query Planning & Indexing Internals',
    category: 'Database Systems',
    provider: 'Postgres Open Academy',
    duration: '7 Hours',
    modulesCount: 7,
    completedModules: 0,
    progressPercentage: 0,
    status: 'Available',
    isMandatory: false,
    description: 'Analyzing EXPLAIN ANALYZE execution trees, partial indexes, BRIN indexing for timeseries logs, and MVCC concurrency tuning.',
    instructor: 'Bruce Momjian',
    badge: 'Elective',
  },
];

export const initialEmployeeGoals: EmployeeGoal[] = [
  {
    id: 'G-01',
    title: 'Deliver SmartHR Employee Workspace Design System with 100% WCAG AA contrast',
    category: 'UI / UX Excellence',
    progress: 95,
    targetDate: 'Sep 30, 2024',
    status: 'On Track',
    keyResults: [
      'Built 8 employee modules with uniform typography and mathematical spacing',
      'Audited color contrast on all cards and tables (all >= 4.5:1 ratio)',
      'Added keyboard focus states and clean tab navigation',
    ],
  },
  {
    id: 'G-02',
    title: 'Deploy FastAPI microservice gateway with sub-40ms response latency',
    category: 'Architecture',
    progress: 88,
    targetDate: 'Oct 15, 2024',
    status: 'On Track',
    keyResults: [
      'Containerized endpoints for attendance, leave, and notifications',
      'Implemented in-memory Redis caching for role permissions',
      'Achieved 28ms P95 latency in load testing (target: < 40ms)',
    ],
  },
  {
    id: 'G-03',
    title: 'Mentor 2 Associate Engineers through distributed queues implementation',
    category: 'People & Culture',
    progress: 75,
    targetDate: 'Oct 31, 2024',
    status: 'On Track',
    keyResults: [
      'Conducted weekly 1:1 architecture pair programming sessions with Hannah & Lucas',
      'Supervised production deployment of background job handlers without rollbacks',
    ],
  },
  {
    id: 'G-04',
    title: 'Publish Engineering RFC for Unified Multi-Region Cache Invalidation',
    category: 'Technical Strategy',
    progress: 100,
    targetDate: 'Sep 01, 2024',
    status: 'Completed',
    keyResults: [
      'Documented cache stampede mitigation strategy',
      'Approved unanimously by Engineering Architecture Council on Aug 28',
    ],
  },
];

export const initialCareerLadder: CareerLadderStep[] = [
  {
    level: 'L2',
    title: 'Junior Software Engineer',
    grade: 'Junior Level',
    status: 'completed',
    dateOrTimeline: 'Mar 2021 - Feb 2022',
    summary: 'Mastered component development, bug remediation, test suites, and git workflows.',
    requirements: ['Solid JavaScript/TypeScript foundations', 'Unit test coverage', 'Agile sprint delivery'],
  },
  {
    level: 'L3',
    title: 'Full-Stack Software Engineer II',
    grade: 'Mid-Level',
    status: 'completed',
    dateOrTimeline: 'Mar 2022 - Dec 2023',
    summary: 'Owned end-to-end full stack features, designed relational schemas, and participated in on-call triage.',
    requirements: ['Independent feature delivery', 'API design and SQL tuning', 'Code review rigor'],
  },
  {
    level: 'L4',
    title: 'Senior Full-Stack Engineer',
    grade: 'Senior Level (Current)',
    status: 'current',
    dateOrTimeline: 'Jan 2024 - Present',
    readinessPercentage: 82,
    summary: 'Leads complex system architectures, champions engineering standards, and mentors teammates toward technical autonomy.',
    requirements: [
      'Cross-team technical alignment',
      'High-velocity reliable architecture execution',
      'Direct peer mentorship & engineering cultural leadership',
    ],
  },
  {
    level: 'L5',
    title: 'Staff Software Engineer / Tech Lead',
    grade: 'Staff Level (Next Target)',
    status: 'target',
    dateOrTimeline: 'Targeted: Q1 2025 (82% Readiness)',
    readinessPercentage: 82,
    summary: 'Multi-squad technical direction, architectural governance, company-wide RFC leadership, and strategic technology selection.',
    requirements: [
      'Org-wide architectural consensus via RFCs (In progress - 1 completed)',
      'Scalable cross-cutting platform systems (> 50k DAU)',
      'Active leadership in hiring bars and senior promotion panels',
    ],
  },
  {
    level: 'L6',
    title: 'Principal Engineer / Director of Architecture',
    grade: 'Executive Engineering',
    status: 'future',
    dateOrTimeline: 'Future Horizon (3-5 Year Outlook)',
    summary: 'Defines multi-year technology vision, cloud financial governance, and high-impact industry innovations.',
    requirements: [
      'Multi-year platform roadmaps',
      'Executive-level technology strategy with C-suite',
      'External thought leadership & industry contributions',
    ],
  },
];

export const initialSkillsMatrix: EmployeeSkillMatrixItem[] = [
  {
    skill: 'TypeScript & React Architecture',
    category: 'Core Engineering',
    currentLevel: 5,
    targetLevel: 5,
    status: 'Mastered',
    verifiedBy: 'Marcus Vance',
  },
  {
    skill: 'FastAPI & Python Microservices',
    category: 'Core Engineering',
    currentLevel: 4,
    targetLevel: 5,
    status: 'Proficient',
    verifiedBy: 'Engineering Council',
  },
  {
    skill: 'Distributed Systems & Queues',
    category: 'Architecture & Cloud',
    currentLevel: 4,
    targetLevel: 5,
    status: 'Proficient',
    verifiedBy: 'Marcus Vance',
  },
  {
    skill: 'Docker, K8s & CI/CD Pipelines',
    category: 'Architecture & Cloud',
    currentLevel: 4,
    targetLevel: 4,
    status: 'Proficient',
    verifiedBy: 'DevOps Lead',
  },
  {
    skill: 'Database Indexing & PostgreSQL',
    category: 'Architecture & Cloud',
    currentLevel: 4,
    targetLevel: 5,
    status: 'Proficient',
    verifiedBy: 'Tech Guild',
  },
  {
    skill: 'Org-wide RFC & Spec Authorship',
    category: 'Leadership & Collaboration',
    currentLevel: 4,
    targetLevel: 5,
    status: 'Developing',
    verifiedBy: 'Staff Panel',
  },
  {
    skill: 'Engineering Mentorship & Sponsorship',
    category: 'Leadership & Collaboration',
    currentLevel: 5,
    targetLevel: 5,
    status: 'Mastered',
    verifiedBy: 'Sarah Chen',
  },
  {
    skill: 'Product & Design Token Systems',
    category: 'Product & Domain',
    currentLevel: 4,
    targetLevel: 5,
    status: 'Proficient',
    verifiedBy: 'Amara Okonkwo',
  },
];

export const initialEmployeeNotifications: EmployeeNotificationItem[] = [
  {
    id: 'EN-01',
    type: 'leave',
    title: 'Leave Request Received',
    message: 'Your 3-day annual leave request (Oct 14 - Oct 16) has been submitted to Marcus Vance for sign-off.',
    timestamp: '2 hours ago',
    read: false,
    actionText: 'View Leave Details',
    targetPage: 'emp-leave',
  },
  {
    id: 'EN-02',
    type: 'training',
    title: 'Compliance Reminder: SOC-2 Certification',
    message: 'Your mandatory SOC-2 Type II course has 1 module remaining. Complete before Oct 05 to maintain compliance.',
    timestamp: '5 hours ago',
    read: false,
    actionText: 'Resume Module',
    targetPage: 'emp-training',
  },
  {
    id: 'EN-03',
    type: 'performance',
    title: 'Q3 Appraisal Cycle Opened',
    message: 'Manager Marcus Vance has initiated your Q3 review cycle. Please submit your self-assessment draft.',
    timestamp: '1 day ago',
    read: false,
    actionText: 'Open Performance',
    targetPage: 'emp-performance',
  },
  {
    id: 'EN-04',
    type: 'attendance',
    title: 'Attendance Logged Successfully',
    message: 'Today’s check-in recorded at 08:54 AM (Hybrid - On-site SF HQ). Enjoy your workday!',
    timestamp: 'Today at 08:54 AM',
    read: true,
    actionText: 'View Attendance',
    targetPage: 'emp-attendance',
  },
  {
    id: 'EN-05',
    type: 'company',
    title: 'SmartHR All-Hands & Product Keynote',
    message: 'Company-wide All Hands scheduled for Friday at 10:00 AM PST. CEO keynote on Q4 platform expansion.',
    timestamp: '2 days ago',
    read: true,
  },
  {
    id: 'EN-06',
    type: 'training',
    title: 'Course Completed: React 19 Mastery',
    message: 'Congratulations! You scored 98% in "React 19 & Next-Gen State Synchronization" and earned a verified skill badge.',
    timestamp: '3 weeks ago',
    read: true,
    actionText: 'View Certificate',
    targetPage: 'emp-training',
  },
];
