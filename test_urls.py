"""Root URLconf for the test suite - industrypool is added by its Alliance Auth url hook."""

from django.urls import include, path

urlpatterns = [path("", include("allianceauth.urls"))]
