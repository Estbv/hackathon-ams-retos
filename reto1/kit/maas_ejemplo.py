"""Ejemplo mínimo de llamada a GLM en Huawei Cloud MaaS.

Uso:
    pip install requests
    export MAAS_API_KEY=...   # nunca la escriba en el código ni la suba al repositorio
    export MAAS_MODEL=glm-5.2
    python maas_ejemplo.py
"""
import json
import os

import requests

if __name__ == '__main__':
    url = os.environ.get("MAAS_ENDPOINT", "https://api-ap-southeast-1.modelarts-maas.com/v2/chat/completions")
    api_key = os.environ["MAAS_API_KEY"]

    # Send request.
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    data = {
        "model": os.environ.get("MAAS_MODEL", "glm-5.2"),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hi"}
        ]
    }
    # verify=False desactiva la verificación SSL: aceptable para pruebas, no para producción.
    response = requests.post(url, headers=headers, data=json.dumps(data), verify=False, timeout=300)

    # Print result.
    print(response.status_code)
    print(response.json()["choices"][0]["message"]["content"] if response.ok else response.text)
