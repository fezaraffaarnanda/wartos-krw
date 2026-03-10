from openai import OpenAI

client = OpenAI(
    api_key="sk-cnhOVHKr2rhhrS509OScFfUuaInwGKO7aZOVjH3g6qOzsfeK",
    base_url="https://ai.ezif.in/v1",
)

print("Mengirim request ke API...")

response = client.chat.completions.create(
    model="glm-5", messages=[{"role": "user", "content": "What is quantum computing?"}]
)

# Debug: cek tipe dan isi mentah response
print(f"Tipe response : {type(response)}")
print(f"Isi response  : {response}")
print()

# Cek apakah response adalah string (endpoint tidak kompatibel)
if isinstance(response, str):
    print(
        "Response adalah string mentah — endpoint tidak mengembalikan format OpenAI standar."
    )
    print("Raw response:")
    print(response)
else:
    # Response normal sesuai format OpenAI
    print("Response berhasil di-parse sebagai ChatCompletion.")
    print("Jawaban:", response.choices[0].message.content)
