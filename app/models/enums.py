from enum import Enum


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"


class ActivityCategory(str, Enum):
    tour = "tour"
    sports = "sports"
    event = "event"


class CourseTheme(str, Enum):
    healing = "healing"
    thrill = "thrill"
    photo_spot = "photo_spot"
    stamp = "stamp"


class SubmissionStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class RewardMilestone(str, Enum):
    badge_6 = "badge_6"
    badge_12 = "badge_12"


class RewardClaimStatus(str, Enum):
    eligible = "eligible"
    requested = "requested"
    preparing = "preparing"
    shipped = "shipped"
    completed = "completed"
