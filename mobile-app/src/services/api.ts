/**
 * API Service
 * Axios instance configured for RAW Timesheet API
 */

import axios from 'axios';
import Constants from 'expo-constants';

// Store token in module scope - this persists across requests
let authToken: string | null = null;

// Callback invoked when the server rejects our token (expired/invalid).
// AuthContext registers this so the app can force a clean re-login.
let onUnauthorized: (() => void) | null = null;
// Debounce so a burst of simultaneous 401s only triggers one logout.
let handlingUnauthorized = false;

export const setUnauthorizedHandler = (handler: (() => void) | null) => {
  onUnauthorized = handler;
};

// API base URL - update this for production
const getDevBaseUrl = () => {
  const hostUri =
    (Constants as any)?.expoConfig?.hostUri ||
    (Constants as any)?.manifest?.hostUri;

  if (hostUri) {
    const host = String(hostUri).split(':')[0];
    if (host) {
      return `http://${host}:8000/api`;
    }
  }

  return 'http://localhost:8000/api';
};

// Production URL - DigitalOcean server (single source of truth for RAW Timesheet)
const PRODUCTION_URL = 'https://admin.rawlabourhire.com/api';

// Set to true to use production backend even in development (for testing via Expo Go over internet)
const USE_PRODUCTION_BACKEND = true;

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL
  ? process.env.EXPO_PUBLIC_API_URL
  : USE_PRODUCTION_BACKEND
  ? PRODUCTION_URL
  : __DEV__
  ? getDevBaseUrl()
  : PRODUCTION_URL;

