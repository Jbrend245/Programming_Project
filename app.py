from flask import Flask, render_template, request
import requests

app = Flask(__name__)

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
API_KEY = "PASTE_YOUR_NEW_KEY_HERE"

# Per-meal targets, roughly 1/3 of EU daily reference intakes
TARGETS = {
    "protein": 17,
    "carbs": 87,
    "sugars": 30,
    "fat": 23,
    "fiber": 8,
    "salt": 2,
}
LABELS = ["Protein", "Carbs", "Sugars", "Fat", "Fibre", "Salt"]

# Foods we already looked up, so we don't ask USDA twice
cache = {}


def get_nutrients(food):
    #Pick out the 6 nutrients we need (per 100 g). None means missing
    result = {
        "protein": None,
        "carbs": None,
        "sugars": None,
        "fat": None,
        "fiber": None,
        "sodium": None,
    }

    for nutrient in food["foodNutrients"]:
        name = nutrient["nutrientName"]
        value = nutrient.get("value", 0)

        if name == "Protein":
            result["protein"] = value
        if name == "Carbohydrate, by difference" or name == "Carbohydrate, by summation":
            result["carbs"] = value
        if name == "Total Sugars" or name == "Sugars, total including NLEA" or name == "Sugars, Total":
            result["sugars"] = value
        if name == "Total lipid (fat)":
            result["fat"] = value
        if name == "Fiber, total dietary":
            result["fiber"] = value
        if name == "Sodium, Na":
            result["sodium"] = value   # in mg

    return result


def search_food(term):
    # Ask USDA for a food. Returns the first good result, or None
    term = term.lower().strip()

    if term in cache:
        return cache[term]

    params = {
        "api_key": API_KEY,
        "query": term,
        "dataType": "Foundation",   # plain ingredients, not brands
        "pageSize": 50, # this dont work
    }
    response = requests.get(SEARCH_URL, params=params)

    if response.status_code != 200:   # 200 means "OK"
        return None

    foods = response.json()["foods"]

    for food in foods:
        nutrients = get_nutrients(food)
        if nutrients["protein"] is not None and nutrients["fat"] is not None:
            cache[term] = food
            return food

    return None


def parse_ingredients(text):
    # Turn lines like 'rice, 150' into [('rice', 150), ...]
    items = []

    for line in text.splitlines():
        if line.strip() == "":
            continue   # skip empty lines

        name = line
        grams = 100   # if no amount is given, use 100 g

        if "," in line:
            parts = line.split(",")
            name = parts[0]
            amount = parts[1].strip()
            if amount.isdigit():   # only use it if it's a whole number
                grams = int(amount)

        items.append((name.strip(), grams))

    return items


# def get_verdict(p):
    # p = the percentages. Returns (meal class, description, tips)
    tips = []
    if p["protein"] < 70:
        tips.append("Low on protein: add eggs, lentils, chicken, tofu or Greek yogurt.")
    if p["fiber"] < 70:
        tips.append("Low on fibre: add vegetables, beans or whole grains.")
    if p["sugars"] > 100:
        tips.append("High in sugar: look for sweet sauces, juice or desserts.")
    if p["salt"] > 100:
        tips.append("High in salt: processed foods and sauces are usually the cause.")
    if p["fat"] > 130:
        tips.append("Heavy on fat: check the oil, butter or cheese amounts.")

    if (p["protein"] < 40 and p["carbs"] < 40 and p["sugars"] < 40
            and p["fat"] < 40 and p["fiber"] < 40 and p["salt"] < 40):
        return ("👻 Ghost", "This meal barely exists. Is that a snack?", tips)
    if p["carbs"] > 120 and p["protein"] < 70:
        return ("🧙 Glass Cannon", "Hits hard with carbs, collapses at 3 pm.", tips)
    if p["sugars"] > 150:
        return ("🍬 Sugar Goblin", "Fast energy, faster crash.", tips)
    if p["salt"] > 150:
        return ("🧂 Salt Knight", "Armour made of sodium. Drink some water.", tips)
    if p["fat"] > 150:
        return ("🛡️ Tank", "Very heavy armour, not much speed.", tips)
    if len(tips) == 0:
        return ("⚔️ Balanced Paladin", "Well rounded on every stat. A balanced meal!", tips)
    return ("🗡️ Adventurer", "Not bad, but a few stats need training.", tips)


def zero_if_missing(value):
    # Turn None into 0 so we can do maths with it
    if value is None:
        return 0
    return value


@app.route("/")
def index():
    text = request.args.get("ingredients", "")

    rows = []
    not_found = []
    missing_fiber = []
    totals = {"protein": 0, "carbs": 0, "sugars": 0, "fat": 0, "fiber": 0, "salt": 0}
    percents = None
    verdict = None

    for name, grams in parse_ingredients(text):
        food = search_food(name)
        if food is None:
            not_found.append(name)
            continue

        n = get_nutrients(food)
        if n["fiber"] is None:
            missing_fiber.append(name)

        # USDA gives amounts per 100 g, so scale to the grams eaten
        factor = grams / 100

        values = {}
        values["protein"] = zero_if_missing(n["protein"]) * factor
        values["carbs"] = zero_if_missing(n["carbs"]) * factor
        values["sugars"] = zero_if_missing(n["sugars"]) * factor
        values["fat"] = zero_if_missing(n["fat"]) * factor
        values["fiber"] = zero_if_missing(n["fiber"]) * factor
        # sodium (mg) -> salt (g): divide by 1000, then times 2.5
        values["salt"] = zero_if_missing(n["sodium"]) / 1000 * 2.5 * factor

        for key in totals:
            totals[key] = totals[key] + values[key]
            values[key] = round(values[key], 1)

        rows.append({
            "search": name,
            "product": food["description"],
            "grams": grams,
            "values": values,
        })

    if len(rows) > 0:
        percents = {}
        for key in TARGETS:
            percents[key] = round(totals[key] / TARGETS[key] * 100)
        verdict = get_verdict(percents)

    for key in totals:
        totals[key] = round(totals[key], 1)

    return render_template(
        "index.html",
        ingredients=text,
        rows=rows,
        totals=totals,
        percents=percents,
        labels=LABELS,
        targets=TARGETS,
        verdict=verdict,
        not_found=not_found,
        missing_fiber=missing_fiber,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
