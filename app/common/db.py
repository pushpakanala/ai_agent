from pymongo import MongoClient, ASCENDING
from .logger import get_logger
from .config import MONGODB_URL, MONGODB
from . import collections

logger = get_logger(__name__)


class DB:
    def __init__(self):
        self.client = None
        self.db = None
        self.collections = None

    def connect_to_mongo(self):
        try:
            logger.info(f"Connecting to MongoDB...{MONGODB_URL}")
            self.client = MongoClient(MONGODB_URL)
            self.db = self.client[MONGODB]
            self.collections = {
                collection: self.db.get_collection(collection)
                for collection in collections.__dir__()
            }
            self.collections["users"].create_index(
                [("email", ASCENDING)],
                unique=True,
            ),
            logger.info(f"Connected to {MONGODB}")
        except Exception as e:
            logger.error("Not able to connect to the database client - {e}")
            raise e

    def close_mongo_connection(self):
        logger.info("Closing MongoDB Connection")
        self.client.close()

    def get_collections(self):
        return self.collections


db = DB()
