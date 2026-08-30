"""Curated question examples from the two project chatbot workbooks."""

AI_QUESTIONS_FILE = "DIP AI chatbot questions.xlsx"
SCHEMA_FILE = "DIP Chatbot Schema.xlsx"
SHARED_FILES = f"{AI_QUESTIONS_FILE}; {SCHEMA_FILE}"

_AI_QUESTION_ROWS = (
    ("Q001", "Where can I find halal food?", "SQL", "Dietary requirements", AI_QUESTIONS_FILE),
    ("Q002", "Where can I get vegetarian food?", "SQL", "Dietary requirements", AI_QUESTIONS_FILE),
    ("Q003", "Where can I find vegan food?", "SQL", "Dietary requirements", AI_QUESTIONS_FILE),
    ("Q004", "Where can I get food under $5?", "SQL", "Budget and affordability", AI_QUESTIONS_FILE),
    ("Q005", "Which places have meals below $8?", "SQL", "Budget and affordability", AI_QUESTIONS_FILE),
    ("Q006", "What is the cheapest food in NTU?", "SQL", "Budget and affordability", AI_QUESTIONS_FILE),
    ("Q007", "Where can I find Korean food?", "SQL", "Cuisine type", AI_QUESTIONS_FILE),
    ("Q008", "Where can I find Japanese food?", "SQL", "Cuisine type", AI_QUESTIONS_FILE),
    ("Q009", "Where can I find Chinese food?", "SQL", "Cuisine type", AI_QUESTIONS_FILE),
    ("Q010", "Where can I find Western food?", "SQL", "Cuisine type", SHARED_FILES),
    ("Q011", "What food places are in North Spine?", "SQL", "Location proximity"),
    ("Q012", "What food places are in South Spine?", "SQL", "Location proximity"),
    ("Q013", "Which food places are near the Library?", "SQL", "Location proximity"),
    ("Q014", "Which places are open after 8pm?", "SQL", "Opening hours"),
    ("Q015", "What food places are open on Sunday?", "SQL", "Opening hours"),
    ("Q016", "Is there anywhere to eat late at night?", "SQL", "Opening hours"),
    ("Q017", "Which places have halal food near North Spine?", "SQL", "Combined structured filters"),
    ("Q018", "Which vegetarian places are near South Spine?", "SQL", "Combined structured filters"),
    ("Q019", "Which Korean food places are under $10?", "SQL", "Combined structured filters"),
    ("Q020", "Where can I find cheap food near North Spine?", "SQL", "Combined structured filters"),
    ("Q021", "Which place has the best food?", "Vector", "Quality and review ranking"),
    ("Q022", "Which place has the best reviews?", "Vector", "Quality and review ranking"),
    ("Q023", "What do students think about the food at North Spine?", "Vector", "Student review summary"),
    ("Q024", "Which place has the biggest portions?", "Vector", "Portion size and satiety"),
    ("Q025", "Where can I get a filling meal?", "Vector", "Portion size and satiety"),
    ("Q026", "Which food place is worth trying?", "Vector", "General recommendation and value"),
    ("Q027", "Which place has good value for money?", "Vector", "General recommendation and value"),
    ("Q028", "Where can I get really good mala?", "Vector", "Dish-specific recommendation"),
    ("Q029", "Which chicken rice do students like the most?", "Vector", "Dish-specific recommendation"),
    ("Q030", "Which place has the nicest atmosphere?", "Vector", "Dining atmosphere"),
    ("Q031", "I'm hungry, what should I eat?", "Vector", "Open-ended recommendation"),
    ("Q032", "I'm craving something spicy. What should I eat?", "Vector", "Open-ended recommendation"),
    ("Q033", "I don't know what to eat. Can you recommend something?", "Vector", "Open-ended recommendation"),
    ("Q034", "What's a good place to eat with my friends?", "Vector", "Open-ended recommendation"),
    ("Q035", "Where can I get something filling?", "Vector", "Open-ended recommendation"),
    ("Q036", "I want to try something new. What food would you recommend?", "Vector", "Open-ended recommendation"),
    ("Q037", "What food do NTU students seem to enjoy the most?", "Vector", "Open-ended recommendation"),
    ("Q038", "What's a cheap place near North Spine that students recommend?", "SQL + Vector", "Filtered recommendation"),
    ("Q039", "Where can I get halal food that students recommend?", "SQL + Vector", "Filtered recommendation"),
    ("Q040", "What's a good Korean place under $10?", "SQL + Vector", "Filtered recommendation"),
    ("Q041", "Where can I get vegetarian food with good reviews?", "SQL + Vector", "Filtered recommendation"),
    ("Q042", "What's a good place near North Spine that's open late?", "SQL + Vector", "Filtered recommendation"),
    ("Q043", "I only have $5. What's something good and filling?", "SQL + Vector", "Filtered recommendation"),
    ("Q044", "Where can I get cheap food that students like?", "SQL + Vector", "Filtered recommendation"),
    ("Q045", "Which halal food place has the best reviews?", "SQL + Vector", "Filtered recommendation"),
    ("Q046", "What's the best cheap Korean food in NTU?", "SQL + Vector", "Filtered recommendation"),
    ("Q047", "Where can I get good food near South Spine after 8pm?", "SQL + Vector", "Filtered recommendation"),
    ("Q048", "I'm looking for something spicy and cheap. What should I eat?", "SQL + Vector", "Filtered recommendation"),
    ("Q049", "Which food places are affordable and have large portions?", "SQL + Vector", "Filtered recommendation"),
    ("Q050", "What's a good place for lunch that's not too expensive?", "SQL + Vector", "Filtered recommendation"),
)

_SCHEMA_QUESTION_ROWS = (
    ("schema_q001", "Where can I get halal food?", "SQL", "Dietary requirements", SCHEMA_FILE),
    ("schema_q002", "Where can I get cheap food?", "SQL", "Budget and affordability", SCHEMA_FILE),
    ("schema_q003", "What food is available at North Spine?", "SQL", "Location proximity", SCHEMA_FILE),
    ("schema_q004", "Where can I get Korean food?", "SQL", "Cuisine type", SCHEMA_FILE),
    ("schema_q005", "What places are vegetarian-friendly?", "SQL", "Dietary requirements", SCHEMA_FILE),
    ("schema_q006", "What is open after 8pm?", "SQL", "Opening hours", SCHEMA_FILE),
    ("schema_q007", "Where can I eat for less than $5?", "SQL", "Budget and affordability", SCHEMA_FILE),
    ("schema_q008", "What food courts are available in NTU?", "SQL", "Food court discovery", SCHEMA_FILE),
    ("schema_q010", "What places are open on weekends?", "SQL", "Opening hours", SCHEMA_FILE),
)

# The first ten entries already carry explicit source metadata because Q010 is
# shared by both workbooks. All remaining Qxxx rows come from the AI questions
# workbook. The exact duplicate in the schema workbook is intentionally merged.
CHATBOT_QUESTION_ROWS = tuple(
    row if len(row) == 5 else (*row, AI_QUESTIONS_FILE)
    for row in _AI_QUESTION_ROWS
) + _SCHEMA_QUESTION_ROWS
