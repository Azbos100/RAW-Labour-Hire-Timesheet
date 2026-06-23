/**
 * My Jobs Screen
 * Display current clocked-in job plus upcoming allocated jobs
 */

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import * as Updates from 'expo-updates';
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import { useAuth } from '../context/AuthContext';
import { clockAPI, assignmentAPI } from '../services/api';

type MyJobsScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList>;
};

interface ClockStatus {
  is_clocked_in: boolean;
  clock_in_time?: string;
  clock_in_address?: string;
  hours_worked_today: number;
  overtime_mode: boolean;
}

interface JobAssignment {
  job_site_id: number;
  job_site_name: string;
  job_site_address: string;
  assignment_date: string | null;
  start_time: string | null;
  assigned_at: string | null;
  accepted: boolean | null;
  is_current?: boolean;
}

export default function MyJobsScreen({ navigation }: MyJobsScreenProps) {
  const { user } = useAuth();
  const [clockStatus, setClockStatus] = useState<ClockStatus | null>(null);
  const [currentJob, setCurrentJob] = useState<JobAssignment | null>(null);
  const [upcomingJobs, setUpcomingJobs] = useState<JobAssignment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [respondingAssignment, setRespondingAssignment] = useState(false);

  const checkForAppUpdate = async () => {
    if (__DEV__ || !Updates.isEnabled) return;
    try {
      const result = await Updates.checkForUpdateAsync();
      if (result.isAvailable) {
        await Updates.fetchUpdateAsync();
        await Updates.reloadAsync();
      }
    } catch (e) {
      console.log('[MyJobs] update check failed:', e);
    }
  };

  const parseAssignmentResponse = (
    assignData: Record<string, unknown>,
    clockData: ClockStatus | null
  ): { current: JobAssignment | null; upcoming: JobAssignment[] } => {
    let current: JobAssignment | null = (assignData.current_job as JobAssignment) || null;
    let upcoming: JobAssignment[] = [];

    if (Array.isArray(assignData.upcoming_jobs) && assignData.upcoming_jobs.length > 0) {
      upcoming = assignData.upcoming_jobs as JobAssignment[];
    } else if (Array.isArray(assignData.assignments) && assignData.assignments.length > 0) {
      const all = assignData.assignments as JobAssignment[];
      if (!current) {
        current = all.find(j => j.is_current) || null;
      }
      const todayMel = new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Melbourne' });
      upcoming = all.filter(j => {
        if (j.is_current) return false;
        if (current && j.job_site_id === current.job_site_id
            && j.assignment_date === current.assignment_date && j.accepted === true) {
          return false;
        }
        return !j.assignment_date || j.assignment_date >= todayMel;
      });
    } else if (assignData.assignment) {
      upcoming = [assignData.assignment as JobAssignment];
    }

    if (!current && clockData?.is_clocked_in) {
      const todayMel = new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Melbourne' });
      current = {
        job_site_id: 0,
        job_site_name: clockData.clock_in_address?.split(',')[0]?.trim() || 'Current job site',
        job_site_address: clockData.clock_in_address || '',
        assignment_date: todayMel,
        start_time: clockData.clock_in_time || null,
        assigned_at: null,
        accepted: true,
        is_current: true,
      };
    }

    if (current) {
      upcoming = upcoming.filter(j => !(
        j.job_site_id === current!.job_site_id
        && j.assignment_date === current!.assignment_date
        && j.accepted === true
      ));
    }

    upcoming.sort((a, b) => (a.assignment_date || '').localeCompare(b.assignment_date || ''));

    return { current, upcoming };
  };

  const fetchData = async () => {
    if (!user?.id) return;
    try {
      const [clockRes, assignRes] = await Promise.all([
        clockAPI.getStatus(user.id),
        assignmentAPI.getAssignment(user.id),
      ]);
      const clockData = clockRes.data as ClockStatus;
      const { current, upcoming } = parseAssignmentResponse(assignRes.data, clockData);

      setClockStatus(clockData);
      setCurrentJob(current);
      setUpcomingJobs(upcoming);
    } catch (error) {
      console.warn('Error fetching data:', error);
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      if (user?.id) {
        setIsLoading(true);
        checkForAppUpdate().finally(() => fetchData());
      }
    }, [user?.id])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const respondToAssignment = async (job: JobAssignment, accepted: boolean) => {
    if (!user?.id || respondingAssignment) return;

    setRespondingAssignment(true);
    try {
      await assignmentAPI.respondToAssignment(user.id, accepted, job.assignment_date);
      setUpcomingJobs(prev =>
        prev.map(j =>
          j.assignment_date === job.assignment_date ? { ...j, accepted } : j
        )
      );
    } catch (error) {
      console.warn('Error responding to assignment:', error);
    } finally {
      setRespondingAssignment(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '';
    const date = new Date(dateStr + 'T12:00:00');
    return date.toLocaleDateString('en-AU', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      timeZone: 'Australia/Melbourne',
    });
  };

  const formatTime = (value?: string | null) => {
    if (!value) return '--:--';
    // Backend sends clock-in as plain HH:MM for current job cards
    if (/^\d{1,2}:\d{2}$/.test(value)) return value;
    let dateString = value;
    if (!value.endsWith('Z') && !value.includes('+') && !value.includes('-', 10)) {
      dateString = value + 'Z';
    }
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleTimeString('en-AU', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Australia/Melbourne',
    });
  };

  const renderJobCard = (job: JobAssignment, options: { showActions?: boolean; isCurrent?: boolean }) => {
    const { showActions = false, isCurrent = false } = options;
    return (
      <View key={`${job.job_site_id}-${job.assignment_date || 'current'}`} style={styles.jobCard}>
        <View style={styles.jobHeader}>
          <View style={[styles.jobIconContainer, isCurrent && styles.jobIconCurrent]}>
            <Ionicons name={isCurrent ? 'time' : 'briefcase'} size={24} color={COLORS.primary} />
          </View>
          <View style={styles.jobTitleContainer}>
            <Text style={styles.jobSiteName}>{job.job_site_name}</Text>
            {isCurrent && (
              <View style={styles.currentBadge}>
                <Ionicons name="radio-button-on" size={14} color="#059669" />
                <Text style={styles.badgeText}>On site now</Text>
              </View>
            )}
            {!isCurrent && job.accepted === true && (
              <View style={styles.acceptedBadge}>
                <Ionicons name="checkmark-circle" size={14} color="#059669" />
                <Text style={styles.badgeText}>Accepted</Text>
              </View>
            )}
            {!isCurrent && job.accepted === false && (
              <View style={styles.declinedBadge}>
                <Ionicons name="close-circle" size={14} color="#DC2626" />
                <Text style={styles.declinedBadgeText}>Declined</Text>
              </View>
            )}
            {!isCurrent && job.accepted === null && (
              <View style={styles.pendingBadge}>
                <Ionicons name="hourglass" size={14} color="#D97706" />
                <Text style={styles.pendingBadgeText}>Pending Response</Text>
              </View>
            )}
          </View>
        </View>

        <View style={styles.jobDetails}>
          {job.job_site_address ? (
            <View style={styles.detailRow}>
              <Ionicons name="location-outline" size={18} color="#6B7280" />
              <Text style={styles.detailText} numberOfLines={2}>
                {job.job_site_address}
              </Text>
            </View>
          ) : null}

          <View style={styles.detailRow}>
            <Ionicons name="calendar-outline" size={18} color="#6B7280" />
            <Text style={styles.detailText}>
              {formatDate(job.assignment_date)}
              {isCurrent ? ' · On site now' : job.start_time ? ` at ${job.start_time}` : ''}
              {isCurrent && job.start_time ? ` · since ${formatTime(job.start_time)}` : ''}
            </Text>
          </View>
        </View>

        {showActions && job.accepted === null && (
          <View style={styles.actionButtons}>
            <TouchableOpacity
              style={styles.declineButton}
              onPress={() => respondToAssignment(job, false)}
              disabled={respondingAssignment}
            >
              {respondingAssignment ? (
                <ActivityIndicator size="small" color="#DC2626" />
              ) : (
                <>
                  <Ionicons name="close-circle-outline" size={20} color="#DC2626" />
                  <Text style={styles.declineButtonText}>Decline</Text>
                </>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.acceptButton}
              onPress={() => respondToAssignment(job, true)}
              disabled={respondingAssignment}
            >
              {respondingAssignment ? (
                <ActivityIndicator size="small" color="#FFFFFF" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle-outline" size={20} color="#FFFFFF" />
                  <Text style={styles.acceptButtonText}>Accept Job</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        )}
      </View>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  const hasAnyJobs = currentJob || upcomingJobs.length > 0;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Clock Status Card */}
      <View style={styles.clockCard}>
        <View style={styles.clockHeader}>
          <Ionicons
            name={clockStatus?.is_clocked_in ? 'time' : 'time-outline'}
            size={32}
            color={clockStatus?.is_clocked_in ? COLORS.success : COLORS.gray}
          />
          <View style={styles.clockInfo}>
            <Text style={styles.clockStatus}>
              {clockStatus?.is_clocked_in ? 'Currently Clocked In' : 'Not Clocked In'}
            </Text>
            {clockStatus?.is_clocked_in && clockStatus.clock_in_time && (
              <Text style={styles.clockTime}>
                Since {formatTime(clockStatus.clock_in_time)}
              </Text>
            )}
          </View>
        </View>

        <TouchableOpacity
          style={[
            styles.clockButton,
            clockStatus?.is_clocked_in ? styles.clockOutBtn : styles.clockInBtn
          ]}
          onPress={() => navigation.navigate(
            clockStatus?.is_clocked_in ? 'ClockOut' : 'ClockIn'
          )}
        >
          <Ionicons
            name={clockStatus?.is_clocked_in ? 'log-out-outline' : 'log-in-outline'}
            size={24}
            color="#FFFFFF"
          />
          <Text style={styles.clockButtonText}>
            {clockStatus?.is_clocked_in ? 'Clock Out' : 'Clock In'}
          </Text>
        </TouchableOpacity>
      </View>

      {currentJob && (
        <>
          <Text style={styles.sectionTitle}>Current Job</Text>
          {renderJobCard(currentJob, { isCurrent: true })}
        </>
      )}

      {upcomingJobs.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>
            {currentJob ? 'Upcoming Jobs' : 'My Assigned Jobs'}
          </Text>
          {upcomingJobs.map(job => renderJobCard(job, {
            showActions: job.accepted === null,
          }))}
        </>
      )}

      {!hasAnyJobs && (
        <>
          <Text style={styles.sectionTitle}>My Assigned Jobs</Text>
          <View style={styles.noJobsCard}>
            <Ionicons name="briefcase-outline" size={48} color="#9CA3AF" />
            <Text style={styles.noJobsText}>No jobs assigned</Text>
            <Text style={styles.noJobsSubtext}>
              You'll be notified when a job is assigned to you
            </Text>
          </View>
        </>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F3F4F6',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F3F4F6',
  },
  clockCard: {
    backgroundColor: '#FFFFFF',
    margin: 16,
    borderRadius: 16,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  clockHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  clockInfo: {
    marginLeft: 12,
  },
  clockStatus: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1F2937',
  },
  clockTime: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 2,
  },
  clockButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  clockInBtn: {
    backgroundColor: COLORS.primary,
  },
  clockOutBtn: {
    backgroundColor: '#DC2626',
  },
  clockButtonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1F2937',
    marginHorizontal: 16,
    marginTop: 8,
    marginBottom: 12,
  },
  jobCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 16,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  jobHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  jobIconContainer: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#FFF7ED',
    justifyContent: 'center',
    alignItems: 'center',
  },
  jobIconCurrent: {
    backgroundColor: '#D1FAE5',
  },
  jobTitleContainer: {
    flex: 1,
    marginLeft: 12,
  },
  jobSiteName: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1F2937',
    marginBottom: 4,
  },
  currentBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#D1FAE5',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
    gap: 4,
  },
  acceptedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#D1FAE5',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
    gap: 4,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#059669',
  },
  declinedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FEE2E2',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
    gap: 4,
  },
  declinedBadgeText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#DC2626',
  },
  pendingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
    gap: 4,
  },
  pendingBadgeText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#D97706',
  },
  jobDetails: {
    marginTop: 16,
    gap: 10,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  detailText: {
    flex: 1,
    fontSize: 14,
    color: '#4B5563',
  },
  actionButtons: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 20,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  declineButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    backgroundColor: '#FEF2F2',
    gap: 6,
  },
  declineButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#DC2626',
  },
  acceptButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 10,
    backgroundColor: '#059669',
    gap: 6,
  },
  acceptButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  noJobsCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    borderRadius: 16,
    padding: 32,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  noJobsText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#4B5563',
    marginTop: 12,
  },
  noJobsSubtext: {
    fontSize: 14,
    color: '#9CA3AF',
    textAlign: 'center',
    marginTop: 4,
  },
});
