from ...provider_api.pixiv import Pixiv
from ...types import ImageRef, MultimediaParseResult, Platform
from ..base.base import BaseParser


class PixivParser(BaseParser):
    __platform__ = Platform.PIXIV
    __supported_type__ = ["图文"]
    __match__ = (
        r"^(http(s)?://)?.+pixiv\.net/(?:[a-z]{2}(?:-[a-z]{2})?/)?artworks/\d+"
        r"|^(http(s)?://)?.+pixiv\.net/member_illust\.php\?[^#]*illust_id=\d+"
    )
    __reserved_parameters__ = ["illust_id"]

    async def _do_parse(self, raw_url: str) -> MultimediaParseResult:
        illust = await Pixiv(self.proxy, cookie=self.cookie.get_value()).parse(raw_url)
        return MultimediaParseResult(
            title=illust.title,
            content=illust.description,
            author_name=illust.author_name,
            media=[
                ImageRef(
                    url=i.url,
                    thumb_url=i.thumb_url,
                    ext=i.ext,
                    width=i.width,
                    height=i.height,
                )
                for i in illust.images
            ],
        )


__all__ = ["PixivParser"]
