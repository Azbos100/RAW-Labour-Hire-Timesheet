# RAW Labour Hire - Timesheet App

A digital timesheet system with GPS clock in/out tracking and MYOB integration for RAW Labour Hire staff management.

## 🎯 Features

### 📱 Staff Mobile App
- **GPS Clock In/Out** - Timestamp with verified location when starting/finishing work
- **Digital Timesheets** - Fill in days, times, job site, worked as (role)
- **View History** - See past timesheets and hours worked
- **Submit for Approval** - Send to supervisor for sign-off

### 👔 Admin Dashboard
- **View All Timesheets** - See staff submissions
- **GPS Location Tracking** - Verify clock in/out locations
- **Approve/Reject Timesheets** - Supervisor workflow
- **Client & Job Site Management** - Manage billing clients
- **MYOB Export** - Generate invoices automatically

### 🔗 MYOB Integration
- Export approved timesheets to MYOB
- Automatic invoice generation
- Client billing streamlined

## 📋 Timesheet Fields (Matching Paper Form)

| Field | Description |
|-------|-------------|
| Docket Number | Auto-generated (e.g., 12538) |
| Employee Name | First name + Surname |
| Client | Company being billed |
| Job Address | Work location |
| Order No | Optional reference |
| **Daily Entry** | |
| Day / Date | MON-SUN with dates |
| Time Start | GPS timestamped |
| Time Finish | GPS timestamped |
| Ordinary Hours | First 8 hours |
| Overtime | Hours over 8 |
| First Aid/Injury | Yes/No/N/A |
| Total Hours | Calculated |
| Comments | Notes |
| Worked As | Job role (Labourer, etc) |
| **Approval** | |
| Supervisor Name | Required for processing |
| Supervisor Signature | Digital signature |
| Contact Number | Supervisor phone |

## 🏗️ Project Structure

```
RAW-Labour-Hire-Timesheet/
├── backend/                    # FastAPI Backend
│   ├── app/
│   │   ├── main.py            # FastAPI app
│   │   ├── models.py          # Database models
│   │   ├── database.py        # DB configuration
│   │   └── routes/
│   │       ├── auth.py        # Authentication
│   │       ├── clock.py       # GPS Clock In/Out
│   │       ├── timesheets.py  # Timesheet CRUD
│   │       ├── clients.py     # Client management
│   │       ├── users.py       # User management
│   │       └── myob.py        # MYOB integration
│   ├── Dockerfile
│   └── requirements.txt
├── mobile-app/                 # React Native Staff App
├── admin-dashboard/            # Next.js Web Dashboard
├── docker-compose.yml
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for dashboard)
- Expo CLI (for mobile app)

### Run with Docker

```bash
# Start all services
docker-compose up -d

# API available at http://localhost:8000
# Dashboard at http://localhost:3000
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Dashboard
cd admin-dashboard
npm install
npm run dev
```

## 📡 API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login, get JWT token
- `GET /api/auth/me` - Get current user

### Clock In/Out (GPS)
- `GET /api/clock/status` - Current clock status
- `POST /api/clock/in` - Clock in with GPS
- `POST /api/clock/out` - Clock out with GPS
- `GET /api/clock/history` - Clock history

### Timesheets
- `GET /api/timesheets/` - List timesheets
- `GET /api/timesheets/current` - Current week
- `GET /api/timesheets/{id}` - Get timesheet details
- `POST /api/timesheets/{id}/submit` - Submit for approval

### Clients & Job Sites
- `GET /api/clients/` - List clients
- `POST /api/clients/` - Create client
- `GET /api/clients/{id}/job-sites` - Job sites for client
- `GET /api/clients/job-sites/all` - All job sites

### MYOB Integration
- `GET /api/myob/status` - Connection status
- `GET /api/myob/export-preview` - Preview export
- `POST /api/myob/export` - Export to MYOB

## 🔐 User Roles

| Role | Permissions |
|------|-------------|
| Worker | Clock in/out, view own timesheets, submit |
| Supervisor | + Approve timesheets, view team |
| Admin | + Manage users, clients, MYOB export |

## 📱 Mobile App Features (Planned)

1. **Login** - Secure authentication
2. **Dashboard** - Today's status, quick clock in/out
3. **Clock In** - Select job site, GPS captured
4. **Clock Out** - Add comments, injury report
5. **Timesheets** - View/edit weekly timesheets
6. **History** - Past timesheets

## 🔧 Environment Variables

```env
# Backend
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/raw_timesheet
SECRET_KEY=your-secret-key
MYOB_CLIENT_ID=your-myob-client-id
MYOB_CLIENT_SECRET=your-myob-client-secret

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 📝 License

Private - RAW Labour Hire

---

**Contact:** accounts@rawlabourhire.com  
**Address:** 12 Hellion crt, Keilor Downs Vic 3038  
**Phone:** +61 414 268 338  
**ABN:** 13 097 261 288
