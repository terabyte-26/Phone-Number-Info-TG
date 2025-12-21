# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/21/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012


import json
import time


def retry_extractor(func, message, attempts=4):
    """
    Retries a function that extracts and parses data.

    :param func: The function that calls the API (should return a raw string)
    :param message: The input text to process
    :param attempts: Max number of retries
    :return: Parsed JSON list/dict
    """
    for i in range(attempts):
        try:
            print(f"Attempt {i + 1} of {attempts}...")

            # 1. Call the API function
            raw_result = func(message)

            # 2. Try to parse the result
            # We use json.loads to ensure it's valid JSON
            parsed_data = json.loads(raw_result)

            print("Success!")
            return parsed_data

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error on attempt {i + 1}: {e}")
            if i < attempts - 1:
                print("Retrying...")
                time.sleep(.5)  # Brief pause before retrying
            else:
                print("Max attempts reached.")
                raise e  # Re-raise the error after last attempt fails