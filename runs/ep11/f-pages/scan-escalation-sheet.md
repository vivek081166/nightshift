Source: scan-escalation-sheet.pdf · md5 9e338d13 · converted 2026-10-08

## On-call escalation sheet

Printed 2024-04-01 · keep next to the desk phone · replace when the owners change

| Role | Name | Extension | Call for |
| :--- | :--- | :--- | :--- |
| web owner | Aiko | ext. 4411 | Front-end releases, CDN and firewall, admin tool, account deletions and restores |
| api owner | Ravi | ext. 4417 | Booking logic, the database, partner integrations, the audit log |
| payments owner | Mei | ext. 4423 | Charges, refunds, payouts, payment provider settings |
| notifier owner | Tom | ext. 4429 | Email and SMS sending, templates, vendor sending limits |
| Incident commander desk | the IC on the rotation | ext. 4400 | Any P1 open for 15 minutes; an owner who has not answered in 10 minutes |
| Platform team desk | whoever is on the desk | ext. 4450 | Deploy tool, paging tool, metrics and log search access (weekdays 10:00 to 18:00 JST) |
| Support lead | the support lead on shift | ext. 4460 | Customer and business messages during an incident |

If the paging tool itself is down: call the owner's extension first, then the incident commander desk on ext. 4400. Write every call in the incident thread.

Sheet owner: Ravi. Next review: 2024-10-01.