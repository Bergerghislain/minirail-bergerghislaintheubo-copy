from pydantic import BaseModel, ConfigDict

from minirail.utils.exc import ErrorCodeEnum


def to_lower_camel_case(snake: str) -> str:
    first, *rest = snake.split("_")
    return first + "".join(part.capitalize() for part in rest)


class Schema(BaseModel):
    """Base for all API schemas.

    - JSON field names are camelCase (`booking_key` <-> `bookingKey`);
      Python code keeps snake_case via `populate_by_name`.
    - `extra="forbid"`: unknown fields in a request are a 422, not silently
      dropped — typos in client payloads must not pass validation.
    - `from_attributes`: output schemas can be built directly from ORM objects.
    """

    model_config = ConfigDict(
        alias_generator=to_lower_camel_case,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class ProblemSchema(Schema):
    """Error payload returned for every handled business exception."""

    error_code: ErrorCodeEnum
    message: str
