import { WorkMode } from '../types';

export interface TeamMember {
  id: string;
  employeeId: string;
  name: string;
  firstName: string;
  lastName: string;
  email: string;
  role: string;
  position: string;
  department: string;
  avatar?: string;
  workMode: WorkMode;
  attendanceStatus: 'Present' | 'Late' | 'On Leave' | 'Remote Active' | 'Offline';
  checkInTime?: string;
  checkOutTime?: string;
  performanceScore: number; // 1.0 - 5.0
  performanceTier: 'Exceptional' | 'Exceeds Expectations' | 'Meets Expectations' | 'Needs Improvement';
  reviewStatus: 'Completed' | 'Review Due' | 'Self-Assessment Submitted' | 'Scheduled';
  trainingProgress: number; // 0 - 100%
  completedCoursesCount: number;
  totalAssignedCourses: number;
  location: string;
  tenure: string;
  weeklyHours: number;
  capacityUtilization: number; // e.g. 85%
  keyGoals: {
    title: string;
    progress: number;
    status: 'On Track' | 'At Risk' | 'Completed';
  }[];
  recentFeedback: string;
  skills: { [skillName: string]: number }; // 1 - 5
}

export interface ManagerAttendanceRecord {
  id: string;
  employeeId: string;
  employeeName: string;
  department: string;
  date: string;
  checkIn: string;
  checkOut: string;
  totalHours: string;
  workMode: WorkMode;
  status: 'Present' | 'Late' | 'Absent' | 'On Leave' | 'Half Day';
  notes?: string;
}

export interface ManagerLeaveApproval {
  id: string;
  employeeId: string;
  employeeName: string;
  avatar?: string;
  position: string;
  department: string;
  leaveType: 'Annual Leave' | 'Sick Leave' | 'Parental' | 'Personal' | 'Bereavement';
  startDate: string;
  endDate: string;
  durationDays: number;
  reason: string;
  appliedDate: string;
  status: 'Pending' | 'Approved' | 'Rejected';
  remainingBalance: number;
  overlappingLeavesCount: number;
  managerNotes?: string;
}

export interface TeamGoal {
  id: string;
  title: string;
  ownerName: string;
  category: 'Engineering Quality' | 'Delivery' | 'Architecture' | 'Team Culture';
  progress: number;
  dueDate: string;
  status: 'On Track' | 'At Risk' | 'Completed';
}

export interface ManagerNotificationItem {
  id: string;
  type: 'approval' | 'attendance' | 'leave' | 'performance' | 'training';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  actionType?: 'approve-leave' | 'review-performance' | 'check-attendance' | 'view-training';
  targetId?: string;
  linkPage?: string;
}

