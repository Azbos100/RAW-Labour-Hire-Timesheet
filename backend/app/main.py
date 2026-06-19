"""
RAW Labour Hire - Timesheet API
Main FastAPI Application
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import os


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Ensure redirects use HTTPS in production"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Fix redirect URLs to use HTTPS if the original request was HTTPS
        if response.status_code in (301, 302, 307, 308):
            location = response.headers.get("location", "")
            if location.startswith("http://") and (
                request.headers.get("x-forwarded-proto") == "https" or
                request.url.scheme == "https"
            ):
                new_location = location.replace("http://", "https://", 1)
                response.headers["location"] = new_location
        return response

from sqlalchemy import text, select, func

from .routes import auth, timesheets, users, clients, clock, myob, tickets, induction, jobsites, notifications, billing
from .database import engine, Base, AsyncSessionLocal
from .models import Client, JobSite, TicketType, InductionDocument


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Run database migrations for new columns
    async with engine.begin() as conn:
        # Add overtime_mode column to timesheet_entries if it doesn't exist
        try:
            await conn.execute(text("""
                ALTER TABLE timesheet_entries 
                ADD COLUMN IF NOT EXISTS overtime_mode BOOLEAN DEFAULT FALSE
            """))
        except Exception as e:
            print(f"Migration note (overtime_mode): {e}")
        
        # Add shift schedule columns to users table
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS shift_start_time TIME;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS shift_end_time TIME;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_monday BOOLEAN DEFAULT TRUE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_tuesday BOOLEAN DEFAULT TRUE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_wednesday BOOLEAN DEFAULT TRUE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_thursday BOOLEAN DEFAULT TRUE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_friday BOOLEAN DEFAULT TRUE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_saturday BOOLEAN DEFAULT FALSE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS works_sunday BOOLEAN DEFAULT FALSE;
            """))
        except Exception as e:
            print(f"Migration note (shift schedule): {e}")

        # Job assignment columns
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assigned_job_site_id INTEGER REFERENCES job_sites(id);
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assignment_accepted BOOLEAN;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assignment_date DATE;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP;
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assignment_start_time VARCHAR(10);
            """))
        except Exception as e:
            print(f"Migration note (job assignment): {e}")
        
        # Push notification token column
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS push_token VARCHAR(255);
            """))
        except Exception as e:
            print(f"Migration note (push_token): {e}")
        
        # Timesheet archive column
        try:
            await conn.execute(text("""
                ALTER TABLE timesheets ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;
            """))
        except Exception as e:
            print(f"Migration note (archived_at): {e}")
        
        # Break tracking columns for timesheet entries
        try:
            await conn.execute(text("""
                ALTER TABLE timesheet_entries ADD COLUMN IF NOT EXISTS unpaid_break_minutes INTEGER DEFAULT 30;
            """))
            await conn.execute(text("""
                ALTER TABLE timesheet_entries ADD COLUMN IF NOT EXISTS paid_break_minutes INTEGER DEFAULT 0;
            """))
            await conn.execute(text("""
                ALTER TABLE timesheet_entries ADD COLUMN IF NOT EXISTS gross_hours FLOAT DEFAULT 0;
            """))
        except Exception as e:
            print(f"Migration note (break columns): {e}")
        
        # Assignment end time for users
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assignment_end_time VARCHAR(10);
            """))
        except Exception as e:
            print(f"Migration note (assignment_end_time): {e}")
        
        # Assigned shift times stored on entry for hour calculations
        try:
            await conn.execute(text("""
                ALTER TABLE timesheet_entries ADD COLUMN IF NOT EXISTS assigned_start_time VARCHAR(10);
            """))
            await conn.execute(text("""
                ALTER TABLE timesheet_entries ADD COLUMN IF NOT EXISTS assigned_end_time VARCHAR(10);
            """))
        except Exception as e:
            print(f"Migration note (assigned shift times): {e}")

        # Foreman / site contact stored on the worker's assignment
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assignment_contact_name VARCHAR(100);
            """))
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS assignment_contact_phone VARCHAR(30);
            """))
        except Exception as e:
            print(f"Migration note (assignment contact): {e}")

    # Seed a default client/job site if none exist
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(Client)
        )
        client_count = result.scalar() or 0
        if client_count == 0:
            client = Client(
                name="RAW Labour Hire",
                contact_email="accounts@rawlabourhire.com",
                address="Default client for initial setup",
                is_active=True,
            )
            session.add(client)
            await session.flush()

            job_site = JobSite(
                client_id=client.id,
                name="General Site",
                address="Default job site",
                is_active=True,
            )
            session.add(job_site)
            await session.commit()
    
    # Seed / top-up default ticket types.
    # Runs on every startup and adds any missing types by name, so new types
    # (e.g. Excavator, Bobcat) appear on the live DB without wiping existing data.
    async with AsyncSessionLocal() as session:
        default_ticket_types = [
            ("White Card", "Construction Induction Card", False),
            ("Working with Children Check", "WWC Check", True),
            ("Scissor Lift", "Elevating Work Platform - Scissor Lift", True),
            ("Boom Lift", "Elevating Work Platform - Boom Lift", True),
            ("Forklift", "Forklift License", True),
            ("Excavator", "Excavator Ticket", True),
            ("Bobcat", "Bobcat / Skid Steer Ticket", True),
            ("First Aid", "First Aid Certificate", True),
            ("Traffic Control", "Traffic Control Certification", True),
            ("Confined Space", "Confined Space Entry", True),
            ("Working at Heights", "Working at Heights Certification", True),
            ("Driver's License", "Driver's License", True),
            ("Other", "Other certification or ticket", True),
        ]
        existing_result = await session.execute(select(TicketType.name))
        existing_names = {n for (n,) in existing_result.all()}
        added = False
        for name, description, has_expiry in default_ticket_types:
            if name not in existing_names:
                session.add(TicketType(name=name, description=description, has_expiry=has_expiry))
                added = True
        if added:
            await session.commit()
    
    # Seed default induction/SWMS documents if none exist
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(InductionDocument)
        )
        doc_count = result.scalar() or 0
        if doc_count == 0:
            default_documents = [
                InductionDocument(
                    title="General Site Safety Induction",
                    description="Required safety induction for all RAW Labour Hire workers",
                    document_type="induction",
                    category="Safety",
                    is_required=True,
                    display_order=1,
                    content="""<h2>RAW Labour Hire - General Site Safety Induction</h2>
