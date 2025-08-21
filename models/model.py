from pydantic import BaseModel

class PackageCreate(BaseModel):
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    
    class Config:
        orm_mode = True
    
    
    