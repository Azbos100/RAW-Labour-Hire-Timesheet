/**
 * API Service
 * Axios instance configured for RAW Timesheet API
 */

import axios from 'axios';
import Constants from 'expo-constants';

// Store token in module scope - this persists across requests
let authToken: string | null = null;

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

// Production URL - Railway deployment
const PRODUCTION_URL = 'https://raw-labour-hire-timesheet-production.up.railway.app/api';

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL
  ? process.env.EXPO_PUBLIC_API_URL
  : __DEV__
  ? getDevBaseUrl()
  : PRODUCTION_URL;

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
    if (error.response?.status === 401) {
      console.log('[API] Unauthorized - token may be expired or missing');
    }
    return Promise.reject(error);
  }
);

export default api;

// Helper to set auth token - stores in module variable
export const setAuthToken = (token: string | null) => {
  authToken = token;
  console.log(`[API] Auth token ${token ? 'SET' : 'CLEARED'}`);
};

// ==================== CLOCK API ====================

export const clockAPI = {
  getStatus: (userId?: number) => api.get('/clock/status', { params: { user_id: userId } }),
  
  clockIn: (data: {
    latitude: number;
    longitude: number;
    job_site_id?: number;
    worked_as?: string;
    user_id?: number;
  }) => api.post('/clock/in', data),
  
  clockOut: (data: {
    latitude: number;
    longitude: number;
    comments?: string;
    first_aid_injury?: boolean;
    user_id?: number;
  }) => api.post('/clock/out', data),
  
  getHistory: (days: number = 7) => api.get(`/clock/history?days=${days}`),
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
  updateProfile: (data: {
    first_name?: string;
    surname?: string;
    phone?: string;
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
