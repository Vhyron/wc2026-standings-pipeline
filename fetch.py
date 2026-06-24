import urllib.request
import json

URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"


def fetch_matches():
    with urllib.request.urlopen(URL) as response:
        data = json.loads(response.read())
    return data["matches"]


matches = fetch_matches()

print(f"Total matches in the file: {len(matches)}")
print("-" * 50)

for match in matches[:5]:
    team1 = match["team1"]
    team2 = match["team2"]
    group = match.get("group", "knockout")

    if "score" in match:
        ft = match["score"]["ft"]
        result = f"{ft[0]}-{ft[1]}"
    else:
        result = "not played yet"

    print(f"[{group}] {team1} vs {team2}: {result}")