<p>Welcome to RAW Labour Hire. Before commencing work, you must read and acknowledge the following safety information.</p>

<h3>1. Personal Protective Equipment (PPE)</h3>
<ul>
<li>High-visibility clothing must be worn at all times on site</li>
<li>Steel-capped safety boots are mandatory</li>
<li>Hard hats must be worn in designated areas</li>
<li>Safety glasses and hearing protection as required</li>
<li>Gloves appropriate to the task being performed</li>
</ul>

<h3>2. Site Rules</h3>
<ul>
<li>Sign in and out at the site office each day</li>
<li>Report to your supervisor before starting work</li>
<li>No alcohol or drugs on site - zero tolerance policy</li>
<li>Mobile phones only to be used in designated areas</li>
<li>Follow all signage and barriers on site</li>
</ul>

<h3>3. Emergency Procedures</h3>
<ul>
<li>Know the location of emergency exits and assembly points</li>
<li>Know the location of first aid kits and fire extinguishers</li>
<li>In case of emergency, follow site warden instructions</li>
<li>Emergency contact: 000</li>
</ul>

<h3>4. Incident Reporting</h3>
<ul>
<li>All incidents, injuries, and near misses MUST be reported immediately</li>
<li>Report to your supervisor and RAW Labour Hire office</li>
<li>Complete an incident report form</li>
</ul>

<h3>5. Declaration</h3>
<p>By signing below, I acknowledge that I have read and understood the above safety information and agree to comply with all site rules and safety requirements.</p>"""
                ),
                InductionDocument(
                    title="Manual Handling SWMS",
                    description="Safe Work Method Statement for manual handling tasks",
                    document_type="swms",
                    category="Manual Handling",
                    is_required=True,
                    display_order=2,
                    content="""<h2>Safe Work Method Statement - Manual Handling</h2>

<h3>Scope of Work</h3>
<p>This SWMS covers all manual handling activities including lifting, carrying, pushing, pulling, and holding loads.</p>

<h3>Hazards Identified</h3>
<ul>
<li>Muscular strain and sprains</li>
<li>Back injuries</li>
<li>Crush injuries from dropped loads</li>
<li>Cuts and abrasions</li>
</ul>

