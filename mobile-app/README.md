# RAW Labour Hire - Mobile App

React Native (Expo) mobile app for RAW Labour Hire staff timesheet management.

## Features

- 📱 **GPS Clock In/Out** - Record time and location when starting/finishing work
- 📋 **View Timesheets** - See weekly timesheets with all entries
- ✅ **Submit for Approval** - Send timesheets to supervisors
- 👤 **Profile Management** - View and manage account settings

## Screens

| Screen | Description |
|--------|-------------|
| Login | Secure authentication |
| Register | New employee signup |
| Dashboard | Clock status, hours today, quick actions |
| Clock In | Select job site, GPS captured |
| Clock Out | Add comments, injury report |
| Timesheets | List all timesheets |
| Timesheet Detail | View/submit individual timesheet |
| Profile | Account settings, logout |

## Setup

### Prerequisites

- Node.js 18+
- Expo CLI: `npm install -g expo-cli`
- Expo Go app on your phone (for testing)

### Install Dependencies

```bash
cd mobile-app
npm install
```

### Run Development Server

```bash
# Start Expo dev server
npm start

# Or run on specific platform
npm run ios
npm run android
npm run web
```

### Configure API URL

Edit `src/services/api.ts` to set your backend URL:

```typescript
const API_BASE_URL = __DEV__ 
  ? 'http://localhost:8000/api'  // Development
  : 'https://api.rawlabourhire.com/api';  // Production
```

## Project Structure

```
mobile-app/
├── App.tsx                    # Main app with navigation
├── app.json                   # Expo configuration
├── package.json
├── src/
│   ├── context/
│   │   └── AuthContext.tsx    # Authentication state
│   ├── services/
│   │   └── api.ts             # API client
│   └── screens/
│       ├── LoginScreen.tsx
│       ├── RegisterScreen.tsx
│       ├── DashboardScreen.tsx
│       ├── ClockInScreen.tsx
│       ├── ClockOutScreen.tsx
│       ├── TimesheetsScreen.tsx
│       ├── TimesheetDetailScreen.tsx
│       └── ProfileScreen.tsx
└── assets/                    # App icons and splash
```

## Building for Production

### Expo Build (Recommended)

```bash
# iOS
eas build --platform ios

# Android
eas build --platform android
```

### Local Build

```bash
expo prebuild
cd ios && pod install && cd ..
npx react-native run-ios
npx react-native run-android
```

## Brand Colors

- Primary Blue: `#1E3A8A`
- Dark: `#1A1A1A`
- Background: `#F5F5F5`
- Success: `#10B981`
- Warning: `#F59E0B`
