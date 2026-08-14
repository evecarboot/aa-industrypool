# Industry Pool

An [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) plugin that lets corp/alliance leadership
delegate build jobs (manufacturing, reactions, invention/research) to members, and track their progress
using corporation ESI industry job data.

## Features

- **Job pool**: leadership post build requests (blueprint, runs, quantity, corp hangar division(s) to pull
  materials from). Members with the `claim_jobs` permission can claim open jobs from the pool.
- **Direct assignment**: leadership can instead assign a job request straight to a specific member.
- **Configurable corp hangars**: admins define which corp hangar divisions (1-7) are available per
  corporation, with a friendly name each - either entered manually or synced from ESI. Job requests then
  pick one or more of these hangars as the material source, instead of a bare division number.
- **Material tracking**: each job request lists the required materials (auto-populated from blueprint data
  via `django-eveuniverse`, editable by managers) and tracks known quantities available in the corp hangar.
- **Claim timeout**: each tracked corporation has a configurable `claim_timeout_hours`. If a member claims a
  job from the pool and doesn't start building it (i.e. no matching ESI industry job appears) within that
  window, it's automatically released back to the open pool and the member is notified.
- **ESI progress tracking**: once a member starts building, the corresponding ESI industry job is matched to
  the job request automatically and its progress/status is displayed.
- **Blueprint inventory**: automatically tracks blueprint locations and stats (ME/TE levels, copy counts)
  in corp hangars via ESI asset sync.
- **Smart job creation**: when creating manufacturing jobs, the system can automatically generate copy jobs
  if insufficient blueprint copies are available, then wait for copies to complete before showing the manufacturing job.
- **Automatic copy job resolution**: when copy jobs are delivered in ESI, the system automatically marks
  their dependencies satisfied and unblocks the parent manufacturing job for claiming.
- **Material stock sync**: periodically pulls corp hangar contents from ESI and updates the available
  quantity for each material on open job requests, so the materials table shows real stock levels.
- **Notifications**: members are notified when their job starts in ESI, when it completes, when a claim
  expires, and when blueprint copies are ready for a manufacturing job.
- **Discord webhooks**: optionally mirror notifications to a Discord webhook by setting
  `INDUSTRYPOOL_DISCORD_WEBHOOK_URL` in your `local.py`.
- **Job comments**: builders and managers can post comments / progress updates on any job request.
- **Job templates**: save common job configurations as templates for quick reuse.
- **Production queue**: a timeline view of all in-progress jobs sorted by ESI completion time.
- **Builder statistics**: a leaderboard showing completed job counts per builder.
- **Multi-corporation filter**: filter the pool list by corporation (for alliances with multiple tracked corps).
- **CSV export**: export the full job list as a CSV file for spreadsheet analysis.
- **Blueprint autocomplete**: search and select blueprint types by name instead of scrolling a huge dropdown.
- **Estimated build time**: job detail pages show an estimated build time from SDE industry activity data.
- **Drag-and-drop priority**: managers can drag jobs in the pool list to reorder their priority.

## Requirements

- Alliance Auth >= 5.2.0
- `django-eveuniverse>=1.3.0`
- `requests>=2.28` (for Discord webhook notifications)
- ESI scope `esi-industry.read_corporation_jobs.v1` on a director-level token for each tracked corporation
- ESI scope `esi-corporations.read_divisions.v1` (optional, to auto-name hangar divisions instead of
  entering names manually)
- ESI scope `esi-assets.read_corporation_assets.v1` (optional, for material stock sync)
- ESI scope `esi-corporations.read_blueprints.v1` (optional, for blueprint inventory and auto-copying)

## Optional Settings

Add any of these to your `local.py` to enable optional features:

```python
# Discord webhook URL for job notifications. If not set, Discord notifications are skipped.
INDUSTRYPOOL_DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your/webhook/url"
```

## Installation

