import json
with open('reports/processed_message_ids.json', 'r') as f:
    data = json.load(f)
new_id = '<010001a145b52235-edbc0cc4-30be-4a3c-a160-95c55b90a74a-000000@email.amazonses.com>'
if new_id not in data:
    data.append(new_id)
with open('reports/processed_message_ids.json', 'w') as f:
    json.dump(data, f)