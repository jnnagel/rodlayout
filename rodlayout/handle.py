from enum import Enum


class Handle(Enum):
    """
    Represents the skill alignHandle strings.
    """

    UPPER_LEFT = 'upperLeft'
    UPPER_CENTER = 'upperCenter'
    UPPER_RIGHT = 'upperRight'
    CENTER_RIGHT = 'centerRight'
    LOWER_RIGHT = 'lowerRight'
    LOWER_CENTER = 'lowerCenter'
    LOWER_LEFT = 'lowerLeft'
    CENTER_LEFT = 'centerLeft'
