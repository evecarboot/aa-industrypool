from esi.openapi_clients import ESIClientProvider

from . import __version__

esi = ESIClientProvider(
    compatibility_date="2024-01-01",
    ua_appname="aa-industrypool",
    ua_version=__version__,
    ua_url="https://github.com/your-org/aa-industrypool",
    operations=[
        "GetCorporationsCorporationIdDivisions",
        "GetCorporationsCorporationIdIndustryJobs",
        "GetCorporationsCorporationIdAssetsBlueprints",
    ],
)
