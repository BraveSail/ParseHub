import re
from dataclasses import dataclass
from typing import Any, cast

import httpx
from bs4 import BeautifulSoup

ILLUST_API = "https://www.pixiv.net/ajax/illust/{}"
PAGES_API = "https://www.pixiv.net/ajax/illust/{}/pages"

REFERER = "https://www.pixiv.net/"
"""pixiv 的 ajax 接口和 i.pximg.net 图床都校验 Referer, 不带会 403"""

# /artworks/<id> (可能带语言前缀, 如 /en/artworks/<id>), 以及旧式 member_illust.php?illust_id=<id>
ILLUST_URL_RES = (
    r"pixiv\.net/(?:[a-z]{2}(?:-[a-z]{2})?/)?artworks/(\d+)",
    r"pixiv\.net/member_illust\.php\?(?:[^#]*&)?illust_id=(\d+)",
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class PixivError(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)


@dataclass
class PixivImage:
    url: str
    thumb_url: str | None = None
    width: int = 0
    height: int = 0
    ext: str = "jpg"


@dataclass
class PixivIllust:
    illust_id: str
    title: str
    author_name: str
    author_id: str
    tags: list[str]
    description: str
    images: list[PixivImage]
    page_count: int
    is_r18: bool
    create_date: str

    @classmethod
    def parse(
        cls,
        data: dict[str, Any],
        pages: list[dict[str, Any]],
        *,
        illust_id: str = "",
    ) -> "PixivIllust":
        raw_tags = (data.get("tags") or {}).get("tags") or []
        tags = [str(t["tag"]) for t in raw_tags if isinstance(t, dict) and t.get("tag")]

        images = [img for page in pages if (img := _parse_image(page))]

        # urls 为空说明是 R-18 作品: pixiv 只对登录用户返回整组图片地址
        if not images:
            raise PixivError("该作品需要登录才能查看 (R-18/受限内容), 请为 pixiv 配置 cookie")

        return cls(
            illust_id=str(data.get("illustId") or illust_id),
            title=str(data.get("illustTitle") or data.get("title") or ""),
            author_name=str(data.get("userName") or ""),
            author_id=str(data.get("userId") or ""),
            tags=tags,
            description=_html_to_text(data.get("description") or data.get("illustComment") or ""),
            images=images,
            page_count=int(data.get("pageCount") or len(images)),
            is_r18=int(data.get("xRestrict") or 0) > 0,
            create_date=str(data.get("createDate") or ""),
        )


IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp")


def _guess_ext(url: str) -> str:
    """pixiv 原图后缀随作品而定 (jpg/png/gif), 要跟着 URL 走而不是固定 jpg"""
    name = url.split("?", 1)[0].rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in IMAGE_EXTS else "jpg"


def _parse_image(page: dict[str, Any]) -> PixivImage | None:
    urls = page.get("urls") or {}
    url = urls.get("original") or urls.get("regular")
    if not url:
        return None
    thumb = urls.get("thumb_mini") or urls.get("small")
    return PixivImage(
        url=str(url),
        thumb_url=str(thumb) if thumb and thumb != url else None,
        width=int(page.get("width") or 0),
        height=int(page.get("height") or 0),
        ext=_guess_ext(str(url)),
    )


def _html_to_text(html: str) -> str:
    """pixiv 的简介是 HTML 片段, 换行用 ``<br />``; 链接文本本身就是可读 URL"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    # 折叠 pixiv 常见的连续空行
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()


class Pixiv:
    def __init__(self, proxy: str | None = None, cookie: dict[str, str] | None = None):
        self.proxy = proxy
        self.cookie = cookie

    async def parse(self, url: str) -> PixivIllust:
        illust_id = self.get_illust_id(url)
        headers = {"User-Agent": UA, "Referer": REFERER}
        async with httpx.AsyncClient(proxy=self.proxy, cookies=self.cookie, timeout=30) as cli:
            illust = await self._fetch(cli, ILLUST_API.format(illust_id), illust_id, headers)
            pages = await self._fetch_pages(cli, illust_id, headers)
        return PixivIllust.parse(illust, pages, illust_id=illust_id)

    async def _fetch(
        self,
        cli: httpx.AsyncClient,
        url: str,
        illust_id: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        result = await cli.get(url, headers=headers)
        if result.status_code != 200:
            raise PixivError(f"获取作品信息失败: HTTP {result.status_code}")
        payload = cast(dict[str, Any], result.json())
        if payload.get("error"):
            raise PixivError(f"作品 {illust_id} 不存在或不可见")
        return cast(dict[str, Any], payload.get("body") or {})

    async def _fetch_pages(
        self,
        cli: httpx.AsyncClient,
        illust_id: str,
        headers: dict[str, str],
    ) -> list[dict[str, Any]]:
        result = await cli.get(PAGES_API.format(illust_id), headers=headers)
        if result.status_code != 200:
            raise PixivError(f"获取作品图片失败: HTTP {result.status_code}")
        payload = cast(dict[str, Any], result.json())
        if payload.get("error"):
            raise PixivError("该作品需要登录才能查看 (R-18/受限内容), 请为 pixiv 配置 cookie")
        return cast(list[dict[str, Any]], payload.get("body") or [])

    @staticmethod
    def get_illust_id(url: str) -> str:
        for pattern in ILLUST_URL_RES:
            if match := re.search(pattern, url):
                return match.group(1)
        raise PixivError("暂不支持该 pixiv 链接, 目前仅支持插画/漫画作品页 (artworks/<id>)")
