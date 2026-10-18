"""Location matching shared by adapters whose sources give free-text location strings."""

import re


def _split_top_level(text: str) -> list[str]:
    """Split on '/' and ';' but not inside parentheses ('Remote (SG; IN)' stays one part)."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch in "/;" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


# Some boards write just 'Bangalore' with no country.
_INDIAN_CITIES = {
    "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "gurgaon", "gurugram", "noida",
    "hyderabad", "pune", "chennai", "kolkata", "ahmedabad", "kochi", "jaipur", "chandigarh",
    "indore", "coimbatore", "thiruvananthapuram", "bhubaneswar", "lucknow", "nagpur",
}
_INDIAN_STATES = {
    "karnataka", "ka", "maharashtra", "mh", "telangana", "tg", "ts", "delhi", "dl", "haryana",
    "hr", "tamil nadu", "tn", "uttar pradesh", "up", "gujarat", "gj", "west bengal", "wb", "kerala", "kl",
}


def _is_indian_city(part: str) -> bool:
    part = re.sub(r"(?i)^remote\s*[-–:,]\s*", "", part)
    pieces = [p.strip().lower() for p in part.split(",")]
    return pieces[0] in _INDIAN_CITIES and all(p in _INDIAN_STATES for p in pieces[1:])


def _countries(part: str) -> list[str]:
    remote_list = re.match(r"(?i)remote\s*\((.*)\)$", part)
    if remote_list:
        return [t.split(",")[-1].strip() for t in remote_list.group(1).split(";")]
    part = re.sub(r"(?i)^remote\s*[-–:,]\s*", "", part)
    # The country is the last comma-part: 'Indianapolis, IN, US' is Indiana, not India.
    return [part.split(",")[-1].strip()]


def in_india(location: str) -> bool:
    """True if any listed place is in India.

    Handles 'Bengaluru, KA, IN / Remote (SG; IN)', 'Bengaluru, India; Mumbai, India',
    'Remote - India', 'South East Asia & India'. Plain 'Remote (US)' is not India.
    """
    return any(
        _is_indian_city(part) or any(c in ("IN", "India") or c.endswith("& India") for c in _countries(part))
        for part in _split_top_level(location)
    )


def location_matches(location: str, wanted: list[str]) -> bool:
    """No wanted locations means no filtering. 'India' gets the smart check, others a substring match."""
    wanted = [w for w in wanted if w]
    if not wanted:
        return True
    return any(in_india(location) if w.lower() == "india" else w.lower() in location.lower() for w in wanted)
