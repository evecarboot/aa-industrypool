# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-14

### Added
- **CRITICAL FIX**: Added missing initial migration file (0001_initial.py) - plugin previously had no migrations at all
- Migration creates all required database tables for the 6 models (General, TrackedCorporation, CorpHangarDivision, TrackedIndustryJob, JobRequest, JobRequestMaterial)
- **UI/UX**: Complete UI redesign with modern, theme-friendly interface
- **UI/UX**: Comprehensive CSS with dark theme support using CSS custom properties
- **UI/UX**: Enhanced pool list with card-based layout, status badges, and priority indicators
- **UI/UX**: Improved job detail page with sidebar layout, progress visualization, and better information hierarchy
- **UI/UX**: Redesigned job form with sectioned layout and better form field organization
- **UI/UX**: Added responsive design for mobile and tablet devices
- **UI/UX**: Added empty state designs with helpful messaging
- **UI/UX**: Added smooth animations and transitions for better user experience

### Changed
- Updated minimum Alliance Auth version requirement from 5.0.0 to 5.2.0
- Updated ESI client compatibility_date from "2025-07-23" to "2024-01-01" for better stability with django-esi 9.x
- Verified compatibility with django-esi 9.4+ (required by Alliance Auth 5.2.0)
- Confirmed all existing API calls use correct methods (result() for single-result endpoints, results() for paginated endpoints)
- Updated makemigrations_settings.py to include DEFAULT_AUTO_FIELD for Django 5.2 compatibility
- **PERFORMANCE**: Added select_related and prefetch_related to views for better query performance
- **PERFORMANCE**: Added select_related to Celery tasks to reduce database queries
- **UI/UX**: All templates now use Bootstrap 5 components and AllianceAuth theme variables
- **UI/UX**: Status badges now use color-coded system that works in both light and dark themes
- **UI/UX**: Priority indicators use emoji system for visual clarity (🔴🟠🟡🟢⚪)

### Fixed
- **CRITICAL**: Fixed missing migration issue - plugin would fail to create database tables without this migration
- Previously, the migrations folder only contained an empty __init__.py file
- **BUG**: Fixed user_can_view_job() in utils.py - was using incorrect field reference (job.corporation_id → job.corporation.corporation_id)
- **BUG**: Added null check in populate_job_materials() to prevent errors when blueprint_type is None
- **CODE QUALITY**: Added proper User model import in models.py instead of using settings.AUTH_USER_MODEL directly
- **ROBUSTNESS**: Added additional select_related/prefetch_related to prevent N+1 query issues
- **UI/UX**: Fixed template tag syntax that was causing issues with dynamic CSS classes

### Compatibility Notes
- This version is compatible with Alliance Auth 5.2.0 and django-esi 9.4+
- **IMPORTANT**: Users upgrading from 0.1.0 need to run migrations manually if they somehow installed the previous version
- New installations will work normally with standard migration process
- **THEME COMPATIBILITY**: UI is fully compatible with both light and dark AllianceAuth themes
- **THEME COMPATIBILITY**: Uses CSS custom properties (var(--bs-*)) for automatic theme adaptation

## [0.1.0] - Initial Release

### Added
- Job pool system for delegating industry build jobs
- Direct assignment capability for specific members
- Configurable corp hangar divisions with ESI sync
- Material tracking with automatic population from blueprint data
- Claim timeout system with automatic release
- ESI progress tracking for industry jobs
- Django admin interface for managing tracked corporations and job requests
- Permission system for basic access, job management, and job claiming
