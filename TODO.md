# RAW Timesheet — To Do

## Admin page — feature backlog (staff requests + MYOB invoicing)

> Captured 19 Jun 2026 from staff recommendations. Headline goal: replicate the
> existing Excel database in the admin page (each client's jobs → staff who worked
> them → hours per site, total hours per site, total hours per staff) and push it
> to **MYOB** to auto-generate the weekly invoices.
>
> Tech constraints found in the codebase:
> - Prod = **Postgres on Railway**, tables auto-create via `Base.metadata.create_all`
>   (no Alembic). New *tables* appear automatically on deploy; new *columns* on
>   existing tables need a one-off migration script. Ticket-type seeding only runs
>   on an empty DB — must top-up missing types so they show on the live DB.
> - MYOB plumbing partly scaffolded already: `MYOBSettings`, `MYOBExport`,
>   `Client.myob_customer_id`, and billing-rate fields exist.

### 1. Tickets tab
- [ ] 1a. **Ticket-type search dropdown** — filter workers by a ticket type (e.g. Forklift) so phone enquiries are instant, instead of scrolling all tickets.
- [ ] 1b. **Add Excavator + Bobcat** ticket types (today only "Other" covers them). Make the seeder top-up missing types on the live DB + add a "manage ticket types" control to add more later.
- [ ] 1c. **Save/download ticket images** to computer/hard drive (front/back, plus "download all for a worker").

### 2. Timesheets
- [ ] 2a. **Sort/group timesheets by week** so weekly invoicing isn't a mess.

### 3. Calendar
- [ ] 3a. **New calendar tab** — month grid; click a day → see how many and which workers were out, and their sites.

### 4. Allocation
- [ ] 4a. **Site-contacts dropdown** — foreman names + phone numbers saved per company, reusable so they don't get re-typed every job.
- [ ] 4b. **Separate "next-day jobs" allocation section** (not jumbled into Workers); shows each day's dockets with clocked/accepted status; lets you clear stale old pending assignments.
- [ ] 4c. **End-of-week dockets auto-grouped Client → Address**, ready for invoicing.

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
  (BUILT — "Export CSV" button.)
- [ ] 5e. **MYOB API integration** — generate invoices (Client_Billing) and optionally payroll
  from this data. `MYOBSettings`/`MYOBExport`/`Client.myob_customer_id` already scaffolded. (PENDING — MYOB not connected yet.)
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

### 6. Clock management
- [ ] 6a. **Manual clock-out from admin** — one-click "Clock out now" for a worker still on the clock (sets clock-out time, recalculates hours, optional note). Note: admins can already fix a forgotten clock-out by editing the entry's Clock-Out Date/Time in the timesheet edit modal — this adds the quick live button.

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
