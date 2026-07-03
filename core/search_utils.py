SEARCH_SYNONYMS = {
    # ماوس
    "ماوس": ["mouse", "mous", "wireless mouse", "gaming mouse"],
    "mouse": ["ماوس", "mous", "wireless mouse", "gaming mouse"],
    "mous": ["ماوس", "mouse", "wireless mouse", "gaming mouse"],

    # كيبورد
    "كيبورد": ["keyboard", "key board", "gaming keyboard"],
    "keyboard": ["كيبورد", "key board", "gaming keyboard"],
    "key board": ["كيبورد", "keyboard", "gaming keyboard"],

    # لابتوب
    "لابتوب": ["laptop", "notebook", "pc"],
    "laptop": ["لابتوب", "notebook", "pc"],
    "notebook": ["لابتوب", "laptop", "pc"],
    "pc": ["لابتوب", "laptop", "notebook"],
}

def normalize_query(query):
    return query.strip().lower()

def expand_keywords(query):
    q = normalize_query(query)

    # إذا الكلمة مو موجودة بالقاموس → رجّعها لوحدها
    if q not in SEARCH_SYNONYMS:
        return [q]

    # إذا موجودة بالقاموس → رجّع المرادفات معها
    synonyms = SEARCH_SYNONYMS.get(q, [])
    return [q] + synonyms
