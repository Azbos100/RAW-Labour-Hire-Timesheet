# RAW Timesheet — To Do

## Operational notes (read first)

> Updated 19 Jun 2026.

- **Where it runs:** everything (admin site + API + Postgres) is on the
  **DigitalOcean** server at `admin.rawlabourhire.com`. The old **Railway**
  deployment is retired — do not point anything at it. (Keep Railway running
  only until all staff have moved to the new app builds, then it can be shut down.)
- **⚠️ Staff must log out & log back in after updating the app.** When staff
  update to iOS build 21+ (or the latest Android APK), their old saved login
  (from the previous server) is rejected and they'll see *"Invalid or expired
  token"* / can't clock in. Fix: **Profile → Log Out → log back in**. Add this
  line to the TestFlight "What to Test" notes and any staff message.
- **Login is rate-limited:** 10 failed attempts from one IP within 10 min →
  that IP is locked out for 10 min (429). Per-IP, so one bad actor can't lock
  out real staff. In-memory (resets on backend restart).

## Admin page — feature backlog (staff requests + MYOB invoicing)

> Captured 19 Jun 2026 from staff recommendations. Headline goal: replicate the
> existing Excel database in the admin page (each client's jobs → staff who worked
> them → hours per site, total hours per site, total hours per staff) and push it
> to **MYOB** to auto-generate the weekly invoices.
>
> Tech constraints found in the codebase:
> - Prod = **Postgres on the DigitalOcean server**, tables auto-create via `Base.metadata.create_all`
>   (no Alembic). New *tables* appear automatically on deploy; new *columns* on
>   existing tables need a one-off migration script. Ticket-type seeding only runs
>   on an empty DB — must top-up missing types so they show on the live DB.
> - MYOB plumbing partly scaffolded already: `MYOBSettings`, `MYOBExport`,
>   `Client.myob_customer_id`, and billing-rate fields exist.

### 1. Tickets tab  — DONE & LIVE (verified 19 Jun 2026)
- [x] 1a. **Ticket-type search dropdown** — "Ticket Type" filter on the Tickets tab (uses `/api/tickets/admin/all?ticket_type_id=`).
- [x] 1b. **Add Excavator + Bobcat** ticket types — both seeded live (ids 12 & 13); "Add type" button adds more (`/api/tickets/admin/types`, reactivates an inactive match).
- [x] 1c. **Save/download ticket images** — per-image "Download front/back" in the ticket modal + "Download images" (all in current filter), sensible filenames `Worker_Type_side.ext`.

### 2. Timesheets — DONE & LIVE (19 Jun 2026)
- [x] 2a. **Sort/group timesheets by week** — Timesheets tab now has a "Pay Week (Sat→Fri)"
  dropdown + "Group by week" toggle with per-week hour/OT subtotals. Works alongside the
  Status/Worker filters.

### 3. Calendar — DONE & LIVE (19 Jun 2026)
- [x] 3a. **New calendar tab** — month grid laid out Sat→Fri; each day shows worker count
  (green if anyone still on site); click a day → table of worker/client/site/in-out/hours.
  Backed by `GET /api/clock/admin/calendar?year&month`.

### 4. Allocation
- [x] 4a. **Site-contacts dropdown** — foreman names + phone numbers saved per company, reusable.
  BUILT & LIVE: manage foremen under the Clients tab (new `client_contacts` table);
  Assign Job modal has a Foreman dropdown filtered to the job site's client; selected
  contact is stored on the assignment, shown in the worker list, and added to the assignment SMS.
- [x] 4b. **Separate "next-day jobs" allocation section** — new **Allocation tab** (defaults to
  Next Day). Shows only that day's allocated jobs (worker/client/site/address/start/foreman/
  accepted/clocked), an "Assign" list of unallocated workers, and an amber banner of stale old
  assignments (pending, past-dated, never clocked) each with **Edit** + **Delete** buttons.
  Built client-side off `/api/users/admin/workers`. DONE & LIVE 19 Jun 2026.
