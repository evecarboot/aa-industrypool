from esi.openapi_clients import ESIClientProvider

from . import __version__

esi = ESIClientProvider(
    compatibility_date="2025-07-23",
    ua_appname="aa-industrypool",
    ua_version=__version__,
    ua_url="https://github.com/evecarboot/aa-industrypool",
    operations=[
        "GetCorporationsCorporationIdDivisions",
        "GetCorporationsCorporationIdIndustryJobs",
    ],
)
