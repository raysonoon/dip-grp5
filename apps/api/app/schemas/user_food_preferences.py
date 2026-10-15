from pydantic import BaseModel, Field


class UserFoodPreferencesResponse(BaseModel):
    allergies: list[str]
    cuisines: list[str]
    locations: list[str]
    likes: list[str]
    dislikes: list[str]
    lifestyle: list[str]
    onboarding_status: str


class UserFoodPreferencesUpdate(BaseModel):
    allergies: list[str] = Field(default_factory=list)
    cuisines: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    lifestyle: list[str] = Field(default_factory=list)
    onboarding_status: str