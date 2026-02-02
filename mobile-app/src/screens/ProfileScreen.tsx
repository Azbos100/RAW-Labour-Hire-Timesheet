/**
 * Profile Screen
 * User profile and settings
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS } from '../constants/colors';
import { useAuth } from '../context/AuthContext';
import { profileAPI } from '../services/api';

export default function ProfileScreen() {
  const { user, logout, updateUser } = useAuth();
  
  // Modal states
  const [showEditProfile, setShowEditProfile] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  
  // Edit profile form
  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [surname, setSurname] = useState(user?.surname || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [saving, setSaving] = useState(false);
  
  // Change password form
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);

  const handleLogout = () => {
    Alert.alert(
      'Log Out',
      'Are you sure you want to log out?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Log Out', style: 'destructive', onPress: logout },
      ]
    );
  };

  const handleEditProfile = () => {
    setFirstName(user?.first_name || '');
    setSurname(user?.surname || '');
    setPhone(user?.phone || '');
    setShowEditProfile(true);
  };

  const handleSaveProfile = async () => {
    if (!firstName.trim() || !surname.trim()) {
      Alert.alert('Error', 'First name and surname are required');
      return;
    }
    
    setSaving(true);
    try {
      const response = await profileAPI.updateProfile({
        first_name: firstName.trim(),
        surname: surname.trim(),
        phone: phone.trim() || undefined,
      }, user?.id);
      
      // Update local user state
      if (updateUser && response.data.user) {
        updateUser(response.data.user);
      }
      
      setShowEditProfile(false);
      Alert.alert('Success', 'Profile updated successfully');
    } catch (error: any) {
      console.warn('Error updating profile:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setShowCurrentPassword(false);
    setShowNewPassword(false);
    setShowChangePassword(true);
  };

  const handleSavePassword = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }
    
    if (newPassword !== confirmPassword) {
      Alert.alert('Error', 'New passwords do not match');
      return;
    }
    
    if (newPassword.length < 6) {
      Alert.alert('Error', 'New password must be at least 6 characters');
      return;
    }
    
    setSaving(true);
    try {
      await profileAPI.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      }, user?.id);
      
      setShowChangePassword(false);
      Alert.alert('Success', 'Password changed successfully');
    } catch (error: any) {
      console.warn('Error changing password:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to change password');
    } finally {
      setSaving(false);
    }
  };

  const handleSupport = () => {
    Alert.alert(
      'Help & Support',
      'How would you like to contact us?',
      [
        { 
          text: 'Email', 
          onPress: () => Linking.openURL('mailto:accounts@rawlabourhire.com')
        },
        { 
          text: 'Call', 
          onPress: () => Linking.openURL('tel:+61414268338')
        },
        { text: 'Cancel', style: 'cancel' },
      ]
    );
  };

  const MenuItem = ({ 
    icon, 
    title, 
    subtitle,
    onPress,
    showArrow = true,
    danger = false,
  }: { 
    icon: keyof typeof Ionicons.glyphMap;
    title: string;
    subtitle?: string;
    onPress?: () => void;
    showArrow?: boolean;
    danger?: boolean;
  }) => (
    <TouchableOpacity style={styles.menuItem} onPress={onPress}>
      <View style={[styles.menuIcon, danger && styles.menuIconDanger]}>
        <Ionicons name={icon} size={22} color={danger ? COLORS.primary : '#6B7280'} />
      </View>
      <View style={styles.menuContent}>
        <Text style={[styles.menuTitle, danger && styles.menuTitleDanger]}>{title}</Text>
        {subtitle && <Text style={styles.menuSubtitle}>{subtitle}</Text>}
      </View>
      {showArrow && (
        <Ionicons name="chevron-forward" size={20} color="#D1D5DB" />
      )}
    </TouchableOpacity>
  );

  return (
    <ScrollView style={styles.container}>
      {/* Profile Header */}
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {user?.first_name?.[0]}{user?.surname?.[0]}
          </Text>
        </View>
        <Text style={styles.name}>{user?.first_name} {user?.surname}</Text>
        <Text style={styles.email}>{user?.email}</Text>
        <View style={styles.roleBadge}>
          <Text style={styles.roleText}>
            {user?.role?.charAt(0).toUpperCase()}{user?.role?.slice(1)}
          </Text>
        </View>
      </View>

      {/* Account Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Account</Text>
        <View style={styles.menuCard}>
          <MenuItem
            icon="person-outline"
            title="Personal Information"
            subtitle="Name, email, phone"
            onPress={handleEditProfile}
          />
          <MenuItem
            icon="lock-closed-outline"
            title="Change Password"
            onPress={handleChangePassword}
          />
          <MenuItem
            icon="notifications-outline"
            title="Notifications"
            subtitle="Push notifications enabled"
            onPress={() => Alert.alert('Notifications', 'Push notifications are enabled for this device. To change notification settings, please use your device settings.')}
          />
        </View>
      </View>

      {/* App Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>App</Text>
        <View style={styles.menuCard}>
          <MenuItem
            icon="help-circle-outline"
            title="Help & Support"
            onPress={handleSupport}
          />
          <MenuItem
            icon="document-text-outline"
            title="Terms & Conditions"
            onPress={() => setShowTerms(true)}
          />
          <MenuItem
            icon="information-circle-outline"
            title="About"
            subtitle="Version 1.0.0"
            showArrow={false}
          />
        </View>
      </View>

      {/* Logout */}
      <View style={styles.section}>
        <View style={styles.menuCard}>
          <MenuItem
            icon="log-out-outline"
            title="Log Out"
            onPress={handleLogout}
            showArrow={false}
            danger
          />
        </View>
      </View>

      {/* Footer */}
      <View style={styles.footer}>
        <Text style={styles.footerLogo}>RAW LABOUR HIRE</Text>
        <Text style={styles.footerText}>12 Hellion crt, Keilor Downs Vic 3038</Text>
        <Text style={styles.footerText}>ABN: 13 097 261 288</Text>
      </View>

      {/* Edit Profile Modal */}
      <Modal
        visible={showEditProfile}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowEditProfile(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Edit Profile</Text>
              <TouchableOpacity onPress={() => setShowEditProfile(false)}>
                <Ionicons name="close" size={24} color="#6B7280" />
              </TouchableOpacity>
            </View>
            
            <ScrollView style={styles.modalBody}>
              <Text style={styles.inputLabel}>First Name *</Text>
              <TextInput
                style={styles.input}
                value={firstName}
                onChangeText={setFirstName}
                placeholder="Enter first name"
                autoCapitalize="words"
              />
              
              <Text style={styles.inputLabel}>Surname *</Text>
              <TextInput
                style={styles.input}
                value={surname}
                onChangeText={setSurname}
                placeholder="Enter surname"
                autoCapitalize="words"
              />
              
              <Text style={styles.inputLabel}>Phone</Text>
              <TextInput
                style={styles.input}
                value={phone}
                onChangeText={setPhone}
                placeholder="Enter phone number"
                keyboardType="phone-pad"
              />
              
              <Text style={styles.inputLabel}>Email</Text>
              <View style={[styles.input, styles.inputDisabled]}>
                <Text style={styles.inputDisabledText}>{user?.email}</Text>
              </View>
              <Text style={styles.inputHint}>Email cannot be changed</Text>
            </ScrollView>
            
            <View style={styles.modalFooter}>
              <TouchableOpacity 
                style={styles.cancelButton}
                onPress={() => setShowEditProfile(false)}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.saveButton, saving && styles.saveButtonDisabled]}
                onPress={handleSaveProfile}
                disabled={saving}
              >
                {saving ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Text style={styles.saveButtonText}>Save Changes</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Change Password Modal */}
      <Modal
        visible={showChangePassword}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowChangePassword(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Change Password</Text>
              <TouchableOpacity onPress={() => setShowChangePassword(false)}>
                <Ionicons name="close" size={24} color="#6B7280" />
              </TouchableOpacity>
            </View>
            
            <ScrollView style={styles.modalBody}>
              <Text style={styles.inputLabel}>Current Password</Text>
              <View style={styles.passwordContainer}>
                <TextInput
                  style={styles.passwordInput}
                  value={currentPassword}
                  onChangeText={setCurrentPassword}
                  placeholder="Enter current password"
                  secureTextEntry={!showCurrentPassword}
                />
                <TouchableOpacity 
                  style={styles.eyeButton}
                  onPress={() => setShowCurrentPassword(!showCurrentPassword)}
                >
                  <Ionicons 
                    name={showCurrentPassword ? 'eye-off' : 'eye'} 
                    size={22} 
                    color="#6B7280" 
                  />
                </TouchableOpacity>
              </View>
              
              <Text style={styles.inputLabel}>New Password</Text>
              <View style={styles.passwordContainer}>
                <TextInput
                  style={styles.passwordInput}
                  value={newPassword}
                  onChangeText={setNewPassword}
                  placeholder="Enter new password"
                  secureTextEntry={!showNewPassword}
                />
                <TouchableOpacity 
                  style={styles.eyeButton}
                  onPress={() => setShowNewPassword(!showNewPassword)}
                >
                  <Ionicons 
                    name={showNewPassword ? 'eye-off' : 'eye'} 
                    size={22} 
                    color="#6B7280" 
                  />
                </TouchableOpacity>
              </View>
              
              <Text style={styles.inputLabel}>Confirm New Password</Text>
              <View style={styles.passwordContainer}>
                <TextInput
                  style={styles.passwordInput}
                  value={confirmPassword}
                  onChangeText={setConfirmPassword}
                  placeholder="Confirm new password"
                  secureTextEntry={!showNewPassword}
                />
              </View>
              <Text style={styles.inputHint}>Password must be at least 6 characters</Text>
            </ScrollView>
            
            <View style={styles.modalFooter}>
              <TouchableOpacity 
                style={styles.cancelButton}
                onPress={() => setShowChangePassword(false)}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.saveButton, saving && styles.saveButtonDisabled]}
                onPress={handleSavePassword}
                disabled={saving}
              >
                {saving ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Text style={styles.saveButtonText}>Change Password</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Terms Modal */}
      <Modal
        visible={showTerms}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowTerms(false)}
      >
        <View style={styles.termsModalOverlay}>
          <View style={styles.termsModalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Terms & Conditions</Text>
              <TouchableOpacity onPress={() => setShowTerms(false)}>
                <Ionicons name="close" size={24} color="#6B7280" />
              </TouchableOpacity>
            </View>
            
            <ScrollView 
              style={styles.termsBody}
              contentContainerStyle={styles.termsBodyContent}
            >
              <Text style={styles.termsTitle}>RAW Labour Hire - Terms of Use</Text>
              <Text style={styles.termsDate}>Last Updated: January 2025</Text>
              
              <Text style={styles.termsHeading}>1. Acceptance of Terms</Text>
              <Text style={styles.termsText}>
                By using the RAW Labour Hire Timesheet App, you agree to these terms and conditions. 
                This app is intended for use by RAW Labour Hire employees and contractors only.
              </Text>
              
              <Text style={styles.termsHeading}>2. Use of the App</Text>
              <Text style={styles.termsText}>
                You agree to use this app solely for recording accurate timesheet information, 
                including clock-in/out times, work locations, and job details. You must not 
                submit false or misleading information.
              </Text>
              
              <Text style={styles.termsHeading}>3. GPS & Location Data</Text>
              <Text style={styles.termsText}>
                This app collects location data when you clock in and out to verify work site 
                attendance. By using the app, you consent to this data collection during 
                clock-in/out operations.
              </Text>
              
              <Text style={styles.termsHeading}>4. Data Privacy</Text>
              <Text style={styles.termsText}>
                Your personal information and timesheet data are stored securely and used only 
                for payroll and client billing purposes. We do not share your data with third 
                parties except as required by law or for MYOB integration.
              </Text>
              
              <Text style={styles.termsHeading}>5. Account Security</Text>
              <Text style={styles.termsText}>
                You are responsible for maintaining the confidentiality of your login credentials. 
                Notify RAW Labour Hire immediately if you suspect unauthorized access to your account.
              </Text>
              
              <Text style={styles.termsHeading}>6. Tickets & Certifications</Text>
              <Text style={styles.termsText}>
                You must ensure all uploaded tickets and certifications are valid and current. 
                RAW Labour Hire reserves the right to verify all documentation.
              </Text>
              
              <Text style={styles.termsHeading}>7. Contact</Text>
              <Text style={styles.termsText}>
                For questions about these terms, contact us at:{'\n'}
                Email: accounts@rawlabourhire.com{'\n'}
                Phone: +61 414 268 338{'\n'}
                Address: 12 Hellion Crt, Keilor Downs VIC 3038
              </Text>
            </ScrollView>
            
            <View style={styles.termsFooter}>
              <TouchableOpacity 
                style={styles.termsButton}
                onPress={() => setShowTerms(false)}
              >
                <Text style={styles.saveButtonText}>I Understand</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F5F5',
  },
  header: {
    backgroundColor: COLORS.primary,
    padding: 24,
    alignItems: 'center',
    paddingTop: 16,
    paddingBottom: 32,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  avatarText: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  name: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 4,
  },
  email: {
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.8)',
    marginBottom: 12,
  },
  roleBadge: {
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 20,
  },
  roleText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '500',
  },
  section: {
    paddingHorizontal: 16,
    paddingTop: 24,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6B7280',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  menuCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
  menuIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: '#F3F4F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  menuIconDanger: {
    backgroundColor: '#EFF6FF',
  },
  menuContent: {
    flex: 1,
  },
  menuTitle: {
    fontSize: 16,
    fontWeight: '500',
    color: '#1A1A1A',
  },
  menuTitleDanger: {
    color: COLORS.primary,
  },
  menuSubtitle: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 2,
  },
  footer: {
    alignItems: 'center',
    padding: 32,
    paddingBottom: 48,
  },
  footerLogo: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1E3A8A',
    letterSpacing: 2,
    marginBottom: 8,
  },
  footerText: {
    fontSize: 12,
    color: '#9CA3AF',
    marginBottom: 2,
  },
  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '80%',
  },
  // Terms modal specific styles
  termsModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    paddingHorizontal: 16,
    paddingVertical: 40,
  },
  termsModalContent: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    flex: 1,
    maxHeight: '100%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1F2937',
  },
  modalBody: {
    padding: 20,
  },
  termsBody: {
    flex: 1,
  },
  termsBodyContent: {
    padding: 20,
    paddingBottom: 30,
  },
  termsFooter: {
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  termsButton: {
    padding: 14,
    borderRadius: 8,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
  },
  modalFooter: {
    flexDirection: 'row',
    padding: 20,
    gap: 12,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#374151',
    marginBottom: 8,
    marginTop: 16,
  },
  input: {
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 8,
    padding: 14,
    fontSize: 16,
    color: '#1F2937',
  },
  inputDisabled: {
    backgroundColor: '#F3F4F6',
  },
  inputDisabledText: {
    color: '#9CA3AF',
    fontSize: 16,
  },
  inputHint: {
    fontSize: 12,
    color: '#9CA3AF',
    marginTop: 6,
  },
  passwordContainer: {
    flexDirection: 'row',
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 8,
    alignItems: 'center',
  },
  passwordInput: {
    flex: 1,
    padding: 14,
    fontSize: 16,
    color: '#1F2937',
  },
  eyeButton: {
    padding: 14,
  },
  cancelButton: {
    flex: 1,
    padding: 14,
    borderRadius: 8,
    backgroundColor: '#F3F4F6',
    alignItems: 'center',
  },
  cancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6B7280',
  },
  saveButton: {
    flex: 1,
    padding: 14,
    borderRadius: 8,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  // Terms styles
  termsTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1F2937',
    marginBottom: 4,
  },
  termsDate: {
    fontSize: 13,
    color: '#9CA3AF',
    marginBottom: 20,
  },
  termsHeading: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1F2937',
    marginTop: 16,
    marginBottom: 8,
  },
  termsText: {
    fontSize: 14,
    color: '#4B5563',
    lineHeight: 22,
  },
});
