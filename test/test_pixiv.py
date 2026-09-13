import pytest

from parsehub import ParseHub, Platform
from parsehub.parsers.parser.pixiv import PixivParser
from parsehub.provider_api.pixiv import Pixiv, PixivError, PixivIllust

# 结构抄自 pixiv /ajax/illust/<id> 的真实响应（只保留断言用到的字段）
ILLUST_BODY = {
    "illustId": "95276699",
    "illustTitle": "Happy New Year from Xinyan!",
    "userId": "71948315",
    "userName": "Kayden Lockes",
    "createDate": "2022-01-03T22:27:47+09:00",
    "pageCount": 2,
    "xRestrict": 0,
    "description": (
        'TWITTER: <strong><a href="https://twitter.com/KaydenLockes" target="_blank">twitter/KaydenLockes</a>'
        "</strong><br /><br />late 5k milestone Art <br /><br />"
        '<a href="/jump.php?https%3A%2F%2Fwww.patreon.com%2FKaydenLockes" target="_blank">'
        "https://www.patreon.com/KaydenLockes</a><br />"
    ),
    "tags": {"tags": [{"tag": "Genshin Impact"}, {"tag": "Xinyan"}]},
}

PAGES_BODY = [
    {
        "urls": {
            "original": "https://i.pximg.net/img-original/img/2022/01/03/22/27/47/95276699_p0.jpg",
            "thumb_mini": "https://i.pximg.net/c/128x128/img-master/img/2022/01/03/22/27/47/95276699_p0_square1200.jpg",
        },
        "width": 1200,
        "height": 1697,
    },
    {
        "urls": {
            "original": "https://i.pximg.net/img-original/img/2022/01/03/22/27/47/95276699_p1.png",
            "thumb_mini": "https://i.pximg.net/c/128x128/img-master/img/2022/01/03/22/27/47/95276699_p1_square1200.jpg",
        },
        "width": 1200,
        "height": 1697,
    },
]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pixiv.net/artworks/95276699",
        "https://pixiv.net/artworks/95276699",
        "https://www.pixiv.net/en/artworks/95276699",
        "https://www.pixiv.net/member_illust.php?mode=medium&illust_id=95276699",
    ],
)
def test_get_illust_id_accepts_supported_urls(url):
    assert Pixiv.get_illust_id(url) == "95276699"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pixiv.net/novel/show.php?id=123",
        "https://www.pixiv.net/users/71948315",
    ],
)
def test_get_illust_id_rejects_unsupported_urls(url):
    with pytest.raises(PixivError):
        Pixiv.get_illust_id(url)


def test_parse_maps_illust_and_pages():
    illust = PixivIllust.parse(ILLUST_BODY, PAGES_BODY)
    assert illust.illust_id == "95276699"
    assert illust.title == "Happy New Year from Xinyan!"
    assert illust.author_name == "Kayden Lockes"
    assert illust.author_id == "71948315"
    assert illust.tags == ["Genshin Impact", "Xinyan"]
    assert illust.page_count == 2
    assert illust.is_r18 is False
    assert [i.url for i in illust.images] == [p["urls"]["original"] for p in PAGES_BODY]
    # thumb 取小图，且不与自己相同
    assert illust.images[0].thumb_url == PAGES_BODY[0]["urls"]["thumb_mini"]


def test_parse_strips_description_html():
    illust = PixivIllust.parse(ILLUST_BODY, PAGES_BODY)
    assert "<br" not in illust.description
    assert "<strong>" not in illust.description
    # 链接文本本身就是可读 URL，不需要还原 jump.php
    assert "https://www.patreon.com/KaydenLockes" in illust.description
    assert "late 5k milestone Art" in illust.description
    assert "\n\n\n" not in illust.description


def test_parse_raises_when_images_are_restricted():
    """R-18 作品对未登录用户不返回 urls，应给出可操作的报错"""
    r18 = dict(ILLUST_BODY, xRestrict=1)
    with pytest.raises(PixivError, match="cookie"):
        PixivIllust.parse(r18, [{"urls": {"original": None}}])


def test_parser_is_registered_and_matches_artwork_url():
    parsers = {p.__platform__: p for p in ParseHub().parsers}
    assert Platform.PIXIV in parsers
    assert parsers[Platform.PIXIV] is PixivParser
    assert PixivParser.match("https://www.pixiv.net/artworks/95276699")
    assert not PixivParser.match("https://www.pixiv.net/novel/show.php?id=123")
