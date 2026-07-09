import wave

from orpheus_tts import OrpheusModel

# Initialize the Orpheus model
model = OrpheusModel(model_name="canopylabs/orpheus-3b-0.1-ft", max_model_len=2048)

# Text prompt for generation - you can inject emotion tags directly into the text!
prompt = "Hey! It actually worked <chuckle> this is so cool."

# Generate the speech (returns raw audio)
print("Generating speech...")
speech_audio = model.generate_speech(prompt=prompt, voice="tara")

# Save the audio output to a WAV file
output_filename = "orpheus_output.wav"
with wave.open(output_filename, "wb") as wav_file:
    wav_file.setnchannels(1)  # Mono
    wav_file.setsampwidth(2)  # 16-bit
    wav_file.setframerate(24000)
    wav_file.writeframes(speech_audio)

print(f"Speech generated and saved to {output_filename}")
