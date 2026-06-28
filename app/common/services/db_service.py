from fastapi import Depends
from typing import Annotated
from datetime import datetime
from app.common.db import db
from pymongo.results import UpdateResult


class DBService:
    def __init__(
        self, collections: Annotated[any, Depends(db.get_collections)]
    ):
        self.collections = collections
        self.date = datetime.utcnow().strftime("%y-%m-%d %H:%M:%S")

    def find_data(
        self,
        collection,
        model,
        filter={},
        projections={},
        sort={},
        page=0,
        offset=None,
    ):  # TODO: include support for projections and sort
        results = self.collections[collection].find(filter)
        if page:
            results = results.skip((page - 1) * offset).limit(offset)
        res = [model(**result) for result in results]
        return res

    def insert_data(self, collection, model, data):
        data = {
            "created_date": self.date,
            "created_by": "system",
            "updated_date": self.date,
            "updated_by": "system",
            **data,
        }
        return self.collections[collection].insert_one(data)

    def upsert_data(
        self,
        collection: str,
        model: str,
        data: dict,
        filter: dict,
        push: dict = {},
        upsert: bool = True,
        on_insert: dict = {},
    ):
        """
        variables:
        ---------
        data: data to be updated or inserted
        push: to insert new items during update.
        on_insert: to add items only on insert
        """
        update_set = {}

        # if len(on_insert.keys()):
        #     update_set.update({"$setOnInsert":on_insert})

        # if len(push.keys()):
        #     update_set.update({"$push":push})

        res: UpdateResult = self.collections[collection].update_one(
            filter,
            {
                "$set": {
                    "updated_date": self.date,
                    "updated_by": "system",
                    **data,
                },  # TODO: Chanage this to dynamic user
                "$setOnInsert": {
                    "created_date": self.date,
                    "created_by": "system",
                    **on_insert,
                },  # TODO: Chanage this to dynamic user
                "$push": {**push},
            },
            upsert,
        )
        return res

    def delete_one(self, collection, model, filter):
        return self.collections[collection].delete_one(filter)

    def delete_many(self, collection, model, filter):
        return self.collections[collection].delete_many(filter)

    def aggregate(self, collection, model, pipeline):
        results = list(self.collections[collection].aggregate(pipeline))
        res = [model(**result) for result in results]
        return res