1. `pip install aa-industrypool`
2. Add `"industrypool"` to `INSTALLED_APPS` in your `local.py`.
3. Add the periodic tasks to `CELERYBEAT_SCHEDULE`:

   ```python
   CELERYBEAT_SCHEDULE["industrypool_sync_industry_jobs"] = {
       "task": "industrypool.tasks.sync_all_corporation_industry_jobs",
       "schedule": crontab(minute="*/15"),
       "apply_offset": True,
   }
   CELERYBEAT_SCHEDULE["industrypool_release_stale_claims"] = {
       "task": "industrypool.tasks.release_stale_claims",
       "schedule": crontab(minute="*/15"),
       "apply_offset": True,
   }
   CELERYBEAT_SCHEDULE["industrypool_sync_hangar_divisions"] = {
       "task": "industrypool.tasks.sync_all_corporation_hangar_divisions",
       "schedule": crontab(hour="*/6"),
       "apply_offset": True,
   }
   CELERYBEAT_SCHEDULE["industrypool_sync_blueprint_assets"] = {
       "task": "industrypool.tasks.sync_all_corporation_blueprint_assets",
       "schedule": crontab(minute="*/30"),
       "apply_offset": True,
   }
   CELERYBEAT_SCHEDULE["industrypool_sync_material_stock"] = {
       "task": "industrypool.tasks.sync_all_corporation_material_stock",
       "schedule": crontab(minute="*/30"),
       "apply_offset": True,
   }
   ```

   | Task | Frequency | Purpose |
   |------|-----------|---------|
   | `sync_all_corporation_industry_jobs` | Every 15 min | Pulls industry job progress from ESI and updates tracked jobs |
   | `release_stale_claims` | Every 15 min | Auto-releases claimed jobs that have timed out |
   | `sync_all_corporation_hangar_divisions` | Every 6 hours | Pulls hangar division names from ESI |
   | `sync_all_corporation_blueprint_assets` | Every 30 min | Syncs BPO/BPC inventory from ESI for auto-copy job creation |
   | `sync_all_corporation_material_stock` | Every 30 min | Syncs material stock levels from corp hangars |

4. Run migrations: `python manage.py migrate industrypool`
5. In Django admin, add a `Tracked Corporation` entry per corp you want to manage, selecting a director
   character that has granted the ESI industry scope, and set `claim_timeout_hours` (default 24, set to 0
   to disable auto-release of stale claims).
6. On that `Tracked Corporation`, add `Corp Hangar Division` rows (inline) for each hangar (1-7) members
   should be able to pull materials from, giving each a name (e.g. "Manufacturing Materials"). Only
   divisions marked active are offered when creating a job request. To auto-fill names from ESI instead of
   typing them, grant the director character the `esi-corporations.read_divisions.v1` scope and either run
   `industrypool.tasks.sync_corporation_hangar_divisions` once or add it to `CELERYBEAT_SCHEDULE`.
7. Assign the `industrypool.basic_access`, `industrypool.claim_jobs` and/or `industrypool.manage_pool`
   permissions to the relevant groups/states.

## Updating

When upgrading from a previous version of `aa-industrypool`, follow these steps to apply
new migrations and any new periodic tasks.

### 1. Update the package

```bash
pip install --upgrade aa-industrypool
```

If you are tracking the git repo directly instead of PyPI, pull the latest changes and
reinstall in editable mode:

```bash
git pull
pip install -e .
```

### 2. Apply new migrations

Each release may ship new migrations (for example, `0002_add_blueprint_system` adds the
blueprint inventory and job dependency tables). Run migrations for the app to bring your
database schema up to date:

```bash
python manage.py migrate industrypool
```

You can preview pending migrations without applying them with:

```bash
python manage.py showmigrations industrypool
```

> **Note**: Do not skip this step. Running new code against an unmigrated database will
> cause errors as soon as a view, task, or admin page touches one of the new tables.

### 3. Add any new periodic tasks

Recent versions added a blueprint asset sync task. If you have not already added it to
your `CELERYBEAT_SCHEDULE`, add it now (see the **Installation** section above for the
full block). The current recommended set of periodic tasks is:

- `industrypool_sync_industry_jobs` - every 15 minutes
- `industrypool_release_stale_claims` - every 15 minutes
- `industrypool_sync_blueprint_assets` - every 30 minutes (only needed for the blueprint
  inventory / auto-copy feature)
- `industrypool_sync_material_stock` - every 30 minutes (updates material availability
  on open job requests from corp hangar contents)

### 4. Grant any new ESI scopes

If you are enabling the blueprint inventory feature for the first time, the director
character for each tracked corporation must have granted the
`esi-assets.read_corporation_assets.v1` scope. Existing tokens without this scope will
cause the blueprint sync task to log a warning and skip that corporation until the scope
is added.

### 5. Restart services

Restart your Alliance Auth stack so the new code, migrations, and Celery tasks are
picked up:

```bash
supervisorctl restart all
```

Or, if you run services individually, restart at minimum:

- `auth` (gunicorn / uwsgi)
- `celery_worker`
- `celery_beat`

### 6. Verify

After restart, check that:

- `python manage.py showmigrations industrypool` shows all migrations as applied (`[X]`).
- The Industry Pool pages load without errors.
- The Celery worker logs show no import or task registration errors.
- If you enabled blueprint sync, run the task once manually and confirm
  `BlueprintInventory` rows appear in admin for your tracked corporations:

  ```bash
  python manage.py shell -c "from industrypool.tasks import sync_all_corporation_blueprint_assets; sync_all_corporation_blueprint_assets.delay()"
  ```

## Permissions

| Permission | Description |
| --- | --- |
| `basic_access` | Can access the Industry Pool app |
| `manage_pool` | Can create, assign and cancel job requests |
| `claim_jobs` | Can claim open job requests from the pool |
| `view_all_jobs` | Can view all job requests and industry jobs across the corporation |
