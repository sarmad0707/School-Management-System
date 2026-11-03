import os
import mysql.connector
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

def get_connection():
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

    return connection


# Database connection test
if __name__ == "__main__":
    try:
        conn = get_connection()
        print("Database Connected Successfully!")
        conn.close()

    except mysql.connector.Error as e:
        print("Database Connection Failed.")
        print("Please check your database settings.")