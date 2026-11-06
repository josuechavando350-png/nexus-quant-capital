"""X105: cap new persistent quarantines; the current suspect request stays denied."""

from .codec import integer


def permits_quarantine(current_count, maximum_count):
    integer(current_count, 0, 100)
    integer(maximum_count, 0, 100)
    return current_count < maximum_count
