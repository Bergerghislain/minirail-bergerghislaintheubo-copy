from minirail.utils.schema import Schema


class StationSchema(Schema):
    code: str
    name: str
    timezone: str
