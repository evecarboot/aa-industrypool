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
- **Blueprint inventory**: automatically tracks individual blueprint items (BPOs and BPCs) and their
  stats (ME/TE levels, runs remaining) in corp hangars via ESI, including blueprints nested inside
  containers within a hangar division.
- **Smart job creation**: when creating manufacturing jobs, the system checks the corp's blueprint
  inventory and automatically generates copy jobs if insufficient copies are available, then waits
  for copies to complete before showing the manufacturing job for claiming. Admins can bypass this
  with the "Use BPO directly" checkbox to use a Blueprint Original for manufacturing without making
  copies first. Jobs can also be created for blueprints not in corp inventory (e.g. a builder has it
  personally) - the system will show a warning but still create the job.
- **Automatic copy job resolution**: when copy jobs are delivered in ESI, the system automatically marks
  their dependencies satisfied and unblocks the parent manufacturing job for claiming.
- **Material stock sync**: periodically pulls corp hangar contents from ESI and updates the available
  quantity for each material on open job requests, so the materials table shows real stock levels.
- **Notifications**: members are notified when their job starts in ESI, when it completes, when a claim
  expires, and when blueprint copies are ready for a manufacturing job.
- **Discord webhooks**: two separate webhooks can be configured:
  - `INDUSTRYPOOL_DISCORD_WEBHOOK_URL` - public webhook for new open-pool jobs (visible to
    all members so they can see what's available to claim)
  - `INDUSTRYPOOL_DISCORD_ADMIN_WEBHOOK_URL` - admin-only webhook for operational events
    (claim expired, job started, job completed, copies ready)
- **Discord DMs**: when a job is directly assigned to a member, they receive a Discord DM
  (via `aadiscordbot`) with the job details and a link. Requires `aadiscordbot` to be
  installed - if it's not, DMs are silently skipped.
- **Job comments**: builders and managers can post comments / progress updates on any job request.
- **Job templates**: save common job configurations as templates for quick reuse.
- **Production queue**: a timeline view of all in-progress jobs sorted by ESI completion time.
- **Builder statistics**: a leaderboard showing completed job counts per builder.
- **Multi-corporation filter**: filter the pool list by corporation (for alliances with multiple tracked corps).
- **CSV export**: export the full job list as a CSV file for spreadsheet analysis.
- **Blueprint autocomplete**: search all buildable items in the game (blueprints, reaction formulas,
  etc.) by name. Results show a green checkmark for items the corp has in its inventory, and a grey
  circle for items the corp doesn't own. Jobs can still be created for items not in inventory.
- **Estimated build time**: job detail pages show an estimated build time from SDE industry activity data.
- **Drag-and-drop priority**: managers can drag jobs in the pool list to reorder their priority.

## Requirements

- Alliance Auth >= 5.2.0
- `django-eveuniverse>=1.3.0`
- `requests>=2.28` (for Discord webhook notifications)
- ESI scope `esi-industry.read_corporation_jobs.v1` on a director-level token for each tracked corporation
- ESI scope `esi-corporations.read_divisions.v1` (optional, to auto-name hangar divisions instead of
  entering names manually)
- ESI scope `esi-assets.read_corporation_assets.v1` (optional, for material stock sync and resolving
  blueprints inside containers in corp hangars)
- ESI scope `esi-corporations.read_blueprints.v1` (optional, for blueprint inventory and auto-copying)

## Optional Settings

Add any of these to your `local.py` to enable optional features:

```python
# Public webhook - new open-pool jobs are posted here so members can see what's available.
INDUSTRYPOOL_DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your/public/webhook/url"

# Admin webhook - operational events (claim expired, job started/completed, copies ready).
# If not set, admin notifications are skipped.
INDUSTRYPOOL_DISCORD_ADMIN_WEBHOOK_URL = "https://discord.com/api/webhooks/your/admin/webhook/url"
```

Direct message notifications (for job assignments) are sent automatically via
`aadiscordbot` if it is installed. No additional configuration is needed - the plugin
detects whether `aadiscordbot` is available and sends DMs accordingly. If it's not
installed, DM notifications are silently skipped.

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

Recent versions added a blueprint asset sync task and a hangar divisions sync task.
If you have not already added them to your `CELERYBEAT_SCHEDULE`, add them now (see
the **Installation** section above for the full block). The current recommended set of
periodic tasks is:

- `industrypool_sync_industry_jobs` - every 15 minutes
- `industrypool_release_stale_claims` - every 15 minutes
- `industrypool_sync_hangar_divisions` - every 6 hours (auto-names hangar divisions from ESI)
- `industrypool_sync_blueprint_assets` - every 30 minutes (syncs BPO/BPC inventory including
  blueprints inside containers, for auto-copy job creation)
- `industrypool_sync_material_stock` - every 30 minutes (updates material availability
  on open job requests from corp hangar contents, including items inside containers)

### 4. Grant any new ESI scopes

If you are enabling the blueprint inventory feature for the first time, the director
character for each tracked corporation must have granted the following scopes:

- `esi-corporations.read_blueprints.v1` - required to fetch the corp's blueprint inventory
- `esi-assets.read_corporation_assets.v1` - required to resolve blueprints inside containers
  within corp hangars, and for material stock sync

Existing tokens without these scopes will cause the blueprint sync task to log a warning
and skip that corporation until the scopes are added. Add the scopes to your
`DEFAULT_TOKEN_SCOPES` in `local.py` and re-authenticate the director character.

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
