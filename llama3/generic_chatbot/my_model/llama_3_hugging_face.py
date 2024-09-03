import json
import requests

"""**HF account Configuration**"""

config_data = json.load(open("config.json"))
HF_TOKEN = "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"

model_name = "meta-llama/Meta-Llama-3-8B"

API_URL = f"https://api-inference.huggingface.co/models/{model_name}"
headers = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

def query_huggingface_api(prompt):
    response = requests.post(API_URL, headers=headers, json={"inputs": prompt})
    response.raise_for_status()  # Raise an error for bad status codes
    return response.json()

def get_response(prompt):
    response = query_huggingface_api(prompt)
    gen_text = response[0]["generated_text"]
    return gen_text

prompt = "What is Machine Learning?"

llama3_response = get_response(prompt)

print(llama3_response)

print(llama3_response[len(prompt):])
