from .groq_client import get_groq_client


def main():
    client = get_groq_client()
    models = client.models.list()

    print("Available Groq models:")

    for model in models.data:
        print(model.id)


if __name__ == "__main__":
    main()