export const initialTeamMembers: TeamMember[] = [
  {
    id: 'EMP-0106',
    employeeId: 'EMP-0106',
    name: 'Chloe Tremblay',
    firstName: 'Chloe',
    lastName: 'Tremblay',
    email: 'chloe.tremblay@example.com',
    position: 'Staff Frontend Architect',
    role: 'Staff Frontend Architect',
    department: 'Engineering',
    workMode: 'Remote',
    attendanceStatus: 'Remote Active',
    checkInTime: '08:45 AM',
    checkOutTime: '—',
    performanceScore: 4.9,
    performanceTier: 'Exceptional',
    reviewStatus: 'Completed',
    trainingProgress: 100,
    completedCoursesCount: 5,
    totalAssignedCourses: 5,
    location: 'Montreal, Canada',
    tenure: '2.4 yrs',
    weeklyHours: 41.5,
    capacityUtilization: 92,
    keyGoals: [
      { title: 'Migrate core design system to Tailwind v4', progress: 100, status: 'Completed' },
      { title: 'Reduce bundle load time below 800ms', progress: 85, status: 'On Track' },
    ],
    recentFeedback: 'Outstanding technical leadership on the new component token hierarchy.',
    skills: {
      'TypeScript & React': 5,
      'System Design': 5,
      'Design Systems': 5,
      'Cloud & CI/CD': 4,
      'Mentorship': 5,
    },
  },
  {
    id: 'EMP-0107',
    employeeId: 'EMP-0107',
    name: 'Tariq Mansoor',
    firstName: 'Tariq',
    lastName: 'Mansoor',
    email: 'tariq.mansoor@example.com',
    position: 'Senior Backend Engineer (Distributed Systems)',
    role: 'Senior Backend Engineer',
    department: 'Engineering',
    workMode: 'Hybrid',
    attendanceStatus: 'Present',
    checkInTime: '09:02 AM',
    checkOutTime: '—',
    performanceScore: 4.8,
    performanceTier: 'Exceptional',
    reviewStatus: 'Completed',
    trainingProgress: 90,
    completedCoursesCount: 4,
    totalAssignedCourses: 4,
    location: 'Austin, TX',
    tenure: '1.8 yrs',
    weeklyHours: 40.0,
    capacityUtilization: 88,
    keyGoals: [
      { title: 'FastAPI REST middleware caching layer', progress: 90, status: 'On Track' },
      { title: 'PostgreSQL read replicas orchestration', progress: 75, status: 'On Track' },
    ],
    recentFeedback: 'Delivered zero-downtime database migration ahead of schedule.',
    skills: {
      'Python & FastAPI': 5,
      'Distributed Systems': 5,
      'Database Architecture': 5,
      'Kubernetes': 4,
      'API Security': 5,
    },
  },
  {
    id: 'EMP-0108',
    employeeId: 'EMP-0108',
    name: 'Priya Sharma',
    firstName: 'Priya',
    lastName: 'Sharma',
    email: 'priya.sharma@example.com',
    position: 'Senior Product Designer',
    role: 'Senior Product Designer',
    department: 'Product & Design',
    workMode: 'Hybrid',
    attendanceStatus: 'Present',
    checkInTime: '09:15 AM',
    checkOutTime: '—',
    performanceScore: 4.7,
    performanceTier: 'Exceeds Expectations',
    reviewStatus: 'Review Due',
    trainingProgress: 85,
    completedCoursesCount: 3,
    totalAssignedCourses: 4,
    location: 'Austin, TX',
    tenure: '2.1 yrs',
    weeklyHours: 39.5,
    capacityUtilization: 84,
    keyGoals: [
      { title: 'Manager Workspace heuristic research', progress: 95, status: 'On Track' },
      { title: 'Accessibility WCAG AA compliance audit', progress: 80, status: 'On Track' },
    ],
    recentFeedback: 'Exceptional visual polish and user research insights on workflows.',
    skills: {
      'Design Systems': 5,
      'User Research': 5,
      'Figma & Prototyping': 5,
      'Design Thinking': 5,
      'Cross-functional': 4,
    },
  },
  {
    id: 'EMP-0109',
    employeeId: 'EMP-0109',
    name: 'Lucas Dupont',
    firstName: 'Lucas',
    lastName: 'Dupont',
    email: 'lucas.dupont@example.com',
    position: 'Full Stack Engineer',
    role: 'Full Stack Engineer',
    department: 'Engineering',
    workMode: 'Remote',
    attendanceStatus: 'Remote Active',
    checkInTime: '08:30 AM',
    checkOutTime: '—',
    performanceScore: 4.4,
    performanceTier: 'Exceeds Expectations',
    reviewStatus: 'Self-Assessment Submitted',
    trainingProgress: 75,
    completedCoursesCount: 3,
    totalAssignedCourses: 4,
    location: 'Paris, France',
    tenure: '1.2 yrs',
    weeklyHours: 38.5,
    capacityUtilization: 80,
    keyGoals: [
      { title: 'Real-time WebSocket notifications module', progress: 70, status: 'On Track' },
      { title: 'Employee 360 data synchronization', progress: 100, status: 'Completed' },
    ],
    recentFeedback: 'Consistent velocity and proactive communication across time zones.',
    skills: {
      'TypeScript & React': 4,
      'Node.js & Python': 4,
      'REST APIs': 5,
      'Testing & QA': 4,
      'Async Collaboration': 4,
    },
  },
  {
    id: 'EMP-0110',
    employeeId: 'EMP-0110',
    name: 'Aisha Al-Mansoor',
    firstName: 'Aisha',
    lastName: 'Al-Mansoor',
    email: 'aisha.mansoor@example.com',
    position: 'Cloud DevOps & Site Reliability Engineer',
    role: 'DevOps Engineer',
    department: 'Engineering',
    workMode: 'Hybrid',
    attendanceStatus: 'Late',
    checkInTime: '09:42 AM',
    checkOutTime: '—',
    performanceScore: 4.6,
    performanceTier: 'Exceeds Expectations',
    reviewStatus: 'Scheduled',
    trainingProgress: 95,
    completedCoursesCount: 4,
    totalAssignedCourses: 4,
    location: 'Austin, TX',
    tenure: '1.5 yrs',
    weeklyHours: 42.0,
    capacityUtilization: 90,
    keyGoals: [
      { title: 'Cloud Run ingress response latency under 120ms', progress: 85, status: 'On Track' },
      { title: 'Terraform multi-region DR automated failover', progress: 65, status: 'At Risk' },
    ],
    recentFeedback: 'Excellent incident response uptime: 99.98% availability this quarter.',
    skills: {
      'Kubernetes & GCP': 5,
      'Terraform IaC': 5,
      'CI/CD Pipelines': 5,
      'Monitoring & SLOs': 4,
      'Security Hardening': 4,
    },
  },
  {
    id: 'EMP-0111',
    employeeId: 'EMP-0111',
    name: 'Carlos Mendez',
    firstName: 'Carlos',
    lastName: 'Mendez',
    email: 'carlos.mendez@example.com',
    position: 'Data & Analytics Engineer',
    role: 'Data Engineer',
    department: 'Engineering',
    workMode: 'Onsite',
    attendanceStatus: 'Present',
    checkInTime: '08:50 AM',
    checkOutTime: '—',
    performanceScore: 4.5,
    performanceTier: 'Exceeds Expectations',
    reviewStatus: 'Completed',
    trainingProgress: 80,
    completedCoursesCount: 4,
    totalAssignedCourses: 5,
    location: 'Austin, TX',
    tenure: '2.0 yrs',
    weeklyHours: 40.0,
    capacityUtilization: 85,
    keyGoals: [
      { title: 'Workforce reporting metrics data warehouse', progress: 90, status: 'On Track' },
      { title: 'Automate weekly KPI aggregation pipeline', progress: 100, status: 'Completed' },
    ],
    recentFeedback: 'Created reliable data transformations for HR & Manager dashboards.',
    skills: {
      'SQL & Data Modeling': 5,
      'Python Data Stack': 4,
      'ETL Pipelines': 5,
      'Metrics Visualization': 4,
      'Data Governance': 4,
    },
  },
  {
    id: 'EMP-0112',
    employeeId: 'EMP-0112',
    name: 'Zoe Washington',
    firstName: 'Zoe',
    lastName: 'Washington',
    email: 'zoe.washington@example.com',
    position: 'QA Lead & Test Automation Engineer',
    role: 'QA Automation Lead',
    department: 'Engineering',
    workMode: 'Onsite',
    attendanceStatus: 'Present',
    checkInTime: '08:55 AM',
    checkOutTime: '—',
    performanceScore: 4.3,
    performanceTier: 'Meets Expectations',
    reviewStatus: 'Review Due',
    trainingProgress: 70,
    completedCoursesCount: 3,
    totalAssignedCourses: 4,
    location: 'Austin, TX',
    tenure: '1.1 yrs',
    weeklyHours: 39.0,
    capacityUtilization: 82,
    keyGoals: [
      { title: 'Cypress E2E regression coverage > 90%', progress: 75, status: 'On Track' },
      { title: 'Automated API schema contract testing', progress: 60, status: 'At Risk' },
    ],
    recentFeedback: 'Catches critical edge-case bugs before production deployments.',
    skills: {
      'E2E Test Frameworks': 5,
      'TypeScript & Cypress': 4,
      'API Testing': 4,
      'Quality Assurance': 5,
      'Bug Triaging': 4,
    },
  },
  {
    id: 'EMP-0113',
    employeeId: 'EMP-0113',
    name: 'Mateo Morales',
    firstName: 'Mateo',
    lastName: 'Morales',
    email: 'mateo.morales@example.com',
    position: 'Frontend Engineer',
    role: 'Frontend Engineer',
    department: 'Engineering',
    workMode: 'Remote',
    attendanceStatus: 'On Leave',
    checkInTime: '—',
    checkOutTime: '—',
    performanceScore: 4.2,
    performanceTier: 'Meets Expectations',
    reviewStatus: 'Completed',
    trainingProgress: 60,
    completedCoursesCount: 2,
    totalAssignedCourses: 4,
    location: 'Mexico City, Mexico',
    tenure: '0.9 yrs',
    weeklyHours: 0,
    capacityUtilization: 0,
    keyGoals: [
      { title: 'Interactive charting components library', progress: 80, status: 'On Track' },
      { title: 'Accessibility review for modal dialogs', progress: 65, status: 'On Track' },
    ],
    recentFeedback: 'Rapid progress on UI deliverables; currently on approved annual leave.',
    skills: {
      'React & Tailwind': 4,
      'JavaScript / TS': 4,
      'UI Architecture': 3,
      'State Management': 4,
      'Collaboration': 4,
    },
  },
  {
    id: 'EMP-0114',
    employeeId: 'EMP-0114',
    name: 'Hannah Becker',
    firstName: 'Hannah',
    lastName: 'Becker',
    email: 'hannah.becker@example.com',
    position: 'Associate Backend Engineer',
    role: 'Associate Backend Engineer',
    department: 'Engineering',
    workMode: 'Hybrid',
    attendanceStatus: 'Present',
    checkInTime: '08:58 AM',
    checkOutTime: '—',
    performanceScore: 4.1,
    performanceTier: 'Meets Expectations',
    reviewStatus: 'Review Due',
    trainingProgress: 90,
    completedCoursesCount: 4,
    totalAssignedCourses: 4,
    location: 'Austin, TX',
    tenure: '0.7 yrs',
    weeklyHours: 40.0,
    capacityUtilization: 78,
    keyGoals: [
      { title: 'Complete SOC2 Security & Compliance module', progress: 100, status: 'Completed' },
      { title: 'Implement rate limiting on auth endpoints', progress: 70, status: 'On Track' },
    ],
    recentFeedback: 'High eagerness to learn and quick turnaround on assigned PR reviews.',
    skills: {
      'Python & APIs': 3,
      'SQL Queries': 4,
      'Git Workflow': 4,
      'Code Quality': 4,
      'Learning Agility': 5,
    },
  },
  {
    id: 'EMP-0115',
    employeeId: 'EMP-0115',
    name: 'Kenji Takahashi',
    firstName: 'Kenji',
    lastName: 'Takahashi',
    email: 'kenji.takahashi@example.com',
    position: 'Product Manager (Workforce Intelligence)',
    role: 'Product Manager',
    department: 'Product & Design',
    workMode: 'Remote',
    attendanceStatus: 'On Leave',
    checkInTime: '—',
    checkOutTime: '—',
    performanceScore: 4.7,
    performanceTier: 'Exceeds Expectations',
    reviewStatus: 'Completed',
    trainingProgress: 100,
    completedCoursesCount: 4,
    totalAssignedCourses: 4,
    location: 'Seattle, WA',
    tenure: '2.5 yrs',
    weeklyHours: 0,
    capacityUtilization: 0,
    keyGoals: [
      { title: 'Q4 Workforce Analytics roadmap approval', progress: 100, status: 'Completed' },
      { title: 'User discovery interviews with 15 HR leads', progress: 90, status: 'On Track' },
    ],
    recentFeedback: 'Strategic clarity and strong empathy for enterprise manager pain points.',
    skills: {
      'Product Strategy': 5,
      'Data Analytics': 4,
      'Stakeholder Mgmt': 5,
      'User Research': 4,
      'Agile Delivery': 5,
    },
  },
  {
    id: 'EMP-0116',
    employeeId: 'EMP-0116',
    name: 'Leila Farouk',
    firstName: 'Leila',
    lastName: 'Farouk',
    email: 'leila.farouk@example.com',
    position: 'Senior UI/UX Researcher',
    role: 'Senior UX Researcher',
    department: 'Product & Design',
    workMode: 'Remote',
    attendanceStatus: 'Remote Active',
    checkInTime: '08:40 AM',
    checkOutTime: '—',
    performanceScore: 4.8,
    performanceTier: 'Exceptional',
    reviewStatus: 'Completed',
    trainingProgress: 100,
    completedCoursesCount: 5,
    totalAssignedCourses: 5,
    location: 'Toronto, Canada',
    tenure: '1.6 yrs',
    weeklyHours: 40.0,
    capacityUtilization: 86,
    keyGoals: [
      { title: 'Usability benchmark study for Attention Center', progress: 100, status: 'Completed' },
      { title: 'Develop quantitative heuristic dashboard', progress: 80, status: 'On Track' },
    ],
    recentFeedback: 'Conducted exceptional contextual inquiries with key enterprise stakeholders.',
    skills: {
      'User Research': 5,
      'Quantitative Studies': 5,
      'Usability Testing': 5,
      'Design Strategy': 4,
      'Data Synthesis': 5,
    },
  },
  {
    id: 'EMP-0117',
    employeeId: 'EMP-0117',
    name: 'Noah Bennett',
    firstName: 'Noah',
    lastName: 'Bennett',
    email: 'noah.bennett@example.com',
    position: 'Infrastructure & Database Administrator',
    role: 'Database Administrator',
    department: 'Engineering',
    workMode: 'Hybrid',
    attendanceStatus: 'Present',
    checkInTime: '08:52 AM',
    checkOutTime: '—',
    performanceScore: 4.5,
    performanceTier: 'Exceeds Expectations',
    reviewStatus: 'Scheduled',
    trainingProgress: 85,
    completedCoursesCount: 4,
    totalAssignedCourses: 4,
    location: 'Austin, TX',
    tenure: '2.2 yrs',
    weeklyHours: 41.0,
    capacityUtilization: 89,
    keyGoals: [
      { title: 'Automated backup validation pipeline', progress: 100, status: 'Completed' },
      { title: 'Query latency optimization under 25ms', progress: 85, status: 'On Track' },
    ],
    recentFeedback: 'Zero downtime during our major database failover drill.',
    skills: {
      'PostgreSQL & Cloud SQL': 5,
      'Performance Tuning': 5,
      'Disaster Recovery': 5,
      'Security Compliance': 4,
      'Cloud Architecture': 4,
    },
  },
];

