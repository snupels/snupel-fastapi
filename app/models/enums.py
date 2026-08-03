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
