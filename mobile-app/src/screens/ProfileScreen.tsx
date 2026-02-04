/**
 * Profile Screen
 * User profile and settings with extended information
 */

import React, { useState, useEffect } from 'react';
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

interface ExtendedUser {
  id: number;
  email: string;
  first_name: string;
  surname: string;
  phone?: string;
  role: string;
  // Extended fields
  address?: string;
  suburb?: string;
  state?: string;
  postcode?: string;
  date_of_birth?: string;
  employment_type?: string;
  start_date?: string;
  // Emergency contact
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relationship?: string;
  // Bank details
  bank_account_name?: string;
  bank_bsb?: string;
  bank_account_number?: string;
  tax_file_number?: string;
}

export default function ProfileScreen() {
  const { user, logout, updateUser } = useAuth();
  const [extendedUser, setExtendedUser] = useState<ExtendedUser | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  
  // Modal states
  const [showPersonalInfo, setShowPersonalInfo] = useState(false);
  const [showAddress, setShowAddress] = useState(false);
  const [showEmergencyContact, setShowEmergencyContact] = useState(false);
  const [showBankDetails, setShowBankDetails] = useState(false);
  const [showEmployment, setShowEmployment] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  
  // Form states
  const [saving, setSaving] = useState(false);
  
  // Personal info form
  const [firstName, setFirstName] = useState('');
  const [surname, setSurname] = useState('');
  const [phone, setPhone] = useState('');
  const [dateOfBirth, setDateOfBirth] = useState('');
  
  // Address form
  const [address, setAddress] = useState('');
  const [suburb, setSuburb] = useState('');
  const [state, setState] = useState('');
  const [postcode, setPostcode] = useState('');
  
  // Emergency contact form
  const [emergencyName, setEmergencyName] = useState('');
  const [emergencyPhone, setEmergencyPhone] = useState('');
  const [emergencyRelationship, setEmergencyRelationship] = useState('');
  
  // Bank details form
  const [bankAccountName, setBankAccountName] = useState('');
  const [bankBsb, setBankBsb] = useState('');
  const [bankAccountNumber, setBankAccountNumber] = useState('');
  const [tfn, setTfn] = useState('');
  
  // Employment form
  const [employmentType, setEmploymentType] = useState('casual');
  
  // Change password form
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);

  useEffect(() => {
    fetchExtendedProfile();
  }, [user?.id]);

  const fetchExtendedProfile = async () => {
    if (!user?.id) return;
    
    try {
      const response = await profileAPI.getProfile(user.id);
      setExtendedUser(response.data);
    } catch (error) {
      console.warn('Error fetching extended profile:', error);
      // Fall back to basic user data
      setExtendedUser(user as ExtendedUser);
    } finally {
      setLoadingProfile(false);
    }
  };

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

  // Personal Info handlers
  const openPersonalInfo = () => {
    setFirstName(extendedUser?.first_name || '');
    setSurname(extendedUser?.surname || '');
    setPhone(extendedUser?.phone || '');
    setDateOfBirth(extendedUser?.date_of_birth || '');
    setShowPersonalInfo(true);
  };

  const savePersonalInfo = async () => {
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
        date_of_birth: dateOfBirth || undefined,
      }, user?.id);
      
      setExtendedUser(prev => ({ ...prev!, ...response.data.user }));
      if (updateUser && response.data.user) {
        updateUser(response.data.user);
      }
      
      setShowPersonalInfo(false);
      Alert.alert('Success', 'Personal information updated');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  // Address handlers
  const openAddress = () => {
    setAddress(extendedUser?.address || '');
    setSuburb(extendedUser?.suburb || '');
    setState(extendedUser?.state || '');
    setPostcode(extendedUser?.postcode || '');
    setShowAddress(true);
  };

  const saveAddress = async () => {
    setSaving(true);
    try {
      const response = await profileAPI.updateProfile({
        address: address.trim() || undefined,
        suburb: suburb.trim() || undefined,
        state: state.trim() || undefined,
        postcode: postcode.trim() || undefined,
      }, user?.id);
      
      setExtendedUser(prev => ({ ...prev!, ...response.data.user }));
      setShowAddress(false);
      Alert.alert('Success', 'Address updated');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  // Emergency contact handlers
  const openEmergencyContact = () => {
    setEmergencyName(extendedUser?.emergency_contact_name || '');
    setEmergencyPhone(extendedUser?.emergency_contact_phone || '');
    setEmergencyRelationship(extendedUser?.emergency_contact_relationship || '');
    setShowEmergencyContact(true);
  };

  const saveEmergencyContact = async () => {
    setSaving(true);
    try {
      const response = await profileAPI.updateProfile({
        emergency_contact_name: emergencyName.trim() || undefined,
        emergency_contact_phone: emergencyPhone.trim() || undefined,
        emergency_contact_relationship: emergencyRelationship.trim() || undefined,
      }, user?.id);
      
      setExtendedUser(prev => ({ ...prev!, ...response.data.user }));
      setShowEmergencyContact(false);
      Alert.alert('Success', 'Emergency contact updated');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  // Bank details handlers
  const openBankDetails = () => {
    setBankAccountName(extendedUser?.bank_account_name || '');
    setBankBsb(extendedUser?.bank_bsb || '');
    setBankAccountNumber(extendedUser?.bank_account_number || '');
    setTfn(extendedUser?.tax_file_number || '');
    setShowBankDetails(true);
  };

  const saveBankDetails = async () => {
    setSaving(true);
    try {
      const response = await profileAPI.updateProfile({
        bank_account_name: bankAccountName.trim() || undefined,
        bank_bsb: bankBsb.trim() || undefined,
        bank_account_number: bankAccountNumber.trim() || undefined,
        tax_file_number: tfn.trim() || undefined,
      }, user?.id);
      
      setExtendedUser(prev => ({ ...prev!, ...response.data.user }));
      setShowBankDetails(false);
      Alert.alert('Success', 'Bank details updated');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  // Employment handlers
  const openEmployment = () => {
    setEmploymentType(extendedUser?.employment_type || 'casual');
    setShowEmployment(true);
  };

  const saveEmployment = async () => {
    setSaving(true);
    try {
      const response = await profileAPI.updateProfile({
        employment_type: employmentType,
      }, user?.id);
      
      setExtendedUser(prev => ({ ...prev!, ...response.data.user }));
      setShowEmployment(false);
      Alert.alert('Success', 'Employment type updated');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  // Password handlers
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
        { text: 'Email', onPress: () => Linking.openURL('mailto:accounts@rawlabourhire.com') },
        { text: 'Call', onPress: () => Linking.openURL('tel:+61414268338') },
        { text: 'Cancel', style: 'cancel' },
      ]
    );
  };

  const getAddressSummary = () => {
    const parts = [extendedUser?.address, extendedUser?.suburb, extendedUser?.state, extendedUser?.postcode].filter(Boolean);
    return parts.length > 0 ? parts.join(', ') : 'Not set';
  };

  const getEmergencyContactSummary = () => {
    if (extendedUser?.emergency_contact_name) {
      return `${extendedUser.emergency_contact_name}${extendedUser.emergency_contact_relationship ? ` (${extendedUser.emergency_contact_relationship})` : ''}`;
    }
    return 'Not set';
  };

  const getBankDetailsSummary = () => {
    if (extendedUser?.bank_account_number) {
      const masked = '****' + extendedUser.bank_account_number.slice(-4);
      return `Account ending ${masked}`;
    }
    return 'Not set';
  };

  const getEmploymentTypeName = (type?: string) => {
    switch (type) {
      case 'full_time': return 'Full Time';
      case 'part_time': return 'Part Time';
      case 'casual': return 'Casual';
      default: return 'Casual';
    }
  };

  const MenuItem = ({ 
    icon, 
    title, 
    subtitle,
    onPress,
    showArrow = true,
    danger = false,
    warning = false,
  }: { 
    icon: keyof typeof Ionicons.glyphMap;
    title: string;
    subtitle?: string;
    onPress?: () => void;
    showArrow?: boolean;
    danger?: boolean;
    warning?: boolean;
  }) => (
    <TouchableOpacity style={styles.menuItem} onPress={onPress}>
      <View style={[styles.menuIcon, danger && styles.menuIconDanger, warning && styles.menuIconWarning]}>
        <Ionicons name={icon} size={22} color={danger ? COLORS.primary : warning ? '#F59E0B' : '#6B7280'} />
      </View>
      <View style={styles.menuContent}>
        <Text style={[styles.menuTitle, danger && styles.menuTitleDanger]}>{title}</Text>
        {subtitle && <Text style={[styles.menuSubtitle, warning && styles.menuSubtitleWarning]}>{subtitle}</Text>}
      </View>
      {showArrow && (
        <Ionicons name="chevron-forward" size={20} color="#D1D5DB" />
      )}
    </TouchableOpacity>
  );

  const renderModal = (
    visible: boolean,
    onClose: () => void,
    title: string,
    content: React.ReactNode,
    onSave: () => void,
  ) => (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={true}
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.modalOverlay}
      >
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{title}</Text>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color="#6B7280" />
            </TouchableOpacity>
          </View>
          
          <ScrollView style={styles.modalBody} keyboardShouldPersistTaps="handled">
            {content}
          </ScrollView>
          
          <View style={styles.modalFooter}>
            <TouchableOpacity style={styles.cancelButton} onPress={onClose}>
              <Text style={styles.cancelButtonText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.saveButton, saving && styles.saveButtonDisabled]}
              onPress={onSave}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator color="#FFFFFF" size="small" />
              ) : (
                <Text style={styles.saveButtonText}>Save</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );

  if (loadingProfile) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      {/* Profile Header */}
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {extendedUser?.first_name?.[0]}{extendedUser?.surname?.[0]}
          </Text>
        </View>
        <Text style={styles.name}>{extendedUser?.first_name} {extendedUser?.surname}</Text>
        <Text style={styles.email}>{extendedUser?.email}</Text>
        <View style={styles.badgeRow}>
          <View style={styles.roleBadge}>
            <Text style={styles.roleText}>
              {extendedUser?.role?.charAt(0).toUpperCase()}{extendedUser?.role?.slice(1)}
            </Text>
          </View>
          <View style={styles.employmentBadge}>
            <Text style={styles.employmentText}>
              {getEmploymentTypeName(extendedUser?.employment_type)}
            </Text>
          </View>
        </View>
      </View>

      {/* Personal Details Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Personal Details</Text>
        <View style={styles.menuCard}>
          <MenuItem
            icon="person-outline"
            title="Personal Information"
            subtitle={`${extendedUser?.first_name} ${extendedUser?.surname}`}
            onPress={openPersonalInfo}
          />
          <MenuItem
            icon="home-outline"
            title="Address"
            subtitle={getAddressSummary()}
            onPress={openAddress}
            warning={!extendedUser?.address}
          />
          <MenuItem
            icon="people-outline"
            title="Emergency Contact"
            subtitle={getEmergencyContactSummary()}
            onPress={openEmergencyContact}
            warning={!extendedUser?.emergency_contact_name}
          />
        </View>
      </View>

      {/* Payment Details Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Payment Details</Text>
        <View style={styles.menuCard}>
          <MenuItem
            icon="card-outline"
            title="Bank Details"
            subtitle={getBankDetailsSummary()}
            onPress={openBankDetails}
            warning={!extendedUser?.bank_account_number}
          />
          <MenuItem
            icon="briefcase-outline"
            title="Employment Type"
            subtitle={getEmploymentTypeName(extendedUser?.employment_type)}
            onPress={openEmployment}
          />
        </View>
      </View>

      {/* Account Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Account</Text>
        <View style={styles.menuCard}>
          <MenuItem
            icon="lock-closed-outline"
            title="Change Password"
            onPress={handleChangePassword}
          />
          <MenuItem
            icon="notifications-outline"
            title="Notifications"
            subtitle="Push notifications enabled"
            onPress={() => Alert.alert('Notifications', 'Use device settings to manage notifications.')}
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

      {/* Personal Info Modal */}
      {renderModal(
        showPersonalInfo,
        () => setShowPersonalInfo(false),
        'Personal Information',
        <>
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
          
          <Text style={styles.inputLabel}>Date of Birth</Text>
          <TextInput
            style={styles.input}
            value={dateOfBirth}
            onChangeText={setDateOfBirth}
            placeholder="DD/MM/YYYY"
          />
          
          <Text style={styles.inputLabel}>Email</Text>
          <View style={[styles.input, styles.inputDisabled]}>
            <Text style={styles.inputDisabledText}>{extendedUser?.email}</Text>
          </View>
          <Text style={styles.inputHint}>Email cannot be changed</Text>
        </>,
        savePersonalInfo
      )}

      {/* Address Modal */}
      {renderModal(
        showAddress,
        () => setShowAddress(false),
        'Address',
        <>
          <Text style={styles.inputLabel}>Street Address</Text>
          <TextInput
            style={styles.input}
            value={address}
            onChangeText={setAddress}
            placeholder="Enter street address"
            autoCapitalize="words"
          />
          
          <Text style={styles.inputLabel}>Suburb</Text>
          <TextInput
            style={styles.input}
            value={suburb}
            onChangeText={setSuburb}
            placeholder="Enter suburb"
            autoCapitalize="words"
          />
          
          <View style={styles.row}>
            <View style={styles.halfInput}>
              <Text style={styles.inputLabel}>State</Text>
              <TextInput
                style={styles.input}
                value={state}
                onChangeText={setState}
                placeholder="VIC"
                autoCapitalize="characters"
                maxLength={3}
              />
            </View>
            <View style={styles.halfInput}>
              <Text style={styles.inputLabel}>Postcode</Text>
              <TextInput
                style={styles.input}
                value={postcode}
                onChangeText={setPostcode}
                placeholder="3000"
                keyboardType="number-pad"
                maxLength={4}
              />
            </View>
          </View>
        </>,
        saveAddress
      )}

      {/* Emergency Contact Modal */}
      {renderModal(
        showEmergencyContact,
        () => setShowEmergencyContact(false),
        'Emergency Contact',
        <>
          <View style={styles.warningBox}>
            <Ionicons name="alert-circle" size={20} color="#F59E0B" />
            <Text style={styles.warningText}>
              Please provide an emergency contact who can be reached in case of workplace incidents.
            </Text>
          </View>
          
          <Text style={styles.inputLabel}>Contact Name</Text>
          <TextInput
            style={styles.input}
            value={emergencyName}
            onChangeText={setEmergencyName}
            placeholder="Full name of contact"
            autoCapitalize="words"
          />
          
          <Text style={styles.inputLabel}>Contact Phone</Text>
          <TextInput
            style={styles.input}
            value={emergencyPhone}
            onChangeText={setEmergencyPhone}
            placeholder="Phone number"
            keyboardType="phone-pad"
          />
          
          <Text style={styles.inputLabel}>Relationship</Text>
          <TextInput
            style={styles.input}
            value={emergencyRelationship}
            onChangeText={setEmergencyRelationship}
            placeholder="e.g. Spouse, Parent, Partner"
            autoCapitalize="words"
          />
        </>,
        saveEmergencyContact
      )}

      {/* Bank Details Modal */}
      {renderModal(
        showBankDetails,
        () => setShowBankDetails(false),
        'Bank Details',
        <>
          <View style={styles.secureBox}>
            <Ionicons name="shield-checkmark" size={20} color="#10B981" />
            <Text style={styles.secureText}>
              Your bank details are encrypted and used only for payroll purposes.
            </Text>
          </View>
          
          <Text style={styles.inputLabel}>Account Name</Text>
          <TextInput
            style={styles.input}
            value={bankAccountName}
            onChangeText={setBankAccountName}
            placeholder="Name on bank account"
            autoCapitalize="words"
          />
          
          <View style={styles.row}>
            <View style={styles.bsbInput}>
              <Text style={styles.inputLabel}>BSB</Text>
              <TextInput
                style={styles.input}
                value={bankBsb}
                onChangeText={setBankBsb}
                placeholder="000-000"
                keyboardType="number-pad"
                maxLength={7}
              />
            </View>
            <View style={styles.accountInput}>
              <Text style={styles.inputLabel}>Account Number</Text>
              <TextInput
                style={styles.input}
                value={bankAccountNumber}
                onChangeText={setBankAccountNumber}
                placeholder="Account number"
                keyboardType="number-pad"
              />
            </View>
          </View>
          
          <Text style={styles.inputLabel}>Tax File Number (TFN)</Text>
          <TextInput
            style={styles.input}
            value={tfn}
            onChangeText={setTfn}
            placeholder="000 000 000"
            keyboardType="number-pad"
            maxLength={11}
          />
          <Text style={styles.inputHint}>Your TFN is stored securely and used for tax purposes only</Text>
        </>,
        saveBankDetails
      )}

      {/* Employment Modal */}
      {renderModal(
        showEmployment,
        () => setShowEmployment(false),
        'Employment Type',
        <>
          <Text style={styles.inputLabel}>Select Employment Type</Text>
          
          <TouchableOpacity
            style={[styles.employmentOption, employmentType === 'casual' && styles.employmentOptionSelected]}
            onPress={() => setEmploymentType('casual')}
          >
            <View style={styles.employmentOptionContent}>
              <View style={[styles.radioCircle, employmentType === 'casual' && styles.radioCircleSelected]}>
                {employmentType === 'casual' && <View style={styles.radioInner} />}
              </View>
              <View style={styles.employmentOptionText}>
                <Text style={[styles.employmentOptionTitle, employmentType === 'casual' && styles.employmentOptionTitleSelected]}>Casual</Text>
                <Text style={styles.employmentOptionDesc}>Work as needed, flexible hours</Text>
              </View>
            </View>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={[styles.employmentOption, employmentType === 'full_time' && styles.employmentOptionSelected]}
            onPress={() => setEmploymentType('full_time')}
          >
            <View style={styles.employmentOptionContent}>
              <View style={[styles.radioCircle, employmentType === 'full_time' && styles.radioCircleSelected]}>
                {employmentType === 'full_time' && <View style={styles.radioInner} />}
              </View>
              <View style={styles.employmentOptionText}>
                <Text style={[styles.employmentOptionTitle, employmentType === 'full_time' && styles.employmentOptionTitleSelected]}>Full Time</Text>
                <Text style={styles.employmentOptionDesc}>Regular 38+ hours per week</Text>
              </View>
            </View>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={[styles.employmentOption, employmentType === 'part_time' && styles.employmentOptionSelected]}
            onPress={() => setEmploymentType('part_time')}
          >
            <View style={styles.employmentOptionContent}>
              <View style={[styles.radioCircle, employmentType === 'part_time' && styles.radioCircleSelected]}>
                {employmentType === 'part_time' && <View style={styles.radioInner} />}
              </View>
              <View style={styles.employmentOptionText}>
                <Text style={[styles.employmentOptionTitle, employmentType === 'part_time' && styles.employmentOptionTitleSelected]}>Part Time</Text>
                <Text style={styles.employmentOptionDesc}>Regular hours, less than 38/week</Text>
              </View>
            </View>
          </TouchableOpacity>
        </>,
        saveEmployment
      )}

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
            
            <ScrollView style={styles.termsBody} contentContainerStyle={styles.termsBodyContent}>
              <Text style={styles.termsTitle}>RAW Labour Hire - Terms of Use</Text>
              <Text style={styles.termsDate}>Last Updated: January 2025</Text>
              
              <Text style={styles.termsHeading}>1. Acceptance of Terms</Text>
              <Text style={styles.termsText}>
                By using the RAW Labour Hire Timesheet App, you agree to these terms.
              </Text>
              
              <Text style={styles.termsHeading}>2. GPS & Location Data</Text>
              <Text style={styles.termsText}>
                This app collects location data during clock in/out to verify work attendance.
              </Text>
              
              <Text style={styles.termsHeading}>3. Data Privacy</Text>
              <Text style={styles.termsText}>
                Your personal and bank information is encrypted and used only for payroll purposes.
              </Text>
              
              <Text style={styles.termsHeading}>4. Contact</Text>
              <Text style={styles.termsText}>
                Email: accounts@rawlabourhire.com{'\n'}
                Phone: +61 414 268 338
              </Text>
            </ScrollView>
            
            <View style={styles.termsFooter}>
              <TouchableOpacity style={styles.termsButton} onPress={() => setShowTerms(false)}>
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
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
  badgeRow: {
    flexDirection: 'row',
    gap: 8,
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
  employmentBadge: {
    backgroundColor: 'rgba(16, 185, 129, 0.3)',
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 20,
  },
  employmentText: {
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
  menuIconWarning: {
    backgroundColor: '#FFFBEB',
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
  menuSubtitleWarning: {
    color: '#F59E0B',
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
    maxHeight: '85%',
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
    maxHeight: 400,
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
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  halfInput: {
    flex: 1,
  },
  bsbInput: {
    flex: 1,
  },
  accountInput: {
    flex: 2,
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
  warningBox: {
    flexDirection: 'row',
    backgroundColor: '#FFFBEB',
    padding: 12,
    borderRadius: 8,
    gap: 10,
    alignItems: 'flex-start',
  },
  warningText: {
    flex: 1,
    fontSize: 14,
    color: '#92400E',
  },
  secureBox: {
    flexDirection: 'row',
    backgroundColor: '#ECFDF5',
    padding: 12,
    borderRadius: 8,
    gap: 10,
    alignItems: 'flex-start',
  },
  secureText: {
    flex: 1,
    fontSize: 14,
    color: '#065F46',
  },
  employmentOption: {
    backgroundColor: '#F9FAFB',
    borderWidth: 2,
    borderColor: '#E5E7EB',
    borderRadius: 12,
    padding: 16,
    marginTop: 12,
  },
  employmentOptionSelected: {
    backgroundColor: '#EFF6FF',
    borderColor: COLORS.primary,
  },
  employmentOptionContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  radioCircle: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#D1D5DB',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  radioCircleSelected: {
    borderColor: COLORS.primary,
  },
  radioInner: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: COLORS.primary,
  },
  employmentOptionText: {
    flex: 1,
  },
  employmentOptionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#374151',
  },
  employmentOptionTitleSelected: {
    color: COLORS.primary,
  },
  employmentOptionDesc: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 2,
  },
  // Terms styles
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
