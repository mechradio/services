import json

with open('../ytlist.json', 'r') as file:
    ytlist = json.load(file)

formatted_data = []
for item in ytlist:
    if 'youtu.be' in item[1]:
        video_id = item[1].split('/')[-1]
    else:
        video_id = item[1].split('=')[-1].split('/')[-1]
    formatted_item = [video_id, {}]
    new_flag = 0
    eurovision = 0
    if len(item) >= 3:  # Checking if item has index 2
        multiplier = item[2].get("multiplier", 1)
        if(multiplier > 1): formatted_item[1]["m"] = multiplier

        new_flag = item[2].get("new", 0)
        if(new_flag): formatted_item[1]["n"] = 1

        eurovision = item[2].get("eurovision", 0)
        if(eurovision): formatted_item[1]["ev"] = eurovision

        dayMultiplier = item[2].get("dayMultiplier", 0)
        if(dayMultiplier): formatted_item[1]["dm"] = dayMultiplier

    if(not formatted_item[1]): formatted_item = video_id

    formatted_data.append(formatted_item)

stringData = json.dumps(formatted_data)
out = stringData.replace(" ", "")

with open('ytlist.min.json', 'w') as outfile:
    outfile.write(out)