<h3>Risk Control Measures</h3>
<ol>
<li><strong>Assess the load:</strong> Check weight, size, shape, and condition before lifting</li>
<li><strong>Plan the lift:</strong> Clear path, identify rest points, get help if needed</li>
<li><strong>Correct lifting technique:</strong>
    <ul>
    <li>Stand close to the load with feet shoulder-width apart</li>
    <li>Bend at the knees, not the waist</li>
    <li>Keep back straight and engage core muscles</li>
    <li>Grip the load firmly</li>
    <li>Lift smoothly using leg muscles</li>
    <li>Keep load close to body</li>
    <li>Avoid twisting - move feet to turn</li>
    </ul>
</li>
<li><strong>Use mechanical aids:</strong> Trolleys, forklifts, or hoists where available</li>
<li><strong>Team lifting:</strong> Use two or more people for heavy or awkward loads</li>
</ol>

<h3>PPE Required</h3>
<ul>
<li>Safety boots</li>
<li>Gloves appropriate to the load</li>
<li>High-visibility clothing</li>
</ul>

<h3>Declaration</h3>
<p>I have read and understood this SWMS and will follow the safe work procedures outlined above.</p>"""
                ),
                InductionDocument(
                    title="Working at Heights SWMS",
                    description="Safe Work Method Statement for elevated work",
                    document_type="swms",
                    category="Heights",
                    is_required=True,
                    display_order=3,
                    content="""<h2>Safe Work Method Statement - Working at Heights</h2>

<h3>Scope of Work</h3>
<p>This SWMS covers all work performed above 2 metres from ground level, including work on scaffolds, ladders, elevated work platforms, and roofs.</p>

<h3>Hazards Identified</h3>
<ul>
<li>Falls from height</li>
<li>Falling objects</li>
<li>Scaffold collapse</li>
<li>Ladder slips</li>
<li>Contact with overhead hazards</li>
</ul>

<h3>Risk Control Measures</h3>
<ol>
<li><strong>Eliminate:</strong> Where possible, perform work at ground level</li>
<li><strong>Substitute:</strong> Use elevated work platforms instead of ladders where practical</li>
<li><strong>Engineering controls:</strong>
    <ul>
    <li>Install guardrails and edge protection</li>
    <li>Use scaffolding with proper handrails and toe boards</li>
    <li>Ensure platforms are properly secured</li>
    </ul>
</li>
<li><strong>Administrative controls:</strong>
    <ul>
    <li>Working at Heights ticket required</li>
    <li>Daily inspection of equipment</li>
    <li>Exclusion zones below work area</li>
    </ul>
</li>
<li><strong>PPE:</strong>
    <ul>
    <li>Full body harness when required</li>
    <li>Hard hat</li>
    <li>Non-slip footwear</li>
    </ul>
</li>
</ol>

<h3>Ladder Safety</h3>
<ul>
<li>Inspect ladder before use</li>
<li>Set up on firm, level ground</li>
<li>Maintain 3 points of contact</li>
<li>Do not overreach</li>
<li>Face the ladder when climbing</li>
</ul>

<h3>Declaration</h3>
<p>I have read and understood this SWMS and confirm I hold a current Working at Heights ticket (if required).</p>"""
                ),
                InductionDocument(
                    title="Hazardous Substances SWMS",
                    description="Safe Work Method Statement for handling hazardous materials",
                    document_type="swms",
                    category="Hazardous Materials",
                    is_required=True,
                    display_order=4,
                    content="""<h2>Safe Work Method Statement - Hazardous Substances</h2>

<h3>Scope of Work</h3>
<p>This SWMS covers handling, storage, and disposal of hazardous substances including chemicals, solvents, and dangerous goods.</p>

<h3>Hazards Identified</h3>
<ul>
<li>Chemical burns</li>
<li>Toxic fumes/vapours</li>
<li>Fire and explosion</li>
<li>Environmental contamination</li>
<li>Allergic reactions</li>
</ul>

<h3>Risk Control Measures</h3>
<ol>
<li><strong>Read the SDS:</strong> Always read the Safety Data Sheet before handling any substance</li>
<li><strong>Storage:</strong>
    <ul>
    <li>Store in designated areas</li>
    <li>Keep containers sealed when not in use</li>
    <li>Separate incompatible substances</li>
    </ul>
</li>
<li><strong>Handling:</strong>
    <ul>
    <li>Use appropriate PPE as per SDS</li>
    <li>Work in well-ventilated areas</li>
    <li>No eating, drinking, or smoking near chemicals</li>
    <li>Wash hands after handling</li>
    </ul>
