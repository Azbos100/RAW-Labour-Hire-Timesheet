/**
 * API Service
 * Axios instance configured for RAW Timesheet API
 */

import axios from 'axios';

// API base URL - update this for production
const API_BASE_URL = __DEV__ 
  ? 'http://localhost:8000/api'  // Development
  : 'https://api.rawlabourhire.com/api';  // Production

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
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
      // Token expired or invalid - will be handled by auth context
      console.log('[API] Unauthorized - token may be expired');
    }
    return Promise.reject(error);
  }
);

export default api;

// ==================== CLOCK API ====================

export const clockAPI = {
  getStatus: () => api.get('/clock/status'),
  
  clockIn: (data: {
    latitude: number;
    longitude: number;
    job_site_id?: number;
    worked_as?: string;
  }) => api.post('/clock/in', data),
  
  clockOut: (data: {
    latitude: number;
    longitude: number;
    comments?: string;
    first_aid_injury?: boolean;
  }) => api.post('/clock/out', data),
  
  getHistory: (days: number = 7) => api.get(`/clock/history?days=${days}`),
};

// ==================== TIMESHEETS API ====================

export const timesheetsAPI = {
  list: (status?: string) => 
    api.get('/timesheets/', { params: { status } }),
  
  getCurrent: () => api.get('/timesheets/current'),
  
  getById: (id: number) => api.get(`/timesheets/${id}`),
  
  submit: (id: number, data: {
    supervisor_name: string;
    supervisor_contact: string;
    injury_reported?: string;
  }) => api.post(`/timesheets/${id}/submit`, data),
};

// ==================== CLIENTS API ====================

export const clientsAPI = {
  list: () => api.get('/clients/'),
  
  getJobSites: (clientId: number) => 
    api.get(`/clients/${clientId}/job-sites`),
  
  getAllJobSites: () => api.get('/clients/job-sites/all'),
};
