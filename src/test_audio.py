import requests

# Configuration
OLLAMA_URL = "http://localhost:11434"
ORPHEUS_FASTAPI_URL = (  # Change port if your FastAPI bridge runs elsewhere
    "http://localhost:8000/generate"
)
OUTPUT_FILENAME = "output.wav"


def generate_wav_file(text_prompt, voice_name="leah"):
    payload = {"text": text_prompt, "voice": voice_name, "ollama_base_url": OLLAMA_URL}

    print(f"Sending request to Orpheus pipeline via Ollama ({OLLAMA_URL})...")

    try:
        # Request the audio generation from the FastAPI wrapper
        response = requests.post(
            ORPHEUS_FASTAPI_URL,
            json=payload,
            headers={"accept": "application/json", "Content-Type": "application/json"},
            stream=True,
        )

        if response.status_code == 200:
            # Write the streaming audio content directly to a .wav file
            with open(OUTPUT_FILENAME, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Success! Audio successfully saved as {OUTPUT_FILENAME}")
        else:
            print(f"Error [{response.status_code}]: {response.text}")

    except requests.exceptions.ConnectionError:
        print(
            "Connection failed. Make sure both Ollama and the Orpheus-FastAPI bridge"
            " are running."
        )


if __name__ == "__main__":
    # Example text with an emotion token supported by Orpheus
    prompt = (
        "Hello! [leah] [happy] This audio file was generated successfully using Ollama."
    )
    generate_wav_file(text_prompt=prompt, voice_name="leah")
