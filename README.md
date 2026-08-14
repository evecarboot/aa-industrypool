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

## Requirements

- Alliance Auth >= 4.0
- `django-eveuniverse`
- ESI scope `esi-industry.read_corporation_jobs.v1` on a director-level token for each tracked corporation
- ESI scope `esi-corporations.read_divisions.v1` (optional, to auto-name hangar divisions instead of
  entering names manually)
- ESI scope `esi-assets.read_corporation_assets.v1` (optional, for hangar stock lookups)

## Installation

1. `pip install aa-industrypool`
2. Add `"industrypool"` to `INSTALLED_APPS` in your `local.py`.
3. Add the periodic tasks to `CELERYBEAT_SCHEDULE`:

   ```python
   CELERYBEAT_SCHEDULE["industrypool_sync_industry_jobs"] = {
       "task": "industrypool.tasks.sync_all_corporation_industry_jobs",
       "schedule": crontab(minute="*/15"),
   }
   CELERYBEAT_SCHEDULE["industrypool_release_stale_claims"] = {
       "task": "industrypool.tasks.release_stale_claims",
       "schedule": crontab(minute="*/15"),
   }
   ```

4. Run migrations: `python manage.py migrate`
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

## Permissions

| Permission | Description |
| --- | --- |
| `basic_access` | Can access the Industry Pool app |
| `manage_pool` | Can create, assign and cancel job requests |
| `claim_jobs` | Can claim open job requests from the pool |
| `view_all_jobs` | Can view all job requests and industry jobs across the corporation |
