"""Presentation and discovery rules; original provider fields remain in the database."""

import re

GANGWON_DISTRICTS = (
    "춘천시", "원주시", "강릉시", "동해시", "태백시", "속초시", "삼척시", "홍천군", "횡성군",
    "영월군", "평창군", "정선군", "철원군", "화천군", "양구군", "인제군", "고성군", "양양군",
)
OTHER_PROVINCE_PATTERN = (
    r"^(서울(?:특별시)?|부산(?:광역시)?|대구(?:광역시)?|인천(?:광역시)?|광주(?:광역시)?|"
    r"대전(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|경기(?:도)?|충북|충남|충청북도|충청남도|"
    r"전북(?:특별자치도)?|전남|전라북도|전라남도|경북|경남|경상북도|경상남도|제주(?:특별자치도|도)?)"
    r"(\s|$)"
)
# Verified spelling variants at the same full address. Sharing an address alone is not a duplicate.
VERIFIED_PLACE_NAMES = (
    ("리틀코브", "양양서핑리틀코브"),
    ("모쿠서프", "양양서핑모쿠서프"),
    ("포이푸", "포이푸서프"),
    ("이스트사이드", "이스트사이드서프"),
    ("포인트브레이크", "포인트브레이크서프하우스"),
    ("서프스타", "서프스타(Surfstar)"),
)


def display_address(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"^(\s*)강월특별자치도(?=\s|$)", r"\1강원특별자치도", value)


def gangwon_address_status(address: str | None) -> bool | None:
    """Explicit administrative address wins over descriptions or approximate map bounds."""
    text = (display_address(address) or "").strip()
    if re.match(OTHER_PROVINCE_PATTERN, text):
        return False
    if re.match(r"^(강원특별자치도|강원도|강원)(\s|$)", text):
        return True
    district = re.match(r"^([가-힣]+[시군])(?:\s|$)", text)
    if district:
        # Bare 고성군 is shared by Gangwon and Gyeongnam: require further evidence.
        if district[1] == "고성군":
            return None
        return district[1] in GANGWON_DISTRICTS
    return None
