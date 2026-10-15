"""Rule-based severity estimate for a complaint.

The AI model is a classifier: it says WHAT the damage is, not how big it is.
So severity here is an estimate from three things the app already stores -
the damage category, how far the AI result can be trusted, and warning words
in the citizen's description. It never measures size, and it only SUGGESTS a
priority: municipal staff still decide the real one.

This module is pure Python (no database, no Flask) so it is easy to test.
"""
import re

AI_TRUST_THRESHOLD = 0.60   # below this, the citizen's own category is used
MAX_KEYWORD_POINTS = 3      # description words can never add more than this

# Base points by category. 4+ is High on its own, 2-3 is Medium, 0-1 is Low.
CATEGORY_POINTS = {
    "Open Manhole": 4,
    "Pothole": 2,
    "Broken Road Surface": 2,
    "Waterlogging": 2,
    "Road Cracks": 1,
    "Damaged Shoulder": 1,
    "Other": 1,
}
DEFAULT_CATEGORY_POINTS = 1

# Words (matched at the start of a word, so "injur" finds "injured").
# Danger words suggest people could be hurt; they can lead to Urgent.
DANGER_KEYWORDS = [
    "accident", "injur", "crash", "bleed", "fall", "fell",
    "school", "hospital", "child", "danger",
]
# Serious words make the damage worse but do not by themselves mean Urgent.
SERIOUS_KEYWORDS = ["deep", "highway", "flood", "collapse", "sinkhole", "huge"]
# Moderate words add one point each.
MODERATE_KEYWORDS = [
    "large", "big", "wide", "traffic", "night", "busy",
    "market", "junction", "stagnant", "overflow",
]


def _find_words(text, keywords):
    """Return [(keyword, word_in_text), ...] for each keyword found."""
    hits = []
    for kw in keywords:
        match = re.search(r"\b" + re.escape(kw) + r"\w*", text)
        if match:
            hits.append((kw, match.group(0)))
    return hits


def _choose_category(damage_category, ai_prediction, ai_confidence):
    """Pick the category to score, and say why."""
    if ai_prediction:
        if ai_confidence is None:
            return ai_prediction, f"Category: {ai_prediction} (set by an administrator)."
        if ai_confidence >= AI_TRUST_THRESHOLD:
            return ai_prediction, (
                f"Category: {ai_prediction} (AI result, {ai_confidence * 100:.0f}% confidence)."
            )
        return damage_category, (
            f"Category: {damage_category} (the citizen's choice, because the AI result "
            "was not confident enough)."
        )
    return damage_category, f"Category: {damage_category} (the citizen's choice, no AI result)."


def assess_severity(damage_category, description, ai_prediction=None, ai_confidence=None):
    """Estimate severity and suggest a priority.

    Returns a dict with:
      level               "Low", "Medium" or "High"
      score               the points behind the level
      suggested_priority  "Low", "Normal", "High" or "Urgent"
      category            the category that was scored
      reasons             short sentences explaining the result
    """
    category, category_reason = _choose_category(damage_category, ai_prediction, ai_confidence)
    points = CATEGORY_POINTS.get(category, DEFAULT_CATEGORY_POINTS)
    reasons = [category_reason]

    text = (description or "").lower()
    danger_hits = _find_words(text, DANGER_KEYWORDS)
    serious_hits = _find_words(text, SERIOUS_KEYWORDS)
    moderate_hits = _find_words(text, MODERATE_KEYWORDS)

    keyword_points = 2 * (len(danger_hits) + len(serious_hits)) + len(moderate_hits)
    keyword_points = min(keyword_points, MAX_KEYWORD_POINTS)
    score = points + keyword_points

    found_words = [word for _, word in danger_hits + serious_hits + moderate_hits]
    if found_words:
        reasons.append("The description mentions: " + ", ".join(found_words) + ".")
    else:
        reasons.append("The description has no warning words.")

    if score >= 4:
        level = "High"
    elif score >= 2:
        level = "Medium"
    else:
        level = "Low"

    if level == "High":
        suggested = "Urgent" if (danger_hits or category == "Open Manhole") else "High"
    elif level == "Medium":
        suggested = "Normal"
    else:
        suggested = "Low"

    return {
        "level": level,
        "score": score,
        "suggested_priority": suggested,
        "category": category,
        "reasons": reasons,
    }