</li>
<li><strong>Spill response:</strong>
    <ul>
    <li>Know location of spill kits</li>
    <li>Contain spill and notify supervisor</li>
    <li>Do not wash chemicals into drains</li>
    </ul>
</li>
</ol>

<h3>PPE Requirements</h3>
<ul>
<li>Chemical-resistant gloves</li>
<li>Safety glasses or goggles</li>
<li>Appropriate respiratory protection</li>
<li>Chemical-resistant clothing if required</li>
</ul>

<h3>Declaration</h3>
<p>I have read and understood this SWMS and will follow safe handling procedures for all hazardous substances.</p>"""
                ),
                InductionDocument(
                    title="COVID-19 Safety Protocol",
                    description="Health and safety measures for COVID-19 prevention",
                    document_type="policy",
                    category="Health",
                    is_required=True,
                    display_order=5,
                    content="""<h2>COVID-19 Safety Protocol</h2>

<h3>Overview</h3>
<p>RAW Labour Hire is committed to providing a safe workplace. All workers must follow these COVID-19 safety measures.</p>

<h3>Requirements</h3>
<ul>
<li><strong>Do not attend work if unwell:</strong> Stay home if you have any cold or flu symptoms</li>
<li><strong>Hand hygiene:</strong> Wash hands regularly with soap or use hand sanitiser</li>
<li><strong>Respiratory hygiene:</strong> Cover coughs and sneezes</li>
<li><strong>Physical distancing:</strong> Maintain distance where practical</li>
<li><strong>Clean touch points:</strong> Wipe down shared tools and equipment</li>
</ul>

<h3>If You Become Unwell</h3>
<ol>
<li>Inform your supervisor immediately</li>
<li>Leave the worksite</li>
<li>Get tested if required</li>
<li>Follow health authority advice</li>
<li>Do not return until cleared</li>
</ol>

