from pydantic import Field
from app.schemas.common import OrmDto


class CommunityProfileResponse(OrmDto):
    id: int
    name: str
    profile_image_url: str | None = Field(serialization_alias="profileImageUrl")
    follower_count: int = Field(ge=0, serialization_alias="followerCount")
    following_count: int = Field(ge=0, serialization_alias="followingCount")
    followed_by_me: bool = Field(serialization_alias="followedByMe")
    is_operator: bool = Field(serialization_alias="isOperator")