export const initialManagerAttendance: ManagerAttendanceRecord[] = [
  {
    id: 'ATT-101',
    employeeId: 'EMP-0106',
    employeeName: 'Chloe Tremblay',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '08:45 AM',
    checkOut: '—',
    totalHours: '7.5 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'Remote active from Montreal hub',
  },
  {
    id: 'ATT-102',
    employeeId: 'EMP-0107',
    employeeName: 'Tariq Mansoor',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '09:02 AM',
    checkOut: '—',
    totalHours: '7.2 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'On-site Austin HQ Floor 3',
  },
  {
    id: 'ATT-103',
    employeeId: 'EMP-0108',
    employeeName: 'Priya Sharma',
    department: 'Product & Design',
    date: '2024-09-12',
    checkIn: '09:15 AM',
    checkOut: '—',
    totalHours: '7.0 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'On-site Austin HQ Floor 2',
  },
  {
    id: 'ATT-104',
    employeeId: 'EMP-0109',
    employeeName: 'Lucas Dupont',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '08:30 AM',
    checkOut: '—',
    totalHours: '7.8 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'Remote active from Paris hub',
  },
  {
    id: 'ATT-105',
    employeeId: 'EMP-0110',
    employeeName: 'Aisha Al-Mansoor',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '09:42 AM',
    checkOut: '—',
    totalHours: '6.5 hrs',
    workMode: 'Hybrid',
    status: 'Late',
    notes: 'Notified manager: traffic delay on MoPac',
  },
  {
    id: 'ATT-106',
    employeeId: 'EMP-0111',
    employeeName: 'Carlos Mendez',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '08:50 AM',
    checkOut: '—',
    totalHours: '7.4 hrs',
    workMode: 'Onsite',
    status: 'Present',
    notes: 'Austin HQ Lab A',
  },
  {
    id: 'ATT-107',
    employeeId: 'EMP-0112',
    employeeName: 'Zoe Washington',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '08:55 AM',
    checkOut: '—',
    totalHours: '7.3 hrs',
    workMode: 'Onsite',
    status: 'Present',
    notes: 'Austin HQ Floor 3',
  },
  {
    id: 'ATT-108',
    employeeId: 'EMP-0113',
    employeeName: 'Mateo Morales',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '—',
    checkOut: '—',
    totalHours: '0.0 hrs',
    workMode: 'Remote',
    status: 'On Leave',
    notes: 'Approved Annual Leave (Day 2 of 4)',
  },
  {
    id: 'ATT-109',
    employeeId: 'EMP-0114',
    employeeName: 'Hannah Becker',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '08:58 AM',
    checkOut: '—',
    totalHours: '7.3 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'On-site Austin HQ Floor 3',
  },
  {
    id: 'ATT-110',
    employeeId: 'EMP-0115',
    employeeName: 'Kenji Takahashi',
    department: 'Product & Design',
    date: '2024-09-12',
    checkIn: '—',
    checkOut: '—',
    totalHours: '0.0 hrs',
    workMode: 'Remote',
    status: 'On Leave',
    notes: 'Approved Personal Leave',
  },
  {
    id: 'ATT-111',
    employeeId: 'EMP-0116',
    employeeName: 'Leila Farouk',
    department: 'Product & Design',
    date: '2024-09-12',
    checkIn: '08:40 AM',
    checkOut: '—',
    totalHours: '7.6 hrs',
    workMode: 'Remote',
    status: 'Present',
    notes: 'Remote active from Toronto hub',
  },
  {
    id: 'ATT-112',
    employeeId: 'EMP-0117',
    employeeName: 'Noah Bennett',
    department: 'Engineering',
    date: '2024-09-12',
    checkIn: '08:52 AM',
    checkOut: '—',
    totalHours: '7.4 hrs',
    workMode: 'Hybrid',
    status: 'Present',
    notes: 'On-site Austin HQ Server Room',
  },
];

