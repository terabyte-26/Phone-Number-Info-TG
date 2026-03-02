import os
import sys

import consts

# Import the SessionManager from tgconvertor
try:
    from TGConvertor import SessionManager
except ImportError:
    from tgconvertor import SessionManager

# --------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------
# Path to your tdata folder
# (Ensure this folder contains the 'key_datas' file inside it)
TDATA_FOLDER = r"C:\Users\Mohammed\PycharmProjects\phone-number-info-TG\tdata"

# Your API Credentials (optional for extraction, but needed to use the session)
API_ID = consts.TelegramConfig.API_ID
API_HASH = consts.TelegramConfig.API_HASH


# --------------------------------------------------------

def main():
    if not os.path.exists(TDATA_FOLDER):
        print(f"Error: The folder '{TDATA_FOLDER}' does not exist.")
        return

    print(f"Processing tdata at: {TDATA_FOLDER}...")

    try:
        # Load the session from tdata
        # Note: Depending on the library version, this might auto-detect the format
        # or require specific flags. The standard usage for tdata is:
        session = SessionManager.from_tdata_folder(TDATA_FOLDER)

        # Convert to Pyrogram String
        # We pass api_id/hash here so they are embedded in the session if needed
        pyrogram_string = session.to_pyrogram_string()

        print("\nSUCCESS! Here is your Pyrogram Session String:\n")
        print(pyrogram_string)
        print("\n------------------------------------------------")

        # Save it to a file
        with open("pyrogram_session.txt", "w") as f:
            f.write(pyrogram_string)
        print("Saved to 'pyrogram_session.txt'")

    except Exception as e:
        print(f"\nAn error occurred during conversion: {e}")
        print("Troubleshooting:")
        print("1. Make sure Telegram Desktop is CLOSED before running this.")
        print("2. Ensure you selected the correct 'tdata' folder (root folder).")


if __name__ == "__main__":
    main()