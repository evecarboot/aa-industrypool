from django.contrib import admin

from .models import (
    BlueprintInventory,
    CorpHangarDivision,
    JobComment,
    JobDependency,
    JobRequest,
    JobRequestMaterial,
    JobTemplate,
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


@admin.register(BlueprintInventory)
class BlueprintInventoryAdmin(admin.ModelAdmin):
    list_display = ("blueprint_type", "corporation", "location_division", "item_id", "quantity", "is_original", "material_efficiency", "time_efficiency")
    list_filter = ("is_original", "corporation", "location_division")
    search_fields = ("blueprint_type__name", "corporation__corporation__corporation_name", "item_id")
    autocomplete_fields = ("blueprint_type",)
    list_display_links = ("blueprint_type", "item_id")


@admin.register(JobDependency)
class JobDependencyAdmin(admin.ModelAdmin):
    list_display = ("parent_job", "child_job", "dependency_type", "required_quantity", "is_satisfied", "created_at")
    list_filter = ("dependency_type", "is_satisfied")
    search_fields = ("parent_job__blueprint_type__name", "child_job__blueprint_type__name")


@admin.register(JobComment)
class JobCommentAdmin(admin.ModelAdmin):
    list_display = ("job_request", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("text", "job_request__blueprint_type__name", "author__username")


@admin.register(JobTemplate)
class JobTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "corporation", "blueprint_type", "activity", "runs", "quantity", "priority")
    list_filter = ("activity", "corporation")
    search_fields = ("name", "blueprint_type__name")
    autocomplete_fields = ("blueprint_type",)
    filter_horizontal = ("hangar_divisions",)
