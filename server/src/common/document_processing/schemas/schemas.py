from pydantic import BaseModel, Field

class TableDescription(BaseModel):
    table_description: str = Field(description="The detailed description of the table.")

class ImageDescription(BaseModel):
    image_description: str = Field(description="The detailed description of the image.")