/** Narrated staff training guide (same host as the API, no /api prefix). */
export const STAFF_GUIDE_URL = API_BASE_URL.replace(/\/api\/?$/, '') + '/guide';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - ALWAYS add token from module variable
api.interceptors.request.use(
  (config) => {
    // Force add the auth token to every request
    if (authToken) {
      config.headers.Authorization = `Bearer ${authToken}`;
    }
    console.log(`[API] ${config.method?.toUpperCase()} ${config.url} (token: ${authToken ? 'YES' : 'NO'})`);
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url: string = error.config?.url || '';
    // Don't force logout on the login/register calls themselves - a 401 there
    // just means wrong credentials and the screen handles its own error message.
    const isAuthEndpoint =
      url.includes('/auth/login') || url.includes('/auth/register');

    if (status === 401 && !isAuthEndpoint) {
      console.log('[API] Unauthorized - session expired, forcing re-login');
      authToken = null;
      if (onUnauthorized && !handlingUnauthorized) {
        handlingUnauthorized = true;
        onUnauthorized();
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// Helper to set auth token - stores in module variable
export const setAuthToken = (token: string | null) => {
  authToken = token;
  // A new valid token means a fresh session - re-arm the 401 handler.
  if (token) {
    handlingUnauthorized = false;
  }
  console.log(`[API] Auth token ${token ? 'SET' : 'CLEARED'}`);
};

// ==================== CLOCK API ====================

export const clockAPI = {
  getStatus: (userId?: number) => api.get('/clock/status', { params: { user_id: userId } }),
  
  clockIn: (data: {
    latitude: number;
    longitude: number;
    address?: string;
    job_site_id?: number;
    job_site_address?: string;
    worked_as?: string;
    user_id?: number;
  }) => api.post('/clock/in', data),
  
  clockOut: (data: {
    latitude: number;
    longitude: number;
    address?: string;
    comments?: string;
    first_aid_injury?: boolean;
    user_id?: number;
    is_overtime?: boolean;  // true=overtime, false=finished at assigned time
  }) => api.post('/clock/out', data),
  
  // Check if overtime prompt should be shown before clock-out
  checkOvertime: (userId?: number) => api.get('/clock/check-overtime', { params: { user_id: userId } }),
  
  getHistory: (days: number = 7) => api.get(`/clock/history?days=${days}`),
  
  // Toggle overtime mode - suppresses clock-out reminders when staying back
  setOvertimeMode: (data: {
    overtime_mode: boolean;
    user_id?: number;
  }) => api.post('/clock/overtime-mode', data),
};

// ==================== TIMESHEETS API ====================

export const timesheetsAPI = {
  list: (status?: string, userId?: number) => 
    api.get('/timesheets/', { params: { status, user_id: userId } }),
  
  getCurrent: () => api.get('/timesheets/current'),
  
  getById: (id: number) => api.get(`/timesheets/${id}`),
  
  submit: (id: number, data: {
    company_name: string;
    supervisor_name: string;
    supervisor_contact: string;
    supervisor_signature?: string;
    injury_reported?: string;
  }) => api.post(`/timesheets/${id}/submit`, data),
  
  submitEntry: (entryId: number, data: {
    company_name: string;
    supervisor_name: string;
    supervisor_contact: string;
    supervisor_signature?: string;
  }) => api.post(`/timesheets/entries/${entryId}/submit`, data),
};

// ==================== CLIENTS API ====================

export const clientsAPI = {
  list: () => api.get('/clients/'),
  
  getJobSites: (clientId: number) => 
    api.get(`/clients/${clientId}/job-sites`),
  
  getAllJobSites: () => api.get('/clients/job-sites/all'),
};

// ==================== TICKETS API ====================

export const ticketsAPI = {
  getTypes: () => api.get('/tickets/types'),
  
  getMyTickets: (userId?: number) => 
    api.get('/tickets/my-tickets', { params: { user_id: userId } }),
  
  upload: (data: {
    ticket_type_id: number;
    ticket_number?: string;
    issue_date?: string;
    expiry_date?: string;
    front_image: string;
    back_image?: string;
  }, userId?: number) => 
    api.post('/tickets/upload', data, { params: { user_id: userId } }),
  
  delete: (ticketId: number, userId?: number) => 
    api.delete(`/tickets/${ticketId}`, { params: { user_id: userId } }),
};

// ==================== PROFILE API ====================

export const profileAPI = {
  getProfile: (userId: number) =>
    api.get(`/users/${userId}`),
  
  updateProfile: (data: {
    first_name?: string;
    surname?: string;
    phone?: string;
    date_of_birth?: string;
    // Address
    address?: string;
    suburb?: string;
    state?: string;
    postcode?: string;
    // Emergency contact
    emergency_contact_name?: string;
    emergency_contact_phone?: string;
    emergency_contact_relationship?: string;
    // Bank details
    bank_account_name?: string;
    bank_bsb?: string;
    bank_account_number?: string;
    tax_file_number?: string;
    // Employment
    employment_type?: string;
  }, userId?: number) => 
    api.patch('/auth/update-profile', data, { params: { user_id: userId } }),
  
  changePassword: (data: {
    current_password: string;
    new_password: string;
  }, userId?: number) => 
    api.post('/auth/change-password', data, { params: { user_id: userId } }),
};

// ==================== INDUCTION API ====================

export const inductionAPI = {
  getDocuments: () => api.get('/induction/documents'),
  
  getStatus: (userId?: number) => 
    api.get('/induction/status', { params: { user_id: userId } }),
  
  signDocument: (data: {
    document_id: number;
    signature: string;
  }, userId?: number) => 
    api.post('/induction/sign', data, { params: { user_id: userId } }),
};

// ==================== JOB ASSIGNMENT API ====================

export const assignmentAPI = {
  // Get worker's job assignments (normalises multi-day list for all app versions)
  getAssignment: async (userId: number) => {
    const res = await api.get(`/users/${userId}/assignment`);
    const data = res.data || {};

    // Prefer explicit arrays from the API
    let jobs = data.upcoming_jobs || data.assignments || data.jobs || [];
    if (!Array.isArray(jobs)) jobs = [];

    if (jobs.length === 0 && data.assignment) {
      jobs = [data.assignment];
    }

    // If the server folded other days into the legacy single card, expand them
    if (jobs.length === 1 && Array.isArray(data.assignments) && data.assignments.length > 1) {
      jobs = data.assignments.filter((j: { is_current?: boolean }) => !j.is_current);
    }
    if (jobs.length === 1 && Array.isArray(data.upcoming_jobs) && data.upcoming_jobs.length > 1) {
      jobs = data.upcoming_jobs;
    }

    data.upcoming_jobs = jobs;
    data.jobs = data.assignments || jobs;
    return { ...res, data };
  },
  
  // Accept or decline job assignment for a specific date
  respondToAssignment: (userId: number, accepted: boolean, assignmentDate?: string | null) => 
    api.post(`/users/${userId}/assignment/respond`, {
      accepted,
      assignment_date: assignmentDate || undefined,
    }),
};
