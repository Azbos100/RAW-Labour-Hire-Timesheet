/**
 * Timesheet Detail Screen
 * View and submit individual timesheet
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  TextInput,
  Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RouteProp } from '@react-navigation/native';
import { RootStackParamList, COLORS } from '../../App';
import { timesheetsAPI } from '../services/api';

type TimesheetDetailScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'TimesheetDetail'>;
  route: RouteProp<RootStackParamList, 'TimesheetDetail'>;
};

interface TimesheetEntry {
  id: number;
  day_of_week: string;
  entry_date: string;
  time_start?: string;
  time_finish?: string;
  ordinary_hours: number;
  overtime_hours: number;
  total_hours: number;
  worked_as?: string;
  comments?: string;
  clock_in_address?: string;
  clock_out_address?: string;
}

interface TimesheetData {
  id: number;
  docket_number: string;
  week_starting: string;
  week_ending: string;
  status: string;
  total_ordinary_hours: number;
  total_overtime_hours: number;
  total_hours: number;
  entries: TimesheetEntry[];
}

export default function TimesheetDetailScreen({ navigation, route }: TimesheetDetailScreenProps) {
  const { timesheetId } = route.params;
  const [timesheet, setTimesheet] = useState<TimesheetData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [supervisorName, setSupervisorName] = useState('');
  const [supervisorContact, setSupervisorContact] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchTimesheet();
  }, [timesheetId]);

  const fetchTimesheet = async () => {
    try {
      const response = await timesheetsAPI.getById(timesheetId);
      setTimesheet(response.data);
    } catch (error) {
      console.error('Error fetching timesheet:', error);
      Alert.alert('Error', 'Unable to load timesheet');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!supervisorName || !supervisorContact) {
      Alert.alert('Error', 'Please enter supervisor name and contact');
      return;
    }

    setIsSubmitting(true);
    try {
      await timesheetsAPI.submit(timesheetId, {
        supervisor_name: supervisorName,
        supervisor_contact: supervisorContact,
      });
      setShowSubmitModal(false);
      Alert.alert('Success', 'Timesheet submitted for approval');
      fetchTimesheet();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to submit timesheet');
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-AU', {
      day: 'numeric',
      month: 'short',
    });
  };

  const formatTime = (timeString?: string) => {
    if (!timeString) return '--:--';
    return timeString.substring(0, 5);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved':
        return '#10B981';
      case 'submitted':
        return '#F59E0B';
      case 'rejected':
        return '#EF4444';
      default:
        return '#6B7280';
    }
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (!timesheet) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>Timesheet not found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerRow}>
            <View style={styles.docketBadge}>
              <Text style={styles.docketText}>#{timesheet.docket_number}</Text>
            </View>
            <View style={[
              styles.statusBadge,
              { backgroundColor: getStatusColor(timesheet.status) + '20' }
            ]}>
              <Text style={[styles.statusText, { color: getStatusColor(timesheet.status) }]}>
                {timesheet.status.charAt(0).toUpperCase() + timesheet.status.slice(1)}
              </Text>
            </View>
          </View>
          <Text style={styles.weekRange}>
            {formatDate(timesheet.week_starting)} - {formatDate(timesheet.week_ending)}
          </Text>
        </View>

        {/* Summary */}
        <View style={styles.summaryCard}>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Ordinary</Text>
            <Text style={styles.summaryValue}>{timesheet.total_ordinary_hours.toFixed(1)}h</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Overtime</Text>
            <Text style={styles.summaryValue}>{timesheet.total_overtime_hours.toFixed(1)}h</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Total</Text>
            <Text style={[styles.summaryValue, styles.summaryTotal]}>
              {timesheet.total_hours.toFixed(1)}h
            </Text>
          </View>
        </View>

        {/* Entries */}
        <View style={styles.entriesSection}>
          <Text style={styles.sectionTitle}>Daily Entries</Text>
          {timesheet.entries.length === 0 ? (
            <View style={styles.noEntries}>
              <Text style={styles.noEntriesText}>No entries yet</Text>
            </View>
          ) : (
            timesheet.entries.map((entry) => (
              <View key={entry.id} style={styles.entryCard}>
                <View style={styles.entryHeader}>
                  <Text style={styles.entryDay}>{entry.day_of_week}</Text>
                  <Text style={styles.entryDate}>{formatDate(entry.entry_date)}</Text>
                </View>
                <View style={styles.entryDetails}>
                  <View style={styles.entryTimeRow}>
                    <Ionicons name="time-outline" size={16} color="#6B7280" />
                    <Text style={styles.entryTime}>
                      {formatTime(entry.time_start)} - {formatTime(entry.time_finish)}
                    </Text>
                  </View>
                  <View style={styles.entryHours}>
                    <Text style={styles.entryHoursText}>{entry.total_hours.toFixed(1)}h</Text>
                  </View>
                </View>
                {entry.worked_as && (
                  <Text style={styles.entryWorkedAs}>Worked as: {entry.worked_as}</Text>
                )}
                {entry.clock_in_address && (
                  <View style={styles.entryLocation}>
                    <Ionicons name="location-outline" size={14} color="#9CA3AF" />
                    <Text style={styles.entryLocationText} numberOfLines={1}>
                      {entry.clock_in_address}
                    </Text>
                  </View>
                )}
              </View>
            ))
          )}
        </View>
      </ScrollView>

      {/* Submit Button (only for draft timesheets) */}
      {timesheet.status === 'draft' && (
        <View style={styles.footer}>
          <TouchableOpacity
            style={styles.submitButton}
            onPress={() => setShowSubmitModal(true)}
          >
            <Ionicons name="send" size={20} color="#FFFFFF" />
            <Text style={styles.submitButtonText}>Submit for Approval</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Submit Modal */}
      <Modal
        visible={showSubmitModal}
        animationType="slide"
        transparent
        onRequestClose={() => setShowSubmitModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Submit Timesheet</Text>
            <Text style={styles.modalSubtitle}>
              Enter supervisor details for approval
            </Text>

            <Text style={styles.inputLabel}>Supervisor Name</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter supervisor's name"
              value={supervisorName}
              onChangeText={setSupervisorName}
            />

            <Text style={styles.inputLabel}>Contact Number</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter contact number"
              value={supervisorContact}
              onChangeText={setSupervisorContact}
              keyboardType="phone-pad"
            />

            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={styles.cancelButton}
                onPress={() => setShowSubmitModal(false)}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.confirmButton, isSubmitting && styles.confirmButtonDisabled]}
                onPress={handleSubmit}
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Text style={styles.confirmButtonText}>Submit</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
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
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    color: '#6B7280',
    fontSize: 16,
  },
  header: {
    backgroundColor: '#FFFFFF',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  docketBadge: {
    backgroundColor: '#1A1A1A',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  docketText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '500',
  },
  weekRange: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  summaryCard: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
  },
  summaryItem: {
    flex: 1,
    alignItems: 'center',
  },
  summaryDivider: {
    width: 1,
    backgroundColor: '#E5E7EB',
  },
  summaryLabel: {
    fontSize: 12,
    color: '#6B7280',
    marginBottom: 4,
  },
  summaryValue: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  summaryTotal: {
    color: COLORS.primary,
  },
  entriesSection: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 12,
  },
  noEntries: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  noEntriesText: {
    color: '#6B7280',
  },
  entryCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  entryHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  entryDay: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  entryDate: {
    fontSize: 14,
    color: '#6B7280',
  },
  entryDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  entryTimeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  entryTime: {
    fontSize: 14,
    color: '#6B7280',
  },
  entryHours: {
    backgroundColor: '#F3F4F6',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 6,
  },
  entryHoursText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  entryWorkedAs: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 8,
  },
  entryLocation: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
    gap: 4,
  },
  entryLocationText: {
    fontSize: 12,
    color: '#9CA3AF',
    flex: 1,
  },
  footer: {
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: 12,
    gap: 8,
  },
  submitButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
  },
  modalTitle: {
    fontSize: 24,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 4,
  },
  modalSubtitle: {
    fontSize: 14,
    color: '#6B7280',
    marginBottom: 24,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#1A1A1A',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#F3F4F6',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    marginBottom: 16,
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  cancelButton: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    backgroundColor: '#F3F4F6',
    alignItems: 'center',
  },
  cancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6B7280',
  },
  confirmButton: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
  },
  confirmButtonDisabled: {
    backgroundColor: '#FCA5A5',
  },
  confirmButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
