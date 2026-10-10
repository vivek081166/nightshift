Source: scan-dr-drill-2023.pdf · tag f4cdd040 · made 2026-10-09

## Backup restore drill report: api database

Sorrel platform team · Drill DR-2023-02

| Drill | DR-2023-02 |
| :--- | :--- |
| Date | 2023-06-13 (Tuesday) |
| Scope | Restore the api primary database from the nightly backup into the restore account in eu-west-1 |
| Recovery point | Nightly backup of 2023-06-13 01:00 JST |
| Drill lead | Ravi |
| Observer | Mei |

### Results

| Step | Target | Actual | Result |
| :--- | :--- | :--- | :--- |
| 1. Find the latest nightly backup in object storage | 10 min | 6 min | Pass |
| 2. Copy the backup to the restore account in eu-west-1 | 45 min | 38 min | Pass |
| 3. Restore the database from the backup | 90 min | 2 h 04 min | Fail |
| 4. Check row counts against the production snapshot | 20 min | 17 min | Pass |
| 5. Start api against the restored database and make a test booking | 30 min | 22 min | Pass |
| Total time to a working api | 4 h | 3 h 27 min | Pass |

Step 3 was slow because the restore used the default instance size. The bookings table came back with 41,880,112 rows, matching the production snapshot exactly.

Follow-up: restore to a larger instance size and repeat the drill in December.

*Ravi*  
Drill lead: Ravi Date: 2023-06-15

*Mei*  
Reviewed: Mei Date: 2023-06-16