<h3>Declaration</h3>
<p>I confirm I am fit for work and will follow all COVID-19 safety measures.</p>"""
                ),
            ]
            for doc in default_documents:
                session.add(doc)
            await session.commit()
    
    # Start the automatic reminder scheduler
    from .services.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    
    yield
    
    # Cleanup on shutdown
    stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title="RAW Labour Hire - Timesheet API",
    description="Digital timesheet system with GPS tracking and MYOB integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Fix HTTPS redirects in production (must be added first)
app.add_middleware(HTTPSRedirectMiddleware)

# CORS - allow mobile app and web dashboard
# In production, mobile apps make requests with various origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for mobile app compatibility
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Global authentication gate ===
# Ensures no /api endpoint can be reached without a valid login token.
# Admin-only areas additionally require an admin token.
import re as _auth_re
from starlette.responses import JSONResponse as _AuthJSONResponse
from jose import jwt as _auth_jwt, JWTError as _AuthJWTError
from .routes.auth import SECRET_KEY as _AUTH_SECRET_KEY, ALGORITHM as _AUTH_ALGORITHM

# Reachable WITHOUT a token
_PUBLIC_EXACT = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}
_PUBLIC_PREFIXES = (
    "/admin",                      # static admin html/login/logo (data lives under /api)
    "/api/auth/login",
    "/api/auth/admin/login",
    "/api/auth/admin/verify",      # validates a token supplied as a query param
    "/api/auth/register",
    "/api/auth/password-reset",
    "/api/induction/pdf/",         # opened by the app's PDF viewer without an auth header
)
# Require an ADMIN token specifically
_ADMIN_PREFIXES = (
    "/api/billing",
    "/api/myob",
    "/api/notifications",
    "/api/jobsites",
)
# Admin-only actions that do NOT carry "/admin" in the path. Matched on
# (method, path) so worker actions on the same prefixes (e.g. GET a timesheet
# or POST .../submit) stay open to the worker who owns them.
_ADMIN_METHOD_PATHS = (
    ("DELETE", _auth_re.compile(r"^/api/timesheets/\d+$")),            # archive (soft delete)
    ("DELETE", _auth_re.compile(r"^/api/timesheets/\d+/permanent$")),  # permanent delete
    ("POST",   _auth_re.compile(r"^/api/timesheets/\d+/approve$")),
    ("POST",   _auth_re.compile(r"^/api/timesheets/\d+/reject$")),
    ("POST",   _auth_re.compile(r"^/api/timesheets/\d+/restore$")),
    ("POST",   _auth_re.compile(r"^/api/clients/\d+/contacts$")),      # add foreman / site contact
    ("DELETE", _auth_re.compile(r"^/api/clients/contacts/\d+$")),      # delete foreman / site contact
)
# Worker endpoints that embed a user id in the path; a non-admin token may
# only act on its OWN id (admin endpoints live under /api/users/admin/...).
_OWN_USER_PATH = _auth_re.compile(r"^/api/users/(\d+)(?:/.*)?$")


def _auth_is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    return any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES)


def _auth_requires_admin(method: str, path: str) -> bool:
    if any(path.startswith(p) for p in _ADMIN_PREFIXES):
        return True
    if path.startswith("/api/") and "/admin" in path:
        return True
    for m, rx in _ADMIN_METHOD_PATHS:
        if method == m and rx.match(path):
            return True
    return False


def _auth_deny(detail: str, status_code: int = 401):
    return _AuthJSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer", "Access-Control-Allow-Origin": "*"},
    )


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    path = request.url.path
    method = request.method
    # Let CORS preflight, static/non-API, and explicitly public paths through
    if method == "OPTIONS" or not path.startswith("/api") or _auth_is_public(path):
        return await call_next(request)

    parts = request.headers.get("authorization", "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return _auth_deny("Authentication required")
    try:
        # verify_sub=False tolerates legacy tokens whose `sub` was an int.
        payload = _auth_jwt.decode(
            parts[1], _AUTH_SECRET_KEY, algorithms=[_AUTH_ALGORITHM],
            options={"verify_sub": False},
        )
    except _AuthJWTError:
        return _auth_deny("Invalid or expired token")

    is_admin = payload.get("type") == "admin"
    sub = payload.get("sub")

    # Expose identity to downstream routes (rate redaction / ownership checks).
    request.state.is_admin = is_admin
    request.state.token_sub = sub

    if _auth_requires_admin(method, path) and not is_admin:
        return _auth_deny("Admin privileges required", status_code=403)

    # IDOR guard: a non-admin may only touch its own user record / data.
    if not is_admin:
        m = _OWN_USER_PATH.match(path)
        if m and str(m.group(1)) != str(sub):
            return _auth_deny("You can only access your own data", status_code=403)
        qs_uid = request.query_params.get("user_id")
        if qs_uid is not None and str(qs_uid) != str(sub):
            return _auth_deny("You can only access your own data", status_code=403)

    return await call_next(request)


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(clients.router, prefix="/api/clients", tags=["Clients"])
app.include_router(timesheets.router, prefix="/api/timesheets", tags=["Timesheets"])
app.include_router(clock.router, prefix="/api/clock", tags=["Clock In/Out"])
app.include_router(myob.router, prefix="/api/myob", tags=["MYOB Integration"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["Tickets/Certifications"])
app.include_router(induction.router, prefix="/api/induction", tags=["Induction/SWMS"])
app.include_router(jobsites.router, prefix="/api/jobsites", tags=["Job Sites"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing/Invoicing"])


@app.get("/")
async def root():
    return {
        "service": "RAW Labour Hire - Timesheet API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "raw-timesheet-api",
        "version": "2.10.0"
    }


# Prevent browsers from serving a stale cached admin page after a deploy
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/admin")
async def admin_dashboard():
    """Serve the admin dashboard"""
    admin_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin", "index.html")
    return FileResponse(admin_path, media_type="text/html", headers=NO_CACHE_HEADERS)


@app.get("/admin/")
async def admin_dashboard_slash():
    """Serve the admin dashboard with trailing slash"""
    admin_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin", "index.html")
    return FileResponse(admin_path, media_type="text/html", headers=NO_CACHE_HEADERS)


@app.get("/admin/{filename}")
async def admin_static(filename: str):
    """Serve static files for admin dashboard"""
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin", filename)
    if os.path.exists(file_path):
        # Determine media type
        if filename.endswith('.html'):
            media_type = "text/html"
        elif filename.endswith('.png'):
            media_type = "image/png"
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            media_type = "image/jpeg"
        elif filename.endswith('.css'):
            media_type = "text/css"
        elif filename.endswith('.js'):
            media_type = "application/javascript"
        else:
            media_type = "application/octet-stream"
        # Don't cache HTML so admin always gets the latest after a deploy;
        # other assets (images, etc.) can be cached normally.
        headers = NO_CACHE_HEADERS if media_type == "text/html" else None
        return FileResponse(file_path, media_type=media_type, headers=headers)
    return {"error": "File not found"}