export const initialManagerNotifications: ManagerNotificationItem[] = [
  {
    id: 'MNOTIF-01',
    type: 'leave',
    title: 'Pending Leave Request: Lucas Dupont',
    message: 'Lucas Dupont requested 4 days Annual Leave (Sep 24 - Sep 27). No sprint overlap detected.',
    timestamp: '15 mins ago',
    read: false,
    actionType: 'approve-leave',
    targetId: 'MGR-LV-201',
    linkPage: 'mgr-leave',
  },
  {
    id: 'MNOTIF-02',
    type: 'attendance',
    title: 'Late Clock-in Alert: Aisha Al-Mansoor',
    message: 'Aisha Al-Mansoor checked in at 09:42 AM (42 mins late). Traffic advisory on MoPac reported.',
    timestamp: '1 hour ago',
    read: false,
    actionType: 'check-attendance',
    linkPage: 'mgr-attendance',
  },
  {
    id: 'MNOTIF-03',
    type: 'performance',
    title: 'Quarterly Review Due: Priya Sharma',
    message: 'Q3 Performance review for Priya Sharma is due in 3 days. Self-assessment has been received.',
    timestamp: '3 hours ago',
    read: false,
    actionType: 'review-performance',
    targetId: 'EMP-0108',
    linkPage: 'mgr-performance',
  },
  {
    id: 'MNOTIF-04',
    type: 'training',
    title: 'Mandatory Compliance Progress: Hannah Becker',
    message: 'Hannah Becker successfully completed the SOC2 Security & Compliance curriculum with a 100% score.',
    timestamp: 'Yesterday',
    read: true,
    actionType: 'view-training',
    linkPage: 'mgr-team',
  },
  {
    id: 'MNOTIF-05',
    type: 'approval',
    title: 'Leave Request: Aisha Al-Mansoor',
    message: 'Aisha Al-Mansoor submitted a 1-day sick leave request for medical appointment on Sep 16.',
    timestamp: 'Yesterday',
    read: false,
    actionType: 'approve-leave',
    targetId: 'MGR-LV-202',
    linkPage: 'mgr-leave',
  },
];

export const managerSkillsMatrixData = [
  { skill: 'TypeScript & React Architecture', lead: 'Chloe Tremblay', avgProficiency: 4.8, trainedCount: 10 },
  { skill: 'Python, FastAPI & Backend APIs', lead: 'Tariq Mansoor', avgProficiency: 4.6, trainedCount: 9 },
  { skill: 'Distributed Systems & Microservices', lead: 'Tariq Mansoor', avgProficiency: 4.5, trainedCount: 8 },
  { skill: 'Kubernetes, Cloud Run & GCP DevOps', lead: 'Aisha Al-Mansoor', avgProficiency: 4.4, trainedCount: 7 },
  { skill: 'UI/UX Design Systems & Accessibility', lead: 'Priya Sharma', avgProficiency: 4.7, trainedCount: 9 },
  { skill: 'PostgreSQL & Query Optimization', lead: 'Noah Bennett', avgProficiency: 4.6, trainedCount: 8 },
  { skill: 'Automated Testing (Cypress / Pytest)', lead: 'Zoe Washington', avgProficiency: 4.3, trainedCount: 11 },
  { skill: 'Product Discovery & Data Analytics', lead: 'Kenji Takahashi', avgProficiency: 4.7, trainedCount: 6 },
];

