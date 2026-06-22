/**
 * Authentication Context
 * Manages user login state and token storage
 */

import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { Alert } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import api, { setAuthToken, setUnauthorizedHandler } from '../services/api';
import { registerForPushNotificationsAsync, savePushToken } from '../services/notifications';

interface User {
  id: number;
  email: string;
  first_name: string;
  surname: string;
  phone?: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (userData: Partial<User>) => Promise<void>;
}

interface RegisterData {
  email: string;
  password: string;
  first_name: string;
  surname: string;
  phone?: string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = 'raw_auth_token';
const USER_KEY = 'raw_user_data';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Tracks whether a session is currently active, for the 401 handler closure.
  const hasSessionRef = useRef(false);

  useEffect(() => {
    hasSessionRef.current = !!token;
  }, [token]);

  // Load stored auth on app start
  useEffect(() => {
    loadStoredAuth();
  }, []);

  // Force a clean re-login whenever the server rejects our token (e.g. it
  // expired after a week). Without this the app would silently loop on 401s.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (hasSessionRef.current) {
        Alert.alert(
          'Session expired',
          'Please log in again to continue.'
        );
      }
      logout();
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const loadStoredAuth = async () => {
    try {
      const storedToken = await SecureStore.getItemAsync(TOKEN_KEY);
      const storedUser = await SecureStore.getItemAsync(USER_KEY);

      if (storedToken && storedUser) {
        setToken(storedToken);
        setUser(JSON.parse(storedUser));
        setAuthToken(storedToken);
      }
    } catch (error) {
      console.error('Error loading auth:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (email: string, password: string) => {
    try {
      // OAuth2 form data format
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      const response = await api.post('/auth/login', formData.toString(), {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      const { access_token, user: userData } = response.data;

      // Store credentials
      await SecureStore.setItemAsync(TOKEN_KEY, access_token);
      await SecureStore.setItemAsync(USER_KEY, JSON.stringify(userData));

      // Set auth header FIRST before updating state
      setAuthToken(access_token);

      // Update state
      setToken(access_token);
      setUser(userData);

      // Register for push notifications
      registerForPushNotificationsAsync().then(async (pushToken) => {
        if (pushToken && userData.id) {
          await savePushToken(userData.id, pushToken);
        }
      }).catch(err => console.warn('Push notification setup failed:', err));
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Login failed';
      throw new Error(message);
    }
  };

  const register = async (data: RegisterData) => {
    try {
      await api.post('/auth/register', data);
      // After registration, log them in
      await login(data.email, data.password);
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Registration failed';
      throw new Error(message);
    }
  };

  const logout = async () => {
    try {
      // Clear stored credentials
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      await SecureStore.deleteItemAsync(USER_KEY);

      // Clear auth header
      setAuthToken(null);

      // Clear state
      setToken(null);
      setUser(null);
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const updateUser = async (userData: Partial<User>) => {
    try {
      if (user) {
        const updatedUser = { ...user, ...userData };
        setUser(updatedUser);
        await SecureStore.setItemAsync(USER_KEY, JSON.stringify(updatedUser));
      }
    } catch (error) {
      console.error('Error updating user:', error);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token,
        isLoading,
        login,
        register,
        logout,
        updateUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
