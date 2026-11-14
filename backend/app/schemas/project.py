"""Project schemes for API.

Author: Maxi-online
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


from datetime import date


class ProjectBase(BaseModel):
    """The basic design of the project.

    Attributes:
        project_id: Project External Identifier.
        name: Name of project.
        region: Implementation region.
        stage: Project stage.
        start_date: Target date for commencement.
        end_date: Target Date for Completion.
        budget: Estimated value.
    """

    project_id: str | None = None
    name: str
    region: str | None = None
    stage: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: float | None = None
    description: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    investor_name: str | None = None
    investor_email: str | None = None
    investor_phone: str | None = None
    contractor_name: str | None = None
    contractor_email: str | None = None
    contractor_phone: str | None = None
    source_urls: list[str] | None = None


class ProjectCreate(ProjectBase):
    'A scheme to create a project at the API entrance.'

    model_config = ConfigDict(extra="forbid")


class ProjectRead(ProjectBase):
    """Project outline for API reading.

    Attributes:
        id: Internal record identifier.
    """

    id: int

    class Config:
        from_attributes = True
