import asyncio
from TGConvertor import SessionManager


async def convert_session():
    # Convert from Tdata folder to Pyrogram session
    session = SessionManager.from_tdata_folder(r'C:\Users\Mohammed\PycharmProjects\phone-number-info-TG\tdata')

    # Await the coroutine to properly save the session
    await session.to_pyrogram_file('my_session.session')
    print("Session converted and saved as 'my_session.session'")


# Run the async function
asyncio.run(convert_session())