- [x] 4c. **End-of-week dockets auto-grouped Client → Address** — already delivered by the
  Invoicing tab's Client Billing view (`/api/billing/client-billing`, Client → Address → Date →
  Worker with subtotals + CSV).

### 5. Invoicing / Excel-database replication → MYOB (headline)

Reference: `Josh's Raw Timesheet New Friday.xlsx` (8 sheets). Replicate this whole
billing/payroll engine in the admin page, driven off the existing timesheet data,
ending in a MYOB push. Sheets to reproduce as admin views (all filtered by Week_End):

- [x] 5a. **Client_Billing view** — pivot Client → Job_Address → Date → Worker, columns
  `Day · Date · Worker · Shift_Type · Role · Ordinary · OT · OT_Sat · OT_Sun · Total`,
  with subtotals at Date / Address / Client levels + grand total. Filter by Week_End + Client.
  (BUILT — new "Invoicing" admin tab + `/api/billing/client-billing`. Derives hours per
  the agreed rule. Invoice-number field still TODO.)
- [x] 5b. **Worker_Totals view** — Worker → total hours for the week, with a green/red
  banner that auto-checks billing total == worker total. (BUILT — `/api/billing/worker-totals`.)
- [x] 5c. **MYOB_Payroll view** — Worker → Shift_Type → Role → summed hours.
  (BUILT — `/api/billing/myob-payroll`.)
- [x] 5d. **Weekly CSV export** of each view in the spreadsheet column layout (opens in Excel).
  (BUILT — "Export CSV" button.) Plus an **"Import-ready (MYOB)"** checkbox that strips
  subtotal/total rows and uses DD/MM/YYYY dates so the file imports cleanly into MYOB.
- [ ] 5e. **MYOB live API push** — PARKED by owner decision 19 Jun 2026. Owner uses
  **MYOB Business** (not AccountRight) and is happy with CSV import for now. When ready to go live:
  1. Register an app at **developer.myob.com** → get Client ID & Secret (owner action).
  2. **Rework `myob.py` for MYOB Business** — current scaffold targets AccountRight
     (`api.myob.com/accountright`); MYOB Business uses a different API base + invoice/payroll
     resource structure.
  3. **Fix OAuth callback auth gate:** `/api/myob` is in `_ADMIN_PREFIXES` in `main.py`, but the
     `GET /api/myob/callback` redirect from MYOB carries no token → must be made public
     (add to `_PUBLIC_PREFIXES`, keep the rest admin-only).
  4. Set `MYOB_REDIRECT_URI=https://admin.rawlabourhire.com/api/myob/callback` in the server `.env`
     and register the same URI in the MYOB app.
  5. Enter **worker pay rates** + **client billing rates** (admin UI for this still TODO) so $ amounts compute.
  6. **Link** each worker → MYOB employee UID and each client → MYOB customer UID.
  7. Build the **admin "Connect to MYOB" screen** (drives `/api/myob/credentials`, `/auth-url`,
     `/company-files`, `/select-company-file`, `/export`).
- [ ] 5f. Invoice-number field per client block (entry + save) once MYOB flow is decided.
- [ ] 5g. Verify on live deploy with real data; confirm Job_Address mapping (job_site vs clock-in address) reads well.

**Data-model gaps vs the spreadsheet (need before 5a–5e are accurate):**
- `OT_Sat` / `OT_Sun` are separate columns in Excel but the DB only has `ordinary_hours`
  + `overtime_hours` on `TimesheetEntry`. Either derive from the entry weekday, or add columns.
- `Shift_Type` (Day/Night) — not stored; derive from start time or add a field (Excel sometimes blank).
- `Role` (e.g. "Reg", operator) — `worked_as` exists on the entry; map it to Role.
- Worker rates: `User` has base/overtime/weekend/night rates but NOT separate **Saturday vs Sunday**
  rate or **Operator_Loading** (Excel `Worker_Rates` has Ordinary/OT/Saturday/Sunday/Night/Operator_Loading).

