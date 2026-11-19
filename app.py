from flask import Flask, render_template, request
import requests

app = Flask(__name__)

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
API_KEY = "7qFDLqdqdw6JrpQN9C6ndbGQhTFtmzJbLGzzK86G"

# Searches we already did, so we don't ask USDA twice
cache = {}


def get_targets(weight):
    """Per-meal targets (1/3 of a day), based on body weight in kg."""
    energy = weight * 30 / 3   # about 30 kcal per kg per day, split over 3 meals

    targets = {
        "protein": weight * 0.83 / 3,   # 0.83 g per kg per day
        "carbs": energy * 0.50 / 4,     # 50% of energy, 4 kcal per g
        "sugars": energy * 0.18 / 4,    # 18% of energy, 4 kcal per g
        "fat": energy * 0.30 / 9,       # 30% of energy, 9 kcal per g
        "fiber": 8,                     # same for everyone
        "energy": energy,
    }
    return targets


def get_nutrients(food):
    """Pick out the 6 nutrients we need (per 100 g). Missing = 0."""
    result = {
        "protein": 0,
        "carbs": 0,
        "sugars": 0,
        "fat": 0,
        "fiber": 0,
        "energy": 0,
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
        # USDA lists energy twice (kcal and kJ), so only keep the kcal one
        if name.startswith("Energy") and nutrient.get("unitName") == "KCAL":
            result["energy"] = value

    return result


def search_food(term):
    """Ask USDA for a food. Returns the list of foods it found."""
    term = term.lower().strip()

    if term in cache:
        return cache[term]

    params = {
        "api_key": API_KEY,
        "query": term,
        "dataType": "Foundation",
        "pageSize": 50,
    }
    response = requests.get(SEARCH_URL, params=params)

    if response.status_code != 200:   # 200 means "OK"
        return []

    foods = response.json()["foods"]
    cache[term] = foods
    return foods


@app.route("/")
def index():
    # 1. Read what's in the web address (?food=banana&weight=60&pick=2)
    term = request.args.get("food", "")
    weight_text = request.args.get("weight", "").strip()
    pick = request.args.get("pick", "")

    # Use 70 kg if the weight box is empty or not a number
    if weight_text.isdigit():
        weight = int(weight_text)
    else:
        weight = 70

    # 2. Search USDA (only if something was typed)
    foods = []
    if term != "":
        foods = search_food(term)

    # 3. If a food in the list was clicked, work out its stats
    chosen = None
    nutrients = None
    percents = None

    if pick.isdigit() and int(pick) < len(foods):
        chosen = foods[int(pick)]
        nutrients = get_nutrients(chosen)
        targets = get_targets(weight)

        # Each nutrient as a % of the meal target, in the hexagon's order
        percents = []
        for key in ["protein", "carbs", "sugars", "fat", "fiber", "energy"]:
            percents.append(round(nutrients[key] / targets[key] * 100))

    # 4. Send everything to the page
    return render_template(
        "index.html",
        term=term,
        weight=weight_text,
        foods=foods,
        chosen=chosen,
        nutrients=nutrients,
        percents=percents,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
