/**
 * My Tickets Screen
 * Manage certifications and licenses
 */

import React, { useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  Modal,
  TextInput,
  Alert,
  Image,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { COLORS } from '../constants/colors';
import { ticketsAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

interface TicketType {
  id: number;
  name: string;
  description: string;
  has_expiry: boolean;
}

interface UserTicket {
  id: number;
  ticket_type_id: number;
  ticket_type_name: string;
  ticket_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  front_image: string | null;
  back_image: string | null;
  status: string;
  is_expired: boolean;
  created_at: string;
}

export default function TicketsScreen() {
  const { user } = useAuth();
  const [tickets, setTickets] = useState<UserTicket[]>([]);
  const [ticketTypes, setTicketTypes] = useState<TicketType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  
  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedType, setSelectedType] = useState<TicketType | null>(null);
  const [ticketNumber, setTicketNumber] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [frontImage, setFrontImage] = useState<string | null>(null);
  const [backImage, setBackImage] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  
  // View ticket modal
  const [viewTicket, setViewTicket] = useState<UserTicket | null>(null);

  const fetchData = async () => {
    try {
      const [typesRes, ticketsRes] = await Promise.all([
        ticketsAPI.getTypes(),
        ticketsAPI.getMyTickets(user?.id),
      ]);
      setTicketTypes(typesRes.data.ticket_types || []);
      setTickets(ticketsRes.data.tickets || []);
    } catch (error) {
      console.warn('Error fetching tickets:', error);
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [user?.id])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const pickImage = async (setImage: (uri: string | null) => void) => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Please allow access to your photo library');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [4, 3],
      quality: 0.7,
      base64: true,
    });

    if (!result.canceled && result.assets[0].base64) {
      const base64Image = `data:image/jpeg;base64,${result.assets[0].base64}`;
      setImage(base64Image);
    }
  };

  const takePhoto = async (setImage: (uri: string | null) => void) => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Please allow access to your camera');
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      allowsEditing: true,
      aspect: [4, 3],
      quality: 0.7,
      base64: true,
    });

    if (!result.canceled && result.assets[0].base64) {
      const base64Image = `data:image/jpeg;base64,${result.assets[0].base64}`;
      setImage(base64Image);
    }
  };

  const showImageOptions = (setImage: (uri: string | null) => void) => {
    Alert.alert(
      'Add Photo',
      'Choose an option',
      [
        { text: 'Take Photo', onPress: () => takePhoto(setImage) },
        { text: 'Choose from Library', onPress: () => pickImage(setImage) },
        { text: 'Cancel', style: 'cancel' },
      ]
    );
  };

  const handleUpload = async () => {
    if (!selectedType) {
      Alert.alert('Error', 'Please select a ticket type');
      return;
    }
    if (!frontImage) {
      Alert.alert('Error', 'Please add a photo of the front of your ticket');
      return;
    }

    setIsUploading(true);
    try {
      await ticketsAPI.upload({
        ticket_type_id: selectedType.id,
        ticket_number: ticketNumber || undefined,
        expiry_date: expiryDate || undefined,
        front_image: frontImage,
        back_image: backImage || undefined,
      }, user?.id);

      Alert.alert('Success', 'Ticket uploaded successfully');
      resetUploadModal();
      fetchData();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to upload ticket');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = (ticket: UserTicket) => {
    Alert.alert(
      'Delete Ticket',
      `Are you sure you want to delete your ${ticket.ticket_type_name}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await ticketsAPI.delete(ticket.id, user?.id);
              setViewTicket(null);
              fetchData();
            } catch (error) {
              Alert.alert('Error', 'Failed to delete ticket');
            }
          },
        },
      ]
    );
  };

  const resetUploadModal = () => {
    setShowUploadModal(false);
    setSelectedType(null);
    setTicketNumber('');
    setExpiryDate('');
    setFrontImage(null);
    setBackImage(null);
  };

  const getStatusColor = (status: string, isExpired: boolean) => {
    if (isExpired) return '#EF4444';
    switch (status) {
      case 'verified': return '#10B981';
      case 'pending': return '#F59E0B';
      case 'rejected': return '#EF4444';
      default: return '#6B7280';
    }
  };

  const getStatusText = (status: string, isExpired: boolean) => {
    if (isExpired) return 'Expired';
    switch (status) {
      case 'verified': return 'Verified';
      case 'pending': return 'Pending Review';
      case 'rejected': return 'Rejected';
      default: return status;
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  const renderTicket = ({ item }: { item: UserTicket }) => (
    <TouchableOpacity
      style={styles.ticketCard}
      onPress={() => setViewTicket(item)}
    >
      <View style={styles.ticketHeader}>
        <View style={styles.ticketIconContainer}>
          <Ionicons name="card" size={24} color={COLORS.primary} />
        </View>
        <View style={styles.ticketInfo}>
          <Text style={styles.ticketName}>{item.ticket_type_name}</Text>
          {item.ticket_number && (
            <Text style={styles.ticketNumber}>#{item.ticket_number}</Text>
          )}
        </View>
        <View style={[styles.statusBadge, { backgroundColor: getStatusColor(item.status, item.is_expired) + '20' }]}>
          <Text style={[styles.statusText, { color: getStatusColor(item.status, item.is_expired) }]}>
            {getStatusText(item.status, item.is_expired)}
          </Text>
        </View>
      </View>
      
      {item.expiry_date && (
        <View style={styles.ticketExpiry}>
          <Ionicons 
            name={item.is_expired ? 'warning' : 'calendar-outline'} 
            size={14} 
            color={item.is_expired ? '#EF4444' : '#6B7280'} 
          />
          <Text style={[styles.expiryText, item.is_expired && styles.expiredText]}>
            {item.is_expired ? 'Expired: ' : 'Expires: '}{formatDate(item.expiry_date)}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={tickets}
        renderItem={renderTicket}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Ionicons name="card-outline" size={64} color="#D1D5DB" />
            <Text style={styles.emptyTitle}>No Tickets Yet</Text>
            <Text style={styles.emptyText}>
              Upload your certifications and licenses to keep them all in one place
            </Text>
          </View>
        }
        ListHeaderComponent={
          <TouchableOpacity
            style={styles.addButton}
            onPress={() => setShowUploadModal(true)}
          >
            <Ionicons name="add-circle" size={24} color={COLORS.primary} />
            <Text style={styles.addButtonText}>Add New Ticket</Text>
          </TouchableOpacity>
        }
      />

      {/* Upload Modal */}
      <Modal
        visible={showUploadModal}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={resetUploadModal}
      >
        <KeyboardAvoidingView
          style={styles.modalContainer}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={resetUploadModal}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Add Ticket</Text>
            <TouchableOpacity onPress={handleUpload} disabled={isUploading}>
              {isUploading ? (
                <ActivityIndicator size="small" color={COLORS.primary} />
              ) : (
                <Text style={styles.saveText}>Save</Text>
              )}
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            {/* Ticket Type Selection */}
            <Text style={styles.label}>Ticket Type *</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.typeSelector}>
              {ticketTypes.map((type) => (
                <TouchableOpacity
                  key={type.id}
                  style={[
                    styles.typeChip,
                    selectedType?.id === type.id && styles.typeChipSelected,
                  ]}
                  onPress={() => setSelectedType(type)}
                >
                  <Text
                    style={[
                      styles.typeChipText,
                      selectedType?.id === type.id && styles.typeChipTextSelected,
                    ]}
                  >
                    {type.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Ticket Number */}
            <Text style={styles.label}>Ticket/License Number</Text>
            <TextInput
              style={styles.input}
              value={ticketNumber}
              onChangeText={setTicketNumber}
              placeholder="Enter ticket number"
              placeholderTextColor="#9CA3AF"
            />

            {/* Expiry Date */}
            {selectedType?.has_expiry && (
              <>
                <Text style={styles.label}>Expiry Date</Text>
                <TextInput
                  style={styles.input}
                  value={expiryDate}
                  onChangeText={setExpiryDate}
                  placeholder="DD/MM/YYYY (e.g. 27/10/2027)"
                  placeholderTextColor="#9CA3AF"
                  keyboardType="numbers-and-punctuation"
                />
                <Text style={styles.dateHint}>Enter as DD/MM/YYYY</Text>
              </>
            )}

            {/* Front Image */}
            <Text style={styles.label}>Front of Ticket *</Text>
            <TouchableOpacity
              style={styles.imageUpload}
              onPress={() => showImageOptions(setFrontImage)}
            >
              {frontImage ? (
                <Image source={{ uri: frontImage }} style={styles.uploadedImage} />
              ) : (
                <View style={styles.uploadPlaceholder}>
                  <Ionicons name="camera" size={32} color="#9CA3AF" />
                  <Text style={styles.uploadText}>Tap to add photo</Text>
                </View>
              )}
            </TouchableOpacity>

            {/* Back Image */}
            <Text style={styles.label}>Back of Ticket (Optional)</Text>
            <TouchableOpacity
              style={styles.imageUpload}
              onPress={() => showImageOptions(setBackImage)}
            >
              {backImage ? (
                <Image source={{ uri: backImage }} style={styles.uploadedImage} />
              ) : (
                <View style={styles.uploadPlaceholder}>
                  <Ionicons name="camera" size={32} color="#9CA3AF" />
                  <Text style={styles.uploadText}>Tap to add photo</Text>
                </View>
              )}
            </TouchableOpacity>
          </ScrollView>
        </KeyboardAvoidingView>
      </Modal>

      {/* View Ticket Modal */}
      <Modal
        visible={!!viewTicket}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setViewTicket(null)}
      >
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setViewTicket(null)}>
              <Ionicons name="close" size={24} color="#6B7280" />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>{viewTicket?.ticket_type_name}</Text>
            <TouchableOpacity onPress={() => viewTicket && handleDelete(viewTicket)}>
              <Ionicons name="trash-outline" size={24} color="#EF4444" />
            </TouchableOpacity>
          </View>

          {viewTicket && (
            <ScrollView style={styles.modalContent}>
              <View style={[styles.statusBadgeLarge, { backgroundColor: getStatusColor(viewTicket.status, viewTicket.is_expired) + '20' }]}>
                <Text style={[styles.statusTextLarge, { color: getStatusColor(viewTicket.status, viewTicket.is_expired) }]}>
                  {getStatusText(viewTicket.status, viewTicket.is_expired)}
                </Text>
              </View>

              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Ticket Number</Text>
                <Text style={styles.detailValue}>{viewTicket.ticket_number || 'Not provided'}</Text>
              </View>

              {viewTicket.expiry_date && (
                <View style={styles.detailRow}>
                  <Text style={styles.detailLabel}>Expiry Date</Text>
                  <Text style={[styles.detailValue, viewTicket.is_expired && styles.expiredText]}>
                    {formatDate(viewTicket.expiry_date)}
                  </Text>
                </View>
              )}

              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Uploaded</Text>
                <Text style={styles.detailValue}>{formatDate(viewTicket.created_at)}</Text>
              </View>

              {viewTicket.front_image && (
                <>
                  <Text style={styles.imageLabel}>Front</Text>
                  <Image source={{ uri: viewTicket.front_image }} style={styles.ticketImage} />
                </>
              )}

              {viewTicket.back_image && (
                <>
                  <Text style={styles.imageLabel}>Back</Text>
                  <Image source={{ uri: viewTicket.back_image }} style={styles.ticketImage} />
                </>
              )}
            </ScrollView>
          )}
        </View>
      </Modal>
    </View>
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
  listContent: {
    padding: 16,
  },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
    borderWidth: 2,
    borderColor: COLORS.primary,
    borderStyle: 'dashed',
  },
  addButtonText: {
    marginLeft: 8,
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.primary,
  },
  ticketCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  ticketHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  ticketIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: COLORS.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  ticketInfo: {
    flex: 1,
  },
  ticketName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1F2937',
  },
  ticketNumber: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 2,
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
  },
  ticketExpiry: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#F3F4F6',
  },
  expiryText: {
    fontSize: 13,
    color: '#6B7280',
    marginLeft: 6,
  },
  expiredText: {
    color: '#EF4444',
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 60,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1F2937',
    marginTop: 16,
  },
  emptyText: {
    fontSize: 14,
    color: '#6B7280',
    textAlign: 'center',
    marginTop: 8,
    paddingHorizontal: 40,
  },
  modalContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1F2937',
  },
  cancelText: {
    fontSize: 16,
    color: '#6B7280',
  },
  saveText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.primary,
  },
  modalContent: {
    flex: 1,
    padding: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
    marginTop: 16,
  },
  typeSelector: {
    flexDirection: 'row',
    marginBottom: 8,
  },
  typeChip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: '#F3F4F6',
    marginRight: 8,
  },
  typeChipSelected: {
    backgroundColor: COLORS.primary,
  },
  typeChipText: {
    fontSize: 14,
    color: '#6B7280',
  },
  typeChipTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  input: {
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    color: '#1F2937',
  },
  dateHint: {
    fontSize: 12,
    color: '#9CA3AF',
    marginTop: 4,
  },
  imageUpload: {
    height: 200,
    borderRadius: 12,
    backgroundColor: '#F9FAFB',
    borderWidth: 2,
    borderColor: '#E5E7EB',
    borderStyle: 'dashed',
    overflow: 'hidden',
  },
  uploadPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  uploadText: {
    marginTop: 8,
    fontSize: 14,
    color: '#9CA3AF',
  },
  uploadedImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  statusBadgeLarge: {
    alignSelf: 'center',
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
    marginBottom: 24,
  },
  statusTextLarge: {
    fontSize: 14,
    fontWeight: '600',
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
  detailLabel: {
    fontSize: 14,
    color: '#6B7280',
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '500',
    color: '#1F2937',
  },
  imageLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginTop: 20,
    marginBottom: 8,
  },
  ticketImage: {
    width: '100%',
    height: 250,
    borderRadius: 12,
    resizeMode: 'contain',
    backgroundColor: '#F9FAFB',
  },
});
