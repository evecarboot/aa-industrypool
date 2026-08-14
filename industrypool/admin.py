from django.contrib import admin

from .models import (
    CorpHangarDivision,
    JobRequest,
    JobRequestMaterial,
    TrackedCorporation,
    TrackedIndustryJob,
)


class JobRequestMaterialInline(admin.TabularInline):
    model = JobRequestMaterial
    extra = 0


class CorpHangarDivisionInline(admin.TabularInline):
    model = CorpHangarDivision
    extra = 0
    fields = ("division_number", "name", "is_active")


@admin.register(JobRequest)
class JobRequestAdmin(admin.ModelAdmin):
    list_display = (
        "blueprint_type",
        "corporation",
        "activity",
        "status",
        "priority",
        "created_by",
        "builder",
        "created_at",
    )
    list_filter = ("status", "activity", "corporation")
    search_fields = ("blueprint_type__name", "created_by__username")
    inlines = (JobRequestMaterialInline,)
    autocomplete_fields = ("blueprint_type",)
    filter_horizontal = ("hangar_divisions",)


@admin.register(TrackedIndustryJob)
class TrackedIndustryJobAdmin(admin.ModelAdmin):
    list_display = ("job_id", "blueprint_type", "installer", "corporation", "status", "start_date", "end_date")
    list_filter = ("status", "corporation")
    search_fields = ("job_id", "blueprint_type__name")


@admin.register(TrackedCorporation)
class TrackedCorporationAdmin(admin.ModelAdmin):
    list_display = ("corporation", "director_character", "claim_timeout_hours", "is_active")
    list_filter = ("is_active",)
    inlines = (CorpHangarDivisionInline,)


@admin.register(CorpHangarDivision)
class CorpHangarDivisionAdmin(admin.ModelAdmin):
    list_display = ("corporation", "division_number", "name", "is_active")
    list_filter = ("is_active", "corporation")
