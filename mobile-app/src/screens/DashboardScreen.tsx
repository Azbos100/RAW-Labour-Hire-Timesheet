/**
 * Dashboard Screen
 * Main screen with clock in/out status and quick actions
 */

import React, { useState, useEffect, useCallback } from 'react';
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
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import { useAuth } from '../context/AuthContext';
import { clockAPI, assignmentAPI } from '../services/api';

type DashboardScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList>;
};

interface ClockStatus {
  is_clocked_in: boolean;
  clock_in_time?: string;
  clock_in_address?: string;
  hours_worked_today: number;
  overtime_mode: boolean;
  week_days_worked: number;
  week_total_hours: number;
  week_overtime_hours: number;
}

interface JobAssignment {
  job_site_id: number;
  job_site_name: string;
  job_site_address: string;
  assignment_date: string | null;
  assigned_at: string | null;
  accepted: boolean | null;
}

export default function DashboardScreen({ navigation }: DashboardScreenProps) {
  const { user } = useAuth();
  const [clockStatus, setClockStatus] = useState<ClockStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [togglingOvertime, setTogglingOvertime] = useState(false);
  const [assignment, setAssignment] = useState<JobAssignment | null>(null);
  const [respondingAssignment, setRespondingAssignment] = useState(false);

  const toggleOvertimeMode = async () => {
    if (!clockStatus?.is_clocked_in || togglingOvertime) return;
    
    setTogglingOvertime(true);
    try {
      const newOvertimeMode = !clockStatus.overtime_mode;
      await clockAPI.setOvertimeMode({
        overtime_mode: newOvertimeMode,
        user_id: user?.id,
      });
      // Update local state
      setClockStatus(prev => prev ? { ...prev, overtime_mode: newOvertimeMode } : null);
    } catch (error) {
      console.warn('Error toggling overtime mode:', error);
    } finally {
      setTogglingOvertime(false);
    }
  };

  const fetchAssignment = async () => {
    if (!user?.id) return;
    try {
      const response = await assignmentAPI.getAssignment(user.id);
      setAssignment(response.data.assignment || null);
    } catch (error) {
      console.warn('Error fetching assignment:', error);
      setAssignment(null);
    }
  };

  const respondToAssignment = async (accepted: boolean) => {
    if (!user?.id || respondingAssignment) return;
    
    setRespondingAssignment(true);
    try {
      await assignmentAPI.respondToAssignment(user.id, accepted);
      // Update local state
      setAssignment(prev => prev ? { ...prev, accepted } : null);
    } catch (error) {
      console.warn('Error responding to assignment:', error);
    } finally {
      setRespondingAssignment(false);
    }
  };

  const fetchClockStatus = async () => {
    try {
      const response = await clockAPI.getStatus(user?.id);
      setClockStatus(response.data);
    } catch (error) {
      console.warn('Error fetching clock status:', error);
      // Set default status if API fails
      setClockStatus({
        is_clocked_in: false,
        hours_worked_today: 0,
        overtime_mode: false,
        week_days_worked: 0,
        week_total_hours: 0,
        week_overtime_hours: 0,
      });
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  };

  // Fetch on screen focus
  useFocusEffect(
    useCallback(() => {
      fetchClockStatus();
      fetchAssignment();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchClockStatus();
    fetchAssignment();
  };

  const formatTime = (isoString?: string) => {
    if (!isoString) return '--:--';
    // Ensure the timestamp is treated as UTC if no timezone specified
    let dateString = isoString;
    if (!isoString.endsWith('Z') && !isoString.includes('+') && !isoString.includes('-', 10)) {
      dateString = isoString + 'Z';
    }
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-AU', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  };

  const formatHours = (hours: number) => {
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return `${h}h ${m}m`;
  };

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.greeting}>{getGreeting()},</Text>
        <Text style={styles.userName}>{user?.first_name} {user?.surname}</Text>
        <Text style={styles.date}>
          {new Date().toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          })}
        </Text>
      </View>

      {/* Clock Status Card */}
      <View style={styles.statusCard}>
        <View style={styles.statusHeader}>
          <View style={[
            styles.statusIndicator,
            clockStatus?.is_clocked_in ? styles.statusActive : styles.statusInactive
          ]} />
          <Text style={styles.statusText}>
            {clockStatus?.is_clocked_in ? 'Clocked In' : 'Clocked Out'}
          </Text>
        </View>

        {clockStatus?.is_clocked_in && (
          <View style={styles.clockDetails}>
            <View style={styles.detailRow}>
              <Ionicons name="time-outline" size={20} color="#9CA3AF" />
              <Text style={styles.detailText}>
                Started at {formatTime(clockStatus.clock_in_time)}
              </Text>
            </View>
            {clockStatus.clock_in_address && (
              <View style={styles.detailRow}>
                <Ionicons name="location-outline" size={20} color="#9CA3AF" />
                <Text style={styles.detailText} numberOfLines={2}>
                  {clockStatus.clock_in_address}
                </Text>
              </View>
            )}
            
            {/* Overtime Mode Toggle */}
            <TouchableOpacity
              style={[
                styles.overtimeToggle,
                clockStatus.overtime_mode && styles.overtimeToggleActive
              ]}
              onPress={toggleOvertimeMode}
              disabled={togglingOvertime}
            >
              <View style={styles.overtimeToggleContent}>
                <Ionicons
                  name={clockStatus.overtime_mode ? 'checkmark-circle' : 'time-outline'}
                  size={24}
                  color={clockStatus.overtime_mode ? '#FFFFFF' : '#F59E0B'}
                />
                <View style={styles.overtimeTextContainer}>
                  <Text style={[
                    styles.overtimeToggleText,
                    clockStatus.overtime_mode && styles.overtimeToggleTextActive
                  ]}>
                    {clockStatus.overtime_mode ? 'Overtime Mode ON' : 'Staying Back?'}
                  </Text>
                  <Text style={[
                    styles.overtimeToggleSubtext,
                    clockStatus.overtime_mode && styles.overtimeToggleSubtextActive
                  ]}>
                    {clockStatus.overtime_mode
                      ? 'Clock-out reminders paused'
                      : 'Tap to pause clock-out reminders'}
                  </Text>
                </View>
              </View>
              {togglingOvertime && (
                <ActivityIndicator size="small" color={clockStatus.overtime_mode ? '#FFFFFF' : '#F59E0B'} />
              )}
            </TouchableOpacity>
          </View>
        )}

        <View style={styles.hoursBox}>
          <Text style={styles.hoursLabel}>Hours Today</Text>
          <Text style={styles.hoursValue}>
            {formatHours(clockStatus?.hours_worked_today || 0)}
          </Text>
        </View>
      </View>

      {/* Job Assignment Card */}
      {assignment && (
        <View style={styles.assignmentCard}>
          <View style={styles.assignmentHeader}>
            <Ionicons name="briefcase" size={24} color={COLORS.primary} />
            <Text style={styles.assignmentTitle}>Job Assignment</Text>
            {assignment.accepted === true && (
              <View style={styles.acceptedBadge}>
                <Text style={styles.acceptedBadgeText}>Accepted</Text>
              </View>
            )}
            {assignment.accepted === false && (
              <View style={styles.declinedBadge}>
                <Text style={styles.declinedBadgeText}>Declined</Text>
              </View>
            )}
          </View>
          
          <View style={styles.assignmentDetails}>
            <Text style={styles.jobSiteName}>{assignment.job_site_name}</Text>
            {assignment.job_site_address && (
              <View style={styles.addressRow}>
                <Ionicons name="location-outline" size={16} color="#6B7280" />
                <Text style={styles.addressText} numberOfLines={2}>
                  {assignment.job_site_address}
                </Text>
              </View>
            )}
            {assignment.assignment_date && (
              <View style={styles.dateRow}>
                <Ionicons name="calendar-outline" size={16} color="#6B7280" />
                <Text style={styles.dateText}>
                  {new Date(assignment.assignment_date).toLocaleDateString('en-AU', {
                    weekday: 'short',
                    day: 'numeric',
                    month: 'short',
                  })}
                </Text>
              </View>
            )}
          </View>

          {/* Accept/Decline buttons - only show if not yet responded */}
          {assignment.accepted === null && (
            <View style={styles.assignmentActions}>
              <TouchableOpacity
                style={styles.declineButton}
                onPress={() => respondToAssignment(false)}
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
                onPress={() => respondToAssignment(true)}
                disabled={respondingAssignment}
              >
                {respondingAssignment ? (
                  <ActivityIndicator size="small" color="#FFFFFF" />
                ) : (
                  <>
                    <Ionicons name="checkmark-circle-outline" size={20} color="#FFFFFF" />
                    <Text style={styles.acceptButtonText}>Accept</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {/* Clock Action Button */}
      <TouchableOpacity
        style={[
          styles.clockButton,
          clockStatus?.is_clocked_in ? styles.clockOutButton : styles.clockInButton
        ]}
        onPress={() => navigation.navigate(
          clockStatus?.is_clocked_in ? 'ClockOut' : 'ClockIn'
        )}
      >
        <Ionicons
          name={clockStatus?.is_clocked_in ? 'log-out-outline' : 'log-in-outline'}
          size={32}
          color="#FFFFFF"
        />
        <Text style={styles.clockButtonText}>
          {clockStatus?.is_clocked_in ? 'CLOCK OUT' : 'CLOCK IN'}
        </Text>
      </TouchableOpacity>

      {/* Quick Stats */}
      <View style={styles.statsContainer}>
        <Text style={styles.sectionTitle}>This Week</Text>
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Ionicons name="calendar-outline" size={24} color={COLORS.primary} />
            <Text style={styles.statValue}>{clockStatus?.week_days_worked || 0}</Text>
            <Text style={styles.statLabel}>Days Worked</Text>
          </View>
          <View style={styles.statBox}>
            <Ionicons name="time-outline" size={24} color={COLORS.primary} />
            <Text style={styles.statValue}>{formatHours(clockStatus?.week_total_hours || 0)}</Text>
            <Text style={styles.statLabel}>Total Hours</Text>
          </View>
          <View style={styles.statBox}>
            <Ionicons name="add-circle-outline" size={24} color="#F59E0B" />
            <Text style={styles.statValue}>{formatHours(clockStatus?.week_overtime_hours || 0)}</Text>
            <Text style={styles.statLabel}>Overtime</Text>
          </View>
        </View>
      </View>

      {/* Help Text */}
      <View style={styles.helpBox}>
        <Ionicons name="information-circle-outline" size={20} color="#6B7280" />
        <Text style={styles.helpText}>
          Remember to clock in when you arrive at the job site and clock out when you leave. 
          Your GPS location will be recorded automatically.
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F5F5',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F5F5F5',
  },
  header: {
    backgroundColor: '#1E3A8A',
    padding: 24,
    paddingTop: 16,
    paddingBottom: 32,
  },
  greeting: {
    fontSize: 16,
    color: 'rgba(255, 255, 255, 0.8)',
  },
  userName: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 4,
  },
  date: {
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.7)',
    marginTop: 8,
  },
  statusCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    marginTop: -16,
    borderRadius: 12,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  statusHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  statusIndicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  statusActive: {
    backgroundColor: '#10B981',
  },
  statusInactive: {
    backgroundColor: '#6B7280',
  },
  statusText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  clockDetails: {
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  detailText: {
    fontSize: 14,
    color: '#6B7280',
    marginLeft: 8,
    flex: 1,
  },
  hoursBox: {
    alignItems: 'center',
  },
  hoursLabel: {
    fontSize: 14,
    color: '#6B7280',
    marginBottom: 4,
  },
  hoursValue: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#1A1A1A',
  },
  clockButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 16,
    marginTop: 24,
    padding: 20,
    borderRadius: 12,
    gap: 12,
  },
  clockInButton: {
    backgroundColor: '#10B981',
  },
  clockOutButton: {
    backgroundColor: '#1E3A8A',
  },
  clockButtonText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  statsContainer: {
    marginTop: 32,
    paddingHorizontal: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 16,
  },
  statsRow: {
    flexDirection: 'row',
    gap: 12,
  },
  statBox: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1A1A1A',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 12,
    color: '#6B7280',
    marginTop: 4,
  },
  helpBox: {
    flexDirection: 'row',
    backgroundColor: '#F3F4F6',
    marginHorizontal: 16,
    marginTop: 24,
    marginBottom: 32,
    padding: 16,
    borderRadius: 8,
    gap: 12,
  },
  helpText: {
    flex: 1,
    fontSize: 13,
    color: '#6B7280',
    lineHeight: 18,
  },
  // Overtime Mode Toggle Styles
  overtimeToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FEF3C7',
    borderWidth: 1,
    borderColor: '#F59E0B',
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
  },
  overtimeToggleActive: {
    backgroundColor: '#F59E0B',
    borderColor: '#D97706',
  },
  overtimeToggleContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  overtimeTextContainer: {
    marginLeft: 12,
    flex: 1,
  },
  overtimeToggleText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#92400E',
  },
  overtimeToggleTextActive: {
    color: '#FFFFFF',
  },
  overtimeToggleSubtext: {
    fontSize: 12,
    color: '#B45309',
    marginTop: 2,
  },
  overtimeToggleSubtextActive: {
    color: 'rgba(255, 255, 255, 0.85)',
  },
  // Job Assignment Card Styles
  assignmentCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    marginHorizontal: 16,
    marginTop: 16,
    padding: 16,
    borderWidth: 2,
    borderColor: COLORS.primary,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  assignmentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  assignmentTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.primary,
    marginLeft: 8,
    flex: 1,
  },
  acceptedBadge: {
    backgroundColor: '#DEF7EC',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  acceptedBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#047857',
  },
  declinedBadge: {
    backgroundColor: '#FEE2E2',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  declinedBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#DC2626',
  },
  assignmentDetails: {
    backgroundColor: '#F9FAFB',
    borderRadius: 8,
    padding: 12,
  },
  jobSiteName: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 8,
  },
  addressRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  addressText: {
    fontSize: 14,
    color: '#6B7280',
    marginLeft: 6,
    flex: 1,
  },
  dateRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  dateText: {
    fontSize: 14,
    color: '#6B7280',
    marginLeft: 6,
  },
  assignmentActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  declineButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FEE2E2',
    borderWidth: 1,
    borderColor: '#FECACA',
    borderRadius: 10,
    paddingVertical: 12,
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
    backgroundColor: '#047857',
    borderRadius: 10,
    paddingVertical: 12,
    gap: 6,
  },
  acceptButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
