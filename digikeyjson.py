import requests
from requests.auth import HTTPBasicAuth
import json
import os

def fetch_digikey_data(part_numbers: list, output_filename: str) -> str:
    """
    Fetch part data from Digikey API for multiple part numbers and save as a single JSON file.
    Returns the filename or raises an Exception on failure.
    """
    client_id = "0dhv3AZgnR9XJnjvVs8RMwI5c2aWbUNA"
    client_secret = "bKXnVOBACsXedDa5"
    auth_url = "https://api.digikey.com/v1/oauth2/token"
    data = {"grant_type": "client_credentials"}
    token_response = requests.post(auth_url, data=data, auth=HTTPBasicAuth(client_id, client_secret))
    if token_response.status_code != 200:
        raise Exception(f"Token error: {token_response.text}")
    access_token = token_response.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-DIGIKEY-Client-Id": client_id,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    product_url = "https://api.digikey.com/products/v4/search/keyword"
    all_specs = []
    for part_number in part_numbers:
        body = {"keywords": part_number, "recordCount": 1}
        response = requests.post(product_url, headers=headers, json=body)
        if response.status_code != 200:
            all_specs.append({"Part Number": part_number.upper(), "Error": f"Search error: {response.text}"})
            continue
        result = response.json()
        if not result.get('Products'):
            all_specs.append({"Part Number": part_number.upper(), "Error": "No product found"})
            continue
        product = result['Products'][0]
        specs = {
            "Part Number": part_number.upper(),
            "Mfr": product.get('Manufacturer', {}).get('Name'),
            "Part Status": product.get('ProductStatus', {}).get('Status'),
        }
        for param in product.get('Parameters', []):
            specs[param.get('ParameterText')] = param.get('ValueText')
        all_specs.append(specs)
    filename = f"{output_filename}.json"
    with open(filename, "w") as f:
        json.dump(all_specs, f, indent=4)
    return filename