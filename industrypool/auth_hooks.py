from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import urls


class IndustryPoolMenuItem(MenuItemHook):
    def __init__(self):
        super().__init__(
            _("Industry Pool"),
            "fas fa-industry fa-fw",
            "industrypool:pool_list",
            1000,
            navactive=["industrypool:"],
        )

    def render(self, request):
        if request.user.has_perm("industrypool.basic_access"):
            return super().render(request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return IndustryPoolMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "industrypool", r"^industrypool/")