**Open decisions:** OT split rule (how Sat/Sun/over-8h fill the columns), Shift_Type source,
whether to add the missing columns (needs a one-off Postgres migration) or derive on the fly,
and MYOB connection status (credentials set up yet?).

### 6. Clock management — DONE & LIVE (19 Jun 2026)
- [x] 6a. **Manual clock-out from admin** — green **"On Site"** button on the Timesheets tab
  (with live count badge) opens a panel of everyone currently clocked in; clock any of them out
  now or at a typed HH:MM. Recalculates hours (incl. 30-min unpaid break for 4h+ shifts) and
  updates timesheet totals. Backed by `GET /api/clock/admin/active` +
  `POST /api/clock/admin/clock-out/{entry_id}`.
  > Cleanup note: 15 workers were found stuck "clocked in" from as far back as January — use the
  > On Site panel to clock them out with the correct finish time.

### Open decisions before building invoicing
- **OT split rule**: how Sat/Sun and over-8h hours fill `OT_Sat / OT_Sun / OT`, and what defines `Shift_Type` (Day/Night). Affects billing accuracy.
- **MYOB connection**: confirm whether MYOB API/developer credentials are already set up, or onboarding is needed (most involved piece).

### Suggested build order
Tickets (1) → Timesheets-by-week (2) → Invoicing/Excel replication (5) → Allocation (4) → Calendar (3) → Manual clock-out (6) folded into whichever touches the dashboard.

---

## Tomorrow — Thu 18 Jun 2026: Upload Android app to Google Play

> iOS is already done (TestFlight build #19, submitted & processing). This is the Android side.

### Build artifact (ready to upload)
- **Android .aab (versionCode 9):**
  https://expo.dev/artifacts/eas/Ws7IOpx1W4xwZb9SyX5P2RLmmkpr7Jc_QmCxh-Blnxc.aab
- EAS build page:
  https://expo.dev/accounts/azbos/projects/raw-timesheet/builds/6c07c038-2261-46dd-9534-4e464ef5c28f
- Play Console: https://play.google.com/console — account: **RAW Labour Hire** (Organization, RAW AUSTRALIA WORK PTY LTD)

### Stage 1 — Finish Play Console account verification (must be done before publishing)
Three tasks on the Play Console home "Finish setting up your developer account":
1. **Google is verifying your identity** — wait; Google emails if docs needed (can take hours–days).
2. **Verify your organization's website** → View details → enter **https://www.rawlabourhire.com**.
   Google confirms via an email sent to an **@rawlabourhire.com** address (e.g. accounts@rawlabourhire.com) — make sure that inbox is reachable.
3. **Verify your phone numbers** — enter the code Google texts/calls.
- Note: Organization account = **exempt** from the "20 testers for 14 days" rule.

### Stage 2 — Create app + upload (once account verified)
1. Home → **Create app** → name "RAW Timesheet", App (not game), Free, accept declarations.
2. **Testing → Internal testing** → **Create new release**.
3. Upload the **.aab** (link above) under App bundles.
4. First upload → accept **Play App Signing** (Google manages the signing key).
5. Add staff Google emails as **testers** → **Save → Review release → Roll out**.
6. Staff install via the opt-in link / Play Store.

### Watch-outs
- This is a **fresh Play account** — Android staff likely weren't on Play before. Play App Signing uses a **different key** than any old direct APK, so staff with an old APK must **uninstall it first** before installing the Play version.
- App package: `com.rawlabourhire.timesheet` · current version 2.10.0 · Android versionCode 9 · iOS build 19.

### Optional follow-up (ask agent)
- Set up a **Google Play service account** (~10 min, one-time) so future Android releases auto-submit from EAS — no manual .aab download/upload.
