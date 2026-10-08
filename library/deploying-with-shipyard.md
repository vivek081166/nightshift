# Deploying with Shipyard

Owner: the platform team (Kenji Sato). Last updated: 2026-09-28.

Shipyard is the deploy pipeline for **api** and **payments**. Both services moved to it on 2026-09-28. From that day on, the old deploy tool no longer controls api or payments: it still lists their old deploys, but it cannot deploy them or roll them back. web and notifier stay on the old deploy tool for now; their move is planned for the first quarter of 2027 and this page will say so when it happens.

Shipyard lives at `shipyard.sorrel.internal`. You sign in with your normal company account. The command line tool is called `shipyard` and is already installed on every on-call laptop that went through the September laptop update. If `shipyard --version` prints nothing, ask in `#platform` before your shift, not during an incident.

## Why we moved

On 2026-08-20 an api rollback waited 38 minutes in the old deploy tool's queue behind a web deploy (see the postmortem "api rollback stuck in the deploy queue"). The old tool runs one job at a time for the whole project, so a rollback for one service can wait for an unrelated deploy of another. Shipyard runs each service in its own lane: a rollback of payments never waits for anything api or web is doing.

The other reasons, in short:

- Every release has a name and a list of what is in it, so "what changed?" has one answer.
- Approvals happen inside Shipyard, so we no longer approve releases in chat and lose the trail.
- The release list keeps the last 30 releases of each service ready to roll back to.

## Releases

A release is one version of one service. Shipyard names releases with a running number per service: `r-212`, `r-213`, and so on. api and payments have their own numbers, so `r-212` on api and `r-212` on payments are different releases. Always say the service with the release name: "payments r-212", never "r-212" on its own.

Each release page shows:

- the commits it contains and who wrote them,
- who approved it and when,
- when it started going out, when it finished, and which nodes run it,
- its state: `rolling out`, `live`, `rolled back`, or `superseded`.

Old deploy ids like `d-4471` still appear in postmortems and in the old tool's history from before 2026-09-28. They do not exist in Shipyard. The first Shipyard releases were api r-200 and payments r-200, both cut from whatever was running on 2026-09-28, so nothing changed on the day of the move.

## Where to see the release list

- In the browser: `shipyard.sorrel.internal`, pick the service, open the **Releases** tab. The newest release is at the top. The release marked `live` is the one running now.
- On the command line: `shipyard releases payments` (or `shipyard releases api`). It prints the last 30 releases, newest first, with state, age and author.

During an incident, paste the output of `shipyard releases <service>` into the incident thread. It answers "what was the last release and how old is it" for everyone at once.

## How a deploy goes out

On-call engineers do not deploy new code during their shift unless they own the change (handbook section 10.3). This section is here so you know what you are looking at.

1. The author opens a release from the main branch: `shipyard release create payments`. Shipyard builds it and gives it the next number.
2. The release waits for approval. A release needs one approval from someone in the service's approver group who is not its author. The groups are `api-release` and `payments-release` in Shipyard; Ravi and Mei manage their own groups.
3. Once approved, the author presses **Start rollout**. Shipyard sends the release to one node per region first, waits five minutes while it watches the error rate, then moves the remaining nodes two at a time.
4. If the error rate on the first nodes goes above the service's limit, Shipyard stops the rollout on its own and leaves the previous release running everywhere else. A stopped rollout is not a rollback; the release page says `rollout halted`.
5. When every node runs the new release, it is marked `live` and the previous one becomes `superseded`.

The deploy windows in handbook section 11 still apply. Shipyard refuses to start a rollout between 22:00 and 07:00 JST unless the release is marked as a fix for an open P1 incident.

## How to roll back

A rollback moves a service back to an earlier release. Use it when the last release is recent enough to be the cause (the five actions at the top of the handbook still decide whether rolling back is the right first move).

### Rolling back to the previous release (the normal case)

Either way works. Both do the same thing and both are recorded on the release page.

**Command line:**

```
shipyard releases payments
shipyard rollback payments --to r-211
```

Use the release just below the `live` one in the list. Shipyard asks you to type the service name to confirm.

**Browser:**

1. Open `shipyard.sorrel.internal`, pick the service, open **Releases**.
2. Find the release just below the `live` one and press **Roll back to this release**.
3. Type the service name in the box to confirm.

What happens next:

- api replaces its nodes two at a time; about six minutes.
- payments first drains in-flight checkouts, then switches; about five minutes. A rollback never reverses a charge or a refund that already went through.
- Shipyard posts the start and the end of the rollback in `#deploys`. Copy both release names into the incident thread yourself as well.

### Who can roll back, and who approves

- **The on-call engineer can roll back one release, with no approval.** This is pre-approved for every on-call engineer, day or night, because rolling back one release is always safe (database migrations are written to work with the previous release).
- **Rolling back two or more releases needs the service owner's approval in Shipyard: Ravi for api, Mei for payments.** Shipyard shows a "needs approval" banner and the owner approves from the release page or from the Shipyard app on their phone. If the owner does not answer, page them; do not ask someone else to approve in their place.
- Nobody can roll back to a release older than the 30 that Shipyard keeps.

### If the rollback does not help

If the service is still unhealthy ten minutes after the rollback finished, the last release was probably not the cause. Do not roll back again to see if an older release helps; that is the two-or-more case and it needs the owner. Page the owner (handbook section 4.2).

## Common questions

**Can I still use the old deploy tool for api or payments?** No. Since 2026-09-28 it only shows their history from before the move. Buttons for api and payments are greyed out there.

**What about feature flags?** Unchanged. Turning a flag off is not a rollback and is the owner's call (handbook section 11).

**Where do I report a problem with Shipyard itself?** `#platform`, and page the platform on-call through the paging tool if it blocks a P1 rollback.

**Is Shipyard's history the same as the incident record?** No. Shipyard records what happened to releases. The incident thread records why. Write both release names in the thread.
